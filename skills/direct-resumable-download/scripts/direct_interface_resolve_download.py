#!/usr/bin/env python3
"""Verified range resume with process-local interface/DoH/TLS pinning."""
from __future__ import annotations

import argparse
from concurrent.futures import FIRST_EXCEPTION, ThreadPoolExecutor, wait
from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urljoin, urlsplit, unquote

PROXY_ENV_NAMES = {"http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"}


class DownloadError(RuntimeError):
    """Protocol/integrity failures that must not become successful downloads."""


@dataclass
class RemoteFile:
    url: str
    size: int
    host: str
    ips: list[str]
    identity: str | None
    if_range: str | None


def clean_env():
    env = {k: v for k, v in os.environ.items() if k not in PROXY_ENV_NAMES}
    env.update(NO_PROXY="*", no_proxy="*")
    return env


def run(cmd, timeout=120):
    return subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, env=clean_env())


def parse_header_value(headers, name):
    block = re.split(r"\r?\n\r?\n", headers.strip())[-1]
    values = [line.split(":", 1)[1].strip() for line in block.splitlines()
              if line.lower().startswith(name.lower() + ":")]
    return values[-1] if values else None


def status_code(headers):
    codes = re.findall(r"^HTTP/\S+ (\d{3})", headers, re.M)
    if not codes:
        raise DownloadError("Missing HTTP response status")
    return int(codes[-1])


def parse_host(url):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.port not in (None, 443)
            or parsed.username or parsed.password):
        raise DownloadError("Only HTTPS port 443 without embedded credentials is supported")
    return parsed.hostname


def parse_filename(url):
    return unquote(urlsplit(url).path.rstrip("/")).rsplit("/", 1)[-1] or "download.bin"


def safe_error(error):
    return re.sub(r"https?://\S+", "<URL>", str(error))[:240]


def doh_resolve(host, interface, doh_host, doh_ip):
    proc = run(["curl", "--interface", interface, "--noproxy", "*", "--connect-to",
                f"{doh_host}:443:{doh_ip}", "-fsS", "--max-time", "30",
                f"https://{doh_host}/resolve?name={host}&type=A"], timeout=40)
    if proc.returncode:
        raise DownloadError(f"DoH failed for {host}: {safe_error(proc.stderr)}")
    ips = [a["data"] for a in json.loads(proc.stdout).get("Answer", [])
           if a.get("type") == 1 and re.fullmatch(r"\d+\.\d+\.\d+\.\d+", a.get("data", ""))]
    if not ips:
        raise DownloadError(f"DoH returned no IPv4 addresses for {host}")
    return ips


def head_with_pinned_ip(url, host, ip, interface):
    proc = run(["curl", "--interface", interface, "--noproxy", "*", "--resolve",
                f"{host}:443:{ip}", "--proto", "=https", "-fsSI", "--connect-timeout", "30",
                "--max-time", "90", "-H", "Accept-Encoding: identity", url], timeout=100)
    if proc.returncode:
        raise DownloadError(f"HEAD failed for {host}: {safe_error(proc.stderr)}")
    return proc.stdout


def discover_download(url, interface, doh_host, doh_ip):
    seen, resolved = set(), {}
    linked_size = linked_etag = None
    for _ in range(10):
        host = parse_host(url)
        if url in seen:
            raise DownloadError("Redirect loop")
        seen.add(url)
        if host not in resolved:
            resolved[host] = doh_resolve(host, interface, doh_host, doh_ip)
        ips = resolved[host]
        headers = head_with_pinned_ip(url, host, ips[0], interface)
        code = status_code(headers)
        linked_size = parse_header_value(headers, "x-linked-size") or linked_size
        linked_etag = parse_header_value(headers, "x-linked-etag") or linked_etag
        if code in (301, 302, 303, 307, 308):
            location = parse_header_value(headers, "location")
            if not location:
                raise DownloadError("Redirect has no Location")
            url = urljoin(url, location)
            continue
        if code != 200:
            raise DownloadError(f"Unexpected HEAD HTTP {code}")
        length = parse_header_value(headers, "content-length")
        if length is None or not length.isdigit() or int(length) < 1:
            raise DownloadError("Could not determine a positive remote file size")
        size = int(length)
        if linked_size is not None and int(linked_size) != size:
            raise DownloadError("Linked size disagrees with final Content-Length")
        encoding = parse_header_value(headers, "content-encoding")
        if encoding and encoding.lower() != "identity":
            raise DownloadError("Encoded responses cannot be byte-range resumed")
        etag = parse_header_value(headers, "etag")
        strong_etag = etag if etag and not etag.startswith("W/") else None
        modified = parse_header_value(headers, "last-modified")
        if linked_etag:
            identity = "etag:" + linked_etag
        elif strong_etag:
            identity = "etag:" + strong_etag
        else:
            identity = "modified:" + modified if modified else None
        return RemoteFile(url, size, host, ips, identity, strong_etag or modified)
    raise DownloadError("Too many redirects (maximum 10)")


