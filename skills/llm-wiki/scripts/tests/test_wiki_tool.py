from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "wiki_tool.py"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def page_text(
    *,
    page_id: str,
    title: str,
    page_type: str,
    source_ref: str,
    source_hash: str = "",
    body: str = "",
) -> str:
    hash_line = f"source_sha256: {source_hash}\n" if source_hash else ""
    return f"""---
id: {page_id}
title: {title}
type: {page_type}
summary: Test page for {title}.
status: active
created: 2026-07-26
updated: 2026-07-26
source_refs:
  - {source_ref}
depends_on:
aliases:
tags:
{hash_line}---

# {title}

{body}
"""


class WikiToolTests(unittest.TestCase):
    def init_wiki(self, root: Path) -> None:
        result = run_cli(
            "init",
            str(root),
            "--title",
            "Agent Engineering",
            "--domain",
            "Research on reliable agent systems",
            "--language",
            "zh",
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_init_is_idempotent_and_preserves_existing_agents(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "wiki"
            root.mkdir()
            agents = root / "AGENTS.md"
            agents.write_text("# Existing project rules\n", encoding="utf-8")

            self.init_wiki(root)
            first = json.loads(
                run_cli(
                    "init",
                    str(root),
                    "--title",
                    "Agent Engineering",
                    "--domain",
                    "Research",
                ).stdout
            )

            self.assertEqual(agents.read_text(encoding="utf-8"), "# Existing project rules\n")
            self.assertIn("AGENTS.md", first["preserved_files"])
            self.assertTrue((root / "WIKI.md").is_file())
            self.assertTrue((root / "raw" / "papers").is_dir())
            self.assertTrue((root / "wiki" / "meta" / "schema-proposals.md").is_file())

            lint = run_cli("lint", str(root), "--json")
            self.assertEqual(lint.returncode, 0, lint.stdout + lint.stderr)
            lint_data = json.loads(lint.stdout)
            codes = {finding["code"] for finding in lint_data["findings"]}
            self.assertIn("AGENTS_NO_WIKI_POINTER", codes)

    def test_valid_source_hash_then_raw_mutation_fails_lint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "wiki"
            self.init_wiki(root)
            raw = root / "raw" / "notes" / "atlas-a.md"
            raw.write_text("Atlas passed 72% under the standard rubric.\n", encoding="utf-8")
            digest = hashlib.sha256(raw.read_bytes()).hexdigest()

            source_page = root / "wiki" / "sources" / "source-atlas-a.md"
            source_page.write_text(
                page_text(
                    page_id="source-atlas-a",
                    title="Atlas evaluation A",
                    page_type="source",
                    source_ref="raw/notes/atlas-a.md",
                    source_hash=digest,
                    body='Atlas passed 72% under the standard rubric '
                    '([raw](../../raw/notes/atlas-a.md)).',
                ),
                encoding="utf-8",
            )
            concept_page = root / "wiki" / "concepts" / "atlas-evaluation.md"
            concept_page.write_text(
                page_text(
                    page_id="atlas-evaluation",
                    title="Atlas evaluation",
                    page_type="concept",
                    source_ref="raw/notes/atlas-a.md",
                    body="The standard rubric reports 72%. [[source-atlas-a]]",
                ),
                encoding="utf-8",
            )
            reindex = run_cli("reindex", str(root))
            self.assertEqual(reindex.returncode, 0, reindex.stderr)

            clean = run_cli("lint", str(root), "--json")
            self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)
            clean_codes = {
                finding["code"] for finding in json.loads(clean.stdout)["findings"]
            }
            self.assertNotIn("RAW_HASH_MISMATCH", clean_codes)

            raw.write_text(
                "Atlas passed 61% under a changed rubric.\n", encoding="utf-8"
            )
            changed = run_cli("lint", str(root), "--json")
            self.assertEqual(changed.returncode, 1, changed.stdout + changed.stderr)
            changed_codes = {
                finding["code"] for finding in json.loads(changed.stdout)["findings"]
            }
            self.assertIn("RAW_HASH_MISMATCH", changed_codes)

    def test_lint_catches_missing_index_and_broken_wikilink(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "wiki"
            self.init_wiki(root)
            raw = root / "raw" / "notes" / "atlas.md"
            raw.write_text("Atlas source.\n", encoding="utf-8")
            digest = hashlib.sha256(raw.read_bytes()).hexdigest()
            page = root / "wiki" / "sources" / "source-atlas.md"
            page.write_text(
                page_text(
                    page_id="source-atlas",
                    title="Atlas source",
                    page_type="source",
                    source_ref="raw/notes/atlas.md",
                    source_hash=digest,
                    body="This points to [[missing-page]].",
                ),
                encoding="utf-8",
            )

            lint = run_cli("lint", str(root), "--json")
            self.assertEqual(lint.returncode, 1, lint.stdout + lint.stderr)
            codes = {finding["code"] for finding in json.loads(lint.stdout)["findings"]}
            self.assertIn("INDEX_MISSING", codes)
            self.assertIn("BROKEN_WIKILINK", codes)

    def test_log_rejects_unknown_operation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "wiki"
            self.init_wiki(root)
            result = run_cli(
                "log",
                str(root),
                "--operation",
                "query",
                "--operation-id",
                "query:read-only",
                "--outcome",
                "success",
                "--subject",
                "read-only query",
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("Unsupported operation", result.stderr)

    def test_evidence_literal_drift_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "wiki"
            self.init_wiki(root)
            raw = root / "raw" / "notes" / "votes.md"
            raw.write_text("The proposal received 103 upvotes.\n", encoding="utf-8")
            digest = hashlib.sha256(raw.read_bytes()).hexdigest()
            page = root / "wiki" / "sources" / "source-votes.md"
            page.write_text(
                page_text(
                    page_id="source-votes",
                    title="Vote result",
                    page_type="source",
                    source_ref="raw/notes/votes.md",
                    source_hash=digest,
                    body="The proposal received 3020 upvotes.",
                ),
                encoding="utf-8",
            )
            self.assertEqual(run_cli("reindex", str(root)).returncode, 0)

            lint = run_cli("lint", str(root), "--json")
            self.assertEqual(lint.returncode, 0, lint.stdout + lint.stderr)
            findings = json.loads(lint.stdout)["findings"]
            suspects = [
                finding
                for finding in findings
                if finding["code"] == "EVIDENCE_LITERAL_NOT_FOUND"
            ]
            self.assertTrue(suspects)
            self.assertIn("3020", suspects[0]["message"])

    def test_reindex_refuses_malformed_page_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "wiki"
            self.init_wiki(root)
            malformed = root / "wiki" / "concepts" / "Bad Name.md"
            malformed.write_text(
                """---
id: Bad Name
title: Bad
type: concept
---

# Bad
""",
                encoding="utf-8",
            )
            result = run_cli("reindex", str(root))
            self.assertEqual(result.returncode, 1)
            self.assertIn("FRONTMATTER_MISSING_FIELDS", result.stdout)
            self.assertIn("PAGE_ID_INVALID", result.stdout)

    def test_frontmatter_rejects_duplicates_empty_items_and_invalid_dates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "wiki"
            self.init_wiki(root)
            malformed = root / "wiki" / "concepts" / "bad-contract.md"
            malformed.write_text(
                """---
id: bad-contract
id: duplicate
title: Bad contract
type: concept
summary: Broken frontmatter.
status: active
created: 2026-02-31
updated: 2999-01-01
source_refs:
EMPTY_LIST_ITEM
depends_on:
aliases:
tags:
---

# Bad
""".replace("EMPTY_LIST_ITEM", "  - "),
                encoding="utf-8",
            )
            lint = run_cli("lint", str(root), "--json")
            self.assertEqual(lint.returncode, 1, lint.stdout + lint.stderr)
            codes = {finding["code"] for finding in json.loads(lint.stdout)["findings"]}
            self.assertIn("FRONTMATTER_INVALID", codes)

            malformed.write_text(
                page_text(
                    page_id="bad-contract",
                    title="Bad contract",
                    page_type="concept",
                    source_ref="raw/notes/missing.md",
                ).replace("created: 2026-07-26", "created: 2026-02-31")
                .replace("updated: 2026-07-26", "updated: 2999-01-01"),
                encoding="utf-8",
            )
            lint = run_cli("lint", str(root), "--json")
            codes = {finding["code"] for finding in json.loads(lint.stdout)["findings"]}
            self.assertIn("PAGE_DATE_INVALID", codes)
            self.assertIn("PAGE_DATE_IN_FUTURE", codes)

    def test_init_and_reindex_refuse_ambiguous_or_fake_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            root.mkdir()
            (root / "app.py").write_text("print('keep me')\n", encoding="utf-8")

            refused = run_cli("init", str(root))
            self.assertEqual(refused.returncode, 2)
            self.assertIn("non-empty directory", refused.stderr)
            self.assertFalse((root / "WIKI.md").exists())

            fake_reindex = run_cli("reindex", str(root))
            self.assertEqual(fake_reindex.returncode, 2)
            self.assertIn("Not an initialized wiki root", fake_reindex.stderr)

            allowed = run_cli("init", str(root), "--allow-existing")
            self.assertEqual(allowed.returncode, 0, allowed.stderr)
            self.assertEqual(
                (root / "app.py").read_text(encoding="utf-8"), "print('keep me')\n"
            )

    def test_init_records_failed_gate_for_preserved_invalid_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            root.mkdir()
            (root / "WIKI.md").write_text("# Invalid contract\n", encoding="utf-8")

            result = run_cli(
                "init",
                str(root),
                "--allow-existing",
                "--title",
                "Preserved Wiki",
                "--domain",
                "Existing project",
            )

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data["init_outcome"], "failed")
            self.assertGreater(data["lint_errors"], 0)
            log_text = (root / "wiki" / "log.md").read_text(encoding="utf-8")
            self.assertIn("- operation_id: init:workspace", log_text)
            self.assertIn("- outcome: failed", log_text)
            self.assertNotIn("- outcome: success", log_text)

    def test_symlink_boundaries_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            root = base / "wiki"
            self.init_wiki(root)
            outside = base / "outside.md"
            outside.write_text("A source outside the wiki.\n", encoding="utf-8")
            linked = root / "raw" / "notes" / "linked.md"
            linked.symlink_to(outside)
            digest = hashlib.sha256(outside.read_bytes()).hexdigest()
            (root / "wiki" / "sources" / "source-linked.md").write_text(
                page_text(
                    page_id="source-linked",
                    title="Linked source",
                    page_type="source",
                    source_ref="raw/notes/linked.md",
                    source_hash=digest,
                ),
                encoding="utf-8",
            )

            lint = run_cli("lint", str(root), "--json")
            self.assertEqual(lint.returncode, 1, lint.stdout + lint.stderr)
            codes = {finding["code"] for finding in json.loads(lint.stdout)["findings"]}
            self.assertIn("SOURCE_REF_OUTSIDE_RAW", codes)
            self.assertIn("RAW_SYMLINK_UNSUPPORTED", codes)

            index = root / "wiki" / "index.md"
            index.unlink()
            index.symlink_to(outside)
            reindex = run_cli("reindex", str(root))
            self.assertEqual(reindex.returncode, 2)
            self.assertIn("must not be a symlink", reindex.stderr)

    def test_lint_requires_raw_root_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "wiki"
            self.init_wiki(root)
            raw_root = root / "raw"
            moved_raw = root / "raw-missing-probe"
            raw_root.rename(moved_raw)

            missing = run_cli("lint", str(root), "--json")
            self.assertEqual(missing.returncode, 1, missing.stdout + missing.stderr)
            missing_codes = {
                finding["code"]
                for finding in json.loads(missing.stdout)["findings"]
            }
            self.assertIn("RAW_ROOT_MISSING", missing_codes)

            raw_root.write_text("not a directory\n", encoding="utf-8")
            invalid = run_cli("lint", str(root), "--json")
            self.assertEqual(invalid.returncode, 1, invalid.stdout + invalid.stderr)
            invalid_codes = {
                finding["code"]
                for finding in json.loads(invalid.stdout)["findings"]
            }
            self.assertIn("RAW_ROOT_NOT_DIRECTORY", invalid_codes)

    def test_raw_must_have_one_unique_source_page(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "wiki"
            self.init_wiki(root)
            raw = root / "raw" / "notes" / "shared.md"
            raw.write_text("Shared evidence reports 17 items.\n", encoding="utf-8")
            digest = hashlib.sha256(raw.read_bytes()).hexdigest()
            (root / "wiki" / "concepts" / "shared-concept.md").write_text(
                page_text(
                    page_id="shared-concept",
                    title="Shared concept",
                    page_type="concept",
                    source_ref="raw/notes/shared.md",
                    body="The source reports 17 items.",
                ),
                encoding="utf-8",
            )
            self.assertEqual(run_cli("reindex", str(root)).returncode, 0)
            unregistered = run_cli("lint", str(root), "--json")
            codes = {
                finding["code"]
                for finding in json.loads(unregistered.stdout)["findings"]
            }
            self.assertIn("SOURCE_REF_UNREGISTERED", codes)
            self.assertIn("RAW_UNREGISTERED", codes)

            for suffix in ("a", "b"):
                (root / "wiki" / "sources" / f"source-shared-{suffix}.md").write_text(
                    page_text(
                        page_id=f"source-shared-{suffix}",
                        title=f"Shared source {suffix}",
                        page_type="source",
                        source_ref="raw/notes/shared.md",
                        source_hash=digest,
                        body="Shared evidence reports 17 items.",
                    ),
                    encoding="utf-8",
                )
            self.assertEqual(run_cli("reindex", str(root)).returncode, 0)
            duplicate = run_cli("lint", str(root), "--json")
            codes = {
                finding["code"] for finding in json.loads(duplicate.stdout)["findings"]
            }
            self.assertIn("SOURCE_PAGE_DUPLICATE_RAW", codes)

    def test_schema_drives_managed_directories_and_rejects_nested_pages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "wiki"
            self.init_wiki(root)
            wiki_contract = root / "WIKI.md"
            wiki_contract.write_text(
                wiki_contract.read_text(encoding="utf-8").replace(
                    "  - queries=query\n", "  - queries=query\n  - decisions=decision\n"
                ),
                encoding="utf-8",
            )
            (root / "wiki" / "decisions").mkdir()
            reindex = run_cli("reindex", str(root))
            self.assertEqual(reindex.returncode, 0, reindex.stdout + reindex.stderr)
            self.assertIn(
                "## Decision", (root / "wiki" / "index.md").read_text(encoding="utf-8")
            )

            nested = root / "wiki" / "concepts" / "nested"
            nested.mkdir()
            (nested / "hidden.md").write_text("# Hidden\n", encoding="utf-8")
            rejected = run_cli("reindex", str(root))
            self.assertEqual(rejected.returncode, 1)
            self.assertIn("NESTED_MANAGED_PAGE", rejected.stdout)

    def test_reindex_rejects_wikilinks_in_plain_text_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "wiki"
            self.init_wiki(root)
            page = root / "wiki" / "concepts" / "unsafe-summary.md"
            page.write_text(
                page_text(
                    page_id="unsafe-summary",
                    title="Unsafe summary",
                    page_type="concept",
                    source_ref="raw/notes/not-yet-ingested.md",
                ).replace(
                    "summary: Test page for Unsafe summary.",
                    "summary: See [[another-page]] for details.",
                ),
                encoding="utf-8",
            )
            rejected = run_cli("reindex", str(root))
            self.assertEqual(rejected.returncode, 1)
            self.assertIn("PAGE_SUMMARY_UNSAFE", rejected.stdout)

    def test_duplicate_raw_content_is_reported_across_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "wiki"
            self.init_wiki(root)
            content = b"Byte-identical source snapshot.\n"
            digest = hashlib.sha256(content).hexdigest()
            for suffix in ("a", "b"):
                raw_ref = f"raw/notes/duplicate-{suffix}.md"
                (root / raw_ref).write_bytes(content)
                (
                    root / "wiki" / "sources" / f"source-duplicate-{suffix}.md"
                ).write_text(
                    page_text(
                        page_id=f"source-duplicate-{suffix}",
                        title=f"Duplicate source {suffix}",
                        page_type="source",
                        source_ref=raw_ref,
                        source_hash=digest,
                    ),
                    encoding="utf-8",
                )
            self.assertEqual(run_cli("reindex", str(root)).returncode, 0)
            lint = run_cli("lint", str(root), "--json")
            self.assertEqual(lint.returncode, 0, lint.stdout + lint.stderr)
            codes = {finding["code"] for finding in json.loads(lint.stdout)["findings"]}
            self.assertIn("SOURCE_CONTENT_DUPLICATE", codes)

    def test_reindex_and_log_retries_are_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "wiki"
            self.init_wiki(root)
            first = json.loads(run_cli("reindex", str(root)).stdout)
            index_path = root / "wiki" / "index.md"
            first_content = index_path.read_bytes()
            first_mtime = index_path.stat().st_mtime_ns
            second = json.loads(run_cli("reindex", str(root)).stdout)
            self.assertFalse(second["changed"])
            self.assertEqual(index_path.read_bytes(), first_content)
            self.assertEqual(index_path.stat().st_mtime_ns, first_mtime)
            self.assertIn("changed", first)

            args = (
                "log",
                str(root),
                "--operation",
                "ingest",
                "--operation-id",
                "ingest:abc123",
                "--outcome",
                "success",
                "--subject",
                "Stable retry",
            )
            appended = json.loads(run_cli(*args).stdout)
            retried = json.loads(run_cli(*args).stdout)
            self.assertTrue(appended["appended"])
            self.assertFalse(retried["appended"])
            log_text = (root / "wiki" / "log.md").read_text(encoding="utf-8")
            self.assertEqual(log_text.count("- operation_id: ingest:abc123"), 1)

            regressed = run_cli(
                *(
                    *args[:-3],
                    "failed",
                    "--subject",
                    "Stable retry",
                )
            )
            self.assertEqual(regressed.returncode, 2)
            self.assertIn("already successful", regressed.stderr)

            reused_identity = run_cli(
                "log",
                str(root),
                "--operation",
                "synthesize",
                "--operation-id",
                "ingest:abc123",
                "--outcome",
                "success",
                "--subject",
                "Different operation",
            )
            self.assertEqual(reused_identity.returncode, 2)
            self.assertIn("already bound", reused_identity.stderr)

            failed_then_success = (
                "log",
                str(root),
                "--operation",
                "ingest",
                "--operation-id",
                "ingest:recoverable",
                "--subject",
                "Recoverable ingest",
            )
            self.assertEqual(
                run_cli(
                    *failed_then_success,
                    "--outcome",
                    "failed",
                ).returncode,
                0,
            )
            self.assertEqual(
                run_cli(
                    *failed_then_success,
                    "--outcome",
                    "success",
                ).returncode,
                0,
            )
            self.assertEqual(run_cli("lint", str(root)).returncode, 0)

            with (root / "wiki" / "log.md").open("a", encoding="utf-8") as handle:
                handle.write(
                    "\n## [2026-07-26] ingest | Stable retry\n\n"
                    "- operation_id: ingest:abc123\n"
                    "- outcome: failed\n"
                )
            invalid_order = run_cli("lint", str(root), "--json")
            self.assertEqual(invalid_order.returncode, 1)
            codes = {
                finding["code"]
                for finding in json.loads(invalid_order.stdout)["findings"]
            }
            self.assertIn("LOG_OUTCOME_ORDER_INVALID", codes)


if __name__ == "__main__":
    unittest.main()
