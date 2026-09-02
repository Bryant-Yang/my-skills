# 万维钢·现代思维工具100讲 Skill

这是一个面向复杂分析与决策的 Agent Skill。它先建立最小问题模型，再从一百个思维工具中选择一个主工具和至多三个补充或反证工具，交付结论、机制、权衡、行动和更新条件。

## 适合处理

- 局面分析、重要选择、概率预测与风险评估
- 学习设计、职业与商业战略
- 合作、制度、组织与领导问题
- 复杂系统干预，以及身份、价值和人生方向反思

简单事实、翻译、摘要、格式转换、机械执行和未请求分析的情绪支持不应触发本 Skill。

## 使用

把 `skills/wan-weigang-modern-thinking-tools-100/` 复制或链接到所用 Agent 的 Skill 目录，然后直接描述问题：

```text
Use $wan-weigang-modern-thinking-tools-100，帮我判断现在该留在大公司，还是加入这家早期创业公司。
```

也可以点名工具：

```text
用非遍历性和凯利公式检查这个投资计划，但不要替我做财务决定。
```

## 包结构

- `SKILL.md`：触发边界、核心流程、证据与安全契约
- `references/catalog-index.md`：十个板块的快速路由
- `references/01-*.md` 至 `10-*.md`：按需加载的一百个工具正文
- `references/operating-guide.md`：组合、运行卡、证据和失败恢复
- `scripts/validate_catalog.py`：校验工具总数、条目结构和引用完整性
- `evals/`：触发边界和输出契约的回归用例
- `reports/`：验证与质量证据

## 来源与边界

本包由 Bryant Yang 根据用户提供的《万维钢·现代思维工具100讲》材料整理为 Agent Skill，不是万维钢官方发布物。原始材料的许可状态未在本仓库中得到独立确认；公开再分发前应由仓库所有者确认相应权利。详见 `references/provenance.md`。

## 维护验证

```bash
python3 scripts/validate_catalog.py

python3 /path/to/yao-meta-skill/scripts/trigger_eval.py \
  --description-file evals/description.txt \
  --baseline-description-file evals/baseline_description.txt \
  --cases evals/trigger_cases.json \
  --semantic-config evals/semantic_config.json
```

输出评测是提交到仓库的 `recorded_fixture`，用于验证断言、边界和报告链路，不应声称为 provider-backed 模型运行证据。人工盲审结果在 reviewer 真正提交选择前保持 pending。
