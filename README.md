# my-skills

Bryant Yang 的可复用 AI coding agent Skill 合集。

## 安装

```bash
git clone <repo-url> ~/.claude/skills
```

仓库中的每个 Skill 位于 `skills/<name>/`。按所用 agent 的 Skill 目录约定，
复制或链接需要的子目录；不要把整个仓库根目录直接当成单个 Skill。

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

---

### `kimi-acp-communication`

通过 Kimi Code 的 ACP 协议安全地列出、恢复和调用 Kimi session。支持流式回复、
权限默认拒绝、显式修改授权和 ACP 子进程回收，并明确区分“agent 收到消息”和
“已经打开的原生 Kimi TUI 实时刷新”。

入口：`skills/kimi-acp-communication/SKILL.md`

依赖：Python 3.11+、支持 `kimi acp` 的 Kimi Code CLI

---

### `llm-wiki`

为代码库建立和持续维护面向 agent 的结构化 Wiki，包含初始化、索引、演进日志、
校验和查询工作流。

入口：`skills/llm-wiki/SKILL.md`

依赖：Python 3.11+

---

### `wan-weigang-modern-thinking-tools-100`

面向复杂分析与决策的思维工具路由器。先建立问题模型，再从一百个工具中选择一个
主工具和至多三个补充或反证工具，交付结论、机制、行动与更新条件。工具正文按十个
板块延迟加载，并包含触发、输出、目录完整性和跨平台回归证据。

入口：`skills/wan-weigang-modern-thinking-tools-100/SKILL.md`

依赖：Python 3.11+（仅维护校验脚本；普通使用无运行时依赖）

---

### `interactive-courseware-generator`

把单个知识点生成或修复为一页自包含、可操作、可观察、可验证的交互式 HTML
课件。先建立“知识点—变量—控件—现象—对比—结论”映射，再生成页面、可选
教学动作和诚实标注检查边界的验证报告。

入口：`skills/interactive-courseware-generator/SKILL.md`

依赖：Node.js 18+（仅用于确定性 HTML 校验器；生成页本身无第三方运行时依赖）

## 从本机 Skill 源同步

仓库只同步白名单中的真实 Skill，不同步嵌套 Git 元数据、缓存或评测工作区：

```bash
scripts/sync-local-skills.sh /path/to/local/myskills
scripts/audit-public.sh
```

当前白名单：

- `kimi-acp-communication`
- `llm-wiki`

`llm-wiki-workspace`、`.git`、`__pycache__`、`.ruff_cache`、日志和字节码不会进入
仓库。`audit-public.sh` 会在发布前检查常见凭据、私钥、机器私有路径、具体
session ID、符号链接和运行产物。
