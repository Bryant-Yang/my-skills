# 交互式课件生成器

将一个知识点或紧凑主题生成、修改或精简为可运行、可操作、可观察、可验证的自包含 HTML 课件。既支持单页模拟器，也支持同一目录中默认 2–4 个概念页与可选综合实验。

## 使用

```text
使用 $interactive-courseware-generator，
为初中生生成一页“光的折射”交互课件：
可以拖动入射角，观察入射线、法线、折射线和角度数值，
并比较空气到水和水到空气两种情况。
```

也可以只生成提示词：

```text
使用 $interactive-courseware-generator，
不要生成 HTML，只输出一套“二分查找”交互课件的完整提示词。
```

也可以生成紧凑课件组：

```text
使用 $interactive-courseware-generator，
做一套 MQTT 入门交互课件。用同一个设备消息案例讲清用途、Topic 路由和 QoS；
不要按术语过度拆页，命令和完整协议轨迹按需展开。
```

也可以从现有教案转译：

```text
使用 $interactive-courseware-generator，
我有一份初中物理《大气压强》教案，把它转成一页可操作的交互课件；
不要照搬教案排版，课堂提问改成先预测后揭示。
```

默认直接构建时交付：

```text
courseware/<slug>/<slug>.html
courseware/<slug>/<slug>.verification.md
```

紧凑课件组默认交付：

```text
courseware/<topic>/index.html
courseware/<topic>/01-<concept>.html
courseware/<topic>/01-<concept>.verification.md
courseware/<topic>/...
courseware/<topic>/README.md
```

需要讲解编排时，额外交付 `<slug>.actions.json`；宿主控制本身只启用 HTML 内的消息桥接。

## 方法核心

```text
教学目标
  → 判断单页或紧凑课件组
  → 用真实任务与贯穿案例确定最短学习路径
  → 知识点—变量—控件—现象—对比—结论映射
  → 自包含 HTML
  → courseware-config 与可选宿主桥接
  → 基于真实 DOM 的可选教学动作
  → 静态、浏览器与学科三层验证
```

## 认知与精确 3D

先从已有经验与具体场景建立因果模型，经示范、对比和抽象映射进入独立预测或迁移，反馈指出误解。空间结构、装配或运动需要精确 3D 时，使用 Blender `bpy` 建模，交付源脚本、参数、`.blend`、实际导出资源与几何/展示检查；页面仍默认自包含。

## 资源

- `SKILL.md`：触发、工作流、输出和完成标准。
- `references/generation-framework.md`：三层中文提示词框架与教案要素转译表。
- `references/subject-visualization.md`：按学科选择母语可视化与依据来源。
- `references/course-suite-framework.md`：紧凑课件组的页数、贯穿案例、四拍结构与目录合同。
- `references/cognitive-design.md`：认知路径、机制解释、理解检查和纠错。
- `references/blender-modeling.md`：精确 3D 路由、bpy 制作、几何验证和内嵌交付。
- `references/runtime-contract.md`：项目无关的运行和教学动作协议。
- `references/quality-gates.md`：验证合同。
- `references/pwm-example.md`：PWM worked example。
- `scripts/validate-courseware.js`：无第三方依赖的静态校验器。
- `evals/trigger_cases.json`：触发、排除和近邻案例。
- `evals/test-skill-contract.js`：紧凑课件组、四拍结构、真实用法和认知负担合同回归。
- `reports/output_quality_scorecard.md`：记录夹具的输出合同对比，不是模型执行证据。

## 验证器

在 skill 根目录运行：

```bash
node scripts/validate-courseware.js /absolute/path/to/courseware.html --json
```

验证器检查 HTML 结构、`courseware-config` schema、变量与 presets、Canvas/SVG、控件、通用消息标记和静态可识别的外部依赖。它不执行页面，因此视觉、运行行为和学科正确性仍需单独检查。

只有用户明确批准外部依赖时才追加 `--allow-external-dependencies`，并在验证报告中逐项列出依赖。
