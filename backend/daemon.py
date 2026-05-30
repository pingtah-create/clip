"""Autonomous discovery + clip + post loop.

Polls channels.txt every DAEMON_INTERVAL_HOURS, finds new uploads since last pass via
RSS (no YouTube Data API quota cost), runs them through pipeline.run(), and uploads
the top N clips above the score threshold. State persists in data/processed.json.

Run with: `python -m backend.daemon`  (or `run_daemon.bat`)

Why RSS instead of the YouTube API: the Data API charges 100 units per channel-list
call, which would cost more quota than the actual uploads do. RSS is free and
gives us the last 15 uploads per channel, which is plenty."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

import feedparser
from dotenv import load_dotenv

from . import jobs, pipeline
from .tools import YT_DLP_CMD

# Windows consoles default to cp1252, which can't encode the arrows/checkmarks we
# print as progress markers — and an encode error there crashes the whole cycle.
# Force the stdout/stderr streams to UTF-8 so the daemon is safe on any console.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Load .env BEFORE reading any DAEMON_* config. override=True for the same reason
# as main.py — beats any inherited shell env vars that would silently override.
load_dotenv(override=True)

ROOT = Path(__file__).resolve().parent.parent
CHANNELS_FILE = ROOT / "channels.txt"
QUERIES_FILE = ROOT / "queries.txt"
PROCESSED_FILE = ROOT / "data" / "processed.json"
# Top-performing clips by view count, written here for the picker to learn from.
TOP_PERFORMERS_FILE = ROOT / "data" / "top_performers.json"
PROCESSED_FILE.parent.mkdir(parents=True, exist_ok=True)

# Only score a clip's performance once it's had time to accumulate views.
STATS_MIN_AGE_HOURS = 48
# How many top clips to feed back into the picker prompt.
TOP_PERFORMERS_KEEP = 8
# Delete each job's intermediate files (source.mp4, audio.wav, per-clip temps) after
# processing, so an unattended multi-week run doesn't fill the disk. Final clips in
# data/clips/ are kept. Set DAEMON_KEEP_INTERMEDIATES=true to disable for debugging.
KEEP_INTERMEDIATES = os.environ.get("DAEMON_KEEP_INTERMEDIATES", "false").lower() == "true"
DATA_ROOT = ROOT / "data"


def _cfg_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except ValueError:
        return default


INTERVAL_HOURS = _cfg_int("DAEMON_INTERVAL_HOURS", 4)
N_CLIPS_PER_VIDEO = _cfg_int("DAEMON_N_CLIPS_PER_VIDEO", 3)
MIN_SCORE_TO_UPLOAD = _cfg_int("DAEMON_MIN_SCORE_TO_UPLOAD", 80)
MAX_DURATION_MIN = _cfg_int("DAEMON_MAX_VIDEO_DURATION_MIN", 180)
# Default raised to 20 min: long-form interviews/podcasts produce far better clips
# (dense self-contained takes, speaker on camera throughout) than short news segments.
MIN_DURATION_MIN = _cfg_int("DAEMON_MIN_VIDEO_DURATION_MIN", 20)
MAX_VIDEO_AGE_DAYS = _cfg_int("DAEMON_MAX_VIDEO_AGE_DAYS", 14)
RESULTS_PER_QUERY = _cfg_int("DAEMON_RESULTS_PER_QUERY", 1)
# Hard cap on how long one video's full pipeline may run before the daemon abandons
# it and moves on. Protects against a corrupt file hanging ffmpeg/whisper forever.
# Generous default: a 3hr source on CPU whisper can legitimately take ~30-40 min.
PIPELINE_TIMEOUT_SEC = _cfg_int("DAEMON_PIPELINE_TIMEOUT_MIN", 60) * 60
DURATION_PRESET = os.environ.get("DAEMON_DURATION_PRESET", "standard")

# First-run mode: on a fresh `processed.json`, just record current videos as "seen"
# without processing them. Prevents the daemon from backfilling 50+ hours of work
# the first time you point it at a busy channel.
FIRST_RUN_SEEDS_ONLY = True


def _load_processed() -> dict[str, dict]:
    if not PROCESSED_FILE.exists():
        return {}
    try:
        return json.loads(PROCESSED_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_processed(state: dict[str, dict]) -> None:
    PROCESSED_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def refresh_top_performers(state: dict[str, dict]) -> None:
    """Pull view counts for clips uploaded >48h ago, rank them, and write the best
    ones to top_performers.json. The picker reads that file so it learns which kinds
    of hooks actually earn views on this channel. Runs once per cycle; cheap quota."""
    now = time.time()
    # Gather every uploaded clip old enough to have meaningful view data.
    candidates: list[dict] = []
    for rec in state.values():
        clipped_at = rec.get("clipped_at", 0)
        if (now - clipped_at) / 3600 < STATS_MIN_AGE_HOURS:
            continue
        for c in rec.get("clips", []):
            if c.get("youtube_id"):
                candidates.append(c)

    ids = [c["youtube_id"] for c in candidates]
    if not ids:
        return

    try:
        from .youtube import fetch_stats
        stats = fetch_stats(ids)
    except Exception as e:
        print(f"  ! stats fetch failed (need youtube.readonly scope? re-auth): {e}")
        return

    for c in candidates:
        c["_views"] = stats.get(c["youtube_id"], {}).get("views", 0)

    top = sorted(candidates, key=lambda c: c.get("_views", 0), reverse=True)[:TOP_PERFORMERS_KEEP]
    payload = [{"title": c["title"], "hook": c["hook"], "score": c.get("score"),
                "views": c.get("_views", 0)} for c in top]
    TOP_PERFORMERS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if top:
        print(f"  stats: top clip '{top[0]['title'][:40]}' has {top[0].get('_views',0)} views")


def _read_lines(path: Path) -> list[str]:
    """Generic: non-blank, non-# lines from a text file. Re-read every cycle so the
    user can edit the file without restarting the daemon."""
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            out.append(s)
    return out


def _read_channels() -> list[str]:
    return _read_lines(CHANNELS_FILE)


def _read_queries() -> list[str]:
    return _read_lines(QUERIES_FILE)


# Append podcast/interview framing to every query so YouTube surfaces long-form
# talking-head content (best clip source) over news snippets. Toggle off with
# DAEMON_PODCAST_BIAS=false.
PODCAST_BIAS = os.environ.get("DAEMON_PODCAST_BIAS", "true").lower() == "true"


def _search_youtube(query: str, limit: int) -> list[dict]:
    """Run a YouTube search via yt-dlp and return candidate video dicts, sorted by
    view count (descending) so the daemon prefers proven, high-traction long-form
    content. No API quota used — yt-dlp scrapes the public search results page.

    Over-fetches (limit×6) because we filter by age/duration/coverage downstream and
    want enough survivors to still pick a strong one."""
    search_q = f"{query} podcast interview" if PODCAST_BIAS else query
    try:
        res = subprocess.run(
            [*YT_DLP_CMD, f"ytsearch{max(limit * 6, 6)}:{search_q}",
             "--flat-playlist",
             "--print", "%(id)s\t%(title)s\t%(upload_date)s\t%(view_count)s",
             "--no-warnings"],
            capture_output=True, text=True, timeout=90,
        )
    except Exception as e:
        print(f"  ! search failed for {query!r}: {e}")
        return []

    out = []
    for line in (res.stdout or "").strip().splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        vid, title, upload_date = parts[0], parts[1], parts[2]
        views = 0
        if len(parts) >= 4:
            try:
                views = int(parts[3]) if parts[3] not in ("NA", "") else 0
            except ValueError:
                views = 0
        # upload_date is YYYYMMDD on yt-dlp's flat-playlist output, sometimes "NA"
        try:
            ts = time.mktime(time.strptime(upload_date, "%Y%m%d")) if upload_date != "NA" else 0
        except ValueError:
            ts = 0
        out.append({
            "id": vid,
            "url": f"https://www.youtube.com/watch?v={vid}",
            "title": title,
            "published_ts": ts,
            "view_count": views,
            "source": f"query: {query}",
        })
    # Prefer high-view content — proven traction is a decent proxy for "worth clipping".
    out.sort(key=lambda v: v.get("view_count", 0), reverse=True)
    return out


def _resolve_channel_id(url: str) -> str | None:
    """YouTube RSS feeds need the raw channel ID (UCxxxxx...). For /@handle and
    /c/custom URLs we ask yt-dlp to extract it — most reliable way without scraping
    HTML or hitting the API."""
    m = re.search(r"channel/(UC[\w-]{20,})", url)
    if m:
        return m.group(1)

    try:
        res = subprocess.run(
            [*YT_DLP_CMD, "--flat-playlist", "--print", "channel_id",
             "--playlist-items", "1", url],
            capture_output=True, text=True, timeout=30,
        )
        lines = (res.stdout or "").strip().splitlines()
        cid = lines[0] if lines else ""
        if cid.startswith("UC"):
            return cid
    except Exception:
        pass
    return None


def _fetch_recent_videos(channel_url: str) -> list[dict]:
    """Return up to ~15 recent video dicts {id, url, title, published_ts} for a channel."""
    cid = _resolve_channel_id(channel_url)
    if not cid:
        print(f"  ! could not resolve channel ID for {channel_url}")
        return []
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
    feed = feedparser.parse(feed_url)
    out = []
    for entry in feed.entries:
        vid = getattr(entry, "yt_videoid", None) or entry.id.split(":")[-1]
        ts = time.mktime(entry.published_parsed) if hasattr(entry, "published_parsed") else 0
        out.append({"id": vid, "url": entry.link, "title": entry.title, "published_ts": ts})
    return out


def _video_metadata(url: str) -> tuple[float | None, float | None]:
    """Probe (duration_minutes, upload_ts) for one video via a single yt-dlp call.
    --flat-playlist doesn't return upload_date for search results, so for query-found
    videos we must do this proper metadata fetch. Returns (None, None) on failure."""
    try:
        res = subprocess.run(
            [*YT_DLP_CMD, "--print", "%(duration)s\t%(upload_date)s",
             "--no-download", "--skip-download", url],
            capture_output=True, text=True, timeout=45,
        )
        line = (res.stdout or "").strip().splitlines()[0] if res.stdout else ""
        if "\t" not in line:
            return None, None
        dur_s, upload_date = line.split("\t", 1)
        dur_min = float(dur_s) / 60.0 if dur_s and dur_s != "NA" else None
        ts: float | None = None
        if upload_date and upload_date != "NA":
            try:
                ts = time.mktime(time.strptime(upload_date, "%Y%m%d"))
            except ValueError:
                ts = None
        return dur_min, ts
    except Exception:
        return None, None


def _video_duration_minutes(url: str) -> float | None:
    """Back-compat shim — only duration."""
    dur, _ = _video_metadata(url)
    return dur


def _should_process(video: dict) -> tuple[bool, str]:
    """Filter: skip Shorts, livestreams, too-short/too-long, and old-for-search-results.
    Does the single metadata fetch so we don't pay for it twice."""
    url = video["url"]
    title = (video["title"] or "").lower()

    if "/shorts/" in url:
        return False, "shorts"
    if any(k in title for k in (" live ", " livestream", "live now", "🔴")):
        return False, "livestream-ish title"

    dur, upload_ts = _video_metadata(url)
    if dur is None:
        return False, "could not probe duration"
    if dur < MIN_DURATION_MIN:
        return False, f"too short ({dur:.1f} min)"
    if dur > MAX_DURATION_MIN:
        return False, f"too long ({dur:.1f} min)"

    # Age check — only enforce for search-sourced videos. Channel RSS already gives
    # us a reliable published_ts upstream and only returns recent uploads anyway.
    if video.get("source", "").startswith("query:") and upload_ts:
        age_days = (time.time() - upload_ts) / 86400
        if age_days > MAX_VIDEO_AGE_DAYS:
            return False, f"too old ({age_days:.0f} days)"

    return True, f"{dur:.1f} min"


