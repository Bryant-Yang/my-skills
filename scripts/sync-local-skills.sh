#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd -P)"
source_root="${1:-"$repo_root/../myskills"}"

if [ ! -d "$source_root" ]; then
  echo "source root does not exist: $source_root" >&2
  exit 1
fi
source_root="$(cd "$source_root" && pwd -P)"

skills=(
  kimi-acp-communication
  llm-wiki
)

for skill in "${skills[@]}"; do
  source_dir="$source_root/$skill"
  target_dir="$repo_root/skills/$skill"

  if [ ! -f "$source_dir/SKILL.md" ]; then
    echo "missing Skill entrypoint: $source_dir/SKILL.md" >&2
    exit 1
  fi
  if [ -L "$source_dir" ] || [ -L "$target_dir" ]; then
    echo "refusing to sync symlinked Skill directory: $skill" >&2
    exit 1
  fi

  mkdir -p "$target_dir"
  rsync -a --delete \
    --exclude='.git/' \
    --exclude='__pycache__/' \
    --exclude='.pytest_cache/' \
    --exclude='.ruff_cache/' \
    --exclude='.mypy_cache/' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='*.log' \
    "$source_dir/" "$target_dir/"
  echo "synced skills/$skill"
done
