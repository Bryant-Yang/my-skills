# vcut：本地离线字幕 CLI

项目/分阶段命令式的本地转写工具：MLX 转写（Qwen3-ASR 或更小的 Whisper，二选一）
+ 字级时间戳，校对、翻译由调用方 Agent 完成，FFmpeg 负责裁切与烧录。全程离线，
无需任何 API Key 或在线服务，不自动下载模型。

仅支持 Apple Silicon（MLX）。需要系统已安装 FFmpeg/FFprobe。

## 转写引擎

| 引擎 | 模型 | 下载体积 | 词级时间戳 | 适用 |
| --- | --- | --- | --- | --- |
| `qwen3`（默认） | Qwen3-ASR-1.7B-8bit + ForcedAligner-0.6B | 约 3 GB | ForcedAligner | 中英混讲、语境提示（--context）质量更好 |
| `whisper` | mlx-community/whisper-large-v3-turbo-q4 | 约 460 MB | DTW 内置，无需 Aligner | 不想下大模型；英文效果好，中文可用 |

whisper 引擎想要极小体积选 `--model mlx-community/whisper-base-mlx`（约 145 MB，
中文较弱）或 `whisper-small-mlx`（约 490 MB）；自定义模型用 `--asr-model` 指向
本地目录或 repo id。校对后重对齐（apply-review）优先使用 ForcedAligner（两个
引擎通用）；whisper 引擎未下载 Aligner 时退化为 cue 内均匀插值，结果标注
`timing_method`，不冒充声学精度。

## 目录约定

```text
<skill 根目录>/
├── vcut              # 启动器：.venv/bin/python localcut/cli.py
├── localcut/         # 本工具源码
├── models/           # 模型（setup.sh 下载或手动放置）
│   ├── mlx-community/Qwen3-ASR-1.7B-8bit        # qwen3 引擎
│   ├── Qwen/Qwen3-ForcedAligner-0.6B            # qwen3 引擎；whisper 引擎可选（高质量重对齐）
│   └── mlx-community/whisper-base               # whisper 引擎
└── .venv/            # Python 虚拟环境（setup.sh 创建）
```

模型路径可用环境变量覆盖：`VCUT_ASR_MODEL`、`VCUT_ALIGNER_MODEL`；引擎可用
`VCUT_ENGINE` 设置默认值（`qwen3`/`whisper`），项目创建后以 project.json 记录为准。

## 快速开始

```sh
./scripts/setup.sh                    # 默认：Qwen3-ASR + ForcedAligner（约 3 GB）
./scripts/setup.sh --engine whisper   # 轻量：Whisper large-v3-turbo q4（约 460 MB）
./scripts/setup.sh --engine whisper --model mlx-community/whisper-base-mlx  # 极简（约 145 MB）
./vcut doctor                         # 环境自检（报告两个引擎各自是否就绪）
```

## 工作流（分阶段命令）

```sh
./vcut create projects/demo.vcut /绝对路径/video.mp4 --language English --engine whisper --context '主题提示词'
./vcut auto projects/demo.vcut          # 转写（可恢复）→ 零时长修复 → 时间结构检查 → 导出
./vcut check projects/demo.vcut
./vcut find projects/demo.vcut 关键词
./vcut clip projects/demo.vcut --start 10 --end 20 --output /绝对路径/clip.mp4
```

`auto` 的 stdout 输出 JSON，转写进度在 stderr。只操作本地文件。视频裁切使用
原视频时间，不拼接多段、不自动烧录字幕。

## 复用已有转写

```sh
./vcut create projects/existing.vcut /绝对路径/video.mp4
./vcut import projects/existing.vcut /绝对路径/transcript.json
./vcut repair projects/existing.vcut
./vcut export projects/existing.vcut
```

导入格式为 `{ "text": "全文", "segments": [{"text":"字/词","start":0.1,"end":0.3}] }`，
时间以秒计。必须对应项目的同一个音频；工具检查时间范围，无法自动证明文字和
音频语义一致。导入格式为扁平的 `{"text": ..., "segments": [{"text","start","end"}]}`，
不接受 Whisper 原始 JSON 的嵌套 words 结构。

## 项目文件

- `project.json`：媒体绝对路径、长度、源文件指纹、语言和术语提示。
- `chunks/*.json`：每 300 秒一个恢复点；时间偏移使用精确的抽取起点。内层
  MLX 自行按低能量边界切短片。
- `raw.json`：原始转写，导入不会覆盖已有文件。
- `repaired.json`：修复副本；修改的字保留 original_start/end 和 timing_method。
- `exports/`：TXT 全文、逐字 JSON、SRT/VTT。重复导出会更新此目录中的派生文件。

`check --raw` 可检查原始数据。退出码：0 成功，1 执行/输入错误，2 时间结构
检查未通过。项目写操作加锁，避免两个进程同时转写同一项目。源媒体大小或修改
时间改变会拒绝继续转写/裁切。

## Agent 校对与翻译（review 流程）

```sh
./vcut prepare-review projects/demo.vcut --output REVIEW.json
# Agent 编辑 REVIEW.json：corrected（校对原文）、translation（译文）、note，
# 顶层 target_language；其余字段与顺序不可改动
./vcut apply-review projects/demo.vcut REVIEW.json --output NEW_REVISION_DIR
```

- `apply-review` 校验源指纹和不可变字段；corrected 有改动时优先对每条 cue 本机重跑
  ForcedAligner 对齐，保留词级结果；Aligner 缺失（如 whisper 引擎）则 cue 内均匀插值并标注。输出新修订目录，含 `source.srt`、
  `translated.srt`、`bilingual.srt/vtt`、`words.json`。
- 源语字幕保留原 cue 外边界，译文继承同一 cue 时间。零时长修复是标注过的
  插值，不是声学准确度保证。原始 raw/repaired/exports 不被覆盖，后续修改
  选择新 revision 目录。
- 字幕 cue 由字词聚合（约 26 字符/5 秒一条，英文词间保留空格）。ForcedAligner
  不保留原文标点，TXT 保留原文标点；长英文词、说话人交叠仍需人工审阅。
- 未包含说话人分离模型。

## 验证

```sh
.venv/bin/python -m unittest discover -s localcut -v
```
