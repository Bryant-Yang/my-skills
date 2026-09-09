#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  direct_resumable_download.sh <url> <destination-directory> [output-filename]

Environment:
  DIRECT_DL_INTERFACE=en0          Physical interface to bind curl to.
  DIRECT_DL_SPLIT=8                Range part count.
  DIRECT_DL_DOH_HOST=dns.alidns.com
  DIRECT_DL_DOH_IP=223.5.5.5
  DIRECT_DL_PROGRESS_INTERVAL=30

Policy:
  This downloader always uses interface-resolve mode:
  clear proxy env, bind curl to a physical interface, resolve true IPs
  through DoH, pin TLS with --resolve, and resume with byte ranges.
  It never changes Clash, TUN, VPN, DNS, Wi-Fi, or system routes.
USAGE
}

if [[ $# -lt 2 || $# -gt 3 ]]; then
  usage >&2
  exit 64
fi

url="$1"
dest_dir="$2"
out_name="${3:-}"

echo "URL: $url"
echo "Destination directory: $dest_dir"
if [[ -n "$out_name" ]]; then
  echo "Output filename: $out_name"
fi

echo "Proxy env check:"
for proxy_name in http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY; do
  if [[ -n "${!proxy_name-}" ]]; then
    echo "  $proxy_name: set; will be cleared for download process"
  else
    echo "  $proxy_name: unset"
  fi
done

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$script_dir/direct_interface_resolve_download.py" "$url" "$dest_dir" "$out_name"
