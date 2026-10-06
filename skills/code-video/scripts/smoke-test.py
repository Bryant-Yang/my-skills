#!/usr/bin/env python3
"""Bounded offline media smoke; every generated asset lives in an owned temp directory."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import wave


def invoke(command, expected=0, evidence=None):
    result = subprocess.run(command, text=True, capture_output=True, timeout=120)
    if (result.returncode == 0) != (expected == 0):
        raise RuntimeError(f"Unexpected status {result.returncode}: {result.stderr[-4000:]}")
    if evidence and evidence not in (result.stdout + result.stderr):
        raise RuntimeError(f"Expected failure evidence missing: {evidence}")
    return result


def digest(file):
    return hashlib.sha256(file.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome", required=True)
    dependency = parser.add_mutually_exclusive_group(required=True)
    dependency.add_argument("--dependency-root")
    dependency.add_argument("--puppeteer-module")
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    report = {"passed": False, "checks": [], "errors": [], "limits": [
        "Synthetic sine audio and a technical Canvas example, not creative quality validation.",
        "Three sampled seek times do not prove every time or every browser is deterministic."]}
    try:
        for tool in ("node", "python3", "ffmpeg", "ffprobe"):
            if not shutil.which(tool):
                raise RuntimeError(f"{tool} required")
        with tempfile.TemporaryDirectory(prefix="code-video-smoke-") as directory:
            root = Path(directory)
            scene = root / "scene"
            scene.mkdir()
            studio = scene / "studio.html"
            template = (here.parent / "assets" / "canvas-starter" / "studio.html").read_text()
            studio.write_text(template)
            audio = root / "tone.wav"
            with wave.open(str(audio), "wb") as wav:
                wav.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
                wav.writeframes(b"".join(struct.pack("<h", int(5000 * math.sin(2 * math.pi * 440 * i / 48000)))
                                         for i in range(38400)))
            out = root / "result.mp4"
            dependency_key = "--dependency-root" if args.dependency_root else "--puppeteer-module"
            dependency_value = args.dependency_root or args.puppeteer_module
            command = ["node", str(here / "render-canvas.mjs"), "--studio", str(studio),
                       "--audio", str(audio), "--out", str(out), "--fps", "12", "--chrome", args.chrome,
                       dependency_key, dependency_value]
            result = json.loads(invoke(command).stdout)
            report["checks"].append({"render_and_full_decode": result["verification"],
                                     "sampled_seek": result["seek_checks"]})
            aligned_audio = root / "frame-aligned.wav"
            with wave.open(str(aligned_audio), "wb") as wav:
                wav.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
                wav.writeframes(b"".join(struct.pack("<h", int(5000 * math.sin(2 * math.pi * 440 * i / 48000)))
                                         for i in range(8000)))
            aligned_command = list(command)
            aligned_command[aligned_command.index("--audio") + 1] = str(aligned_audio)
            aligned_command[aligned_command.index("--out") + 1] = str(root / "frame-aligned.mp4")
            aligned_command[aligned_command.index("--fps") + 1] = "24"
            aligned = json.loads(invoke(aligned_command).stdout)
            if aligned["verification"]["observed"]["frames"] != 4 or result["verification"]["observed"]["frames"] != 10:
                raise RuntimeError("PCM frame ceiling does not preserve aligned/partial-frame sample counts")
            report["checks"].append({"exact_pcm_frame_ceiling": {
                "samples": 8000, "sample_rate": 48000, "fps": 24, "expected_frames": 4,
                "verification": aligned["verification"], "baseline_0_8s_12fps_frames": 10}})
            original = digest(out)
            alias_directory = root / "output-alias"
            alias_directory.symlink_to(root, target_is_directory=True)
            source_overlap = list(command)
            source_overlap[source_overlap.index("--audio") + 1] = str(out)
            source_overlap[source_overlap.index("--out") + 1] = str(alias_directory / out.name)
            invoke(source_overlap + ["--overwrite"], expected=1,
                   evidence="Output must be different from source audio and HTML")
            if digest(out) != original:
                raise RuntimeError("Parent directory alias overwrote source media")
            report["checks"].append("symlink parent output alias rejected; original source MP4 SHA preserved")
            symlink = root / "report-symlink.json"
            hardlink = root / "report-hardlink.json"
            symlink.symlink_to(out)
            os.link(out, hardlink)
            for target in (out, symlink, hardlink):
                invoke(["python3", str(here / "verify-video.py"), str(out), "--report", str(target)],
                       expected=1, evidence="report target overlaps input video")
                if digest(out) != original or digest(target) != original:
                    raise RuntimeError("Overlapping report target changed video data")
            if not symlink.is_symlink() or not hardlink.samefile(out):
                raise RuntimeError("Overlapping report aliases were modified")
            report["checks"].append("same-path, symlink and hardlink report collisions rejected without changes")
            invoke(command, expected=1, evidence="Output already exists")
            if digest(out) != original:
                raise RuntimeError("Existing output changed without overwrite")
            report["checks"].append("existing output protected")
            studio.write_text(template.replace("</html>", '<script src="missing-local-asset.js"></script></html>'))
            invoke(command + ["--overwrite"], expected=1, evidence="missing-local-asset.js")
            if digest(out) != original:
                raise RuntimeError("Failed overwrite changed accepted movie")
            report["checks"].append("missing resource rejected; failed overwrite preserves movie")
            studio.write_text(template.replace("</html>", '<script src="https://invalid.example/blocked.js"></script></html>'))
            invoke(command + ["--overwrite"], expected=1, evidence="External browser resource blocked")
            if digest(out) != original:
                raise RuntimeError("External request failure changed accepted movie")
            report["checks"].append("external browser resource blocked")
            studio.write_text(template)
            invoke(command + ["--overwrite", "--duration", "3"], expected=1, evidence="more than one frame")
            if digest(out) != original:
                raise RuntimeError("Duration mismatch changed accepted movie")
            report["checks"].append("duration mismatch rejected")
            studio.write_text(template.replace("</html>", '<script>window.renderAt = () => new Promise(() => {});</script></html>'))
            invoke(command + ["--overwrite", "--ready-timeout", "2000"], expected=1, evidence="renderAt(0) timed out")
            if digest(out) != original:
                raise RuntimeError("Render timeout changed accepted movie")
            report["checks"].append("unresolved render promise times out and preserves movie")
            studio.write_text(template)
            invoke(["python3", str(here / "verify-video.py"), str(out), "--frames", "999"], expected=1, evidence="frames: expected 999")
            report["checks"].append("wrong expected frame count rejected")
            invoke(command + ["--overwrite", "--width", "720", "--height", "1280"], expected=1,
                   evidence="Canvas intrinsic dimensions must match")
            report["checks"].append("wrong requested dimensions rejected")
            (root / "local-resource.js").write_text("window.localResourceLoaded = true;\n")
            studio.write_text(template.replace("</html>", '<script src="../local-resource.js"></script></html>'))
            invoke(command + ["--overwrite"], expected=1, evidence="local-resource.js")
            invoke(command + ["--overwrite", "--resource-root", str(root)])
            report["checks"].append("parent resource requires explicit resource root; declared root works")
            studio.write_text(template)
            silent = root / "silent.wav"
            with wave.open(str(silent), "wb") as wav:
                wav.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
                wav.writeframes(bytes(76800))
            silent_command = list(command)
            silent_command[silent_command.index("--audio") + 1] = str(silent)
            silent_command[silent_command.index("--out") + 1] = str(root / "silent.mp4")
            invoke(silent_command, expected=1, evidence="audio is silent")
            if (root / "silent.mp4").exists():
                raise RuntimeError("Failed silent-audio verification published movie")
            invoke(silent_command + ["--allow-silent-audio"])
            report["checks"].append("silent audio rejected by default; explicit permission works")
            if list(root.glob(".code-video-*")):
                raise RuntimeError("Owned temporary render directory left behind")
            report["checks"].append("owned render temporary directories cleaned")
            report["passed"] = True
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        report["errors"].append(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
