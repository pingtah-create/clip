"""Active-speaker-tracking 9:16 reframe.

Approach: sample every Nth frame with mediapipe FaceMesh, pick the active speaker
among multiple faces (face size weighted by mouth openness — the talker's mouth
moves), interpolate centers, smooth with EMA, then render the cropped video
frame-by-frame with OpenCV. Mux audio back with ffmpeg at the end.

Why mouth-openness instead of true audio-visual sync (TalkNet)? It's a cheap
heuristic with no extra model/deps that gets the host-vs-guest case right ~80% of
the time. Real ASD would be a half-day ML add for marginal gain on talking-head clips.

Why not pure ffmpeg with sendcmd? Per-frame crop expressions are painful to author and
mediapipe runs inline anyway. OpenCV gives us full control and isn't much slower."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np

from .tools import FFMPEG


TARGET_W = 1080
TARGET_H = 1920  # 9:16
DETECT_EVERY = 3        # detect faces every N frames (interpolate between)
EMA_ALPHA = 0.12        # how quickly the crop window follows the face (lower = smoother)
EDGE_PAD = 0.08         # keep face this far from the crop edges (fraction of crop width)
# How much wider than a strict 9:16 column the crop region is, to avoid the "blown-up
# face" look. 1.0 = tightest vertical strip (very zoomed). 1.4 = crop 40% wider then
# scale to fit width, showing shoulders/surroundings. Env-tunable via REFRAME_ZOOM_OUT.
ZOOM_OUT = max(1.0, float(os.environ.get("REFRAME_ZOOM_OUT", "1.4")))


def reframe(input_video: Path, start: float, end: float, output: Path) -> float:
    """Cut [start, end] from input_video, reframe to 9:16 following the active speaker,
    write to output. Returns face_coverage (0..1) — the fraction of the clip that had a
    visible face — so the pipeline can reject visually-dead clips."""
    output.parent.mkdir(parents=True, exist_ok=True)

    # First: extract the segment losslessly-ish to a temp file so OpenCV reads less
    tmp = output.with_suffix(".seg.mp4")
    _extract_segment(input_video, start, end, tmp)

    cap = cv2.VideoCapture(str(tmp))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Base 9:16 crop is a narrow full-height column (src_h * 9/16 wide). That blows the
    # face up too much, so we widen the crop by ZOOM_OUT, then scale the wider region
    # down to the 1080-wide target and center-crop the overflow height back to 9:16.
    # Net effect: the speaker sits in a pulled-back frame showing shoulders/context.
    base_crop_w = src_h * 9 / 16
    crop_w = int(round(min(base_crop_w * ZOOM_OUT, src_w)))
    # Height of the region whose 9:16 portion we keep, given the widened width.
    crop_h = int(round(crop_w * 16 / 9))
    if crop_h > src_h:
        # Can't get enough height for the widened width — fall back to full height
        # and the widest 9:16-compatible column we can take.
        crop_h = src_h
        crop_w = min(int(round(src_h * 9 / 16 * ZOOM_OUT)), src_w)

    # Pass 1: detect faces, build a smoothed center-x sequence + coverage score
    centers_x, face_coverage = _detect_face_centers(cap, n_frames, src_w, src_h)
    cap.release()
    smoothed = _ema(centers_x, EMA_ALPHA, default=src_w / 2)

    # Pass 2: render the crop with OpenCV → ffmpeg pipe
    # ffmpeg reads raw bgr24 frames over stdin so we don't write a giant intermediate file
    silent_out = output.with_suffix(".silent.mp4")
    ff = subprocess.Popen(
        [
            FFMPEG, "-y",
            "-f", "rawvideo", "-vcodec", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", f"{TARGET_W}x{TARGET_H}",
            "-r", f"{fps}",
            "-i", "-",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(silent_out),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    cap = cv2.VideoCapture(str(tmp))
    i = 0
    half = crop_w / 2
    min_cx = half
    max_cx = src_w - half
    # Vertical: center the crop_h window in the source (clamped to bounds).
    eff_crop_h = min(crop_h, src_h)
    y0 = max(0, (src_h - eff_crop_h) // 2)
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            cx = smoothed[i] if i < len(smoothed) else smoothed[-1]
            cx = float(np.clip(cx, min_cx, max_cx))
            x0 = int(round(cx - half))
            x0 = max(0, min(x0, src_w - crop_w))
            cropped = frame[y0:y0 + eff_crop_h, x0:x0 + crop_w]
            if cropped.shape[1] != crop_w or cropped.shape[0] != eff_crop_h:
                # Edge case from rounding; pad to expected size
                cropped = cv2.copyMakeBorder(
                    cropped, 0, max(0, eff_crop_h - cropped.shape[0]),
                    0, max(0, crop_w - cropped.shape[1]), cv2.BORDER_REPLICATE,
                )
            resized = cv2.resize(cropped, (TARGET_W, TARGET_H), interpolation=cv2.INTER_AREA)
            ff.stdin.write(resized.tobytes())
            i += 1
    finally:
        cap.release()
        ff.stdin.close()
        ff.wait()

    # Mux original audio (from the segment) onto the silent reframed video
    _mux_audio(silent_out, tmp, output)

    # Clean up temps
    tmp.unlink(missing_ok=True)
    silent_out.unlink(missing_ok=True)
    return face_coverage


def _extract_segment(src: Path, start: float, end: float, dst: Path) -> None:
    # Re-encode to ensure precise cuts (stream copy can drift to nearest keyframe).
    cmd = [
        FFMPEG, "-y",
        "-ss", f"{start}",
        "-to", f"{end}",
        "-i", str(src),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k",
        str(dst),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# FaceMesh lip landmark indices (upper-inner and lower-inner lip) — the gap between
# them tracks mouth openness, our proxy for "is this person talking right now".
_LIP_TOP = 13
_LIP_BOTTOM = 14
# How much we favor a moving mouth over a big face. A face whose mouth is open scores
# size * (1 + TALK_BONUS * openness); a still listener stays near its raw size.
_TALK_BONUS = 6.0


def _detect_face_centers(cap, n_frames: int, src_w: int, src_h: int) -> tuple[list[float | None], float]:
    """For each sampled frame, return the x-center of the *active speaker*, plus the
    fraction of sampled frames that actually contained a face (face_coverage 0..1).

    Multi-face heuristic: among detected faces we pick the one that best combines
    face size with mouth movement (lip gap). On a host+guest interview this follows
    whoever is talking instead of locking onto the largest face. Falls back to
    largest-face when only one face is present or FaceMesh finds no clear mover.

    face_coverage lets the pipeline reject clips that are mostly slides/B-roll with
    no visible speaker — those tank Shorts retention."""
    mp_mesh = mp.solutions.face_mesh.FaceMesh(
        static_image_mode=False, max_num_faces=4,
        refine_landmarks=False, min_detection_confidence=0.4,
    )
    centers: list[float | None] = [None] * max(n_frames, 1)
    i = 0
    last_known = src_w / 2.0
    sampled = 0
    with_face = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if i % DETECT_EVERY == 0:
                sampled += 1
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                res = mp_mesh.process(rgb)
                cx = _pick_speaker_x(res, src_w, src_h)
                if cx is not None:
                    centers[i] = cx
                    last_known = cx
                    with_face += 1
                else:
                    centers[i] = last_known
            i += 1
    finally:
        mp_mesh.close()
    coverage = (with_face / sampled) if sampled else 0.0
    return centers, coverage


def _pick_speaker_x(mesh_res, src_w: int, src_h: int) -> float | None:
    """From FaceMesh multi-face output, return the x-center of the active speaker.
    Scores each face by size * (1 + TALK_BONUS * mouth_openness)."""
    if not mesh_res.multi_face_landmarks:
        return None

    best_x = None
    best_score = -1.0
    for lm in mesh_res.multi_face_landmarks:
        xs = [p.x for p in lm.landmark]
        ys = [p.y for p in lm.landmark]
        face_w = (max(xs) - min(xs))            # normalized 0..1
        face_h = (max(ys) - min(ys)) or 1e-6
        cx = (min(xs) + max(xs)) / 2 * src_w

        # Mouth openness normalized by face height so it's scale-invariant.
        top = lm.landmark[_LIP_TOP].y
        bot = lm.landmark[_LIP_BOTTOM].y
        openness = abs(bot - top) / face_h

        score = face_w * (1.0 + _TALK_BONUS * openness)
        if score > best_score:
            best_score = score
            best_x = cx
    return best_x


def _ema(values: list[float | None], alpha: float, default: float) -> list[float]:
    """Forward-fill Nones, then exponential moving average for smoothness."""
    filled: list[float] = []
    last = default
    for v in values:
        if v is not None:
            last = v
        filled.append(last)
    out: list[float] = []
    ema = filled[0] if filled else default
    for v in filled:
        ema = alpha * v + (1 - alpha) * ema
        out.append(ema)
    return out


def _mux_audio(video: Path, audio_src: Path, out: Path) -> None:
    cmd = [
        FFMPEG, "-y",
        "-i", str(video), "-i", str(audio_src),
        "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
        "-map", "0:v:0", "-map", "1:a:0?",
        "-shortest",
        "-movflags", "+faststart",
        str(out),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
