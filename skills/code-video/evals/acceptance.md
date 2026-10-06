# code-video 1.0.0 验收记录

验收日期：2026-10-07。此记录区分 skill 试读、工具运行、接口核对和影片主观检查，不把测试样板当成创作成片。

## 合并范围

将 PDoomVideo 的 `code-video`、`video-aesthetic`、`hf-canvas-bridge` 整理为一个入口，按需加载视觉叙事、Canvas 制作、HyperFrames 桥接与成片验收。吸收关键帧先行、稳定实体、真实音轨时间轴、确定性 seek 和实际编码回归经验；不沿用固定幕数、个人路径、效果次数或伪精确审美评分。

## 实际运行

环境：Node.js 26.9.0、Python 3.14.7、FFmpeg/ffprobe 9.0.2、Chrome 154.0.8037.95、puppeteer-core 25.11.0。依赖由测试环境提供，skill 没有安装软件或下载浏览器。

| 测试 | 观察与结果 |
| --- | --- |
| 离线横屏导出 | H264/AAC、yuv420p、1280×720、12 fps、10 帧；完整音视频解码通过 |
| 离线竖屏导出 | H264/AAC、yuv420p、720×1280、12 fps、10 帧；完整音视频解码通过 |
| 时长与声音 | 两例音频 0.8 s，视频及容器 0.833333 s；一帧以内取整；单声道，decoded RMS −19.35、sample peak −16.24 dBFS |
| 确定性抽查 | 首、中、末三个时点，正逆序及独立冷页面的无损 PNG 一致；不推论所有时间与浏览器都一致 |
| 资源与就绪 | 缺本地资源、外部请求、未完成的 render Promise 均失败；显式资源根允许合法上级资源，默认根拒绝越界 |
| 输出保护 | 默认拒绝覆盖；失败的显式覆盖保留原片；本次临时帧目录清理 |
| 参数与静音 | 错误时长、宽高及预期帧数被拒绝；静音默认失败，明确允许后通过，仍要求音轨 |
| 验证报告保护 | 报告与输入影片同路径、symlink 或 hardlink 重叠时拒绝，影片 SHA 与别名关系保持；独立报告正常写入 |

复现横屏与失败场景：

```bash
python3 <skill-dir>/scripts/smoke-test.py \
  --chrome <existing-chrome-binary> \
  --dependency-root <project-with-installed-puppeteer-core>
```

横竖样板与合成正弦音频只验证工具行为，不证明布局、中文旁白、叙事或审美。实际影片应另按 [成片验收](../references/acceptance.md) 检查。

## HyperFrames 有限接入验收

使用已安装的 `hyperframes@0.8.97` 与 GSAP 3.15.0，在独立本地测试工程运行，没有下载或安装：

- CLI `snapshot` 的 0/1 秒输出已查看；`check` 的 lint/runtime 无发现，layout 实际采样 `[0,1]`。motion 未启用，contrast 为零检查，均不记为通过。
- 实际 runtime 的 `renderSeek`、GSAP modifier 与 chained waiter 联动：0/0.5/1/1.5 秒正逆请求 PNG 一致，新页面 1 秒一致；延迟 setup 600 ms、paint 25 ms 时首帧等待约 837 ms，setup/paint 故障实际 reject。
- Canvas→img 的静态调色路径实际建立 shader；exposure=1 时目标灰色像素从 110 变为 220。未由这一次测试推出其他效果的开关、复原或色彩空间结论。

此路线未测试编码 MP4、音轨、producer beginFrame、并行 worker、LUT/HDR 或动态效果恢复。版本依赖与具体接入边界见 [HyperFrames 桥接](../references/hyperframes-bridge.md)；Canvas 导出器的 MP4 测试不能替代 HyperFrames 编码验收。

## 独立试读

另一个 Agent 仅依据 skill 处理两个新输入，未联网、生成音频或视频：

- 45 秒竖屏概率例子：保留两段现成音频的 12.4/21.2 秒段级依据，明确缺少正文，先核对内容再编句内动作；补足目标时长不重复计尾垫，不伪称词级对齐。稳定签的身份与剩余集合，区分抽走中奖签和未中奖签的条件概率。
- 64 秒配乐 p5 源码审阅：保留声音、风格、renderer 和只读范围；没有现成 MP4 时报告成片未验证，不偷偷生成新片。

试读发现原措辞可能把所有 review 扩展为成片生产，已改为区分成片 review、源码只读与局部审阅。这是行为试读与问题修正记录，不是两条创作任务的执行结果或学习实验。

## 独立审查与修正

独立规格审查无 P1/P2/P3 发现。代码规范审查发现两项可复现问题，均按最小范围修正；实际回归与独立复审通过，最终无遗留 P1/P2/P3：

| 问题 | 修正与回归判据 |
| --- | --- |
| P2：输出父目录软链接可绕过源影片保护 | 已存在输出用真实路径与来源比较；源 MP4 同时作为音轨时，别名输出配合覆盖实际失败，源 SHA 不变 |
| P3：音频小数舍入多算一帧 | 用解码 PCM 的整数 `duration_ts × time_base` 求时长；8000 samples / 48000 Hz 在 24 fps 下实际导出 4 帧，原 0.8 s / 12 fps 仍为 10 帧 |

## 发布检查

Skill Creator 元数据校验、Python/Node 语法、CLI help、YAML、本包相对引用、暂存 diff、独立规范与规格 review、发布快照审计均通过。仅提交 README 的本 skill 目录项及 `skills/code-video/`，运行素材与私人测试日志不进入 Git。

原工作目录的全目录审计会被既有、被 Git 忽略的 `vcut/.venv` 软链接拦截。保留该环境，不修改审计标准；发布审计针对 Git 暂存导出的干净快照运行同一个 `scripts/audit-public.sh`，只证明实际发布文件。

未执行：完整创作影片的主观试听、学习效果测量、其他操作系统、生产发布或远程自动任务。本记录不替代使用本 skill 产出的每部影片验收。
