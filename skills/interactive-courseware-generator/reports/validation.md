# 验证记录

日期：`2026-09-03`

## 已通过

- 项目无关性扫描：Skill 源码、参考、评测和保留报告中不存在特定产品名、旧配置字段、旧动作名或机器私有路径。
- HTML 校验器：合法夹具 `22` 项通过、`0` error、`0` warning；错误夹具被拦截出 `5` 个 error。
- 触发评测：`5` 个应触发、`5` 个不应触发、`5` 个近邻案例全部通过；precision=`1.0`，recall=`1.0`。
- 输出评测：`5` 个 `recorded_fixture` 案例，包含 `1` 个 `file-backed fixture`、`1` 个 near-neighbor 和 `1` 个学科边界案例；with-skill 断言通过率 `100%`，baseline `0%`，delta=`+100`，无回归；生成 `5` 组盲审材料。
- Meta Skill 验证：validate、lint、governance 和 resource boundary 全部通过；治理分 `90/100`；初始加载估算 `749/1300` tokens。
- Skill IR 编译：OpenAI、Claude、generic、Agent Skills compatible 和 VS Code 五个目标全部通过，无 warning 或 failure。
- 运行时一致性：五个目标全部通过。
- 信任检查：扫描未发现凭据或远程依赖。唯一 warning 是未发现依赖锁文件；校验器只使用 Node.js 内置模块，没有第三方依赖需要锁定。
- 打包验证：OpenAI、Claude、generic、VS Code 四种包生成成功；压缩包共 `55` 个条目，无嵌套 Skill，归档验证通过。未提供 registry audit，因此 metadata parity 保持 warning。

## 证据边界与剩余风险

- 输出评测使用预先记录的 `recorded_fixture`，不是 provider-backed 模型运行证据。
- 盲审包已经生成，但没有伪造 reviewer 选择；人工裁决保持 pending。
- 尚未对模型实时生成的课件执行浏览器视觉回归和学科专家复核。
- 元 Skill 的 trust 脚本会扫描 JavaScript 文本和 secret，但当前脚本能力清单只枚举 Python；因此 `validate-courseware.js` 的行为另由源码审查和 Node.js 实测覆盖。
- 安装模拟器要求非空权限审批表，因本 Skill 没有网络、外部写入、subprocess 或交互权限而未伪造审批；该模拟门禁保持未通过，不影响仓库源码使用。
- 临时打包与安装模拟产物已移出工作树，可在系统废纸篓中恢复。

## 复现命令

在仓库根目录运行：

```bash
node skills/interactive-courseware-generator/scripts/validate-courseware.js \
  skills/interactive-courseware-generator/evals/fixtures/minimal-valid-courseware.html --json

node skills/interactive-courseware-generator/scripts/validate-courseware.js \
  skills/interactive-courseware-generator/evals/fixtures/invalid-courseware.html --json

scripts/audit-public.sh
```

第二条命令预期以退出码 `1` 拒绝错误夹具。
