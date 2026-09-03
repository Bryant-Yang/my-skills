# 交互式课件生成器

将一个知识点生成或修改为一页可运行、可操作、可观察、可验证的自包含 HTML 课件。

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

默认直接构建时交付：

```text
courseware/<slug>/<slug>.html
courseware/<slug>/<slug>.verification.md
```

需要讲解编排或宿主控制时，额外交付 `<slug>.actions.json`。

## 方法核心

```text
教学目标
  → 知识点—变量—控件—现象—对比—结论映射
  → 自包含 HTML
  → courseware-config 与可选宿主桥接
  → 基于真实 DOM 的可选教学动作
  → 静态、浏览器与学科三层验证
```

## 资源

- `SKILL.md`：触发、工作流、输出和完成标准。
- `references/generation-framework.md`：三层中文提示词框架。
- `references/runtime-contract.md`：项目无关的运行和教学动作协议。
- `references/quality-gates.md`：验证合同。
- `references/pwm-example.md`：PWM worked example。
- `scripts/validate-courseware.js`：无第三方依赖的静态校验器。
- `evals/trigger_cases.json`：触发、排除和近邻案例。
- `reports/output_quality_scorecard.md`：记录夹具的输出合同对比，不是模型执行证据。

## 验证器

在 skill 根目录运行：

```bash
node scripts/validate-courseware.js /absolute/path/to/courseware.html --json
```

验证器检查 HTML 结构、`courseware-config`、变量、Canvas/SVG、控件、通用消息和远程依赖。它不执行页面，因此视觉、运行行为和学科正确性仍需单独检查。
