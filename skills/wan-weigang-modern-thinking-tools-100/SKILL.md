---
name: wan-weigang-modern-thinking-tools-100
description: Use when a user wants structured help with a non-trivial situation analysis, consequential decision, risk forecast, learning design, career or business strategy, cooperation or organization issue, complex-system intervention, or values reflection by selecting and applying the smallest useful subset of 万维钢《现代思维工具100讲》. Also trigger when the user names 万维钢、现代思维工具100讲, or a catalog tool. Do not trigger for simple facts, translation, summarization, formatting, mechanical execution, therapy, or emotional support without requested analysis.
metadata:
  version: "0.1.0"
  author: "Bryant Yang"
  source_attribution: "基于用户提供的《万维钢·现代思维工具100讲》材料整理"
  compatibility: "Agent Skills compatible; rg is optional for named-tool lookup"
---

# 万维钢·现代思维工具100讲

把一百个概念当作可运行的心智程序，而不是知识展览。目标是改变问题表示、判断标准或行动方案，并把决定权留给用户。

## 核心契约

- 每次只选 **1 个主工具**；最多增加 **3 个**补充、定界或反证工具。
- 工具必须实际改变分析；删掉后结论不变的概念不要写进答案。
- 当前事实、专业数据、用户目标和硬约束高于任何课程框架。
- 只有缺失信息足以翻转建议时才追问；否则写明假设并继续。
- 重要且可逆的决定优先小试；难逆、高损失或涉及他人权利时提高证据门槛。

## 路由与按需读取

1. 先建立最小问题地图：目标、价值前提、硬约束、时间尺度、状态与反馈、关键未知、失败方式。
2. 阅读 [references/catalog-index.md](references/catalog-index.md)，选择最相关板块。
3. 只读取被选中的板块文件。若点名具体工具，用 `rg -n '^### .*<工具名>' references/` 定位，再读取该条完整内容。
4. 跨板块、工具冲突或高风险判断时，再阅读 [references/operating-guide.md](references/operating-guide.md) 的组合、证据与安全协议。
5. 来源与改编边界见 [references/provenance.md](references/provenance.md)。不要把本 Skill 描述成万维钢官方发布物。

## 执行流程

1. **重述问题**：明确真正要决定的事项、约束、尺度和关键未知。
2. **先给结论**：直接回答怎么办或怎么看，不用理论拖延。
3. **选择工具**：说明主工具为什么适用；补充工具各承担一种不同角色。
4. **运行机制**：具体化变量、因果链、分布、反馈、激励或状态转移。能量化就给范围与假设，不能量化就说明方向与不确定性。
5. **生成选项**：保留基准方案，说明为何不选其他方案，并设计可逆试验或退出条件。
6. **压力测试**：检查基准率、缺失样本、尾部风险、代理指标、二阶反应和最强反例。
7. **落实行动**：给出下一步、观察指标、复盘时点，以及维持、修正或推翻判断的证据。

## 证据与安全边界

- 明确区分 **事实、推断、情景假设、价值判断、未知**；思维工具决定怎样看，证据决定事实上是什么。
- 医疗、法律、财务、安全等高风险任务必须核验当前规则或寻求合格专业意见；本 Skill 只改善问题结构。
- 不替用户规定人生目标，不把效率、财富、声望或能力自动升级为终极价值。
- 不使用叙事、身份、地位、激励或领导力工具实施欺骗、操控、羞辱、强迫或剥削。
- 用户只需要倾听或表达时，先回应人；未经邀请不要用框架压过体验。

## 默认输出

1. **结论**：一句可执行判断。
2. **问题模型**：目标、约束、尺度、关键未知。
3. **所用工具**：一个主工具，至多三个补充或反证工具及其角色。
4. **分析**：机制、证据、权衡、风险、替代解释。
5. **行动**：现在做什么、暂不做什么、如何小试或止损。
6. **更新条件**：什么证据出现时加码、转向或停止。

完成前确认：主工具确实改变判断；答案包含行动与更新证据；用户能动性得到尊重。若工具没有增加解释力，撤回到朴素答案并停止叠加概念。

维护目录、触发边界或输出契约时，运行 `scripts/validate_catalog.py`，并按 `evals/trigger_cases.json` 与 `evals/output/cases.jsonl` 做回归；普通使用不需要执行这些维护检查。
