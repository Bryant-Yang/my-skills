# 验证记录

日期：`2026-09-03`

## 已通过的可复现检查

- HTML 校验器语法检查通过。
- 两组合规夹具（数值变量、枚举变量）均以退出码 `0` 通过，结果为 `0 error / 0 warning`；外部依赖夹具只有在显式传入批准参数后才转为带警告的通过。
- 四组负向夹具均以退出码 `1` 被拒绝，且错误代码与预期完全一致：缺少页面合同 `5` 项、非对象配置 `1` 项、非法 schema `10` 项、外部依赖 `1` 项。
- Skill Creator quick validation 通过；临时 `.skill` 包生成成功且压缩归档完整性检查通过。
- 所有 JSON、YAML 均可解析；仓库 `scripts/audit-public.sh` 通过，未发现凭据、机器私有路径、符号链接或本地产物。
- 通用与 OpenAI adapter 的默认提示词均保持教学动作按需生成；manifest 已登记实际存在的 `agents` 组件。
- 紧凑课件组合同回归通过：覆盖页数预算、禁止按术语拆页、四拍信息层级、真实用法、渐进披露与认知负担门禁。

## 现有评测证据边界

- `evals/trigger_cases.json` 是 `20` 条带标签的触发、排除和近邻样本集，新增紧凑协议课件组与“降低干扰”场景；本仓库没有保存 provider-backed 路由运行，因此不报告 precision 或 recall。
- `evals/output/cases.jsonl` 是 `5` 组人工记录的 fixture。`reports/output_quality_scorecard.*` 的 `100% / 0%` 只表示这些固定文本通过必含字串断言，不是模型实际运行结果，也不是 release gate。
- 盲审材料已生成，但没有 reviewer 选择；人工裁决保持 pending。
- 已使用真实 MQTT 课件完成一次定性迭代：从单页过载到同目录紧凑课件组，并在 1440×900、768×1024、390×844 检查主操作、渐进展开、导航和横向溢出。该案例用于提炼通用规则，不作为 provider-backed 模型基准或学科专家复核。
- 静态校验器只验证可确定的结构、schema、处理器标记和静态可识别的外部引用；消息语义、动态拼接的网络地址、选择器可见性与状态同步仍需浏览器检查。

## 复现命令

在仓库根目录运行：

```bash
node --check skills/interactive-courseware-generator/scripts/validate-courseware.js

node skills/interactive-courseware-generator/evals/test-validator.js

node skills/interactive-courseware-generator/evals/test-skill-contract.js

scripts/audit-public.sh
```

回归脚本逐项断言两组正向夹具的零错误、零警告，以及四组负向夹具的退出码和完整错误代码集合。

Skill Creator 检查需要先把 `<skill-creator-dir>` 和 `<skill-dir>` 替换为实际绝对路径：

```bash
uv run --with pyyaml python \
  <skill-creator-dir>/scripts/quick_validate.py <skill-dir>

package_dir="$(mktemp -d /tmp/courseware-skill-package.XXXXXX)"
(
  cd <skill-creator-dir>
  uv run --with pyyaml python -m scripts.package_skill \
    <skill-dir> "$package_dir"
)
unzip -t "$package_dir/interactive-courseware-generator.skill"
```

打包产物只用于归档完整性检查，不是仓库交付物。
