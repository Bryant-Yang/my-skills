# HyperFrames 条件桥接

仅在已有工程使用 HyperFrames，或用户明确选用它时加载。继续使用工程锁定的版本与本地资源；此模块不要求迁移、安装其他 skill、上传或使用云渲染。版本升级须单独验证，不把 `@latest` 混进可复现的渲染命令。

## 先选接入层

| 已有工程 | 接法 | 边界 |
| --- | --- | --- |
| 普通 HyperFrames HTML | 注册与 root ID 一致的暂停 GSAP 时间轴 | 正常的页面创作契约；框架管理时间与媒体 |
| 已有 Three.js / TypeGPU adapter | 在 `hf-seek` 监听器中绘制，并同步调用 `event.detail.waitUntil(promise)` | 事件由对应 adapter 发出；不能假定普通 Canvas 页面也会收到 |
| 自己控制捕获 host | 实现 `FrameAdapter` 的 `init / seekFrame / destroy` | 官方导出的实验性 v0 API；不是往任意 HTML 注入就生效的插件 |
| 旧 Canvas / p5 项目，经 GSAP 驱动且绘制异步 | 隔离 ready、串行绘制及 runtime waiter 兼容桥 | 项目经验与内部 hook；需要锁版本及真实捕获验收 |

不同时接入两套 seek 驱动，否则可能重复绘制、改变帧状态。`window.ready` 是旧项目自己的约定，不是 HyperFrames 通用就绪 API。新代码优先由初始化函数返回 Promise；资源、字体和绘图环境真正可用后才 resolve。

## 一帧的完成边界

顺序必须是：**等待初始化 → 按请求的绝对时间绘制 → 等待合成及图像解码 → 允许捕获**。时间属于请求，不来自播放进度或墙钟；每次 seek 都恢复完整状态。故障必须传递给捕获方，不能 `catch(console.warn)` 后继续截空帧。

已有 GPU adapter 可用以下形式。必须在事件监听器的同步部分注册 Promise，不能先 `await` 再调用 `waitUntil`：

```js
window.addEventListener("hf-seek", (event) => {
  const complete = queuePaint(event.detail.time);
  event.detail.waitUntil(complete);
});
```

`queuePaint` 仍需等待初始化并串行执行。`window.__hf.buildReady[key]` 可声明 adapter 看不见的初始化工作；它负责 setup，就绪不能代替每次 seek 的完成屏障。该 registry 及 `hf-seek` 细节按工程版本核对。

### 旧 runtime waiter 兼容模式

下列辅助代码仅用于已经依赖 `__hfWaitForSeekCompletion` 的工程。核对过的 npm `hyperframes@0.8.97` runtime 会重新赋值这个函数，因此简单覆盖会失效。用 accessor 保留 runtime waiter，并等待自己的完整绘制链；不改变 runtime 的原始等待逻辑。

`ready` 是工程提供的 Promise，`paintNow(t)` 必须包括所有异步合成和解码。此函数不负责注册 GSAP 或生成初始化 Promise：

```js
function installCanvasSeekBridge(ready, paintNow) {
  const key = "__hfWaitForSeekCompletion";
  const previous = Object.getOwnPropertyDescriptor(window, key);
  const readOnly = previous && ("value" in previous ? !previous.writable : !previous.set);
  if (previous && (!previous.configurable || readOnly)) {
    throw new Error("Cannot attach the canvas seek barrier");
  }
  let runtimeWait = window[key];
  let pending = Promise.resolve();
  const settledReady = Promise.resolve(ready);
  function queuePaint(time) {
    if (!Number.isFinite(time) || time < 0) {
      throw new Error("Seek time must be finite and non-negative");
    }
    pending = pending.then(() => settledReady).then(() => paintNow(time));
    return pending;
  }
  const wait = async () => {
    if (typeof runtimeWait === "function") await runtimeWait.call(window);
    // The runtime wait may enqueue more paints; wait until the chain is stable.
    let observed;
    do {
      observed = pending;
      await observed;
    } while (observed !== pending);
  };
  Object.defineProperty(window, key, {
    configurable: true,
    get: () => wait,
    set: (value) => { if (value !== wait) runtimeWait = value; },
  });
  return {
    queuePaint,
    async dispose() {
      try { await pending; } finally {
        if (previous) {
          Object.defineProperty(window, key, previous);
          if ("value" in previous && previous.writable) window[key] = runtimeWait;
          else if (previous.set) previous.set.call(window, runtimeWait);
        } else if (typeof runtimeWait === "function") {
          Object.defineProperty(window, key, {
            configurable: true, writable: true, value: runtimeWait,
          });
        } else delete window[key];
      }
    },
  };
}
```

