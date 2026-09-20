---
name: vcut
description: 使用本机 MLX Qwen3-ASR 和 ForcedAligner 为视频制作字幕，由当前 Agent 校对、翻译并导出原文或双语 SRT/VTT，可用 FFmpeg 烧录字幕。适用于本地视频转写和字幕校准，不负责配音或自动发布。
---

# vcut 本地字幕

CLI：本 skill 目录下的 `./vcut`（Apple Silicon + macOS）。首次使用先运行
`scripts/setup.sh` 创建 venv、安装依赖并下载模型；模型和 Python 随本目录
定位，无需 LM Studio、LLM API Key 或另建服务。接口和约束见
`localcut/README.md`。CLI 不会自动运行语义模型：当前 Agent 本身负责校对和翻译。

## 工作流

1. 运行 `./vcut doctor`；已有项目先核对 project.json 的媒体、语言和范围。新媒体 `./vcut create PROJECT MEDIA --language English`（中文用 Chinese），再 `./vcut auto PROJECT`。保留原视频和已有转写，不重新跑无关全片。
2. `./vcut prepare-review PROJECT --output REVIEW.json`。读取全文上下文及所有 rows；长视频按带上下文的批次处理，不漏行。仅编辑 corrected、translation、note，以及顶层 target_language，保留其他字段和顺序。大项目建议用脚本按行号合并编辑，不要手改大 JSON；合并前做词级漂移校验：每行 corrected 与原 text 的词集差异必须全部来自该行内更正，相邻行互相借词即行号错位，先修正再继续。
3. corrected 忠实保留口语、事实和原语言，只纠错、加标点；不把摘要或润色稿冒充原话。人名、数字、术语不确定时核实原片：Agent 听不了音频时，用 ffmpeg 抽对应时间点的帧读画面（屏幕文字、URL、面板数值）最有效；无法确认的保留并记 note。条目可能从句中切开，结合邻行理解，但不要跨行移动词或修改时间。
4. 需要翻译时填写所有 translation 和 target_language；否则二者留空。纯承接性 cue 也要给译文片段（把中文按语义切进相邻 cue），留空会在译文字幕产生空条目。翻译以校对后的原文为准，不添加原文没有的信息。双语逐句对应，不要求译文逐字对应原声。
5. `./vcut apply-review PROJECT REVIEW.json --output NEW_REVISION_DIR`。它校验源指纹和不可变字段；改过原文会本机重新 ForcedAligner 对齐，保留词级结果。源语字幕保留原 cue 外边界，译文继承同一 cue 时间，不为目标语言伪造逐词时间。零时长修复是标注过的插值，不是声学准确度保证。
6. 检查 revision 的 words.json、source.srt；有翻译时检查 translated.srt/bilingual.srt。原始 raw/repaired/exports 不被覆盖，后续修改选择新 revision 目录。展示疑点及实测范围。

## 烧录与验收

用户要成片时使用 FFmpeg 的 subtitles/libass。先检查选定 binary 有 subtitles
filter；系统 ffmpeg 可能没有，优先查已有 imageio-ffmpeg binary，不擅自安装或
替换环境。输出使用新文件名、`-n` 防覆盖。

在字幕文件所在目录运行，使用固定简单文件名以避免 filter 路径转义问题：

```sh
FFMPEG -n -i /absolute/source.mp4 -vf "subtitles=source.srt" -c:v libx264 -crf 18 -c:a copy /absolute/new-captioned.mp4
```

默认 SRT 样式为底部居中，通常即可。不要照搬网上的 force_style 样式参数
（如 Alignment=8），某些 libass 构建下渲染位置会不符预期；需要自定义样式时，
先短时段小样渲染抽帧，确认实际落点后再全片编码。原片已有字幕时选不遮挡的
位置。实际抽帧检查中文字体、换行、遮挡与字幕位置；用 ffprobe 检查时长和
音视频轨。抽查纠错点的声画同步，结构校验不替代听辨。交付可点击视频和字幕
路径，说明是否只测了片段；不宣称全片已验收。
