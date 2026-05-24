"""Face-tracking 9:16 reframe.

Approach: sample every Nth frame for face detection (mediapipe), interpolate centers,
smooth with EMA, then render the cropped video frame-by-frame with OpenCV. Mux audio
back with ffmpeg at the end.

Why not pure ffmpeg with sendcmd? Per-frame crop expressions are painful to author and
mediapipe runs inline anyway. OpenCV gives us full control and isn't much slower."""

from __future__ import annotations

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


def reframe(input_video: Path, start: float, end: float, output: Path) -> Path:
    """Cut [start, end] from input_video, reframe to 9:16 following faces, write to output (silent)."""
    output.parent.mkdir(parents=True, exist_ok=True)

    # First: extract the segment losslessly-ish to a temp file so OpenCV reads less
    tmp = output.with_suffix(".seg.mp4")
    _extract_segment(input_video, start, end, tmp)

    cap = cv2.VideoCapture(str(tmp))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # The crop window is 9:16 inscribed in the source. Width is whatever fits.
    crop_h = src_h
    crop_w = int(round(src_h * 9 / 16))
    if crop_w > src_w:
        # Source is already narrower than 9:16 — pillarbox instead by limiting height
        crop_w = src_w
        crop_h = int(round(src_w * 16 / 9))

    # Pass 1: detect faces, build a smoothed center-x sequence
    centers_x = _detect_face_centers(cap, n_frames, src_w, src_h)
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
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            cx = smoothed[i] if i < len(smoothed) else smoothed[-1]
            cx = float(np.clip(cx, min_cx, max_cx))
            x0 = int(round(cx - half))
            cropped = frame[:crop_h, x0:x0 + crop_w]
            if cropped.shape[1] != crop_w or cropped.shape[0] != crop_h:
                # Edge case from rounding; pad to expected size
                cropped = cv2.copyMakeBorder(
                    cropped, 0, max(0, crop_h - cropped.shape[0]),
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
    return output


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


def _detect_face_centers(cap, n_frames: int, src_w: int, src_h: int) -> list[float | None]:
    """For each frame index, return the x-center of the most prominent face, or None."""
    mp_fd = mp.solutions.face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.4)
    centers: list[float | None] = [None] * max(n_frames, 1)
    i = 0
    last_known = src_w / 2.0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if i % DETECT_EVERY == 0:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                res = mp_fd.process(rgb)
                if res.detections:
                    # Pick the largest face (most likely the speaker)
                    best = max(res.detections, key=lambda d: d.location_data.relative_bounding_box.width)
                    bbox = best.location_data.relative_bounding_box
                    cx = (bbox.xmin + bbox.width / 2) * src_w
                    centers[i] = cx
                    last_known = cx
                else:
                    centers[i] = last_known
            i += 1
    finally:
        mp_fd.close()
    return centers


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