# Module-level flag — flips to True the first time YouTube returns quotaExceeded.
# Subsequent clips in this cycle skip the upload attempt entirely so we don't waste
# 10-15s per call hammering a wall. Reset on each new cycle.
_quota_exhausted = False


def _process_one(video: dict) -> dict:
    """Run the full pipeline on one video and upload its eligible clips. Returns the
    record we'll write to processed.json."""
    global _quota_exhausted
    print(f"  → processing: {video['title']}")
    job = jobs.create(video["url"], N_CLIPS_PER_VIDEO, DURATION_PRESET)

    # Run the pipeline in a worker thread with a hard timeout. If a corrupt file hangs
    # ffmpeg/whisper, we abandon it after PIPELINE_TIMEOUT_SEC and move on rather than
    # freezing the daemon forever. The orphaned thread is a daemon thread, so it won't
    # block process exit; its stuck ffmpeg child is cleaned up on the next restart.
    import threading
    worker = threading.Thread(target=pipeline.run, args=(job.id,), daemon=True)
    worker.start()
    worker.join(timeout=PIPELINE_TIMEOUT_SEC)
    if worker.is_alive():
        print(f"  !! pipeline exceeded {PIPELINE_TIMEOUT_SEC // 60} min — abandoning this video")
        return {"clipped_at": time.time(), "title": video["title"],
                "source": video.get("source", "channel"), "url": video.get("url"),
                "num_clips": 0, "num_uploaded": 0, "error": "pipeline timeout"}

    job = jobs.get(job.id)
    if not job:
        return {"clipped_at": time.time(), "num_clips": 0, "num_uploaded": 0,
                "error": "job vanished"}

    done_clips = [c for c in job.clips if c.status == "done" and c.file]
    print(f"  ✓ rendered {len(done_clips)}/{len(job.clips)} clips")

    uploaded = 0
    skipped_quota = 0
    # Per-clip detail recorded into processed.json so a failed/odd upload is always
    # explainable after the fact (the Job object is in-memory only and dies with the
    # process). One dict per rendered clip: title, score, hook, file, upload outcome.
    clip_records: list[dict] = []
    try:
        from .youtube import upload as yt_upload
        privacy = os.environ.get("YOUTUBE_PRIVACY", "private").lower()
        tags = [t.strip() for t in os.environ.get("YOUTUBE_DEFAULT_TAGS", "shorts").split(",")
                if t.strip()]
        for c in done_clips:
            rec = {
                "title": c.title,
                "score": c.score,
                "hook": c.hook,
                "file": c.file,
                "youtube_id": None,
                "upload_status": None,
            }
            if c.score < MIN_SCORE_TO_UPLOAD:
                print(f"    skip (score {c.score} < {MIN_SCORE_TO_UPLOAD}): {c.title}")
                rec["upload_status"] = f"below_threshold (score {c.score} < {MIN_SCORE_TO_UPLOAD})"
                clip_records.append(rec)
                continue
            if _quota_exhausted:
                # We already hit 429 earlier in this cycle. Don't waste a network call.
                print(f"    skip (quota exhausted): {c.title}")
                rec["upload_status"] = "skipped_quota"
                skipped_quota += 1
                clip_records.append(rec)
                continue
            try:
                desc = (f"{c.hook}\n\nFrom: {video['title']}"
                        if c.hook else f"From: {video['title']}")
                vid_id = yt_upload(Path(c.file), title=c.title, description=desc,
                                   tags=tags, privacy=privacy)
                print(f"    ↑ uploaded: {c.title} → {vid_id}")
                rec["youtube_id"] = vid_id
                rec["upload_status"] = "uploaded"
                uploaded += 1
            except Exception as e:
                print(f"    ! upload failed for {c.title}: {type(e).__name__}: {e}")
                rec["upload_status"] = f"failed: {type(e).__name__}"
                if "quotaExceeded" in str(e):
                    print("    !! YouTube daily quota exhausted — skipping further uploads "
                          "until next cycle. Rendered clips stay on disk for manual upload.")
                    _quota_exhausted = True
                    skipped_quota += 1
                    rec["upload_status"] = "skipped_quota"
            clip_records.append(rec)
    except Exception as e:
        print(f"  ! upload module error: {e}")

    # Reclaim disk: drop the job's intermediate dir (source.mp4 + audio.wav + temps).
    # Final clips live in data/clips/<id>/ and are untouched. Best-effort — a failure
    # here must never crash the daemon.
    if not KEEP_INTERMEDIATES:
        try:
            job_dir = DATA_ROOT / "jobs" / job.id
            if job_dir.exists():
                shutil.rmtree(job_dir, ignore_errors=True)
        except Exception as e:
            print(f"  ! cleanup warning (non-fatal): {e}")

    return {
        "clipped_at": time.time(),
        "title": video["title"],
        "source": video.get("source", "channel"),
        "url": video.get("url"),
        "num_clips": len(done_clips),
        "num_uploaded": uploaded,
        "num_skipped_quota": skipped_quota,
        "clips": clip_records,
    }


