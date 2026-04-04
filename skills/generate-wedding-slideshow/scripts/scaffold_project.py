#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import secrets
import shutil
from pathlib import Path

SUPPORTED_PHOTOS = {".jpg", ".jpeg", ".png", ".webp"}
DEFAULT_PLAYLIST = [
    "园游会",
    "今天你要嫁给我",
    "暖暖",
    "我们俩",
    "遇到",
    "这样就很好",
    "陪你度过漫长岁月",
    "给你给我",
    "Love Paradise",
    "My Only",
    "婚礼进行曲",
    "Panorama",
    "One Call Away",
    "爱的飞行日记",
    "慢慢喜欢你",
    "爱上了",
    "这就是爱情",
    "最好的都给你",
    "甜甜的",
]

CAPTION_POOL = [
    "目光所及 皆是温柔",
    "把喜欢写进每一帧光影",
    "从此欢喜有了回声",
    "把此刻留给往后回看",
    "愿爱与热望都不被辜负",
    "这一程 山海与星光同在",
    "故事继续 甜意不散",
    "今天适合把幸福放大",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scaffold a reusable wedding slideshow project.")
    parser.add_argument("--title", required=True, help="Project title shown on the opening page.")
    parser.add_argument("--subtitle", default="Love, Joy, Celebration", help="Opening page subtitle.")
    parser.add_argument("--photo-dir", required=True, help="Source photo directory.")
    parser.add_argument("--output-dir", required=True, help="Output project directory.")
    parser.add_argument("--share-password", help="Optional password for the share server.")
    parser.add_argument("--playlist-brief", help="Optional natural-language playlist brief.")
    parser.add_argument("--theme", default="starry", choices=["starry"], help="Theme name.")
    parser.add_argument("--overwrite", action="store_true", help="Allow writing into an existing directory.")
    return parser.parse_args()


def project_template_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "assets" / "project-template"


def collect_photos(photo_dir: Path) -> list[Path]:
    files = [
        path
        for path in sorted(photo_dir.rglob("*"))
        if path.is_file() and not path.name.startswith(".") and path.suffix.lower() in SUPPORTED_PHOTOS
    ]
    if not files:
        raise SystemExit(f"未在 {photo_dir} 中找到可用照片。")
    return files


def ensure_output_dir(output_dir: Path, overwrite: bool) -> None:
    if output_dir.exists() and any(output_dir.iterdir()) and not overwrite:
        raise SystemExit(f"输出目录 {output_dir} 已存在且非空，请使用 --overwrite 或换一个目录。")
    output_dir.mkdir(parents=True, exist_ok=True)


def copy_template(output_dir: Path) -> None:
    shutil.copytree(project_template_dir(), output_dir, dirs_exist_ok=True)


def copy_photos(photos: list[Path], output_photo_dir: Path) -> list[str]:
    output_photo_dir.mkdir(parents=True, exist_ok=True)
    used_names: set[str] = set()
    copied: list[str] = []

    for idx, source in enumerate(photos, start=1):
        target_name = source.name
        if target_name in used_names:
            target_name = f"{idx:03d}-{target_name}"
        used_names.add(target_name)
        shutil.copy2(source, output_photo_dir / target_name)
        copied.append(target_name)

    return copied


def build_project_data(args: argparse.Namespace, photo_names: list[str]) -> dict:
    return {
        "title": args.title,
        "subtitle": args.subtitle,
        "theme": args.theme,
        "opening": {
            "title": args.title,
            "subtitle": args.subtitle,
        },
        "closing": {
            "title": "谢谢见证",
            "subtitle": "愿爱与喜悦长久停留",
        },
        "timing": {
            "openingMs": 3600,
            "photoMs": 4800,
            "closingMs": 3600,
        },
        "captionPool": CAPTION_POOL,
        "photos": [f"photos-web/{name}" for name in photo_names],
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_share_config(password: str) -> dict:
    return {
        "host": "127.0.0.1",
        "port": 3017,
        "password": password,
        "cookieSecret": secrets.token_urlsafe(32),
    }


def create_music_placeholders(output_dir: Path, playlist_brief: str | None) -> None:
    music_dir = output_dir / "music"
    music_dir.mkdir(parents=True, exist_ok=True)

    brief = playlist_brief.strip() if playlist_brief else ""
    if brief:
        write_text(music_dir / "playlist-brief.txt", brief + "\n")
        order_text = "# 按下载后的真实文件名或歌名，每行一首\n"
    else:
        write_text(
            music_dir / "playlist-brief.txt",
            "未提供自然语言歌单描述，建议使用默认推荐歌单。\n",
        )
        order_text = "\n".join(DEFAULT_PLAYLIST) + "\n"

    write_text(music_dir / "playlist-order.txt", order_text)


def create_project_readme(output_dir: Path, title: str, share_password: str) -> None:
    content = f"""# {title}

这是由 `generate-wedding-slideshow` skill 生成的婚礼项目。

## 内容

- `wedding-starry.html`
  大屏正片
- `share/`
  分享版服务
- `photos-web/`
  照片目录
- `music/`
  音乐目录

## 下一步

1. 把需要的音乐下载到 `music/`
2. 运行 `sync_playlist.py` 生成 `data/playlist.json`
3. 打开 `wedding-starry.html` 预览大屏正片
4. 运行分享版：

```bash
cd share
node server.js
```

分享密码默认是：`{share_password}`
"""
    write_text(output_dir / "README.md", content)


def main() -> None:
    args = parse_args()
    photo_dir = Path(args.photo_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()

    if not photo_dir.is_dir():
        raise SystemExit(f"照片目录不存在：{photo_dir}")

    ensure_output_dir(output_dir, args.overwrite)
    copy_template(output_dir)

    photos = collect_photos(photo_dir)
    copied_names = copy_photos(photos, output_dir / "photos-web")

    password = args.share_password or "".join(secrets.choice("0123456789") for _ in range(8))
    write_json(output_dir / "data" / "project.json", build_project_data(args, copied_names))
    write_json(output_dir / "data" / "playlist.json", {"tracks": []})
    write_json(output_dir / "share" / "share-config.json", build_share_config(password))
    create_music_placeholders(output_dir, args.playlist_brief)
    create_project_readme(output_dir, args.title, password)

    print(f"已生成项目：{output_dir}")
    print(f"照片数量：{len(copied_names)}")
    print(f"分享密码：{password}")


if __name__ == "__main__":
    main()
