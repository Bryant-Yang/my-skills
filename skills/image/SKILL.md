---
name: image
description: Use when the user wants to generate an image, draw something, create a picture, or asks for visual content. Triggers on /image or phrases like "帮我生成一张图", "画一个", "生成图片", "出一张图" etc.
---

# AI 生图 Skill

使用 gptsapi.net 生图，内置 1050 条高质量 prompt 素材库（来自 gpt4o-image-prompts 仓库），每次生图都从库中匹配参考。

## 执行流程（必须严格按顺序）

### 第一步：从素材库搜索参考 prompt
```bash
python3 ~/.claude/skills/image/search_prompts.py "用户描述的关键词" 3
```
- 分析搜索结果，找到与用户意图最接近的英文 prompt
- 如果库中有高度匹配的，以它为基础改写；如果匹配度低，仅借鉴其风格结构

### 第二步：构造最终 prompt
基于库中参考 + 用户具体要求，合成一个高质量英文 prompt，包含：
- **主体**：具体描述对象
- **风格**：photorealistic / cinematic / oil painting / watercolor / anime / concept art 等
- **光线**：golden hour / studio lighting / dramatic shadows / soft natural light 等
- **构图**：close-up / wide landscape / aerial view / bokeh background 等
- **质量词**：highly detailed, 8k resolution, masterpiece

### 第三步：生图
```bash
bash ~/.claude/skills/image/generate.sh "最终英文prompt"
# 指定模型：
bash ~/.claude/skills/image/generate.sh "prompt" "gemini-2.5-flash-image-hd"
```

### 第四步：展示
用 Read 工具读取返回的图片路径，展示图片，并告知用户：
- 参考了哪条库中的 prompt（标题）
- 最终使用的 prompt 是什么

## 可用模型

| 模型 | 特点 |
|------|------|
| `gpt-image-1.5`（默认） | 质量最高，写实风格强 |
| `gemini-2.5-flash-image-hd` | Google 出品，速度快 |

## 配置

API key 存放在 `~/.claude/skills/image/config.env`，格式：
```
GPTSAPI_KEY=your_api_key_here
GPTSAPI_BASE_URL=https://api.gptsapi.net/v1
GPTSAPI_DEFAULT_MODEL=gpt-image-1.5
```

## 注意事项

- 生图约需 10-30 秒，生成时告知用户正在处理
- 图片保存在 `/tmp/generated_image_*.png`
- **必须先搜索素材库再生图**，不能跳过第一步
