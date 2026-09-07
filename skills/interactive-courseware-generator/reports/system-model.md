# System Model

Skill: `interactive-courseware-generator`

- Evidence maturity: `provisional`
- Lifecycle band: `library`
- Doctrine: Structure drives behavior: improve the boundary, feedback loops, drift watch, and leverage points before adding weight.

## System Boundary Map

- Owned job: 把一个教学知识点或紧凑主题稳定转换为低干扰、贴近实际、可运行、可操作、可观察、可验证且可选支持宿主控制的交互式 HTML 课件。
- Output boundary: 单页自包含课件，或同一目录中默认 2–4 个概念页、可选综合实验、目录与逐页验证报告。
- Maturity assumption: `library`
- Input boundary:
  - 主题、学习目标、学习者、变量、现象、学科模型或现有 HTML。
- Non-goals:
  - 静态幻灯片、学期级课程大纲、普通网站、教学平台、只解释源码。
- Constraints:
  - 项目无关；不依赖特定产品、仓库或私有协议；每个交互页默认单文件、无远程依赖；真实验证与模型自检分开。
- Standards:
  - 页数按学习问题、因果模型、观察对象和先备关系共同确定；变量必须映射到可观察现象；默认界面按问题、主要操作、核心现象、结论组织；真实案例与最小用法进入主线；确定性逻辑由普通代码实现；学科不确定性必须披露。
- Human judgment boundary:
  - Infer non-core gaps visibly; ask one focused clarification only for an unresolved core job, primary output, or explicit direction conflict.
  - Escalate visible tradeoffs when benchmark patterns conflict with local privacy, naming, or governance constraints.
  - Do not silently broaden the skill into adjacent jobs just because the examples are nearby.

## Cognitive and Geometry Contract

- 教学路径由先备经验、关键误解和因果链导出，经具体机制示范、单条件对比与抽象映射进入独立预测/迁移；反馈指出错因，设计检查不等于学习效果证据。
- 精确 3D 使用 Blender bpy，保留参数/来源/单位/公差、blend 和导出资源，验证关键几何、运动关系与页面同步；工具失败不得以近似画面冒充。
- 详细规则见 references/cognitive-design.md 与 references/blender-modeling.md。

## Feedback Loops

### Intent boundary loop

- Signal: The intent, primary output, secondary outputs, and exclusions are explicitly recorded.
- Response: Ask only the highest-leverage clarification before adding package weight.
- Evidence: reports/intent-context.json and evals/trigger_cases.json

### Reference synthesis loop

- Signal: Reference patterns are useful only after they are reduced to project-independent design rules.
- Response: Borrow one pattern at a time and keep the rest as reviewer-visible evidence.
- Evidence: references/design-rationale.md and reports/artifact-design-profile.md
- Current patterns:
  - Borrow progressive disclosure: keep the entrypoint lean and move depth into references or scripts.
  - Borrow a small hypothesis-test-learn loop so the first revision is evidence-backed.
  - Borrow the habit of designing from the required hand-back output backwards.
  - Do not let packaging or platform concerns swallow the core job boundary.
  - Do not create experimental overhead that exceeds the skill's real risk tier.

### Output quality loop

- Signal: Recorded fixtures and predicted risk families identify candidate failure modes, not measured model behavior.
- Response: Apply predicted output-risk families as self-repair checks before final output.
- Evidence: reports/output-risk-profile.md and reports/output_quality_scorecard.md
- Current risk families:
  - Code and command safety
  - Tutorial quality
  - Markdown readability
  - Citation and footnote clutter
  - Screenshot and visual capture

### Reviewer feedback loop

- Signal: Human review is still needed to judge behavior that static checks miss.
- Response: Capture lightweight feedback and turn repeated findings into gates or references.
- Evidence: reports/output_blind_review_pack.md; reviewer decisions are pending

### Lifecycle loop

- Signal: As reuse grows, the skill needs stronger gates, ownership, and regression evidence.
- Response: Promote only when the next gate improves reliability more than context cost.
- Evidence: manifest.json and reports/validation.md

## Delay And Drift Watch

### Trigger drift

- Watch signal: Users start invoking the skill for adjacent one-off or explanation-only requests.
- Countermeasure: Add near-neighbor exclusions and route evals before expanding workflow steps.
- Cadence: per trigger or description change

### Output drift

- Watch signal: Outputs remain valid but become generic, cluttered, or weakly aligned with the user's domain.
- Countermeasure: Refresh output-risk and artifact-design profiles, then add one self-repair check.
- Cadence: after the first 3-5 real uses
- Risk families:
  - Code and command safety
  - Tutorial quality
  - Markdown readability
  - Citation and footnote clutter
  - Screenshot and visual capture

### Reference drift

- Watch signal: Borrowed benchmark patterns no longer fit the local job or add ceremony without payoff.
- Countermeasure: Re-run reference synthesis and keep only patterns that improve the current boundary.
- Cadence: per material benchmark or product assumption change

### Governance drift

- Watch signal: Skill usage becomes team-critical while ownership, review cadence, or rollback evidence stays informal.
- Countermeasure: Promote maturity tier and add reviewer-visible lifecycle evidence.
- Cadence: monthly

## Failure Pattern Map

### Boundary failure

- Symptom: The skill handles nearby requests that were never part of the recurring job.
- Repair: Narrow the description and add explicit non-goals before adding more execution steps.

### Feedback gap

- Symptom: The skill has rules but no signal telling authors which rule should change after use.
- Repair: Turn repeated reviewer feedback into one eval, one reference note, or one self-repair check.

### Output degradation

- Symptom: The result is structurally correct but generic, cluttered, or weakly matched to the user's domain.
- Repair: Use output-risk families as pre-final checks.
- Current Risk Families:
  - Code and command safety
  - Tutorial quality
  - Markdown readability
  - Citation and footnote clutter
  - Screenshot and visual capture
  - 术语驱动的过度拆页
  - 默认首屏信息过载
  - 缺少真实案例与可迁移用法

### Prompt-behavior mismatch

- Symptom: The role, task, and format are copied from a prompt instead of becoming stable skill behavior.
- Repair: Convert reusable role/task/format assumptions into workflow, reports, or references.

## Highest Leverage Moves

### 1. Tune the frontmatter description

- Why: The description is the highest-leverage routing surface.
- Move: Name the recurring job, expected input, output, and strongest non-goal in compact language.

### 2. Install output self-repair checks

- Why: The likely failure families are: Code and command safety, Tutorial quality, Markdown readability.
- Move: Add only the checks that prevent recurring output mistakes.

### 3. Borrow one pattern, not a whole product

- Why: External references improve quality when reduced to structure, not copied as surface style.
- Move: Start from: Borrow progressive disclosure: keep the entrypoint lean and move depth into references or scripts.

### 4. Close the lifecycle loop

- Why: Team-reused skills need visible ownership, review cadence, and regression evidence.
- Move: Keep manifest, validation evidence, and review artifacts aligned after each material change.

## Reviewer Use

- Reviewer should ask whether the skill's structure will keep producing the desired behavior after repeated real use.
- Prefer changing the system boundary, feedback loop, or leverage point before adding more prose.
- If a problem repeats, convert it into a named failure pattern and one regression check.
