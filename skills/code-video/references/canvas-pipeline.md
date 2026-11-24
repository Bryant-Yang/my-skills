# Canvas/p5 制作与导出

本路线适用于已有程序画布，或需要精确对象、文字、关系和时间控制的动画。复用当前工程与依赖，不要求有某个个人目录、特定渲染仓库或手绘组件。

## 尺寸与渲染契约

画布属性、场景 W/H、容器比例、字幕区和导出参数一致。已有横屏脚手架不能只改标题便用来出竖屏；改本期副本，保留共享工程。

可接入本包渲染器的页面提供：

```js
// 固定输入、字体与素材准备好后才置 true。
window.ready = true;
window.renderAt = (t, type = 'image/jpeg', quality = 0.94) => {
  drawFrame(t); // 清画布、重建本时刻状态；不得依赖上一帧。
  return canvas.toDataURL(type, quality);
};
```

`canvas.width/height` 决定输出像素尺寸，CSS 决定预览布局。默认识别 `canvas#out`、`canvas#film` 或页面唯一的 `<canvas>`，多画布页面通过 `--selector` 显式指定。页面可以维护可选的 `window.__layoutWarnings = []`，在 `renderAt(t)` 内记录文字实测宽度超出容器的告警，由导出器在关键帧和成片阶段汇总输出。

## 确定性、就绪与防穿模原语

- 状态来自 `t`、固定输入和固定 seed。避免墙钟、未播种随机数、跨帧累积或依赖播放历史。画面动作、模拟和粒子都能从目标时间重建。
- `t = 0`（默认播放器封面帧）应直接建立主结构或可读初始态，避免把核心面板全部设为零透明度入场而产生空白封面。
- 动态生长的进度条、柱体或擦除面板内含文字时，使用 `ctx.save(); ctx.beginPath(); ctx.rect(x, y, currentW, h); ctx.clip()` 对文字做同步裁切揭示，并将紧邻其右侧的次级徽章安排在主条到位之后或固定安全坐标，防止 `p ≈ 0.35` 中途帧发生文字溢框与组件互撞。
- 嵌入外部实测截图或示意图时，按源图真实宽高比做等比居中（`contain`）或明确安全裁切，禁止直接把不同比例的图片硬拉进目标矩形导致圆轮、图标或 UI 几何变形。
- 字体加载、图像解码、离屏缓冲和当前帧绘制完成后才声明 `ready`。顺序、乱序与冷启动抽同一时点，比较实际无损帧。

## 音轨与「一幕多句」双层时间轴

复用用户音频，或选择已授权且可用的 TTS。多数分段式配音服务不仅按换行分段，还会按句末标点（`。！？；`）拆句；强行把整幕十几秒文案改成一逗到底，既会损失问句与句号的自然语调，也会让单条长字幕长时间占屏。

推荐采用 **视觉幕（Beat）1 : N 语音句（Sentence）** 双层结构：

1. 每幕包含若干自然短句，幕内句间设短气口（如 `250–300 ms`），幕尾设阅读与观察停留（如 `1200–1800 ms`）。
2. 每句分别保存口语读音文本（将易读崩的符号或缩写转为自然读法，或配置发音词典）与精炼屏幕字幕（保留准确技术符号与单位），避免将 TTS 妥协写法直接印上屏幕。
3. 读取导出音频的实际样本偏移（如 `start_frame` 与 `frames`）切出每句真实 PCM，在幕内拼入短气口静音、幕尾按帧边界（`sample_rate / fps` 样本整数倍）补齐尾垫，同时生成幕级动画时长与句级精确字幕（画布滚动字幕及独立 `.srt`）。
4. 按 PCM 样本计数或整数 `duration_ts × time_base` 核对拼接总长与帧边界，避免小数舍入多算一帧；补入 lead/gap/tail 后用拼接音轨的实际总长作为最终时长，不能再加一遍尾垫。

## 使用本包工具

依赖：Node.js、已安装的 `puppeteer-core`、Chrome/Chromium、FFmpeg/ffprobe；验证器使用 Python 标准库。先检查是否已有；本包脚本不下载浏览器、不安装软件、不调用 TTS。

从 skill 文件所在目录解析 `<skill-dir>`，命令中的项目、资源和输出路径使用当前任务的实际值。完整选项以 `--help` 为准：

```bash
# 1) 全量渲染前：免音频抽检首帧、过渡中途帧与各幕终态，并收集排版越界告警
node <skill-dir>/scripts/render-canvas.mjs \
  --studio <project>/studio-draft.html \
  --keyframes 0,3.2,8.5,16.0 \
  --out-dir <project>/out/keyframes \
  --chrome <chrome-binary> \
  --dependency-root <project-with-puppeteer-core>

# 2) 多页面并行导出成片（可附带 FFMETADATA1 章节文件）
node <skill-dir>/scripts/render-canvas.mjs \
  --studio <project>/studio.html --audio <project>/out/combined.wav \
  --out <project>/out/film.mp4 --fps 24 --workers 4 \
  --chapters <project>/out/chapters.ffmeta \
  --chrome <chrome-binary> \
  --dependency-root <project-with-puppeteer-core> \
  --resource-root <local-resource-root>

# 3) 独立校验流属性、章节与可选的编码音轨 ASR 转写覆盖率
python3 <skill-dir>/scripts/verify-video.py <project>/out/film.mp4 \
  --width 1920 --height 1080 --fps 24 --expect-chapters 5 \
  --transcript-file <project>/out/encoded-asr.txt \
  --expected-text-file <project>/out/expected-voice.txt \
  --report <project>/out/verify-video.json
```

`--dependency-root` 是已安装 `node_modules/puppeteer-core` 的项目目录，无需把依赖包复制进每个新视频目录。`--workers` 在验证单页正逆序与冷启动确定性一致后，自动启动多个隔离沙箱页面并行渲染长片帧序列。若工程自备渲染器支持帧文件增量缓存，修改单幕代码后可仅删除受影响帧区间（`beat.frame .. beat.frame + beat.frames`）局部重渲，但跨幕共享组件或时间轴改变时必须全量重渲。

最小 [Canvas 样板](../assets/canvas-starter/studio.html) 仅展示 `ready`、纯函数 `renderAt(t)`、生长条块 `clipRect` 裁切及 `window.__layoutWarnings` 越界遥测，正式影片须替换为本题的视觉内容。
