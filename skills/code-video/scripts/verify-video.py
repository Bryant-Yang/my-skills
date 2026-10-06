#!/usr/bin/env python3
"""Verify observable media properties; no aesthetic or listening claim."""

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path


def run(command):
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"{command[0]} failed: {result.stderr[-4000:]}")
    return result


def positive_number(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be a finite positive number")
    return number


def positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def require_separate_report(video, destination):
    if video.resolve() == destination.resolve() or (
            video.exists() and destination.exists() and video.samefile(destination)):
        raise RuntimeError("report target overlaps input video; no report file will be written")


def write_report(video, destination, report):
    # Recheck immediately before writing; atomic replacement also preserves the
    # old target inode if another directory entry points at the same input file.
    require_separate_report(video, destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent,
                                         prefix=".code-video-report-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        require_separate_report(video, destination)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--width", type=positive_int)
    parser.add_argument("--height", type=positive_int)
    parser.add_argument("--fps", type=positive_number)
    parser.add_argument("--duration", type=positive_number)
    parser.add_argument("--frames", type=positive_int)
    parser.add_argument("--channels", type=positive_int)
    parser.add_argument("--allow-silent-audio", action="store_true",
                        help="permit intentionally silent audio; a stream is still required")
    parser.add_argument("--duration-tolerance", type=positive_number,
                        help="seconds; default is one frame plus AAC priming tolerance")
    parser.add_argument("--silence-threshold-db", type=float, default=-60.0,
                        help="maximum RMS threshold for declaring silence")
    parser.add_argument("--peak-limit-db", type=float, default=-0.1,
                        help="reject decoded sample peaks at or above this dBFS value")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = {"schema": 1, "passed": False, "checks": {}, "errors": [],
              "limits": ["No semantic, aesthetic, human listening, or learning validation.",
                         "Peak checks inspect decoded samples, not intersample true peaks.",
                         "Non-silence is an RMS threshold check, not speech intelligibility."]}
    report_writable = args.report is not None
    try:
        if args.report:
            try:
                require_separate_report(args.video, args.report)
            except (RuntimeError, OSError) as exc:
                report_writable = False
                raise RuntimeError(str(exc)) from exc
        for name in ("ffprobe", "ffmpeg"):
            if not shutil.which(name):
                raise RuntimeError(f"{name} is required on PATH")
        if not args.video.is_file():
            raise RuntimeError("video must be an existing regular file")
        if not math.isfinite(args.silence_threshold_db) or not math.isfinite(args.peak_limit_db):
            raise RuntimeError("audio thresholds must be finite")
        if args.silence_threshold_db >= args.peak_limit_db or args.peak_limit_db > 0:
            raise RuntimeError("audio thresholds require silence < peak limit <= 0 dBFS")
        data = json.loads(run(["ffprobe", "-v", "error", "-count_frames",
                               "-show_streams", "-show_format", "-of", "json",
                               str(args.video.resolve())]).stdout)
        videos = [s for s in data["streams"] if s["codec_type"] == "video"]
        audios = [s for s in data["streams"] if s["codec_type"] == "audio"]
        if len(videos) != 1 or len(audios) != 1:
            raise RuntimeError("expected exactly one video and one audio stream")
        video, audio = videos[0], audios[0]
        fps = float(Fraction(video["avg_frame_rate"]))
        nominal_fps = float(Fraction(video["r_frame_rate"]))
        if fps <= 0 or abs(fps - nominal_fps) > 0.001:
            raise RuntimeError("expected a constant frame rate")
        frame_count = int(video["nb_read_frames"])
        video_duration, audio_duration = float(video["duration"]), float(audio["duration"])
        container_duration = float(data["format"]["duration"])
        tolerance = args.duration_tolerance or (1 / fps + 0.055)
        report["observed"] = {"width": video["width"], "height": video["height"],
                              "fps": fps, "frames": frame_count, "channels": audio["channels"],
                              "video_codec": video["codec_name"], "audio_codec": audio["codec_name"],
                              "pixel_format": video.get("pix_fmt"),
                              "video_duration": video_duration, "audio_duration": audio_duration,
                              "container_duration": container_duration,
                              "duration_tolerance": tolerance}
        if min(frame_count, video_duration, audio_duration, container_duration) <= 0:
            raise RuntimeError("media has an empty stream")
        for key in ("width", "height", "channels"):
            expected = getattr(args, key)
            if expected is not None and report["observed"][key] != expected:
                report["errors"].append(f"{key}: expected {expected}, got {report['observed'][key]}")
        if args.fps and abs(fps - args.fps) > 0.001:
            report["errors"].append(f"fps: expected {args.fps}, got {fps}")
        if args.frames and frame_count != args.frames:
            report["errors"].append(f"frames: expected {args.frames}, got {frame_count}")
        if abs(video_duration - frame_count / fps) > tolerance:
            report["errors"].append("frame count and video duration disagree")
        if abs(video_duration - audio_duration) > tolerance:
            report["errors"].append("audio/video durations differ beyond tolerance")
        start_difference = abs(float(video.get("start_time", 0)) - float(audio.get("start_time", 0)))
        if start_difference > tolerance:
            report["errors"].append("audio/video stream starts differ beyond tolerance")
        if args.duration:
            for label, duration in (("video", video_duration), ("audio", audio_duration),
                                    ("container", container_duration)):
                if abs(duration - args.duration) > tolerance:
                    report["errors"].append(f"{label} duration differs from expected {args.duration}")
        timestamps = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_frames",
                          "-show_entries", "frame=best_effort_timestamp_time", "-of", "csv=p=0",
                          str(args.video.resolve())]).stdout
        points = []
        for line in timestamps.splitlines():
            if not line.strip():
                continue
            first = line.split(",", 1)[0]
            try:
                point = float(first)
            except ValueError:
                continue  # FFprobe may append an SEI side-data row to a frame.
            if not math.isfinite(point):
                raise RuntimeError("frame timestamp is not finite")
            points.append(point)
        if len(points) != frame_count:
            raise RuntimeError("could not verify all video frame timestamps")
        timing_tolerance = max(0.0005, 1 / fps * 0.001)
        report["checks"]["constant_frame_timestamps"] = all(
            abs((point - points[0]) - index / fps) <= timing_tolerance
            for index, point in enumerate(points))
        if not report["checks"]["constant_frame_timestamps"]:
            report["errors"].append("video frame timestamps are not uniformly spaced")
        run(["ffmpeg", "-nostdin", "-v", "error", "-xerror", "-i", str(args.video.resolve()),
             "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"])
        report["checks"]["full_decode"] = True
        # float PCM avoids integer conversion hiding a full-scale decoded peak.
        levels = run(["ffmpeg", "-nostdin", "-hide_banner", "-i", str(args.video.resolve()),
                      "-map", "0:a:0", "-vn", "-af", "astats=metadata=0:reset=0",
                      "-f", "null", "-"]).stderr
        overall = levels.split("Overall")[-1]
        peak_match = re.search(r"Peak level dB:\s*(-?inf|[-+0-9.eE]+)", overall)
        rms_match = re.search(r"RMS level dB:\s*(-?inf|[-+0-9.eE]+)", overall)
        if not peak_match or not rms_match:
            raise RuntimeError("ffmpeg did not report decoded audio levels")
        peak, rms = float(peak_match.group(1)), float(rms_match.group(1))
        report["observed"]["audio_peak_dbfs"] = peak if math.isfinite(peak) else None
        report["observed"]["audio_rms_dbfs"] = rms if math.isfinite(rms) else None
        report["checks"]["non_silent"] = math.isfinite(rms) and rms > args.silence_threshold_db
        report["checks"]["sample_peak_below_limit"] = peak < args.peak_limit_db
        report["checks"]["silent_audio_explicitly_allowed"] = args.allow_silent_audio
        if not report["checks"]["non_silent"] and not args.allow_silent_audio:
            report["errors"].append("audio is silent or below RMS threshold")
        if math.isfinite(peak) and not report["checks"]["sample_peak_below_limit"]:
            report["errors"].append("decoded audio reaches configured peak limit")
        report["checks"]["expected_properties"] = not report["errors"]
        report["passed"] = not report["errors"]
    except (RuntimeError, OSError, ValueError, KeyError, ZeroDivisionError) as exc:
        report["errors"].append(str(exc))
    if report_writable:
        try:
            write_report(args.video, args.report, report)
        except (RuntimeError, OSError) as exc:
            report["passed"] = False
            report["errors"].append(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
