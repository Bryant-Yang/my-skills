---
name: direct-resumable-download
description: Use this skill whenever the user wants fast resumable downloads, large model/video/audio/file downloads, Hugging Face direct file downloads, or explicitly says "不要走 Clash", "不要走 Clash Verge TUN", "绕开代理流量", "直连下载", "断点续传", "续传", "aria2", "curl -C", or asks to download missing ComfyUI/LM Studio/Ollama/local AI assets. It always uses the process-local interface-resolve downloader: clear proxy env, bind curl to a physical interface, resolve true IPs through DoH, pin TLS with --resolve, and resume with byte ranges. It never changes Clash Verge, TUN, VPN, DNS, Wi-Fi, or system route settings.
---

# Direct Resumable Download

Use this skill for large direct downloads on the user's Mac, especially when Clash Verge TUN / fake-IP DNS is enabled and the user says not to route traffic through Clash.

## Policy

There is one supported strategy:

- Do not modify Clash Verge, TUN, VPN, DNS, Wi-Fi, system proxy, routing tables, or subscription settings.
- Do not use a generic route-check-and-abort workflow for this user.
- Do not set `DIRECT_DL_ALLOW_TUN_ROUTE`.
- Do not hand-write a one-off downloader.
- Always use the bundled `direct_resumable_download.sh` entrypoint, which calls the interface-resolve downloader.

The interface-resolve downloader is intentionally process-local and aggressive:

- clears `http_proxy`, `https_proxy`, `all_proxy`, `HTTP_PROXY`, `HTTPS_PROXY`, and `ALL_PROXY`;
- binds `curl` to `DIRECT_DL_INTERFACE`, default `en0`;
- resolves original and redirected HTTPS hosts through DoH, default `dns.alidns.com` via `223.5.5.5`;
- pins TLS connections with `--resolve host:443:ip`;
- downloads byte ranges into `<filename>.parts`;
- resumes from partial ranges;
- assembles the final file only after every part reaches the expected size.

If that process-local route cannot resolve, cannot determine size, cannot establish TLS, or repeatedly fails, stop and report the exact blocker. Do not fall back to Clash/TUN traffic.

## Workflow

1. Identify the exact file URL.
   - For Hugging Face, use a `resolve/main/...` file URL.
   - `hf-mirror.com/.../resolve/main/...` is acceptable when direct Hugging Face resolution is unstable.
   - For ComfyUI workflows, inspect the workflow/model note and derive the concrete model URLs first.

2. Identify the destination directory.
   - Inspect the local installation first; the following are example layouts.
   - ComfyUI models: `${HOME}/ComfyUI-Shared/models/<model_type>`.
   - ComfyUI input media: `${HOME}/ComfyUI-Shared/input`.
   - LM Studio GGUF: inspect the local LM Studio model folder before choosing.

3. Run the bundled entrypoint. The example assumes the Skill is installed or linked
   at `$HOME/.agents/skills/direct-resumable-download`; for another installation
   root, use that Skill directory's `scripts/direct_resumable_download.sh`.
   Requires macOS, Bash, Python 3, and curl with interface binding support:

   ```bash
   "${HOME}/.agents/skills/direct-resumable-download/scripts/direct_resumable_download.sh" \
     "<url>" \
     "<destination-directory>" \
     ["output-filename"]
   ```

4. Use environment knobs only when needed:

   ```bash
   DIRECT_DL_INTERFACE=en0
   DIRECT_DL_SPLIT=8
   DIRECT_DL_DOH_HOST=dns.alidns.com
   DIRECT_DL_DOH_IP=223.5.5.5
   DIRECT_DL_PROGRESS_INTERVAL=30
   ```

5. Verify completion.
   - Check final file size against the expected size printed by the downloader.
   - For safetensors, open with `safe_open(..., framework="pt", device="cpu")`.
   - For ComfyUI models, query `http://127.0.0.1:8188/object_info/<loader>` when ComfyUI is running.
   - Delete `.parts` directories only after final files have been verified.

## Current implementation limits

- Use only a trusted HTTPS source that correctly honors byte-range requests. The
  downloader checks assembled size but does not validate HTTP Content-Range or
  a content hash; size alone does not prove integrity. Verify a published checksum
  or the file format before using the result.
- Resume only the same unchanged file with the same `DIRECT_DL_SPLIT` value and
  destination. Parts do not store a source identity or range-layout manifest.
- Repeated range failures currently retry without a built-in attempt limit.
  Monitor the process and interrupt it when failures repeat, as required above.

## Reporting

Keep the final answer short:

- State whether the download completed or resumed.
- Give final paths and verified sizes.
- State that the downloader used process-local interface binding, true-IP DoH resolution, and range resume without changing Clash/TUN/system network settings.
- If blocked, identify the blocker: DNS/DoH, TLS, missing size, HTTP status, permission, disk space, or repeated range failure.

## Examples

Download a ComfyUI model:

```bash
"${HOME}/.agents/skills/direct-resumable-download/scripts/direct_resumable_download.sh" \
  "https://hf-mirror.com/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors" \
  "${HOME}/ComfyUI-Shared/models/diffusion_models"
```

Download a GGUF into LM Studio:

```bash
"${HOME}/.agents/skills/direct-resumable-download/scripts/direct_resumable_download.sh" \
  "https://huggingface.co/HauhauCS/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive/resolve/main/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive-Q6_K_P.gguf" \
  "${HOME}/.lmstudio/models/HauhauCS/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive"
```
