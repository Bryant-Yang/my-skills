#!/usr/bin/env bash
# 调用 gptsapi.net 生图，保存到 /tmp/generated_image_*.png
# 用法: ./generate.sh "your prompt here" [model]

PROMPT="$1"
CONFIG_FILE="$(dirname "$0")/config.env"

if [ ! -f "$CONFIG_FILE" ]; then
  echo "错误：配置文件不存在，请创建 $CONFIG_FILE 并设置 GPTSAPI_KEY" >&2
  exit 1
fi

source "$CONFIG_FILE"

if [ -z "$GPTSAPI_KEY" ]; then
  echo "错误：GPTSAPI_KEY 未配置，请在 $CONFIG_FILE 中设置" >&2
  exit 1
fi

MODEL="${2:-${GPTSAPI_DEFAULT_MODEL:-gpt-image-1.5}}"
API_KEY="$GPTSAPI_KEY"
OUT_FILE="/tmp/generated_image_$(date +%s).png"
TMP_JSON="/tmp/img_resp_$(date +%s).json"
TMP_PAYLOAD="/tmp/img_payload_$(date +%s).json"

if [ -z "$PROMPT" ]; then
  echo "Usage: $0 <prompt> [model]" >&2
  exit 1
fi

echo "正在生图（模型: $MODEL）..." >&2

# 用 python 构造 payload，避免 shell 转义问题
python3 -c "
import json, sys
payload = {'model': sys.argv[1], 'prompt': sys.argv[2], 'n': 1}
print(json.dumps(payload))
" "$MODEL" "$PROMPT" > "$TMP_PAYLOAD"

curl -s \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d "@$TMP_PAYLOAD" \
  "https://api.gptsapi.net/v1/images/generations" \
  -o "$TMP_JSON"

rm -f "$TMP_PAYLOAD"

python3 - "$TMP_JSON" "$OUT_FILE" <<'PYEOF'
import json, base64, sys, urllib.request

tmp_json, out_file = sys.argv[1], sys.argv[2]

with open(tmp_json, 'rb') as f:
    data = json.loads(f.read())

if 'error' in data:
    print(f"生图失败: {data['error'].get('message', data['error'])}", file=sys.stderr)
    sys.exit(1)

item = data['data'][0]
if 'b64_json' in item:
    with open(out_file, 'wb') as f:
        f.write(base64.b64decode(item['b64_json']))
elif 'url' in item:
    urllib.request.urlretrieve(item['url'], out_file)
else:
    print('未知响应格式', file=sys.stderr)
    sys.exit(1)

print(out_file)
PYEOF

rm -f "$TMP_JSON"
