# 通用课件运行协议

本协议只定义可移植的课件内部结构，不依赖具体平台。生成页必须可以直接在浏览器打开运行；只有用户需要嵌入 LMS、课堂应用或其他宿主时，才启用可选消息桥接。

## Courseware Config

HTML 中内嵌一份机器可读配置：

```html
<script type="application/json" id="courseware-config">
{
  "schemaVersion": 1,
  "kind": "simulation",
  "topic": "concept_slug",
  "description": "这一页演示什么",
  "variables": [
    {
      "name": "main_variable",
      "label": "主变量",
      "control": "range",
      "min": 0,
      "max": 100,
      "step": 1,
      "default": 50,
      "unit": "%"
    }
  ],
  "presets": [
    {
      "name": "低值对比",
      "variables": { "main_variable": 20 }
    }
  ],
  "hostBridge": true
}
</script>
```

规则：

- `schemaVersion` 固定为 `1`，`kind` 固定为 `simulation`。
- `topic` 使用稳定英文 slug，但不绑定任何产品 ID。
- `variables[].name` 是内部状态、DOM 和动作协议共用的变量键。
- 数值变量提供 `min/max/step/default/unit`；枚举变量提供 `options`。
- `presets[].variables` 只能引用已声明变量。
- 不需要宿主控制时可省略 `hostBridge`，同时不必实现消息监听。

## DOM 命名

推荐使用以下稳定钩子：

```text
变量控件：      #{variable_name}-slider 或 [data-var="{variable_name}"]
变量显示：      #{variable_name}-display
启动：          #start-btn
暂停：          #pause-btn
重置：          #reset-btn
运行状态：      #status-display
主可视化：      #visualization 或 #canvas
预设：          [data-preset="preset-name"]
```

如果输出教学动作，动作目标必须能在最终 HTML 中查到，并且执行时可见。

## 可选宿主消息桥接

监听器先检查 `event.data` 是普通对象，再按 `type` 分支。未知类型安全忽略。宿主可自行把这些中性消息映射到自己的 API。

### COURSEWARE_SET_STATE

```json
{
  "type": "COURSEWARE_SET_STATE",
  "state": { "main_variable": 20 }
}
```

只接受配置中声明的变量；数值做范围约束，枚举做白名单检查，并通过页面唯一的 `setState()` 同步状态、控件、数值和可视化。

### COURSEWARE_HIGHLIGHT

```json
{
  "type": "COURSEWARE_HIGHLIGHT",
  "target": "#main_variable-slider",
  "content": "观察这个变量"
}
```

查不到目标时安全返回；高亮应明显、临时且不改变布局。

### COURSEWARE_ANNOTATE

```json
{
  "type": "COURSEWARE_ANNOTATE",
  "target": "#result-display",
  "content": "结果会随变量变化"
}
```

注释使用 `textContent`，不把消息内容写入 `innerHTML`，并避免越出视口。

### COURSEWARE_REVEAL

```json
{
  "type": "COURSEWARE_REVEAL",
  "target": "#formula-panel"
}
```

只显示页面中预先存在的内容，不根据消息创建或执行代码。

## 可选教学动作文件

`<slug>.actions.json` 使用中性、可映射的命令格式：

```json
[
  { "type": "narration", "content": "先观察初始状态。" },
  {
    "type": "command",
    "command": "set_state",
    "params": { "state": { "main_variable": 20 } }
  },
  {
    "type": "command",
    "command": "highlight",
    "params": { "target": "#main_variable-slider", "content": "改变核心输入" }
  },
  {
    "type": "command",
    "command": "annotate",
    "params": { "target": "#result-display", "content": "观察结果" }
  },
  {
    "type": "command",
    "command": "reveal",
    "params": { "target": "#formula-panel" }
  }
]
```

宿主若存在，负责把 `set_state/highlight/annotate/reveal` 映射为对应的 `COURSEWARE_*` 消息；Skill 不假定宿主技术栈。

## 安全边界

- 默认单文件、无远程依赖、无网络请求。
- 不把用户输入或消息内容交给 `eval`、`Function`、`innerHTML` 或动态脚本标签。
- 不在 HTML 中写入 API key、用户隐私、本地绝对路径或产品专用凭据。
- 页面不假设与宿主同源，也不假设 iframe 权限；嵌入方式与 sandbox 策略由宿主决定。
