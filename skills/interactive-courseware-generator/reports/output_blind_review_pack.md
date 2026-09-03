# Output Blind A/B Review Pack

This packet hides whether each variant came from the baseline or the skill-guided output. Use the separate answer key only after review.

- Pairs: `5`
- Seed: `yao-output-eval-blind-v1`
- Answer key separate: `True`

## Case: build-interactive-page

Prompt: 生成一页牛顿第二定律交互课件。

Rubric:
- `interaction-map` (1.0): Output uses the causal interaction map.
- `core-artifacts` (1.0): Output names HTML and verification artifacts.
- `runtime-contract` (1.0): Output includes the neutral runtime contract.
- `real-validation` (1.0): Output promises deterministic validation rather than self-check only.

### Variant A

先建立知识点→变量→控件→可观察现象→对比状态→因果结论映射，再交付 newton-second-law.html 和 newton-second-law.verification.md；HTML 内含 courseware-config、稳定 DOM ID 和 Canvas/SVG，能脱离宿主独立运行，并执行确定性验证。

### Variant B

生成一个带质量和力滑块的漂亮 HTML 页面。

## Case: prompt-only-mode

Prompt: 不要生成 HTML，只给我一份可以复用的折射模拟课件提示词。

Rubric:
- `prompt-artifact` (1.0): Output names the prompt artifact.
- `three-prompt-layers` (1.0): Output includes all prompt layers.
- `causal-map` (1.0): Output includes variable-to-phenomenon mapping.
- `honest-status` (1.0): Output does not pretend HTML was built.

### Variant A

你是一个前端开发者，请生成漂亮的折射模拟页面。

### Variant B

输出 refraction.prompt.md，包含单页教学规格、变量—现象映射、HTML system prompt、填充后的 user prompt 和教学动作 prompt；明确这是提示词交付，未生成或验证 HTML。

## Case: repair-existing-page

Prompt: 这个波动模拟 HTML 的暂停和重置有问题，请修好。

Rubric:
- `scope-control` (1.0): Output preserves existing courseware and limits change.
- `state-machine` (1.0): Output names the required state model and reset behavior.
- `regression` (1.0): Output plans relevant regression checks.
- `status-boundary` (1.0): Output preserves honest validation labels.

### Variant A

重写按钮点击函数并返回修改后的代码。

### Variant B

保留现有课件，只修复 running/paused/ended 状态机和 reset 全量恢复；随后重新检查每个变量、presets、控制台和移动视口。若原页面启用了 hostBridge，再回归四类 COURSEWARE_* 消息，并在 verification.md 中区分已通过、警告、未检查。

## Case: domain-correctness-boundary

Prompt: 做一个舵机 PWM 角度模拟页，保证绝对准确。

Rubric:
- `model-required` (1.0): Output asks for the actual servo signal model.
- `rejects-false-equivalence` (1.0): Output rejects naive duty-cycle mapping.
- `honest-domain-status` (1.0): Output discloses domain validation status.

### Variant A

可以，占空比直接映射为 0 到 180 度，我会生成绝对准确的模拟。

### Variant B

先确认采用的舵机脉宽、周期和角度模型；不能把一般占空比直接等同于角度。页面可先按明确的理想化模型生成，但在没有器件规格或来源复核时将学科正确性标为待复核，不声称绝对准确。

## Case: near-neighbor-static-deck

Prompt: 制作一套二十页静态 PPT，包含封面、目录和总结。

Rubric:
- `declines-route` (1.0): Output says the request is outside this skill.
- `states-boundary` (1.0): Output names the owned boundary.
- `routes-neighbor` (1.0): Output routes to presentation work.

### Variant A

我会使用交互式课件生成框架，把每页做成 HTML 模拟器。

### Variant B

这不是本 skill 的任务：它只负责一页交互式 HTML 课件。应改用演示文稿/PPT 制作能力，并保留封面、目录、内容页和总结的整套幻灯片结构。
