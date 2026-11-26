#!/usr/bin/env python3
"""Verify observable media properties; no aesthetic or human listening claim."""

import argparse
from array import array
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
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


def unit_ratio(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0 or number > 1:
        raise argparse.ArgumentTypeError("must be in (0, 1]")
    return number


def normalize_text(text):
    # Keep letters, digits, and CJK ideographs; strip whitespace and punctuation.
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", text.lower(), flags=re.UNICODE).replace("_", "")


def multiset_recall(expected_norm, observed_norm):
    if not expected_norm:
        return 1.0
    exp_counts = Counter(expected_norm)
    obs_counts = Counter(observed_norm)
    matched = sum(min(count, obs_counts[ch]) for ch, count in exp_counts.items())
    return matched / len(expected_norm)


def require_separate_report(video, destination):
    if video.resolve() == destination.resolve() or (
            video.exists() and destination.exists() and video.samefile(destination)):
        raise RuntimeError("report target overlaps input video; no report file will be written")


def write_report(video, destination, report):
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


def frame_l1_diff(a: bytes, b: bytes) -> float:
    return sum(abs(x - y) for x, y in zip(a, b)) / max(1, len(a))


def inspect_video_flicker(video_path: Path, fps: float) -> dict:
    """Pure-stdlib scan for 1-frame flashes, short collapse bursts, and #808080 gray-border frames."""
    w, h = 64, 36
    stride = w * h * 3
    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", str(video_path),
         "-vf", f"scale={w}:{h}:flags=area", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True,
    )
    if proc.returncode:
        raise RuntimeError(f"ffmpeg flicker scan failed: {proc.stderr.decode('utf-8', 'replace')[-2000:]}")
    raw = proc.stdout
    n = len(raw) // stride
    if n < 3:
        return {"frames_scanned": n, "gray_border_frames": [], "single_frame_flashes": [], "burst_flashes": []}

    # Extract interior stage bytes (x: 4..60, y: 2..34) and check bottom-right gray border strips
    stages = []
    lumas = []
    gray_border_frames = []
    for i in range(n):
        base = i * stride
        frame = raw[base:base + stride]
        # Stage interior
        stage_chunks = [frame[(y * w + 4) * 3:(y * w + 60) * 3] for y in range(2, 34)]
        st = b"".join(stage_chunks)
        stages.append(st)
        lumas.append(sum(st) / len(st))

        # Check right & bottom strips for Playwright HiDPI #808080 padding while top-left has content
        edge_pts = []
        for y in range(4, 30, 2):
            for x in (58, 60, 62):
                o = (y * w + x) * 3
                edge_pts.append((frame[o], frame[o + 1], frame[o + 2]))
        for x in range(4, 56, 4):
            for y in (32, 34):
                o = (y * w + x) * 3
                edge_pts.append((frame[o], frame[o + 1], frame[o + 2]))
        gray_hits = sum(
            1 for r, g, b in edge_pts
            if abs(r - 128) <= 12 and abs(g - 128) <= 12 and abs(b - 128) <= 12
            and max(r, g, b) - min(r, g, b) <= 10
        )
        if gray_hits / len(edge_pts) >= 0.85:
            # Verify top-left is not the exact same uniform gray
            tl_chunks = [frame[(y * w + 4) * 3:(y * w + 36) * 3] for y in range(4, 22)]
            tl = b"".join(tl_chunks)
            tl_diff = sum(abs(v - 128) for v in tl) / len(tl)
            if tl_diff > 18.0:
                gray_border_frames.append({"frame": i, "sec": round(i / fps, 3)})

    diffs = [frame_l1_diff(stages[i], stages[i + 1]) for i in range(n - 1)]
    single_flashes = []
    for i in range(1, n - 1):
        dp, dn = diffs[i - 1], diffs[i]
        if dp > 12.0 and dn > 12.0:
            ds = frame_l1_diff(stages[i - 1], stages[i + 1])
            luma_dev = abs(lumas[i] - 0.5 * (lumas[i - 1] + lumas[i + 1]))
            if ds < min(dp, dn) * 0.50 and luma_dev > 6.0:
                single_flashes.append({
                    "frame": i, "sec": round(i / fps, 3),
                    "diff_prev": round(dp, 1), "diff_skip": round(ds, 1),
                    "luma": [round(lumas[i - 1], 1), round(lumas[i], 1), round(lumas[i + 1], 1)],
                })

    burst_flashes = []
    i = 1
    while i < n - 2:
        if diffs[i - 1] > 18.0:
            for k in range(2, min(16, n - i)):
                if diffs[i + k - 1] > 18.0 and frame_l1_diff(stages[i - 1], stages[i + k]) < 6.0:
                    burst_flashes.append({
                        "start_frame": i, "sec": round(i / fps, 3),
                        "length_frames": k, "entry_diff": round(diffs[i - 1], 1),
                    })
                    i += k
                    break
        i += 1

    return {
        "frames_scanned": n,
        "gray_border_frames": gray_border_frames[:20],
        "gray_border_count": len(gray_border_frames),
        "single_frame_flashes": single_flashes[:20],
        "single_frame_flash_count": len(single_flashes),
        "burst_flashes": burst_flashes[:20],
        "burst_flash_count": len(burst_flashes),
    }


