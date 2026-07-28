# LLM Wiki Skill

把零散资料整理成一套会持续积累的 Markdown 知识库。

它不是给文件套一层检索，也不是把聊天记录存起来。每次加入新资料时，Agent
会把内容编译进现有 wiki：补充概念和实体、更新已有结论、保留冲突、维护引用，
让下一次查询从已经整理好的知识出发。

设计源自 Andrej Karpathy 的
[LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
构想，并补上了长期使用需要的来源校验、写入边界、幂等日志和 schema 演进规则。

## 适合用来做什么

- 长期研究一个主题，持续加入论文、文章、访谈和笔记
- 维护个人知识库或 Obsidian vault
- 做竞品分析、尽调、课程笔记和专题阅读
- 让多个来源共同支持一个结论，同时保留分歧和不确定性
- 定期检查知识库中的内部坏链接、陈旧页面、孤立内容和本地来源漂移

一次性总结不需要它。只有当结果要进入一套长期维护的知识库时，这个 skill
才应该介入。

## 它怎么工作

每个知识库分成三层：

```text
<wiki-root>/
├── AGENTS.md          # Agent 入口
├── WIKI.md            # 机器可读的 schema 和维护规则
├── raw/               # 原始资料快照，只新增，不改写
└── wiki/              # Agent 编译和维护的知识页
    ├── index.md       # 内容索引
    ├── log.md         # 可解析、可重试的操作记录
    ├── sources/
    ├── entities/
    ├── concepts/
    ├── syntheses/
    ├── queries/
    └── meta/
```

`raw/` 是证据，`wiki/` 是当前理解，`WIKI.md` 决定两者如何连接。Markdown
始终是 source of truth；Obsidian、qmd 或向量索引都只是可选工具。

## 安装

需要 Python 3.11 或更高版本。仓库是私有的，因此还需要安装 GitHub CLI
并执行过 `gh auth login`，当前账号也必须有这个仓库的读取权限。

使用 GitHub CLI 克隆到个人 skill 目录：

```bash
gh repo clone Bryant-Yang/llm-wiki-skill "${HOME}/.agents/skills/llm-wiki"
```

如果你的 Agent 使用其他 skill 根目录，把仓库放到对应目录即可。新会话通常比
当前已经打开的会话更容易识别刚安装的 skill。

## 快速开始

初始化一个中文研究 wiki：

```bash
SKILL_DIR="${HOME}/.agents/skills/llm-wiki"

python3 "$SKILL_DIR/scripts/wiki_tool.py" init /path/to/my-wiki \
  --title "Agent 工程知识库" \
  --domain "Agent 架构、评测与运行时治理" \
  --language zh
```

随后可以直接对 Agent 说：

```text
把这篇论文加入 /path/to/my-wiki，保留原文，更新受影响的概念页。

基于 /path/to/my-wiki 回答：Atlas 的通过率是多少？如果来源有冲突，不要替我裁决。

检查 /path/to/my-wiki 的健康状态，只报告问题，先不要改文件。

以后所有评测结论都必须注明数据集版本，把这条规则加入 wiki schema。
```

手动运行结构检查：

```bash
python3 "$SKILL_DIR/scripts/wiki_tool.py" lint /path/to/my-wiki
python3 "$SKILL_DIR/scripts/wiki_tool.py" lint /path/to/my-wiki --json
```

## 核心行为

### Ingest

每份资料先保存为新的 raw 快照，再由唯一的 source page 登记路径和 SHA-256。
Agent 会先搜索现有页面，再决定新建、更新、标记争议，或记录为
`no-material`。同一来源的重试不会重复写日志。

### Query

普通查询只读。Agent 先读索引，再搜索相关页面和别名，回答时区分已确认事实、
当前综合、争议结论和知识空白。只有明确要求“保存进知识库”时，查询结果才会
变成新页面。

### Lint

确定性工具检查页面合同、索引覆盖、内部 wiki/本地 Markdown 链接、source
注册、raw 哈希、日志状态机、别名冲突和高信号数字或日期漂移。HTTP 链接可用性
不在当前检查范围内。语义是否真的被来源支持，仍需要 Agent 或人进行审阅；
结构检查不会冒充事实判断。

### Evolve

长期规则写在 `WIKI.md`。单次异常先进入 schema proposal；同类问题重复出现，
或者用户明确批准后，才执行迁移。结构演进必须说明影响范围、验证方法和回滚
路径，并通过负向探针证明新规则确实能拦住目标问题。

这里的“持续进化”是可追踪的治理流程，不代表有后台任务正在自行修改知识库。
真要自动运行，还需要额外配置 scheduler、状态、锁、通知和取消机制。

## 安全边界

- 原始资料默认只保存在本地，不会由这个 skill 自动上传
- 已登记的 raw 文件通过哈希检测改动，但不会被操作系统强制设为只读
- source 内容一律按不可信数据处理，资料中的指令不会自动执行
- 写入前必须解析出唯一 wiki root，不使用“最近打开的 wiki”之类的全局指针
- 每个 wiki 同一时间只允许一个 writer；并行工作应拆分分支或页面所有权
- Git 提交、推送、同步和公开发布都需要用户明确授权

## 仓库结构

```text
.
├── SKILL.md
├── README.md
├── assets/templates/
├── references/
│   ├── architecture.md
│   ├── workflows.md
│   ├── evolution.md
│   └── design-basis.md
├── scripts/
│   ├── wiki_tool.py
│   └── tests/
└── evals/evals.json
```

详细页面合同见
[`references/architecture.md`](references/architecture.md)，操作流程见
[`references/workflows.md`](references/workflows.md)，schema 演进规则见
[`references/evolution.md`](references/evolution.md)。

## 开发与验证

运行内置测试：

```bash
python3 -m unittest discover -s scripts/tests -v
```

检查一个实际 wiki：

```bash
python3 scripts/wiki_tool.py lint /path/to/my-wiki --json
```

实现仅依赖 Python 标准库。Obsidian 和 git 都是可选项。

## 设计参考

- [Andrej Karpathy: LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- [Astro-Han/karpathy-llm-wiki](https://github.com/Astro-Han/karpathy-llm-wiki)
- [Ar9av/obsidian-wiki](https://github.com/Ar9av/obsidian-wiki)
- [Hermes Agent llm-wiki](https://github.com/NousResearch/hermes-agent/tree/main/skills/research/llm-wiki)

更完整的设计来源和取舍记录在
[`references/design-basis.md`](references/design-basis.md)。
