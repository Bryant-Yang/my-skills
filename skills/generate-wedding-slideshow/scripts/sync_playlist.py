#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SUPPORTED_AUDIO = {".mp3", ".m4a", ".aac", ".wav", ".flac"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create playlist.json from a music directory.")
    parser.add_argument("--music-dir", required=True, help="Music directory inside the generated project.")
    parser.add_argument("--output-file", required=True, help="Output playlist.json file.")
    parser.add_argument("--order-file", help="Optional ordered song list or filename list.")
    return parser.parse_args()


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", text.lower())


def list_tracks(music_dir: Path) -> dict[str, Path]:
    tracks = {}
    for path in sorted(music_dir.iterdir()):
        if path.is_file() and path.suffix.lower() in SUPPORTED_AUDIO:
            tracks[path.name] = path
    if not tracks:
        raise SystemExit(f"未在 {music_dir} 中找到音频文件。")
    return tracks


def build_order(tracks: dict[str, Path], order_file: Path | None) -> list[Path]:
    track_list = list(tracks.values())
    if not order_file or not order_file.exists():
        return track_list

    by_name = {path.name: path for path in track_list}
    by_stem = {normalize(path.stem): path for path in track_list}
    ordered: list[Path] = []
    used: set[Path] = set()

    lines = [
        line.strip()
        for line in order_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    for line in lines:
        if line in by_name:
            match = by_name[line]
        else:
            token = normalize(Path(line).stem)
            match = by_stem.get(token)
            if match is None:
                match = next((path for path in track_list if token and token in normalize(path.stem)), None)
        if match and match not in used:
            ordered.append(match)
            used.add(match)

    for path in track_list:
        if path not in used:
            ordered.append(path)

    return ordered


def main() -> None:
    args = parse_args()
    music_dir = Path(args.music_dir).expanduser().resolve()
    output_file = Path(args.output_file).expanduser().resolve()
    order_file = Path(args.order_file).expanduser().resolve() if args.order_file else None

    if not music_dir.is_dir():
        raise SystemExit(f"音乐目录不存在：{music_dir}")

    tracks = list_tracks(music_dir)
    ordered = build_order(tracks, order_file)
    payload = {
        "tracks": [f"music/{path.name}" for path in ordered],
    }
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已写入歌单：{output_file}")
    print(f"歌曲数量：{len(ordered)}")


if __name__ == "__main__":
    main()