def cycle() -> None:
    """One pass through all channels. Idempotent — IDs in processed.json are skipped."""
    global _quota_exhausted
    # Each cycle starts fresh — the quota window resets at midnight Pacific so a
    # 4-hour-later cycle has a real chance of working again.
    _quota_exhausted = False

    state = _load_processed()
    first_run = len(state) == 0 and FIRST_RUN_SEEDS_ONLY

    # Update the performance feedback file from prior uploads' view counts.
    if not first_run:
        try:
            refresh_top_performers(state)
        except Exception as e:
            print(f"  ! refresh_top_performers error (non-fatal): {e}")

    channels = _read_channels()
    queries = _read_queries()
    if not channels and not queries:
        print("(nothing to do — both channels.txt and queries.txt are empty)")
        return

    print(f"\n=== cycle @ {time.strftime('%Y-%m-%d %H:%M:%S')} ===")
    print(f"channels: {len(channels)} | queries: {len(queries)} | first-run: {first_run}")

    new_videos: list[dict] = []
    seen_ids: set[str] = set()

    for ch_url in channels:
        print(f"\n[channel] {ch_url}")
        try:
            videos = _fetch_recent_videos(ch_url)
        except Exception as e:
            print(f"  ! feed error: {e}")
            continue
        print(f"  feed: {len(videos)} recent videos")
        for v in videos:
            if v["id"] in state or v["id"] in seen_ids:
                continue
            seen_ids.add(v["id"])
            new_videos.append(v)

    for q in queries:
        print(f"\n[query] {q}")
        results = _search_youtube(q, RESULTS_PER_QUERY)
        print(f"  search: {len(results)} candidates")
        kept = 0
        for v in results:
            if v["id"] in state or v["id"] in seen_ids:
                continue
            # Age filter — fresh results only, so the daemon doesn't post a clip of
            # a year-old video and look spammy.
            if v["published_ts"]:
                age_days = (time.time() - v["published_ts"]) / 86400
                if age_days > MAX_VIDEO_AGE_DAYS:
                    continue
            seen_ids.add(v["id"])
            new_videos.append(v)
            kept += 1
            if kept >= RESULTS_PER_QUERY:
                break

    print(f"\nfound {len(new_videos)} new videos across all sources")

    if first_run:
        # Seed processed.json so we don't backfill on the first run. Subsequent
        # cycles will only see genuinely-new uploads.
        for v in new_videos:
            state[v["id"]] = {"clipped_at": time.time(), "title": v["title"],
                              "num_clips": 0, "num_uploaded": 0, "seeded": True}
        _save_processed(state)
        print(f"first-run: seeded {len(new_videos)} videos as already-seen, "
              "no processing this cycle")
        return

    for v in new_videos:
        ok, reason = _should_process(v)
        if not ok:
            print(f"  - skip ({reason}): {v['title']}")
            state[v["id"]] = {"clipped_at": time.time(), "title": v["title"],
                              "num_clips": 0, "num_uploaded": 0, "skipped": reason}
            _save_processed(state)
            continue
        try:
            state[v["id"]] = _process_one(v)
        except Exception as e:
            print(f"  !! pipeline failed: {type(e).__name__}: {e}")
            traceback.print_exc()
            state[v["id"]] = {"clipped_at": time.time(), "title": v["title"],
                              "num_clips": 0, "num_uploaded": 0, "error": str(e)}
        _save_processed(state)