使用前先确认 runtime 已存在或会赋值此 hook，安装位置在首个 seek 前。只装一次，销毁时卸载并保留最新 runtime waiter；切换 composition 后重建自己的桥。不可配置或不可还原的宿主属性不使用此模式。调用方为 setup / seek 配置有限超时，并中止失败的捕获。

GSAP 时间轴必须完全建好后再注册到 `window.__timelines[rootId]`，root ID 与 key 相同。旧桥可让 tween 的 modifier 把绝对时间传给 `queuePaint`；某些 seek 会抑制 `onUpdate`，所以只依赖回调不够。此技巧依赖锁定的 GSAP/runtime 行为：必须验 `t=0`、末帧、反向与随机 seek；不要把“曾在一个项目可用”当作跨版本保证。首帧也显式进入同一 ready 链，不能在 `!ready` 时提前返回成功。

## Canvas 与调色

`data-color-grading` 的 shader 目标是 `<img>` / `<video>`，不能直接挂在 `<canvas>` 或 wrapper。需要把画布接到该媒体管线时，可在每次绘制后镜像到 `<img>` 并等待解码：

```js
frameImg.src = canvas.toDataURL("image/png");
await frameImg.decode();
```

PNG 适合验证颜色、细线和文字；若为性能改用 JPEG，单独评估损失。Canvas 必须未被跨源资源污染。镜像层与画布尺寸一致，并避免同时显示原画布与镜像造成双重叠加。动态 `src`、shader 上传及捕获的先后仍要通过实际 snapshot / render 检验，`decode()` 完成不自动证明调色层已重绘。

- payload 按 `adjust / details / effects / lut` 等结构嵌套，允许的 keys 与范围查工程版本的 schema；不手写未经核对的完整默认对象。
- `intensity` 控制主调色及 LUT 等，**不是 grain、bloom、CRT 等效果的总开关**。需要动画时使用该版本明确暴露的具体属性。
- 当前官方 reference 列出的 CSS 属性包括 `--hf-color-grading-{intensity,lut-intensity,exposure,blur,bloom,kuwahara,pixelate,ascii,dither}`。值应在 payload 和 inline style 中从目标静止态起步，再交给时间轴；不能假定所有效果都可按时间开关。
- 没有公开动画接口的效果，先保持静态或不使用；不要根据名称猜 CSS 变量。若另做分层或烘焙方案，重新验 seek、合成和色彩。
- 特效时机、强度和持续时间由画面及说明目的决定。PSNR、亮度差只能表明像素变化，不能证明更好看或更易懂。

## DOM 与媒体契约

root 声明 `data-composition-id / data-duration / data-width / data-height`，CSS 使用 `width:100%; height:100%` 或 `inset:0`。Canvas 的 backing pixels 与设计尺寸对应，避免 CSS 拉伸。片段用 `class="clip"` 及 `data-start / data-duration / data-track-index`；root 时长覆盖最后一个片段和音频尾部。

每个 `<audio>` 使用唯一 `id`、本地 `src` 和明确时间窗；让框架定位、seek 与混音，不能靠 `audio.play()` 带动画时钟。声音是否存在须检查最终 MP4。对 `.clip` 内的子节点做入退场，避免与 runtime 的显隐管理争抢；独立视频不要叠两层普通 `data-start` 祖先。子 composition 的 host、文件内 ID 和 timeline key 应一致，合并后的 DOM ID 保持唯一。

