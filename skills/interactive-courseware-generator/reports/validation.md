# 2026-09-11 v1.3.0 演进验证

本次新增教案转译输入路径、学科可视化语言参考、密度与学段门禁，并同步触发面、IR、adapter 与元数据。没有生成完整新课件，也没有改动旧 fixture 的评分来代表新增能力。

## 变更范围

- `references/subject-visualization.md`（新增）：按学科选择母语可视化、母语挂接变量—现象映射、学科依据来源与不臆造条目编号规则。
- `references/generation-framework.md`：新增输入形态判断（主题/教案/现有课件）与教案要素转译表；规划入口挂接学科可视化语言。
- `references/cognitive-design.md`：学段决定密度与抽象度。
- `references/quality-gates.md`：学科母语与来源门禁、去标题密度测试；验证报告模板同步。
- `SKILL.md`：触发描述加入教案转译；资源路由、工作流第 1 步、硬规则、完成标准与回归任务类型同步。
- 触发面：`evals/trigger_cases.json` 新增教案转译样本，`reports/skill-ir.json` 严格镜像并登记新参考。
- `evals/test-skill-contract.js`：新增教案转译、学科母语、密度测试与来源门禁断言；版本断言升至 1.3.0。
- `agents/interface.yaml`、`agents/openai.yaml`、`manifest.json`、`README.md`、`reports/intent-context.json`、`reports/system-model.md`、`evals/semantic_config.json` 同步。

## 已执行

- `test-skill-contract.js`、`test-validator.js`：通过。
- `skill-ir.json`、`trigger_cases.json`、`manifest.json`、`intent-context.json`、`semantic_config.json` JSON 解析：通过。
- SKILL.md 本地引用完整性由合同回归覆盖：通过。

## 证据边界

- 教案要素转译表与学科母语表是设计规则与评审判据，来自公开教学设计方法论的转写；本次未执行模型端到端教案转译或学科课件生成，不能称为行为回归通过。
- 新增触发样本未运行 provider-backed 路由评测，不报告 precision 或 recall。
- 未做实际学习者实验；学段密度规则是设计约定，不是学习效果证据。
- 学科可视化语言不包含任何课程标准原文；引用课标原文的需求仍要求使用时核对权威来源。

---

# 2026-09-07 v1.2.0 增强验证

本次修改认知教学路径、精确 3D 制作合同、提示词、验收规则和相关元数据。没有生成完整新课件，也没有改动旧 fixture 的评分来代表新增能力。

## 已执行

- `test-skill-contract.js`、`test-validator.js`、Skill Creator `quick_validate.py`：通过。
- JSON/YAML 解析、Markdown 本地引用、临时归档完整性、`audit-public.sh` 和 `git diff --check`：通过。
- 本机 Blender `5.2.1 LTS`，通过后台 Python 实际执行参数建模、尺寸断言、保存 `.blend`、导出 GLB、清空场景、重新导入及尺寸/对象名复核。
- 测试尺寸：120 × 40 × 20 mm；公差：`1e-6 m`；导出后最大尺寸误差：`2.682209010451686e-9 m`；对象名保留。此基础案例是长方体，不验证任意装配、运动约束或物理机制。
- Blender 命令参数经本机 `--help` 核对。IES/WWC 学习指导页面已读取，教学设计参考链接保存在 `references/cognitive-design.md`。Blender 在线文档本次返回 HTTP 403，相关执行行为以本机实测为据，不声称在线文档核对通过。

## 新增能力的证据边界

- `evals/teaching-spatial-cases.md` 提供七个行为评审场景与失败判据，尚未执行独立模型端到端生成，不能称为七个通过的行为回归。
- 本次未进行完整 3D 课件的浏览器、移动端、动画或视觉检查；未做实际学习者实验，不能宣称学习效果已有实测提升。
- 已将对应检查加入课件交付门禁；静态结构检查不能证明几何或教学正确。

## Blender 基础链路复现

在仓库根目录运行，下列输出目录必须尚不存在（防止覆盖现有文件）：

```bash
blender --background --factory-startup --python-exit-code 1 \
  --python skills/interactive-courseware-generator/evals/blender-roundtrip-smoke.py \
  -- --output-dir /tmp/courseware-bpy-roundtrip-new
```

成功时生成 `model.blend`、`model.glb` 与 `result.json`。脚本会改动其运行进程中的场景，应按上述命令在独立后台进程运行，不在用户打开的工程中执行。

---

# 2026-09-03 历史验证记录

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
