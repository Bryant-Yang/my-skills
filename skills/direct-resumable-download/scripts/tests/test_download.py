"""Protocol and resume regressions using real curl and isolated loopback fixtures."""
import argparse
import contextlib
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("downloader", Path(__file__).parents[1] / "direct_interface_resolve_download.py")
dl = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = dl
spec.loader.exec_module(dl)
REAL_POPEN = subprocess.Popen
DATA = bytes(range(256)) * 512


class Fixture(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def handle(self):
        try:
            super().handle()
        except ConnectionResetError:
            pass

    def do_GET(self):
        start, end = map(int, self.headers["Range"].removeprefix("bytes=").split("-"))
        if self.path == "/transient":
            self.send_response(503)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        ignored = self.path == "/ignore"
        body = DATA if ignored else DATA[start:end+1]
        self.send_response(200 if ignored else 206)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("ETag", '"changed"' if self.path == "/changed" else '"fixture"')
        if not ignored:
            offset = start + 1 if self.path == "/wrong" else start
            self.send_header("Content-Range", f"bytes {offset}-{end}/{len(DATA)}")
        self.end_headers()
        try:
            if self.path == "/drop" and start == 0:
                self.wfile.write(body[:5])
                self.wfile.flush()
                self.close_connection = True
            elif self.path == "/slow":
                time.sleep(2)
                self.wfile.write(body)
            else:
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass


class DownloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.remote = dl.RemoteFile("https://fixture.test/good", len(DATA), "fixture.test", ["127.0.0.1"], 'etag:"fixture"', '"fixture"')

    def tearDown(self):
        self.tmp.cleanup()

    def local_curl(self, cmd, **kwargs):
        # Only the test adapter removes HTTPS/interface pinning for loopback.
        # The production command is checked before adapting it.
        self.assertIn("--interface", cmd)
        self.assertIn("--resolve", cmd)
        self.assertNotIn("--location", cmd)
        self.assertEqual(cmd[cmd.index("--noproxy")+1], "*")
        self.assertFalse(dl.PROXY_ENV_NAMES.intersection(kwargs["env"]))
        cmd = list(cmd)
        for option in ("--interface", "--resolve"):
            i = cmd.index(option)
            del cmd[i:i+2]
        cmd[cmd.index("--proto")+1] = "=http"
        cmd[-1] = cmd[-1].replace("https://fixture.test", f"http://127.0.0.1:{self.server.server_port}")
        return REAL_POPEN(cmd, **kwargs)

    def transfer(self, path="good", start=0, end=15, existing=0, timeout=3):
        self.remote.url = "https://fixture.test/" + path
        with patch.object(dl.subprocess, "Popen", side_effect=self.local_curl):
            return dl.download_range(self.remote, "en0", start, end, self.root / "part", existing, timeout, threading.Event())

    def arguments(self, **updates):
        values = dict(url="https://fixture.test/good", destination_directory=str(self.root),
                      output_filename="model.bin", interface="en0", doh_host="dns.test", doh_ip="127.0.0.1",
                      split=3, small_file_threshold=0, sha256=hashlib.sha256(DATA).hexdigest(),
                      max_attempts=2, request_timeout=3, progress_interval=1)
        values.update(updates)
        return argparse.Namespace(**values)

    def test_relative_multihop_redirects_are_joined_and_each_host_pinned(self):
        headers = ["HTTP/2 302\r\nLocation: /api/cache\r\n\r\n",
                   "HTTP/2 307\r\nLocation: https://cdn.test/file\r\nX-Linked-Size: 10\r\nX-Linked-Etag: abc\r\n\r\n",
                   'HTTP/2 200\r\nContent-Length: 10\r\nETag: "abc"\r\n\r\n']
        with patch.object(dl, "doh_resolve", return_value=["192.0.2.1"]) as dns, patch.object(dl, "head_with_pinned_ip", side_effect=headers) as head:
            result = dl.discover_download("https://origin.test/file", "en0", "dns.test", "192.0.2.2")
        self.assertEqual(head.call_args_list[1].args[0], "https://origin.test/api/cache")
        self.assertEqual([c.args[0] for c in dns.call_args_list], ["origin.test", "cdn.test"])
        self.assertEqual(result.identity, "etag:abc")

    def test_redirect_downgrade_rejected(self):
        with patch.object(dl, "doh_resolve", return_value=["192.0.2.1"]), patch.object(dl, "head_with_pinned_ip", return_value="HTTP/2 302\r\nLocation: http://cdn.test/file\r\n\r\n"):
            with self.assertRaises(dl.DownloadError):
                dl.discover_download("https://origin.test/file", "en0", "dns.test", "192.0.2.2")

    def test_tiny_file_ranges_have_no_negative_or_empty_parts(self):
        self.assertEqual(dl.part_ranges(2, 8), [(0, 0), (1, 1)])

    def test_valid_range_written_exactly(self):
        self.assertTrue(self.transfer(start=16, end=31)[0])
        self.assertEqual((self.root / "part").read_bytes(), DATA[16:32])

    def test_ignored_partial_range_never_appended(self):
        (self.root / "part").write_bytes(b"keep")
        with self.assertRaises(dl.DownloadError):
            self.transfer("ignore", existing=4)
        self.assertEqual((self.root / "part").read_bytes(), b"keep")

    def test_single_whole_file_200_is_accepted(self):
        self.assertTrue(self.transfer("ignore", end=len(DATA)-1)[0])
        self.assertEqual((self.root / "part").read_bytes(), DATA)

    def test_whole_file_200_may_omit_head_validator(self):
        self.assertEqual(dl.validate_response("HTTP/1.1 200\r\nContent-Length: 16\r\n\r\n", 0, 15, 16, '"fixture"'), 200)

    def test_whole_file_200_may_weaken_same_head_etag(self):
        self.assertEqual(dl.validate_response('HTTP/1.1 200\r\nContent-Length: 16\r\nETag: W/"fixture"\r\n\r\n', 0, 15, 16, '"fixture"'), 200)

    def test_partial_206_must_keep_validator(self):
        with self.assertRaises(dl.DownloadError):
            dl.validate_response("HTTP/1.1 206\r\nContent-Length: 8\r\nContent-Range: bytes 0-7/16\r\n\r\n", 0, 7, 16, '"fixture"')
        with self.assertRaises(dl.DownloadError):
            dl.validate_response('HTTP/1.1 206\r\nContent-Length: 8\r\nContent-Range: bytes 0-7/16\r\nETag: W/"fixture"\r\n\r\n', 0, 7, 16, '"fixture"')

    def test_wrong_content_range_rejected(self):
        with self.assertRaises(dl.DownloadError):
            self.transfer("wrong")
        self.assertFalse((self.root / "part").exists())

    def test_changed_get_validator_rejected(self):
        with self.assertRaises(dl.DownloadError):
            self.transfer("changed")
        self.assertFalse((self.root / "part").exists())

    def test_validated_transport_partial_can_resume(self):
        self.assertFalse(self.transfer("drop")[0])
        self.assertEqual((self.root / "part").read_bytes(), DATA[:5])
        self.assertTrue(self.transfer("drop", existing=5)[0])
        self.assertEqual((self.root / "part").read_bytes(), DATA[:16])

    def test_request_timeout_is_bounded(self):
        start = time.monotonic()
        self.assertFalse(self.transfer("slow", timeout=1)[0])
        self.assertLess(time.monotonic()-start, 1.8)

    def test_legacy_parts_not_adopted(self):
        parts = self.root / "parts"
        parts.mkdir()
        (parts / "part-00").write_bytes(b"old")
        with self.assertRaises(dl.DownloadError):
            dl.prepare_parts(parts, self.remote.url, self.remote, [(0, 15)], None)
        self.assertEqual((parts / "part-00").read_bytes(), b"old")

    def test_changed_layout_identity_or_url_rejected(self):
        parts = self.root / "parts"
        dl.prepare_parts(parts, self.remote.url, self.remote, [(0, 15)], None)
        with self.assertRaises(dl.DownloadError):
            dl.prepare_parts(parts, self.remote.url, self.remote, [(0, 7), (8, 15)], None)
        with self.assertRaises(dl.DownloadError):
            dl.prepare_parts(parts, self.remote.url + "?changed", self.remote, [(0, 15)], None)
        self.remote.identity = 'etag:"new"'
        with self.assertRaises(dl.DownloadError):
            dl.prepare_parts(parts, self.remote.url, self.remote, [(0, 15)], None)

    def test_signed_url_not_persisted(self):
        url = self.remote.url + "?signature=private-value"
        dl.prepare_parts(self.root / "parts", url, self.remote, [(0, 15)], None)
        self.assertNotIn("private-value", (self.root / "parts/manifest.json").read_text())

    def test_checksum_failure_preserves_existing_destination(self):
        dest, parts = self.root / "dest", self.root / "parts"
        dest.write_bytes(b"original")
        parts.mkdir()
        (parts / "part-00").write_bytes(b"bad")
        with self.assertRaises(dl.DownloadError):
            dl.assemble(dest, parts, [(0, 2)], "0"*64)
        self.assertEqual(dest.read_bytes(), b"original")
        self.assertEqual((parts / "part-00").read_bytes(), b"bad")

    def test_oversized_parts_not_truncated(self):
        parts = self.root / "parts"
        parts.mkdir()
        (parts / "part-00").write_bytes(b"oversized")
        with self.assertRaises(dl.DownloadError):
            dl.assemble(self.root / "dest", parts, [(0, 2)], None)
        self.assertEqual((parts / "part-00").read_bytes(), b"oversized")

    def test_complete_multirange_download_and_revalidation(self):
        with patch.object(dl, "discover_download", return_value=self.remote), patch.object(dl.subprocess, "Popen", side_effect=self.local_curl), contextlib.redirect_stdout(io.StringIO()):
            dl.download_file(self.arguments())
            self.assertEqual((self.root / "model.bin").read_bytes(), DATA)
            with patch.object(dl, "download_range", side_effect=AssertionError("Should rehash instead of downloading")):
                dl.download_file(self.arguments())

    def test_size_only_existing_destination_is_not_trusted(self):
        (self.root / "model.bin").write_bytes(b"x" * len(DATA))
        with patch.object(dl, "discover_download", return_value=self.remote), patch.object(dl.subprocess, "Popen", side_effect=self.local_curl), contextlib.redirect_stdout(io.StringIO()):
            dl.download_file(self.arguments())
        self.assertEqual((self.root / "model.bin").read_bytes(), DATA)

    def test_retry_limit_stops(self):
        with patch.object(dl, "discover_download", return_value=self.remote), patch.object(dl, "download_range", return_value=(False, "network failed")) as transfer, patch.object(dl.time, "sleep"), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(dl.DownloadError, "Retry limit"):
                dl.download_file(self.arguments(split=1))
        self.assertEqual(transfer.call_count, 2)

    def test_no_validator_or_hash_does_not_retry_unidentified_bytes(self):
        self.remote.identity = self.remote.if_range = None
        with patch.object(dl, "discover_download", return_value=self.remote), patch.object(dl, "download_range", return_value=(False, "network failed")) as transfer, contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(dl.DownloadError, "Cannot safely"):
                dl.download_file(self.arguments(sha256=None))
        self.assertEqual(transfer.call_count, 1)

    def test_live_transfer_resume_from_metadata(self):
        args = self.arguments(split=1)
        parts = self.root / "model.bin.parts"
        dl.prepare_parts(parts, args.url, self.remote, [(0, len(DATA)-1)], args.sha256)
        (parts / "part-00").write_bytes(DATA[:500])
        with patch.object(dl, "discover_download", return_value=self.remote), patch.object(dl.subprocess, "Popen", side_effect=self.local_curl), contextlib.redirect_stdout(io.StringIO()):
            dl.download_file(args)
        self.assertEqual((self.root / "model.bin").read_bytes(), DATA)

    def test_recorded_completed_hash_rejects_corrupted_parts(self):
        args = self.arguments(split=1, sha256=None)
        parts = self.root / "model.bin.parts"
        metadata = dl.prepare_parts(parts, args.url, self.remote, [(0, len(DATA)-1)], None)
        metadata["completed_sha256"] = hashlib.sha256(DATA).hexdigest()
        dl.write_metadata(parts / "manifest.json", metadata)
        (parts / "part-00").write_bytes(b"x" * len(DATA))
        (self.root / "model.bin").write_bytes(b"original")
        with patch.object(dl, "discover_download", return_value=self.remote), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(dl.DownloadError, "SHA-256 mismatch"):
                dl.download_file(args)
        self.assertEqual((self.root / "model.bin").read_bytes(), b"original")

    def test_small_file_automatically_uses_single_part(self):
        with patch.object(dl, "discover_download", return_value=self.remote), patch.object(dl.subprocess, "Popen", side_effect=self.local_curl), contextlib.redirect_stdout(io.StringIO()):
            dl.download_file(self.arguments(small_file_threshold=len(DATA)))
        saved = json.loads((self.root / "model.bin.parts/manifest.json").read_text())
        self.assertEqual(saved["ranges"], [[0, len(DATA)-1]])

    def test_protocol_error_is_not_retried(self):
        with patch.object(dl, "discover_download", return_value=self.remote), patch.object(dl, "download_range", side_effect=dl.DownloadError("Invalid range")) as transfer, contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(dl.DownloadError, "Invalid range"):
                dl.download_file(self.arguments(split=1))
        self.assertEqual(transfer.call_count, 1)

    def test_http_503_is_transient_without_appending(self):
        self.assertFalse(self.transfer("transient")[0])
        self.assertFalse((self.root / "part").exists())


if __name__ == "__main__":
    unittest.main()