def inspect_sentence_tails(media_path: Path, timeline_path: Path, max_tail_dbfs: float) -> dict:
    """Measure RMS dBFS in the final 50ms of each sentence from a timeline JSON."""
    tl = json.loads(timeline_path.read_text(encoding="utf-8"))
    sentences = []
    if isinstance(tl.get("beats"), list):
        for b in tl["beats"]:
            for s in b.get("sentences", []):
                if "start" in s and "end" in s:
                    sentences.append(s)
    elif isinstance(tl.get("sentences"), list):
        sentences = [s for s in tl["sentences"] if "start" in s and "end" in s]
    if not sentences:
        raise RuntimeError("sentence-timeline contains no sentences with start/end timestamps")

    sr = 24000
    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", str(media_path),
         "-map", "0:a:0", "-vn", "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
        capture_output=True,
    )
    if proc.returncode:
        raise RuntimeError(f"ffmpeg sentence-tail decode failed: {proc.stderr.decode('utf-8', 'replace')[-2000:]}")
    samples = array("h")
    samples.frombytes(proc.stdout)
    win = int(sr * 0.050)
    worst_db = -120.0
    clipped = []
    for idx, s in enumerate(sentences):
        end_idx = min(len(samples), int(round(float(s["end"]) * sr)))
        start_idx = max(0, end_idx - win)
        seg = samples[start_idx:end_idx]
        if not seg:
            continue
        rms = math.sqrt(sum((v / 32768.0) ** 2 for v in seg) / len(seg) + 1e-12)
        db = round(20.0 * math.log10(rms), 2)
        if db > worst_db:
            worst_db = db
        if db > max_tail_dbfs:
            clipped.append({"index": idx + 1, "end_sec": round(float(s["end"]), 3), "tail50ms_dbfs": db})
    return {
        "sentences_checked": len(sentences),
        "max_tail_dbfs_limit": max_tail_dbfs,
        "worst_tail50ms_dbfs": round(worst_db, 2),
        "clipped_sentences": clipped[:20],
        "clipped_count": len(clipped),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--width", type=positive_int)
    parser.add_argument("--height", type=positive_int)
    parser.add_argument("--fps", type=positive_number)
    parser.add_argument("--duration", type=positive_number)
    parser.add_argument("--frames", type=positive_int)
    parser.add_argument("--channels", type=positive_int)
    parser.add_argument("--expect-chapters", type=positive_int,
                        help="require this exact number of monotonic non-empty container chapters")
    parser.add_argument("--transcript-file", type=Path,
                        help="ASR transcript produced from the encoded video's audio stream")
    parser.add_argument("--expected-text-file", type=Path,
                        help="expected spoken narration text to reconcile against --transcript-file")
    parser.add_argument("--min-char-coverage", type=unit_ratio, default=0.78,
                        help="minimum normalized character recall when --expected-text-file is given")
    parser.add_argument("--allow-silent-audio", action="store_true",
                        help="permit intentionally silent audio; a stream is still required")
    parser.add_argument("--duration-tolerance", type=positive_number,
                        help="seconds; default is one frame plus AAC priming tolerance")
    parser.add_argument("--silence-threshold-db", type=float, default=-60.0,
                        help="maximum RMS threshold for declaring silence")
    parser.add_argument("--peak-limit-db", type=float, default=-0.1,
                        help="reject decoded sample peaks at or above this dBFS value")
    parser.add_argument("--check-flicker", action="store_true",
                        help="scan decoded video frames for 1-frame flashes, short collapse bursts, and gray-border frames")
    parser.add_argument("--sentence-timeline", type=Path,
                        help="optional timeline JSON (beats[].sentences[].{start,end}) to check final 50ms tail decay")
    parser.add_argument("--max-tail-dbfs", type=float, default=-38.0,
                        help="maximum allowed final-50ms RMS dBFS per sentence (default -38.0 for dry voice; raise for BGM mix)")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    limits = [
        "No semantic, aesthetic, human listening, or learning validation.",
        "Peak checks inspect decoded samples, not intersample true peaks.",
        "Non-silence is an RMS threshold check, not speech intelligibility.",
    ]
    if args.transcript_file is not None or args.expected_text_file is not None:
        limits.append(
            "ASR transcript reconciliation checks text recall, not pronunciation, voice identity, prosody, or mix quality."
        )
    report = {"schema": 1, "passed": False, "checks": {}, "errors": [], "limits": limits}
    report_writable = args.report is not None
    try:
        if args.report:
            try:
                require_separate_report(args.video, args.report)
            except (RuntimeError, OSError) as exc:
                report_writable = False
                raise RuntimeError(str(exc)) from exc
        if bool(args.transcript_file) != bool(args.expected_text_file):
            raise RuntimeError("provide both --transcript-file and --expected-text-file, or neither")
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
                               "-show_streams", "-show_chapters", "-show_format", "-of", "json",
                               str(args.video.resolve())]).stdout)
        videos = [s for s in data["streams"] if s["codec_type"] == "video"]
        audios = [s for s in data["streams"] if s["codec_type"] == "audio"]
        chapters = data.get("chapters", [])
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
        report["observed"] = {
            "width": video["width"],
            "height": video["height"],
            "fps": fps,
            "frames": frame_count,
            "channels": audio["channels"],
            "chapters": len(chapters),
            "video_codec": video["codec_name"],
            "audio_codec": audio["codec_name"],
            "pixel_format": video.get("pix_fmt"),
            "video_duration": video_duration,
            "audio_duration": audio_duration,
            "container_duration": container_duration,
            "duration_tolerance": tolerance,
        }
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
        if args.expect_chapters is not None:
            valid_chapters = len(chapters) == args.expect_chapters
            prev_end = 0.0
            for ch in chapters:
                ch_start = float(ch.get("start_time", -1))
                ch_end = float(ch.get("end_time", -1))
                ch_title = str(ch.get("tags", {}).get("title", "")).strip()
                if not (ch_title and ch_start >= -0.001 and ch_end > ch_start and
                        abs(ch_start - prev_end) <= tolerance and ch_end <= container_duration + tolerance):
                    valid_chapters = False
                    break
                prev_end = ch_end
            report["checks"]["chapters_valid"] = valid_chapters
            if not valid_chapters:
                report["errors"].append(
                    f"chapters: expected {args.expect_chapters} contiguous titled chapters within duration, got {len(chapters)}"
                )
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
        if args.transcript_file and args.expected_text_file:
            if not args.transcript_file.is_file() or not args.expected_text_file.is_file():
                raise RuntimeError("transcript-file and expected-text-file must be existing regular files")
            obs_norm = normalize_text(args.transcript_file.read_text(encoding="utf-8"))
            exp_norm = normalize_text(args.expected_text_file.read_text(encoding="utf-8"))
            if not exp_norm:
                raise RuntimeError("expected-text-file has no normalizable characters")
            coverage = round(multiset_recall(exp_norm, obs_norm), 4)
            report["observed"]["transcript_char_coverage"] = coverage
            passed_cov = bool(obs_norm) and coverage >= args.min_char_coverage
            report["checks"]["transcript_coverage"] = passed_cov
            if not passed_cov:
                report["errors"].append(
                    f"transcript coverage {coverage} below required {args.min_char_coverage}"
                )
        if args.check_flicker:
            flicker = inspect_video_flicker(args.video.resolve(), fps)
            report["observed"]["flicker"] = flicker
            total_glitches = (
                flicker["gray_border_count"]
                + flicker["single_frame_flash_count"]
                + flicker["burst_flash_count"]
            )
            report["checks"]["no_flicker"] = total_glitches == 0
            if total_glitches > 0:
                report["errors"].append(
                    f"flicker/border glitches detected: gray={flicker['gray_border_count']}, "
                    f"1f={flicker['single_frame_flash_count']}, burst={flicker['burst_flash_count']}"
                )
        if args.sentence_timeline:
            if not args.sentence_timeline.is_file():
                raise RuntimeError("sentence-timeline must be an existing regular file")
            tails = inspect_sentence_tails(args.video.resolve(), args.sentence_timeline.resolve(), args.max_tail_dbfs)
            report["observed"]["sentence_tails"] = tails
            report["checks"]["clean_sentence_tails"] = tails["clipped_count"] == 0
            if tails["clipped_count"] > 0:
                report["errors"].append(
                    f"sentence tail clipping: {tails['clipped_count']} sentences exceed {args.max_tail_dbfs} dBFS "
                    f"(worst {tails['worst_tail50ms_dbfs']} dBFS)"
                )
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
