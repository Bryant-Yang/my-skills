#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$repo_root"

if ! command -v rg >/dev/null 2>&1; then
  echo "ripgrep (rg) is required" >&2
  exit 1
fi

bad_links="$(find skills -type l -print)"
if [ -n "$bad_links" ]; then
  echo "refusing to publish symlinks under skills/:" >&2
  printf '%s\n' "$bad_links" >&2
  exit 1
fi

artifact_paths="$(find skills -type f \( \
  -name '*.pyc' -o \
  -name '*.pyo' -o \
  -name '*.log' -o \
  -name '.DS_Store' \
\) -print)"
if [ -n "$artifact_paths" ]; then
  echo "local artifacts found under skills/:" >&2
  printf '%s\n' "$artifact_paths" >&2
  exit 1
fi

secret_pattern='BEGIN (RSA|OPENSSH|EC|PGP) PRIVATE KEY|github_pat_[A-Za-z0-9_]{20,}|gh[opurs]_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|Bearer[[:space:]]+[A-Za-z0-9._-]{20,}|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}'
secret_files="$(rg -l --hidden \
  --glob '!.git/**' \
  --glob '!scripts/audit-public.sh' \
  "$secret_pattern" . || true)"
if [ -n "$secret_files" ]; then
  echo "possible credential material found; filenames only:" >&2
  printf '%s\n' "$secret_files" >&2
  exit 1
fi

private_path_files="$(rg -l --hidden \
  --glob '!.git/**' \
  --glob '!scripts/audit-public.sh' \
  '(/Users/[^/[:space:]]+|/home/[^/[:space:]]+|session_[0-9a-fA-F-]{16,})' \
  . || true)"
if [ -n "$private_path_files" ]; then
  echo "possible machine-private path or concrete session id found:" >&2
  printf '%s\n' "$private_path_files" >&2
  exit 1
fi

echo "public-safety audit passed"
