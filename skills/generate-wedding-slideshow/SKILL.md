---
name: generate-wedding-slideshow
description: Generate a reusable wedding slideshow project from a photo directory, a short title brief, and a natural-language playlist request. Use when Codex needs to scaffold a wedding big-screen slideshow plus a password-protected share page without hard-coded names, dates, or specific photos, especially when music should be downloaded via $go-music-dl.
---

# Generate Wedding Slideshow

## Overview

生成一个**独立项目目录**，默认包含：

- `wedding-starry.html` 大屏正片
- `share/` 带密码的分享版
- `photos-web/` 照片目录
- `music/` 音乐目录
- `data/project.json` 与 `data/playlist.json` 配置

不要改用户当前工程。始终输出到新的目标目录。

## Workflow

1. 收集最少输入
2. 生成独立项目目录
3. 整理照片
4. 处理歌单与下载音乐
5. 生成播放配置
6. 验证正片与分享版

## Step 1. 收集最少输入

默认只收这几项：

- 标题，例如“婚礼纪念”或“XX 与 XX”
- 副标题，可空
- 照片目录路径
- 输出目录路径
- 自然语言歌单描述，可空
- 分享密码，可空

如果用户没有给歌单描述，用 [references/default-playlist.md](references/default-playlist.md) 的推荐歌单。

如果用户没有给分享密码，生成一个 6 到 10 位数字密码。

## Step 2. 生成独立项目目录

运行：

```bash
python3 scripts/scaffold_project.py \
  --title "婚礼纪念" \
  --subtitle "Love, Joy, Celebration" \
  --photo-dir "/path/to/photos" \
  --output-dir "/path/to/output"
```

可选参数：

- `--share-password 123456`
- `--playlist-brief "偏甜暖、中文流行、适合婚礼现场"`
- `--theme starry`
- `--overwrite`

脚本会：

- 复制 `assets/project-template/` 到输出目录
- 拷贝照片到新项目的 `photos-web/`
- 生成 `data/project.json`
- 生成分享版配置
- 写入默认或占位歌单文件

## Step 3. 处理歌单与下载音乐

如果用户给的是自然语言歌单描述：

1. 先把描述整理成有顺序的歌曲列表
2. 使用 `$go-music-dl`
3. 把歌曲下载到新项目的 `music/` 目录

推荐提示方式：

```text
Use $go-music-dl to download these wedding tracks into <project>/music in this exact order: ...
```

不要把真实音频放进 skill 仓库。只下载到生成后的项目目录。

## Step 4. 生成播放配置

下载完音乐后，运行：

```bash
python3 scripts/sync_playlist.py \
  --music-dir "/path/to/output/music" \
  --output-file "/path/to/output/data/playlist.json"
```

如果已经有明确顺序文件，再加：

```bash
--order-file "/path/to/output/music/playlist-order.txt"
```

`playlist-order.txt` 一行一个歌名或文件名。脚本会尽量按名字匹配真实音频文件。

## Step 5. 验证

至少验证这几件事：

- `data/project.json` 中照片数量大于 0
- `data/playlist.json` 格式正确
- `wedding-starry.html` 能加载
- `share/server.js` 能启动

分享版启动方式：

```bash
cd /path/to/output/share
node server.js
```

## Theme Boundary

第一版只正式支持 `starry`。

保留扩展位，但不要把 skill 做成重系统：

- 不做主题管理后台
- 不做数据库
- 不做部署系统
- 不做多层抽象工厂

只保留足够清晰的模板边界，后续可以继续加：

- `themes/starry`
- `themes/minimal`
- `themes/future`

## Resources

### scripts/

- `scaffold_project.py`
  创建独立项目目录，复制模板并生成项目配置。
- `sync_playlist.py`
  根据音乐目录和可选顺序文件生成 `data/playlist.json`。

### references/

- `default-playlist.md`
  默认推荐歌单。
- `project-layout.md`
  生成项目的结构说明。

### assets/

- `project-template/`
  可直接复制的匿名婚礼模板，不包含真实姓名、日期、照片和音频。
