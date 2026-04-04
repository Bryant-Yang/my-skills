# My Skills

一组可复用的个人 Codex skills。

这个仓库只放通用 skill、模板、脚本和匿名示例，不放真实照片、真实姓名、真实日期、私有音频或客户数据。

## Repository Layout

- `skills/`
  每个 skill 的完整实现目录，包含 `SKILL.md`、脚本、参考资料和模板资源。
- `examples/`
  每个 skill 的匿名输入示例或 brief。
- `docs/`
  仓库级说明、边界说明和后续迭代记录。

## Included Skills

### `generate-wedding-slideshow`

从一组照片、一个简短标题和一份自然语言歌单描述，生成一套独立的婚礼播放项目。

输出内容：

- 大屏正片
- 带密码的分享版
- 匿名项目配置
- 可继续补充音乐的目录结构

这个 skill 的目标不是做一套复杂系统，而是把一类高频、可复用的交付流程压缩成一个足够轻、但可以直接工作的模板与脚本组合。

## What This Repo Optimizes For

- 目录清晰，单个 skill 自包含
- 模板匿名，可直接复用
- 输入尽量少，输出尽量完整
- 先做能落地的最小工具，再考虑扩展

## Quick Start

1. 进入目标 skill 目录，例如 `skills/generate-wedding-slideshow/`
2. 阅读对应的 `SKILL.md`
3. 按要求提供输入目录、输出目录和简要说明
4. 用内置脚本生成独立项目

## Notes

- 仓库中的 wedding 模板是匿名模板，不绑定任何具体婚礼
- 音乐文件不进入仓库；如需下载，交由对应 skill 在生成后的项目目录中处理
- 后续可以继续增加新的风格或新的 skill，但不会把这个仓库做成重型平台