def part_ranges(total, count):
    count = min(total, count)
    base = total // count
    return [(i * base, total - 1 if i == count - 1 else (i + 1) * base - 1) for i in range(count)]


def validate_response(headers, start, end, total, if_range=None):
    code = status_code(headers)
    if code == 206:
        if parse_header_value(headers, "content-range") != f"bytes {start}-{end}/{total}":
            raise DownloadError("Incorrect Content-Range")
    elif not (code == 200 and start == 0 and end == total - 1):
        raise DownloadError(f"HTTP {code}: server did not honor the requested range")
    length = parse_header_value(headers, "content-length")
    if length is not None and length != str(end - start + 1):
        raise DownloadError("Response Content-Length disagrees with requested range")
    encoding = parse_header_value(headers, "content-encoding")
    if encoding and encoding.lower() != "identity":
        raise DownloadError("Encoded range response")
    if if_range:
        field = "etag" if if_range.startswith('"') else "last-modified"
        received = parse_header_value(headers, field)
        # Mirrors may weaken/omit HEAD's ETag on a full 200 GET. This is not
        # range reuse: require exact bytes/hash, but never relax a 206 validator.
        comparable = received.removeprefix("W/") if code == 200 and received and field == "etag" else received
        if comparable != if_range and (code == 206 or received is not None):
            raise DownloadError("Response validator changed or disappeared")
    return code


def download_range(remote, interface, start, end, part_path, existing, timeout, stop, ip_index=0):
    first = start + existing
    need = end - first + 1
    with tempfile.TemporaryDirectory(prefix=".attempt-", dir=part_path.parent) as attempt:
        body, header = Path(attempt) / "body", Path(attempt) / "headers"
        cmd = ["curl", "--interface", interface, "--noproxy", "*", "--http1.1",
               "--resolve", f"{remote.host}:443:{remote.ips[ip_index % len(remote.ips)]}",
               "--proto", "=https", "--range", f"{first}-{end}", "--connect-timeout", "30",
               "--max-time", str(timeout), "--max-filesize", str(need), "--speed-limit", "10240",
               "--speed-time", "60", "--silent", "--show-error", "-H", "Accept-Encoding: identity",
               "--dump-header", str(header), "--output", str(body)]
        if remote.if_range:
            cmd.extend(["-H", "If-Range: " + remote.if_range])
        cmd.append(remote.url)
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=clean_env())
        validated = False
        try:
            deadline = time.monotonic() + timeout + 10
            while proc.poll() is None:
                if stop.is_set() or time.monotonic() > deadline:
                    raise DownloadError("Transfer cancelled or exceeded request timeout")
                if not validated and header.exists():
                    text = header.read_text(errors="replace")
                    if text.endswith("\n\n"):
                        code = status_code(text)
                        if 100 <= code < 200:
                            time.sleep(0.05)
                            continue
                        if code in (408, 429) or code >= 500:
                            proc.kill()
                            proc.communicate()
                            return False, f"Transient HTTP {code}"
                        validate_response(text, first, end, remote.size, remote.if_range)
                        validated = True
                time.sleep(0.05)
            _, err = proc.communicate()
            text = header.read_text(errors="replace") if header.exists() else ""
            if not text.strip():
                return False, safe_error((err or b"").decode(errors="replace")) or "No response headers"
            code = status_code(text)
            if code in (408, 429) or code >= 500:
                return False, f"Transient HTTP {code}"
            validate_response(text, first, end, remote.size, remote.if_range)
            got = body.stat().st_size if body.exists() else 0
            if got > need:
                raise DownloadError("Response body exceeds the requested range")
            if not proc.returncode and got != need:
                raise DownloadError("Successful response has a short body")
            # Only validated 206 transport failures may contribute resumable bytes.
            if got and (code == 206 or (not proc.returncode and got == need)):
                with part_path.open("ab") as dest, body.open("rb") as source:
                    shutil.copyfileobj(source, dest, 1024 * 1024)
            return proc.returncode == 0, safe_error((err or b"").decode(errors="replace"))
        finally:
            if proc.poll() is None:
                proc.kill()
            if proc.stderr and not proc.stderr.closed:
                proc.communicate()
            else:
                proc.wait()


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_metadata(path, metadata):
    with tempfile.NamedTemporaryFile(mode="w", prefix=".manifest-", dir=path.parent, delete=False) as stream:
        tmp = Path(stream.name)
        try:
            stream.write(json.dumps(metadata, indent=2) + "\n")
            stream.flush()
            tmp.replace(path)
        finally:
            tmp.unlink(missing_ok=True)


