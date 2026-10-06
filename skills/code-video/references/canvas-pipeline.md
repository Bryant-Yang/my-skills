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

`canvas.width/height` 决定输出像素尺寸，CSS 决定预览布局。页面可以提供播放或 scrub，但离线渲染直接取 t，不按播放键。其他成熟 renderer 可能还有 `gpuInfo()` 或 `renderSheet()` 契约；使用哪个工具就核对哪个实际接口，不要求所有工程实现不存在的接口。

## 确定性与就绪

- 状态来自 t、固定输入和固定 seed。避免墙钟、未播种随机数、跨帧累积或依赖播放历史。画面动作、模拟和粒子都能从目标时间重建。
- 字体加载、图像解码、离屏缓冲和当前帧绘制完成后才声明 ready。页面错误、缺失资源或字体替换须处理，不能因第二次截图恰好正确便通过。
- 固定导出 fps，使用明确帧索引与时间映射；不按不稳定的浏览器 rAF 速度截图。确认最后一帧、音轨与容器时长的取整关系。
- 离线导出使用已准备的本地资源。视频素材若需逐帧确定性，可先按输出 fps 解码成图像序列；不能让嵌入媒体自行播放并假装同步。
- 顺序、乱序与冷启动抽同一时点，比较实际无损帧。完整像素比对用于发现保留状态，语义正确仍需查看关键动作。

p5 工程的随机与噪声按实际代码设置种子；第三方库也可能引入随机，不能只检查自己的脚本。组件若需文字合成、离屏绘制或相机配对，保留其真实顺序和约束；不要把某个项目的 helper 名称变成通用 Canvas 接口。

## 音轨与时间轴

复用用户音频，或选择已授权且可用的 TTS。读取实际音频时长与句/词 cue；分段 boundary 是块内相对时间，必须按实际拼接偏移换算。按 PCM 样本计数或整数 `duration_ts × time_base` 核对拼接长度与帧边界，避免显示用的小数舍入多算一帧；JSON 的申报时长不能替代实际解码。

补入 lead/gap/tail 后用拼接音轨的总长作为最终时长，不能再加一遍尾垫。固定目标时长需要明确编辑、补静音或调整动作，不静默拉伸声音。没有词级 cue 时采用段级事件或明示编辑估计；不要根据字数宣称固定同步误差。

## 使用本包工具

依赖：Node.js、已安装的 `puppeteer-core`、Chrome/Chromium、FFmpeg/ffprobe；验证器使用 Python 标准库。先检查是否已有；本包脚本不下载浏览器、不安装软件、不调用 TTS。

从 skill 文件所在目录解析 `<skill-dir>`，命令中的项目、资源和输出路径使用当前任务的实际值。完整选项以脚本 `--help` 为准。

```bash
node <skill-dir>/scripts/render-canvas.mjs \
  --studio <project>/studio.html --audio <project>/assets/narration.wav \
  --out <project>/out/film.mp4 --duration <actual-seconds> --fps 24 \
  --width 1080 --height 1920 --chrome <chrome-binary> \
  --dependency-root <project-with-puppeteer-core> \
  --resource-root <local-resource-root>

python3 <skill-dir>/scripts/verify-video.py <project>/out/film.mp4 \
  --width 1080 --height 1920 --fps 24 --duration <actual-seconds> \
  --report <project>/verification/technical.json
```

`--dependency-root` 是已安装 `node_modules/puppeteer-core` 的项目目录，也可用 `--puppeteer-module` 指向模块入口或包目录。`--resource-root` 默认 studio 所在目录；旧工程使用 `../node_modules` 等相对资源时，显式给包含这些资源的上级根，真实文件路径仍不能越界。页面只读取本次本地服务资源，不请求外部网络。

宽高参数是对实际画布属性的断言，不负责缩放或修正构图。省略 `--duration` 时取音轨实测长度；显式时长与音轨差不得超过一帧。帧数按输出帧边界取整，视频可能比音轨长不足一帧，验收按该 fps 的容差解释，不宣称所有容器时长完全相等。

现有输出默认保留，明确覆盖才使用渲染器 `--overwrite`。配音/音乐任务默认拒绝意外静音；有意静音时显式使用 `--allow-silent-audio`，它仍要求实际音轨。音频检查使用 decoded RMS 与 sample peak，不是感知响度、true peak 或真人试听。

本包每次使用独有的临时帧目录；若使用其他 renderer 的断点续渲，只有源码、输入与时间轴未变才能复用旧帧。按源哈希失效须覆盖所有实际输入；不确定影响范围时重新全量渲染。

最小 [Canvas 样板](../assets/canvas-starter/studio.html) 只展示 ready、纯函数与按时刻绘制，正式影片须替换为本题的视觉内容。技术 smoke 不是叙事成片。
