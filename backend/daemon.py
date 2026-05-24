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
import subprocess
import time
import traceback
from pathlib import Path

import feedparser
from dotenv import load_dotenv

from . import jobs, pipeline
from .tools import YT_DLP_CMD

# Load .env BEFORE reading any DAEMON_* config. override=True for the same reason
# as main.py — beats any inherited shell env vars that would silently override.
load_dotenv(override=True)

ROOT = Path(__file__).resolve().parent.parent
CHANNELS_FILE = ROOT / "channels.txt"
QUERIES_FILE = ROOT / "queries.txt"
PROCESSED_FILE = ROOT / "data" / "processed.json"
PROCESSED_FILE.parent.mkdir(parents=True, exist_ok=True)


def _cfg_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except ValueError:
        return default


INTERVAL_HOURS = _cfg_int("DAEMON_INTERVAL_HOURS", 4)
N_CLIPS_PER_VIDEO = _cfg_int("DAEMON_N_CLIPS_PER_VIDEO", 3)
MIN_SCORE_TO_UPLOAD = _cfg_int("DAEMON_MIN_SCORE_TO_UPLOAD", 80)
MAX_DURATION_MIN = _cfg_int("DAEMON_MAX_VIDEO_DURATION_MIN", 180)
MIN_DURATION_MIN = _cfg_int("DAEMON_MIN_VIDEO_DURATION_MIN", 5)
MAX_VIDEO_AGE_DAYS = _cfg_int("DAEMON_MAX_VIDEO_AGE_DAYS", 14)
RESULTS_PER_QUERY = _cfg_int("DAEMON_RESULTS_PER_QUERY", 1)
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


def _search_youtube(query: str, limit: int) -> list[dict]:
    """Run a YouTube search via yt-dlp and return up to `limit` video dicts. No API
    quota used — yt-dlp scrapes the public search results page. Sorted by YouTube's
    default relevance ranking; we filter by age downstream."""
    try:
        res = subprocess.run(
            [*YT_DLP_CMD, f"ytsearch{limit * 3}:{query}",  # over-fetch since some get filtered
             "--flat-playlist",
             "--print", "%(id)s\t%(title)s\t%(upload_date)s\t%(channel)s",
             "--no-warnings"],
            capture_output=True, text=True, timeout=60,
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
            "source": f"query: {query}",
        })
    return out[:limit * 3]  # return all fetched; caller filters by age + dedup


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
    # Synchronous — the daemon serializes work, no parallel jobs.
    pipeline.run(job.id)

    job = jobs.get(job.id)
    if not job:
        return {"clipped_at": time.time(), "num_clips": 0, "num_uploaded": 0,
                "error": "job vanished"}

    done_clips = [c for c in job.clips if c.status == "done" and c.file]
    print(f"  ✓ rendered {len(done_clips)}/{len(job.clips)} clips")

    uploaded = 0
    skipped_quota = 0
    try:
        from .youtube import upload as yt_upload
        privacy = os.environ.get("YOUTUBE_PRIVACY", "private").lower()
        tags = [t.strip() for t in os.environ.get("YOUTUBE_DEFAULT_TAGS", "shorts").split(",")
                if t.strip()]
        for c in done_clips:
            if c.score < MIN_SCORE_TO_UPLOAD:
                print(f"    skip (score {c.score} < {MIN_SCORE_TO_UPLOAD}): {c.title}")
                continue
            if _quota_exhausted:
                # We already hit 429 earlier in this cycle. Don't waste a network call.
                print(f"    skip (quota exhausted): {c.title}")
                skipped_quota += 1
                continue
            try:
                desc = (f"{c.hook}\n\nFrom: {video['title']}"
                        if c.hook else f"From: {video['title']}")
                vid_id = yt_upload(Path(c.file), title=c.title, description=desc,
                                   tags=tags, privacy=privacy)
                print(f"    ↑ uploaded: {c.title} → {vid_id}")
                uploaded += 1
            except Exception as e:
                print(f"    ! upload failed for {c.title}: {type(e).__name__}: {e}")
                if "quotaExceeded" in str(e):
                    print("    !! YouTube daily quota exhausted — skipping further uploads "
                          "until next cycle. Rendered clips stay on disk for manual upload.")
                    _quota_exhausted = True
                    skipped_quota += 1
    except Exception as e:
        print(f"  ! upload module error: {e}")

    return {
        "clipped_at": time.time(),
        "title": video["title"],
        "source": video.get("source", "channel"),
        "num_clips": len(done_clips),
        "num_uploaded": uploaded,
        "num_skipped_quota": skipped_quota,
    }


def cycle() -> None:
    """One pass through all channels. Idempotent — IDs in processed.json are skipped."""
    global _quota_exhausted
    # Each cycle starts fresh — the quota window resets at midnight Pacific so a
    # 4-hour-later cycle has a real chance of working again.
    _quota_exhausted = False

    state = _load_processed()
    first_run = len(state) == 0 and FIRST_RUN_SEEDS_ONLY

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
    main()