def prepare_parts(parts_dir, url, remote, ranges, expected_hash):
    metadata = {"version": 2, "source_url_sha256": hashlib.sha256(url.encode()).hexdigest(),
                "size": remote.size, "identity": remote.identity, "ranges": [list(r) for r in ranges],
                "expected_sha256": expected_hash}
    path = parts_dir / "manifest.json"
    if parts_dir.is_symlink():
        raise DownloadError("Parts directory must not be a symlink")
    parts_dir.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise DownloadError("Resume manifest must be a regular file")
    if path.exists():
        saved = json.loads(path.read_text())
        if not isinstance(saved, dict):
            raise DownloadError("Invalid resume manifest")
        if any(saved.get(k) != v for k, v in metadata.items()):
            raise DownloadError("Resume identity/layout changed; keep old parts and use a new destination")
        if not remote.identity and not expected_hash:
            raise DownloadError("Cannot safely resume without a validator or expected SHA-256")
        return saved
    if any(parts_dir.iterdir()):
        raise DownloadError("Legacy/unidentified parts cannot be adopted; use a new destination")
    write_metadata(path, metadata)
    return metadata


def assemble(dest, parts_dir, ranges, expected_hash):
    with tempfile.NamedTemporaryFile(prefix=".assemble-", dir=dest.parent, delete=False) as output:
        tmp = Path(output.name)
        try:
            for i, (start, end) in enumerate(ranges):
                part = parts_dir / f"part-{i:02d}"
                if not part.is_file() or part.is_symlink() or part.stat().st_size != end-start+1:
                    raise DownloadError(f"part-{i:02d} is not exactly complete")
                with part.open("rb") as source:
                    shutil.copyfileobj(source, output, 1024 * 1024)
            output.flush()
            digest = sha256(tmp)
            if expected_hash and digest != expected_hash:
                raise DownloadError("SHA-256 mismatch; final destination not replaced; parts retained")
            tmp.replace(dest)
            return digest
        finally:
            tmp.unlink(missing_ok=True)