def print_status() -> None:
    """`python -m backend.daemon --status` — human-readable dump of processed.json.
    Shows what got clipped, what got skipped and why, and which clips have YouTube
    IDs vs. are sitting on disk waiting (e.g. quota-skipped)."""
    state = _load_processed()
    if not state:
        print("No processed.json yet — daemon hasn't completed a cycle.")
        return

    rows = sorted(state.items(), key=lambda kv: kv[1].get("clipped_at", 0), reverse=True)
    total_up = sum(r.get("num_uploaded", 0) for _, r in rows)
    total_ready = 0  # rendered clips not yet on YouTube
    for _, r in rows:
        for c in r.get("clips", []):
            if c.get("upload_status") in ("skipped_quota", None) and not c.get("youtube_id"):
                total_ready += 1

    print(f"{len(rows)} videos tracked | {total_up} clips uploaded | "
          f"{total_ready} clips rendered but not yet uploaded\n")

    for vid, r in rows[:15]:
        when = time.strftime("%m-%d %H:%M", time.localtime(r.get("clipped_at", 0)))
        if r.get("seeded"):
            head = "seeded (first-run)"
        elif r.get("skipped"):
            head = f"skipped: {r['skipped']}"
        elif r.get("error"):
            head = f"error: {r['error'][:40]}"
        else:
            head = f"clips={r.get('num_clips',0)} up={r.get('num_uploaded',0)}"
        print(f"[{when}] {head}")
        print(f"         {r.get('title','?')[:72]}")
        for c in r.get("clips", []):
            yid = c.get("youtube_id")
            link = f"https://youtu.be/{yid}" if yid else (c.get("file") or "")
            print(f"           · [{c.get('score','?'):>3}] {c.get('upload_status','?'):<28} "
                  f"{c.get('title','?')[:40]}")
            if yid:
                print(f"                 {link}")


def main() -> None:
    print(f"Clip daemon starting. Interval: {INTERVAL_HOURS}h. Ctrl+C to stop.")
    print(f"Config: clips/video={N_CLIPS_PER_VIDEO}, min_score={MIN_SCORE_TO_UPLOAD}, "
          f"duration={MIN_DURATION_MIN}–{MAX_DURATION_MIN}min, preset={DURATION_PRESET}")
    while True:
        try:
            cycle()
        except KeyboardInterrupt:
            print("\nstopping.")
            return
        except Exception as e:
            print(f"!! cycle crashed: {type(e).__name__}: {e}")
            traceback.print_exc()
        sleep_s = INTERVAL_HOURS * 3600
        next_at = time.strftime("%H:%M", time.localtime(time.time() + sleep_s))
        print(f"\nsleeping until {next_at} ({INTERVAL_HOURS}h)…")
        try:
            time.sleep(sleep_s)
        except KeyboardInterrupt:
            print("\nstopping.")
            return


if __name__ == "__main__":
    import sys
    if "--status" in sys.argv:
        print_status()
    elif "--once" in sys.argv:
        # Run a single cycle and exit — useful for testing without the 4h loop.
        cycle()
    else:
        main()
