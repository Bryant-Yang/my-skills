#!/usr/bin/env python3
"""Resumable direct-ish downloader for TUN/proxy-heavy macOS setups.

This helper keeps all network choices process-local:
- clears proxy environment variables
- binds curl to a physical interface such as en0
- resolves HTTPS hosts through DoH using the same interface
- pins curl TLS connections with --resolve host:443:ip
- downloads byte ranges into .parts and assembles the final file

It does not change VPN, TUN, DNS, Wi-Fi, route, or Clash settings.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
from pathlib import Path


PROXY_ENV_NAMES = {
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
}


def clean_env() -> dict[str, str]:
    env = os.environ.copy()
    for name in PROXY_ENV_NAMES:
        env.pop(name, None)
    env["NO_PROXY"] = "*"
    env["no_proxy"] = "*"
    return env


def run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        timeout=timeout,
        env=clean_env(),
    )


def parse_header_value(headers: str, name: str) -> str | None:
    prefix = name.lower() + ":"
    value = None
    for line in headers.splitlines():
        if line.lower().startswith(prefix):
            value = line.split(":", 1)[1].strip()
    return value


def parse_host(url: str) -> str:
    host = urllib.parse.urlparse(url).hostname
    if not host:
        raise SystemExit(f"ERROR: cannot parse host from URL: {url}")
    return host


def parse_filename(url: str) -> str:
    path = urllib.parse.unquote(urllib.parse.urlparse(url).path.rstrip("/"))
    return path.rsplit("/", 1)[-1] if path else "download.bin"


def doh_resolve(host: str, interface: str, doh_host: str, doh_ip: str) -> list[str]:
    query_url = f"https://{doh_host}/resolve?name={host}&type=A"
    cmd = [
        "curl",
        "--interface",
        interface,
        "--noproxy",
        "*",
        "--connect-to",
        f"{doh_host}:443:{doh_ip}",
        "-fsS",
        "--max-time",
        "30",
        query_url,
    ]
    proc = run(cmd, timeout=40)
    if proc.returncode != 0:
        raise RuntimeError(f"DoH failed for {host}: {proc.stderr.strip()}")
    data = json.loads(proc.stdout)
    ips = [
        answer["data"]
        for answer in data.get("Answer", [])
        if answer.get("type") == 1
        and re.match(r"^\d+\.\d+\.\d+\.\d+$", answer.get("data", ""))
    ]
    if not ips:
        raise RuntimeError(f"No A records for {host}: {proc.stdout}")
    return ips


def head_with_pinned_ip(url: str, host: str, ip: str, interface: str) -> str:
    cmd = [
        "curl",
        "--interface",
        interface,
        "--noproxy",
        "*",
        "--resolve",
        f"{host}:443:{ip}",
        "-fsSI",
        "--max-time",
        "90",
        url,
    ]
    proc = run(cmd, timeout=100)
    if proc.returncode != 0:
        raise RuntimeError(f"HEAD failed for {url}: {proc.stderr.strip()}")
    return proc.stdout


def discover_download(
    url: str,
    interface: str,
    doh_host: str,
    doh_ip: str,
) -> tuple[str, int, str, list[str]]:
    original_host = parse_host(url)
    original_ips = doh_resolve(original_host, interface, doh_host, doh_ip)
    headers = head_with_pinned_ip(url, original_host, original_ips[0], interface)

    location = parse_header_value(headers, "location")
    size_text = parse_header_value(headers, "x-linked-size")
    final_url = location or url
    final_host = parse_host(final_url)
    final_ips = doh_resolve(final_host, interface, doh_host, doh_ip)

    if size_text is None:
        final_headers = head_with_pinned_ip(final_url, final_host, final_ips[0], interface)
        size_text = parse_header_value(final_headers, "content-length")

    if size_text is None:
        raise RuntimeError("Could not determine remote file size from headers")

    return final_url, int(size_text), final_host, final_ips


def part_ranges(total: int, count: int) -> list[tuple[int, int]]:
    base = total // count
    ranges: list[tuple[int, int]] = []
    for i in range(count):
        start = i * base
        end = total - 1 if i == count - 1 else start + base - 1
        ranges.append((start, end))
    return ranges


def progress(parts_dir: Path, ranges: list[tuple[int, int]]) -> tuple[int, int]:
    done = 0
    for idx, (start, end) in enumerate(ranges):
        need = end - start + 1
        part = parts_dir / f"part-{idx:02d}"
        got = part.stat().st_size if part.exists() else 0
        done += min(got, need)
    return done, ranges[-1][1] + 1


def download_range(
    signed_url: str,
    host: str,
    ip: str,
    interface: str,
    start: int,
    end: int,
    part_path: Path,
    existing: int,
) -> tuple[int, str]:
    byte_range = f"{start + existing}-{end}"
    cmd = [
        "curl",
        "--interface",
        interface,
        "--noproxy",
        "*",
        "--http1.1",
        "--resolve",
        f"{host}:443:{ip}",
        "--fail",
        "--location",
        "--range",
        byte_range,
        "--connect-timeout",
        "30",
        "--speed-limit",
        "10240",
        "--speed-time",
        "60",
        "--silent",
        "--show-error",
        "--output",
        "-",
        signed_url,
    ]
    with part_path.open("ab") as output:
        proc = subprocess.Popen(
            cmd,
            stdout=output,
            stderr=subprocess.PIPE,
            text=False,
            env=clean_env(),
        )
        _, err = proc.communicate()
    return proc.returncode, (err or b"").decode("utf-8", "replace")


def assemble(dest: Path, parts_dir: Path, ranges: list[tuple[int, int]]) -> None:
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    with tmp.open("wb") as output:
        for idx, (start, end) in enumerate(ranges):
            need = end - start + 1
            part = parts_dir / f"part-{idx:02d}"
            got = part.stat().st_size if part.exists() else 0
            if got < need:
                raise RuntimeError(f"{part} incomplete: {got}/{need}")
            if got > need:
                with part.open("r+b") as handle:
                    handle.truncate(need)
            with part.open("rb") as source:
                shutil.copyfileobj(source, output, 1024 * 1024)

    expected = ranges[-1][1] + 1
    actual = tmp.stat().st_size
    if actual != expected:
        raise RuntimeError(f"assembled size mismatch: {actual}/{expected}")
    tmp.replace(dest)


def download_file(args: argparse.Namespace) -> None:
    out_name = args.output_filename or parse_filename(args.url)
    dest_dir = Path(args.destination_directory)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / out_name

    signed_url, total, final_host, ips = discover_download(
        args.url,
        args.interface,
        args.doh_host,
        args.doh_ip,
    )
    ranges = part_ranges(total, args.split)
    parts_dir = Path(str(dest) + ".parts")
    parts_dir.mkdir(parents=True, exist_ok=True)

    print(f"URL: {args.url}", flush=True)
    print(f"Destination: {dest}", flush=True)
    print(
        f"Mode: interface_resolve interface={args.interface} final_host={final_host} ips={ips}",
        flush=True,
    )
    print(f"Expected size: {total}", flush=True)

    if dest.exists() and dest.stat().st_size == total:
        print(f"Completed file already exists: {dest}", flush=True)
        return

    while True:
        todo: list[tuple[int, int, int, int]] = []
        for idx, (start, end) in enumerate(ranges):
            need = end - start + 1
            part = parts_dir / f"part-{idx:02d}"
            got = part.stat().st_size if part.exists() else 0
            if got > need:
                with part.open("r+b") as handle:
                    handle.truncate(need)
                got = need
            if got < need:
                todo.append((idx, start, end, got))

        if not todo:
            break

        results: queue.Queue[tuple[int, int, str]] = queue.Queue()

        def worker(task: tuple[int, int, int, int]) -> None:
            idx, start, end, got = task
            ip = ips[idx % len(ips)]
            part = parts_dir / f"part-{idx:02d}"
            print(f"START part-{idx:02d} {start + got}-{end} ip={ip}", flush=True)
            rc, err = download_range(
                signed_url,
                final_host,
                ip,
                args.interface,
                start,
                end,
                part,
                got,
            )
            results.put((idx, rc, err))

        threads = [
            threading.Thread(target=worker, args=(task,), daemon=True)
            for task in todo
        ]
        for thread in threads:
            thread.start()

        last_report = time.time()
        while any(thread.is_alive() for thread in threads):
            now = time.time()
            if now - last_report >= args.progress_interval:
                done, expected = progress(parts_dir, ranges)
                print(f"PROGRESS {done}/{expected} ({done / expected:.2%})", flush=True)
                last_report = now
            time.sleep(1)

        for thread in threads:
            thread.join()

        done, expected = progress(parts_dir, ranges)
        print(f"PROGRESS {done}/{expected} ({done / expected:.2%})", flush=True)

        failed = []
        while not results.empty():
            idx, rc, err = results.get()
            if rc != 0:
                failed.append((idx, rc, err.strip()[:240]))

        if failed:
            for idx, rc, err in failed:
                print(f"PART_RETRY part-{idx:02d} rc={rc} err={err}", flush=True)
            signed_url, size_check, final_host, ips = discover_download(
                args.url,
                args.interface,
                args.doh_host,
                args.doh_ip,
            )
            if size_check != total:
                raise RuntimeError(f"remote size changed: {size_check} != {total}")
            time.sleep(2)

    assemble(dest, parts_dir, ranges)
    print(f"Completed file: {dest}", flush=True)
    print(f"Completed size: {dest.stat().st_size}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("destination_directory")
    parser.add_argument("output_filename", nargs="?")
    parser.add_argument("--interface", default=os.environ.get("DIRECT_DL_INTERFACE", "en0"))
    parser.add_argument("--split", type=int, default=int(os.environ.get("DIRECT_DL_SPLIT", "8")))
    parser.add_argument("--doh-host", default=os.environ.get("DIRECT_DL_DOH_HOST", "dns.alidns.com"))
    parser.add_argument("--doh-ip", default=os.environ.get("DIRECT_DL_DOH_IP", "223.5.5.5"))
    parser.add_argument(
        "--progress-interval",
        type=int,
        default=int(os.environ.get("DIRECT_DL_PROGRESS_INTERVAL", "30")),
    )
    args = parser.parse_args()

    if args.split < 1:
        raise SystemExit("ERROR: --split must be >= 1")

    download_file(args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