def download_file(args):
    name = args.output_filename or parse_filename(args.url)
    if name in (".", "..") or Path(name).name != name or "/" in name or "\\" in name:
        raise DownloadError("Output filename must be a single filename")
    directory = Path(args.destination_directory)
    directory.mkdir(parents=True, exist_ok=True)
    dest = directory / name
    if dest.is_symlink():
        raise DownloadError("Destination must not be a symlink")
    lock_path = Path(str(dest) + ".download.lock")
    if lock_path.is_symlink():
        raise DownloadError("Download lock must not be a symlink")
    with lock_path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise DownloadError("Another downloader owns this destination") from None
        remote = discover_download(args.url, args.interface, args.doh_host, args.doh_ip)
        count = 1 if (remote.size <= args.small_file_threshold or not (remote.identity or args.sha256)) else args.split
        ranges = part_ranges(remote.size, count)
        parts_dir = Path(str(dest) + ".parts")
        print(f"Source host: {parse_host(args.url)}; final host: {remote.host}", flush=True)
        print(f"Destination: {dest}\nMode: interface_resolve interface={args.interface}\nExpected size: {remote.size}; parts: {len(ranges)}", flush=True)
        if dest.is_file() and dest.stat().st_size == remote.size and args.sha256 and sha256(dest) == args.sha256:
            print("Completed file verified against expected SHA-256", flush=True)
            return
        metadata = prepare_parts(parts_dir, args.url, remote, ranges, args.sha256)
        if (dest.is_file() and dest.stat().st_size == remote.size and metadata.get("completed_sha256")
                and sha256(dest) == metadata["completed_sha256"]):
            print("Completed file verified against recorded SHA-256", flush=True)
            return
        stop = threading.Event()
        try:
            for attempt in range(args.max_attempts):
                todo = []
                for i, (start, end) in enumerate(ranges):
                    part = parts_dir / f"part-{i:02d}"
                    if part.is_symlink():
                        raise DownloadError("Part file must not be a symlink")
                    got = part.stat().st_size if part.exists() else 0
                    if got > end-start+1:
                        raise DownloadError("Oversized part; refusing to truncate/adopt it")
                    if got < end-start+1:
                        todo.append((start, end, part, got))
                if not todo:
                    break
                with ThreadPoolExecutor(max_workers=len(todo)) as pool:
                    futures = [pool.submit(download_range, remote, args.interface, *task,
                                           args.request_timeout, stop, ip_index=i) for i, task in enumerate(todo)]
                    pending = set(futures)
                    try:
                        while pending:
                            completed, pending = wait(pending, timeout=args.progress_interval, return_when=FIRST_EXCEPTION)
                            for future in completed:
                                future.result()
                            done = sum(min((parts_dir / f"part-{i:02d}").stat().st_size, end-start+1)
                                       for i, (start, end) in enumerate(ranges) if (parts_dir / f"part-{i:02d}").exists())
                            print(f"PROGRESS {done}/{remote.size} ({done/remote.size:.2%})", flush=True)
                    except BaseException:
                        stop.set()
                        raise
                    failed = [message for future in futures for ok, message in [future.result()] if not ok]
                if not failed:
                    break
                if not remote.identity and not args.sha256:
                    raise DownloadError("Cannot safely retry/resume without a validator or expected SHA-256")
                if attempt + 1 == args.max_attempts:
                    raise DownloadError(f"Retry limit reached ({args.max_attempts} attempts): {failed[0]}")
                print(f"RETRY attempt {attempt+2}/{args.max_attempts}: {failed[0]}", flush=True)
                refreshed = discover_download(args.url, args.interface, args.doh_host, args.doh_ip)
                if (refreshed.size, refreshed.identity) != (remote.size, remote.identity):
                    raise DownloadError("Remote identity changed during transfer")
                remote = refreshed
                time.sleep(min(2**attempt, 8))
            digest = assemble(dest, parts_dir, ranges, args.sha256 or metadata.get("completed_sha256"))
            metadata["completed_sha256"] = digest
            write_metadata(parts_dir / "manifest.json", metadata)
            print(f"Completed file: {dest}\nCompleted size: {dest.stat().st_size}\nSHA-256: {digest}", flush=True)
        finally:
            stop.set()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("destination_directory")
    parser.add_argument("output_filename", nargs="?")
    parser.add_argument("--interface", default=os.environ.get("DIRECT_DL_INTERFACE", "en0"))
    parser.add_argument("--split", type=int, default=int(os.environ.get("DIRECT_DL_SPLIT", "8")))
    parser.add_argument("--doh-host", default=os.environ.get("DIRECT_DL_DOH_HOST", "dns.alidns.com"))
    parser.add_argument("--doh-ip", default=os.environ.get("DIRECT_DL_DOH_IP", "223.5.5.5"))
    parser.add_argument("--progress-interval", type=int, default=int(os.environ.get("DIRECT_DL_PROGRESS_INTERVAL", "30")))
    parser.add_argument("--max-attempts", type=int, default=int(os.environ.get("DIRECT_DL_MAX_ATTEMPTS", "4")))
    parser.add_argument("--request-timeout", type=int, default=int(os.environ.get("DIRECT_DL_REQUEST_TIMEOUT", "300")))
    parser.add_argument("--small-file-threshold", type=int, default=int(os.environ.get("DIRECT_DL_SMALL_FILE_THRESHOLD", str(32*1024*1024))))
    parser.add_argument("--sha256", default=os.environ.get("DIRECT_DL_SHA256"))
    args = parser.parse_args()
    if min(args.split, args.max_attempts, args.request_timeout, args.progress_interval) < 1 or args.small_file_threshold < 0:
        parser.error("Counts/timeouts must be positive; small-file threshold must be nonnegative")
    if args.sha256:
        args.sha256 = args.sha256.lower()
        if not re.fullmatch(r"[0-9a-f]{64}", args.sha256):
            parser.error("SHA-256 must contain 64 hexadecimal characters")
    download_file(args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except (DownloadError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(f"ERROR: {safe_error(error)}", file=sys.stderr)
        raise SystemExit(1)
