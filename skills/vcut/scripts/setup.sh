#!/bin/sh
# vcut skill setup: venv + dependencies + models + self-check.
# Apple Silicon Mac only (MLX). FFmpeg/FFprobe must be on PATH (e.g. brew install ffmpeg).
set -e
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

if [ ! -x .venv/bin/python ]; then
    PY=$(command -v python3.12 || command -v python3)
    echo "==> creating .venv with $PY"
    "$PY" -m venv .venv
fi
./.venv/bin/python -m pip install -U pip
echo "==> installing python dependencies"
./.venv/bin/python -m pip install "mlx>=0.32" "mlx-qwen3-asr>=0.3.5" "numpy>=2"

mkdir -p models/mlx-community models/Qwen
download() {
    dest="$2"
    if [ -n "$(ls "$dest" 2>/dev/null)" ]; then
        echo "==> $dest already present, skip"
    else
        echo "==> downloading $1"
        HF_HUB_OFFLINE=0 ./.venv/bin/python - "$1" "$dest" <<'PYEOF'
import sys
from huggingface_hub import snapshot_download
snapshot_download(repo_id=sys.argv[1], local_dir=sys.argv[2])
PYEOF
    fi
}
download mlx-community/Qwen3-ASR-1.7B-8bit models/mlx-community/Qwen3-ASR-1.7B-8bit
download Qwen/Qwen3-ForcedAligner-0.6B    models/Qwen/Qwen3-ForcedAligner-0.6B

echo "==> self-check"
./vcut doctor
echo "==> done. Try: ./vcut create projects/demo.vcut /absolute/path/video.mp4 --language English"