不为消警告直接加 `data-layout-allow-overflow`；只对本来允许全幅出血的元素使用。`check` 中某项为 0 samples 表示需要核实有没有实际运行，不能读成通过。文本布局还需人工读帧，Canvas 字体尺寸和遮挡不由 DOM lint 全包。

## 验证与操作

使用工程已有 CLI（例如 package script 或锁定版本的本地 binary），先看该版本 `--help`，再执行 `check`、时间点 `snapshot` 和 `render`；不固定 worker、quality 或过期开关，也不要求 catalog 查询使用某种语言。发现效果目录项时检查它是完整 demo、子 composition 还是可嵌原语，防止 ID 冲突与背景覆盖。

桥接验收至少包括：

1. 冷启动首帧不是空白；延迟初始化/解码时捕获确实等待，失败不会伪装成功。
2. 同一时间点的顺序、逆序、随机请求及新页面结果一致；并行 worker 不共享可变绘图状态。
3. 对照调色前、目标效果时刻、恢复后的**整帧**；检查原画布没有偷偷盖住镜像，shader 也没有使用上一帧。
4. 检查实际编码 MP4 的末帧、声音、字幕和尺寸，完整解码后再交付；不要用 snapshot 替代成片验收。

## 来源与核对范围

核对日期：2026-10-06。官方源码固定到 `b9998dd5a823f70c40fc6978b18c0b63546d967d`，另检查已有 npm `hyperframes@0.8.97` 发布包的 runtime、捕获等待调用、调色 lint 与 CLI help。旧项目的内部桥接不能承诺在后续版本原样有效。

- [官方 FrameAdapter 文档与实验 API 边界](https://github.com/heygen-com/hyperframes/blob/b9998dd5a823f70c40fc6978b18c0b63546d967d/docs/concepts/frame-adapters.mdx)
- [GPU seek 事件及同步 waitUntil 实现](https://github.com/heygen-com/hyperframes/blob/b9998dd5a823f70c40fc6978b18c0b63546d967d/packages/core/src/runtime/adapters/seek-dispatch.ts)
- [Runtime 类型：setup 与 seek 等待接口](https://github.com/heygen-com/hyperframes/blob/b9998dd5a823f70c40fc6978b18c0b63546d967d/packages/core/src/runtime/window.d.ts)
- [官方调色结构、可动画属性与 intensity 边界](https://github.com/heygen-com/hyperframes/blob/b9998dd5a823f70c40fc6978b18c0b63546d967d/docs/reference/color-grading.mdx)
- [官方确定性契约](https://github.com/heygen-com/hyperframes/blob/b9998dd5a823f70c40fc6978b18c0b63546d967d/docs/concepts/determinism.mdx)

2026-10-07 补充了隔离工程的真实桥接测试：已有 `hyperframes@0.8.97`、GSAP 3.15.0、系统 Chrome 154.0.8037.95，以 SwiftShader 和 screenshot 捕获 Canvas → PNG img → runtime 的输出，未安装、下载或升级。

- CLI `snapshot` 实际截取并查看 0s / 1s；`check` 的 lint/runtime 无发现，layout 实际采样这两个时刻。motion 未启用，contrast 无 DOM 文本而 checked=0，未把两项当作实测通过。
- 实际 runtime 的 `renderSeek` 通过 modifier 驱动串行绘制，再等 chained waiter；4 个时刻正逆请求的 PNG 哈希一致，新页面的同一时刻也一致。故意延迟初始化和每帧绘制时，首帧等到完成；setup / paint 失败使 waiter reject。
- 中性输出的灰块像素保持 RGB(110,110,110)，CLI 与浏览器的 0s / 1s 像素一致；静态 exposure=1 确实进入调色 shader 并改变实际输出。未测试所有效果、动画后的复原、LUT 或 HDR。

未执行 HyperFrames MP4 编码、音频混音、producer beginFrame、并行 worker 或原生产项目迁移。本节的 fixture 验收只覆盖上述版本与捕获路径，不能据此宣称完整成片或跨版本桥接已通过。
