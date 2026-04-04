# my-skills

Bryant Yang 的 Claude Code skill 合集。

## 安装

```bash
git clone <repo-url> ~/.claude/skills
```

Skills 目录放在 `~/.claude/skills/` 下，Claude Code 会自动加载。

## Skills

### `generate-wedding-slideshow`

给一组照片和一段歌单描述，生成一套完整的婚礼展示项目。

**输出：**
- `wedding-starry.html` — 大屏正片（全屏轮播 + 背景音乐）
- `share/` — 带密码保护的网页分享版（Node.js 服务）
- `data/project.json` + `data/playlist.json` — 项目配置

**用法：**

直接告诉 Claude：
```
Use $generate-wedding-slideshow，照片在 /path/to/photos，输出到 /path/to/output，歌单偏甜暖中文流行
```

或手动运行脚本：
```bash
python3 skills/generate-wedding-slideshow/scripts/scaffold_project.py \
  --title "婚礼纪念" \
  --photo-dir /path/to/photos \
  --output-dir /path/to/output \
  --playlist-brief "偏甜暖，中文流行为主"
```

依赖：Python 3、Node.js

---

### `image`

用自然语言生成图片，内置 1050 条 prompt 参考库辅助构建高质量 prompt。

**用法：**

```
/image 画一只在雨中撑伞的猫，赛博朋克风格
```

**配置：**

复制并填写 API key：
```bash
cp skills/image/config.env.example skills/image/config.env
# 编辑 config.env，填入 GPTSAPI_KEY
```

支持模型：`gpt-image-1.5`（默认）、`gemini-2.5-flash-image-hd`

依赖：Python 3、curl
