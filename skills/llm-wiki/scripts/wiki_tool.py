#!/usr/bin/env python3
"""Deterministic scaffolding and structural checks for an LLM Wiki.

The Markdown files remain the source of truth. This helper deliberately avoids
third-party dependencies and semantic rewriting.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = SKILL_DIR / "assets" / "templates"
REQUIRED_FIELDS = {
    "id",
    "title",
    "type",
    "summary",
    "status",
    "created",
    "updated",
    "source_refs",
    "depends_on",
    "aliases",
    "tags",
}
SUPPORTED_SCHEMA_VERSION = 1
TEXT_SOURCE_SUFFIXES = {
    ".csv",
    ".htm",
    ".html",
    ".json",
    ".log",
    ".md",
    ".rst",
    ".srt",
    ".tsv",
    ".txt",
    ".vtt",
    ".xml",
    ".yaml",
    ".yml",
}
ALLOWED_INITIAL_ENTRIES = {
    ".git",
    ".gitignore",
    "AGENTS.md",
    "README",
    "README.md",
}
LOG_OUTCOMES = {"success", "failed"}
LOG_OPERATIONS = {
    "init",
    "ingest",
    "synthesize",
    "lint",
    "schema-evolve",
    "migrate",
    "archive",
}
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
WIKILINK_RE = re.compile(r"(?<!!)\[\[([^\]]+)\]\]")
MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
LOG_HEADING_RE = re.compile(
    r"^## \[(\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}Z)?)\] "
    r"([a-z][a-z-]*) \| (.+)$"
)
LOG_OPERATION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
HIGH_SIGNAL_PATTERNS = (
    re.compile(r"\b\d+(?:\.\d+)?\s*%"),
    re.compile(
        r"\b\d+(?:\.\d+)?\s*(?:K|M|B|ms|sec(?:onds?)?|min(?:utes?)?|"
        r"hours?|days?|GB|MB|TB|tokens?|parameters?|upvotes?)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b20\d{2}-\d{2}-\d{2}\b"),
    re.compile(r"\b\d{4,}\b"),
    re.compile(r'["“]([^"”\n]{20,200})["”]'),
)


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    path: str
    message: str
    hint: str = ""


@dataclass
class Page:
    path: Path
    relpath: str
    text: str
    body: str
    metadata: dict[str, Any]

    @property
    def page_id(self) -> str:
        value = self.metadata.get("id", "")
        return value if isinstance(value, str) else ""

    @property
    def page_type(self) -> str:
        value = self.metadata.get("type", "")
        return value if isinstance(value, str) else ""


@dataclass(frozen=True)
class WikiSchema:
    version: int
    directory_types: dict[str, str]
    status_values: set[str]

    @property
    def page_types(self) -> set[str]:
        return set(self.directory_types.values())


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def normalize_root(value: str) -> Path:
    unresolved = Path(value).expanduser()
    if unresolved.is_symlink():
        raise ValueError(f"Wiki root must not be a symlink: {unresolved}")
    root = unresolved.resolve()
    if root == Path(root.anchor):
        raise ValueError("Refusing to use a filesystem root as a wiki root")
    if root.exists() and not root.is_dir():
        raise ValueError(f"Wiki root is not a directory: {root}")
    return root


def render_template(name: str, replacements: dict[str, str]) -> str:
    path = TEMPLATE_DIR / name
    text = path.read_text(encoding="utf-8")
    for key, value in replacements.items():
        text = text.replace(f"__{key}__", value)
    return text


def write_if_missing(path: Path, content: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        return True
    except FileExistsError:
        return False


def assert_write_target(root: Path, path: Path) -> None:
    """Reject writes through a symlink or outside the resolved wiki root."""
    try:
        relative = path.absolute().relative_to(root.absolute())
    except ValueError as error:
        raise ValueError(f"Write target is not lexically inside wiki root: {path}") from error
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"Refusing to write through a symlink: {current}")
    if not resolve_inside(root, path):
        raise ValueError(f"Write target escapes wiki root: {path}")
    parent = path if path.is_dir() else path.parent
    if parent.exists() and not resolve_inside(root, parent):
        raise ValueError(f"Write target parent escapes wiki root: {parent}")


def require_existing_wiki_root(root: Path, *, require_log: bool = True) -> None:
    """Require the local marker files before any non-init write."""
    required: list[tuple[Path, str]] = [
        (root / "WIKI.md", "file"),
        (root / "wiki", "directory"),
        (root / "wiki" / "index.md", "file"),
    ]
    if require_log:
        required.append((root / "wiki" / "log.md", "file"))
    for path, expected_kind in required:
        if path.is_symlink():
            raise ValueError(f"Wiki control path must not be a symlink: {path}")
        if not path.exists():
            raise ValueError(f"Not an initialized wiki root; missing: {path}")
        if expected_kind == "file" and not path.is_file():
            raise ValueError(f"Wiki control path must be a file: {path}")
        if expected_kind == "directory" and not path.is_dir():
            raise ValueError(f"Wiki control path must be a directory: {path}")
        if not resolve_inside(root, path):
            raise ValueError(f"Wiki control path escapes root: {path}")


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clean_one_line(value: str) -> str:
    return " ".join(value.split())


def parse_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str, str | None]:
    if not text.startswith("---\n"):
        return {}, text, "missing opening frontmatter delimiter"
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text, "missing closing frontmatter delimiter"

    block = text[4:end]
    body = text[end + 5 :]
    metadata: dict[str, Any] = {}
    current_list: str | None = None

    for raw_line in block.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if raw_line.startswith("  - "):
            if current_list is None:
                return {}, body, f"list item has no key: {raw_line.strip()}"
            values = metadata.setdefault(current_list, [])
            if not isinstance(values, list):
                return {}, body, f"field mixes scalar and list: {current_list}"
            values.append(parse_scalar(raw_line[4:]))
            continue
        if raw_line.startswith((" ", "\t")):
            return {}, body, f"unsupported YAML indentation: {raw_line}"
        if ":" not in raw_line:
            return {}, body, f"frontmatter line has no colon: {raw_line}"

        key, raw_value = raw_line.split(":", 1)
        key = key.strip()
        value = raw_value.strip()
        if not key:
            return {}, body, "frontmatter has an empty key"
        if key in metadata:
            return {}, body, f"duplicate frontmatter key: {key}"
        if value == "":
            metadata[key] = []
            current_list = key
        else:
            metadata[key] = parse_scalar(value)
            current_list = None
    return metadata, body, None


def load_schema(root: Path, findings: list[Finding]) -> WikiSchema | None:
    path = root / "WIKI.md"
    if not path.is_file():
        findings.append(
            Finding("error", "SCHEMA_MISSING", "WIKI.md", "Wiki schema is missing")
        )
        return None
    text = path.read_text(encoding="utf-8")
    metadata, _body, error = parse_frontmatter(text)
    if error:
        findings.append(
            Finding(
                "error",
                "SCHEMA_FRONTMATTER_INVALID",
                "WIKI.md",
                error,
            )
        )
        return None

    raw_version = metadata.get("schema_version")
    try:
        version = int(raw_version)
    except (TypeError, ValueError):
        findings.append(
            Finding(
                "error",
                "SCHEMA_VERSION_INVALID",
                "WIKI.md",
                "schema_version must be an integer",
            )
        )
        return None
    if version != SUPPORTED_SCHEMA_VERSION:
        findings.append(
            Finding(
                "error",
                "SCHEMA_VERSION_UNSUPPORTED",
                "WIKI.md",
                f"Schema version {version} is unsupported; helper supports "
                f"{SUPPORTED_SCHEMA_VERSION}",
                "Migrate the wiki or use a helper version that understands its contract.",
            )
        )
        return None

    raw_mappings = metadata.get("managed_directory_types")
    if not isinstance(raw_mappings, list) or not raw_mappings:
        findings.append(
            Finding(
                "error",
                "SCHEMA_DIRECTORIES_INVALID",
                "WIKI.md",
                "managed_directory_types must be a non-empty block list",
            )
        )
        return None
    directory_types: dict[str, str] = {}
    for entry in raw_mappings:
        if not isinstance(entry, str) or entry.count("=") != 1:
            findings.append(
                Finding(
                    "error",
                    "SCHEMA_DIRECTORY_MAPPING_INVALID",
                    "WIKI.md",
                    f"Expected directory=type, got {entry!r}",
                )
            )
            continue
        directory, page_type = (part.strip() for part in entry.split("=", 1))
        if (
            not ID_RE.fullmatch(directory)
            or not ID_RE.fullmatch(page_type)
            or "/" in directory
        ):
            findings.append(
                Finding(
                    "error",
                    "SCHEMA_DIRECTORY_MAPPING_INVALID",
                    "WIKI.md",
                    f"Unsafe directory/type mapping: {entry!r}",
                )
            )
            continue
        if directory in directory_types:
            findings.append(
                Finding(
                    "error",
                    "SCHEMA_DIRECTORY_DUPLICATE",
                    "WIKI.md",
                    f"Managed directory appears twice: {directory}",
                )
            )
            continue
        directory_types[directory] = page_type
    if len(set(directory_types.values())) != len(directory_types):
        findings.append(
            Finding(
                "error",
                "SCHEMA_PAGE_TYPE_DUPLICATE",
                "WIKI.md",
                "Each managed page type must map to exactly one directory",
            )
        )
    if "source" not in directory_types.values():
        findings.append(
            Finding(
                "error",
                "SCHEMA_SOURCE_TYPE_MISSING",
                "WIKI.md",
                "One managed directory must map to the reserved source page type",
            )
        )

    raw_statuses = metadata.get("status_values")
    if not isinstance(raw_statuses, list) or not raw_statuses:
        findings.append(
            Finding(
                "error",
                "SCHEMA_STATUSES_INVALID",
                "WIKI.md",
                "status_values must be a non-empty block list",
            )
        )
        return None
    status_values = {
        item.strip()
        for item in raw_statuses
        if isinstance(item, str) and ID_RE.fullmatch(item.strip())
    }
    if len(status_values) != len(raw_statuses):
        findings.append(
            Finding(
                "error",
                "SCHEMA_STATUSES_INVALID",
                "WIKI.md",
                "Every status value must be unique lowercase kebab-case",
            )
        )

    if any(item.severity == "error" and item.path == "WIKI.md" for item in findings):
        return None
    return WikiSchema(version, directory_types, status_values)


def managed_markdown_files(
    root: Path, schema: WikiSchema, findings: list[Finding]
) -> list[Path]:
    wiki = root / "wiki"
    if not wiki.is_dir():
        return []
    files: list[Path] = []
    for directory in schema.directory_types:
        base = wiki / directory
        if base.is_symlink():
            findings.append(
                Finding(
                    "error",
                    "MANAGED_DIRECTORY_SYMLINK_UNSUPPORTED",
                    base.relative_to(root).as_posix(),
                    "Managed directories must not be symlinks",
                )
            )
            continue
        if not base.exists():
            findings.append(
                Finding(
                    "error",
                    "MANAGED_DIRECTORY_MISSING",
                    base.relative_to(root).as_posix(),
                    "Directory declared by WIKI.md does not exist",
                )
            )
            continue
        if not base.is_dir():
            findings.append(
                Finding(
                    "error",
                    "MANAGED_DIRECTORY_NOT_DIRECTORY",
                    base.relative_to(root).as_posix(),
                    "Managed path is not a directory",
                )
            )
            continue
        files.extend(base.glob("*.md"))
        for nested in base.rglob("*.md"):
            if nested.parent != base:
                findings.append(
                    Finding(
                        "error",
                        "NESTED_MANAGED_PAGE",
                        nested.relative_to(root).as_posix(),
                        "Managed pages must be directly inside their declared directory",
                    )
                )
    return sorted(files)


def parse_pages(
    root: Path, schema: WikiSchema, findings: list[Finding]
) -> list[Page]:
    pages: list[Page] = []
    for path in managed_markdown_files(root, schema, findings):
        relpath = path.relative_to(root).as_posix()
        if path.is_symlink():
            findings.append(
                Finding(
                    "error",
                    "PAGE_SYMLINK_UNSUPPORTED",
                    relpath,
                    "Managed pages must be real files inside the wiki root",
                )
            )
            continue
        if not resolve_inside(root, path):
            findings.append(
                Finding(
                    "error",
                    "PAGE_OUTSIDE_WIKI_ROOT",
                    relpath,
                    "Managed page resolves outside the wiki root",
                )
            )
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append(
                Finding(
                    "error",
                    "PAGE_NOT_UTF8",
                    relpath,
                    "Managed Markdown page is not valid UTF-8",
                    "Convert the wiki page to UTF-8; do not alter raw source files.",
                )
            )
            continue
        metadata, body, error = parse_frontmatter(text)
        if error:
            findings.append(
                Finding(
                    "error",
                    "FRONTMATTER_INVALID",
                    relpath,
                    error,
                    "Use the YAML subset documented in references/architecture.md.",
                )
            )
        pages.append(Page(path, relpath, text, body, metadata))
    return pages


def list_value(page: Page, key: str, findings: list[Finding]) -> list[str]:
    value = page.metadata.get(key, [])
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        cleaned: list[str] = []
        for item in value:
            if not item.strip():
                findings.append(
                    Finding(
                        "error",
                        "FRONTMATTER_LIST_EMPTY_ITEM",
                        page.relpath,
                        f"{key} must not contain empty list items",
                    )
                )
                continue
            cleaned.append(item.strip())
        return cleaned
    findings.append(
        Finding(
            "error",
            "FRONTMATTER_LIST_REQUIRED",
            page.relpath,
            f"{key} must use YAML block-list syntax",
        )
    )
    return []


def resolve_inside(base: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def wiki_targets(text: str) -> list[str]:
    targets: list[str] = []
    for match in WIKILINK_RE.finditer(text):
        target = match.group(1).split("|", 1)[0].split("#", 1)[0].strip()
        if target:
            targets.append(Path(target).stem)
    return targets


def normalized_evidence_text(value: str) -> str:
    return " ".join(value.casefold().split())


def high_signal_literals(body: str) -> set[str]:
    literals: set[str] = set()
    for pattern in HIGH_SIGNAL_PATTERNS:
        for match in pattern.finditer(body):
            value = match.group(1) if match.lastindex else match.group(0)
            value = clean_one_line(value)
            if value:
                literals.add(value)
    return literals


def add_contract_findings(
    root: Path,
    schema: WikiSchema,
    pages: list[Page],
    findings: list[Finding],
) -> tuple[dict[str, Page], dict[str, list[str]]]:
    pages_by_id: dict[str, Page] = {}
    aliases_by_page: dict[str, list[str]] = {}
    seen_aliases: dict[str, str] = {}

    for page in pages:
        missing = sorted(REQUIRED_FIELDS - page.metadata.keys())
        if missing:
            findings.append(
                Finding(
                    "error",
                    "FRONTMATTER_MISSING_FIELDS",
                    page.relpath,
                    f"Missing required fields: {', '.join(missing)}",
                )
            )

        for field in ("id", "title", "type", "summary", "status", "created", "updated"):
            value = page.metadata.get(field)
            if not isinstance(value, str) or not value.strip():
                findings.append(
                    Finding(
                        "error",
                        "FRONTMATTER_VALUE_REQUIRED",
                        page.relpath,
                        f"{field} must be a non-empty scalar",
                    )
                )

        title = page.metadata.get("title", "")
        if isinstance(title, str) and ("[[" in title or "]]" in title):
            findings.append(
                Finding(
                    "error",
                    "PAGE_TITLE_UNSAFE",
                    page.relpath,
                    "Page title must not contain wiki-link delimiters",
                )
            )
        summary = page.metadata.get("summary", "")
        if isinstance(summary, str) and ("[[" in summary or "]]" in summary):
            findings.append(
                Finding(
                    "error",
                    "PAGE_SUMMARY_UNSAFE",
                    page.relpath,
                    "Page summary must be plain text without wiki-link delimiters",
                )
            )

        page_id = page.page_id
        if page_id:
            if not ID_RE.fullmatch(page_id):
                findings.append(
                    Finding(
                        "error",
                        "PAGE_ID_INVALID",
                        page.relpath,
                        f"Invalid page id: {page_id}",
                        "Use globally unique lowercase kebab-case.",
                    )
                )
            if page.path.stem != page_id:
                findings.append(
                    Finding(
                        "error",
                        "PAGE_ID_FILENAME_MISMATCH",
                        page.relpath,
                        f"Page id {page_id!r} does not match filename stem {page.path.stem!r}",
                    )
                )
            if page_id in pages_by_id:
                findings.append(
                    Finding(
                        "error",
                        "PAGE_ID_DUPLICATE",
                        page.relpath,
                        f"Duplicate page id also used by {pages_by_id[page_id].relpath}",
                    )
                )
            else:
                pages_by_id[page_id] = page

        page_type = page.page_type
        if page_type and page_type not in schema.page_types:
            findings.append(
                Finding(
                    "error",
                    "PAGE_TYPE_INVALID",
                    page.relpath,
                    f"Unsupported page type: {page_type}",
                )
            )
        expected_type = schema.directory_types.get(page.path.parent.name)
        if page_type and expected_type and page_type != expected_type:
            findings.append(
                Finding(
                    "error",
                    "PAGE_DIRECTORY_TYPE_MISMATCH",
                    page.relpath,
                    f"Directory {page.path.parent.name!r} requires type "
                    f"{expected_type!r}, got {page_type!r}",
                )
            )

        status = page.metadata.get("status", "")
        if isinstance(status, str) and status and status not in schema.status_values:
            findings.append(
                Finding(
                    "error",
                    "PAGE_STATUS_INVALID",
                    page.relpath,
                    f"Unsupported status: {status}",
                )
            )
        if status in {"contested", "needs-review"}:
            findings.append(
                Finding(
                    "warning",
                    "PAGE_REVIEW_NEEDED",
                    page.relpath,
                    f"Page status is {status}",
                )
            )

        parsed_dates: dict[str, date] = {}
        for field in ("created", "updated"):
            value = page.metadata.get(field, "")
            if isinstance(value, str) and value and not DATE_RE.fullmatch(value):
                findings.append(
                    Finding(
                        "error",
                        "PAGE_DATE_INVALID",
                        page.relpath,
                        f"{field} must use YYYY-MM-DD, got {value!r}",
                    )
                )
            elif isinstance(value, str) and value:
                try:
                    parsed_dates[field] = date.fromisoformat(value)
                except ValueError:
                    findings.append(
                        Finding(
                            "error",
                            "PAGE_DATE_INVALID",
                            page.relpath,
                            f"{field} is not a real calendar date: {value!r}",
                        )
                    )

        today = datetime.now(timezone.utc).date()
        for field, parsed_date in parsed_dates.items():
            if parsed_date > today:
                findings.append(
                    Finding(
                        "error",
                        "PAGE_DATE_IN_FUTURE",
                        page.relpath,
                        f"{field} date must not be in the future",
                    )
                )

        if (
            parsed_dates.get("created")
            and parsed_dates.get("updated")
            and parsed_dates["created"] > parsed_dates["updated"]
        ):
            findings.append(
                Finding(
                    "error",
                    "PAGE_DATE_ORDER_INVALID",
                    page.relpath,
                    "created date must not be after updated date",
                )
            )
        updated = page.metadata.get("updated", "")
        if isinstance(updated, str) and DATE_RE.fullmatch(updated):
            try:
                age_days = (today - date.fromisoformat(updated)).days
                if age_days > 180 and status == "active":
                    findings.append(
                        Finding(
                            "warning",
                            "PAGE_POSSIBLY_STALE",
                            page.relpath,
                            f"Active page has not been updated for {age_days} days",
                        )
                    )
            except ValueError:
                pass

        if len(page.body.splitlines()) > 300:
            findings.append(
                Finding(
                    "warning",
                    "PAGE_TOO_LARGE",
                    page.relpath,
                    "Page body exceeds 300 lines",
                    "Consider a source-backed split with explicit cross-links.",
                )
            )

        aliases = list_value(page, "aliases", findings)
        aliases_by_page[page_id] = aliases
        for name in [page_id, *aliases]:
            folded = name.casefold().strip()
            if not folded:
                if name in aliases:
                    findings.append(
                        Finding(
                            "error",
                            "ALIAS_EMPTY",
                            page.relpath,
                            "Aliases must not contain empty values",
                        )
                    )
                continue
            if "[[" in name or "]]" in name:
                findings.append(
                    Finding(
                        "error",
                        "ALIAS_UNSAFE",
                        page.relpath,
                        f"Alias contains wiki-link delimiters: {name!r}",
                    )
                )
            previous = seen_aliases.get(folded)
            if previous and previous != page_id:
                findings.append(
                    Finding(
                        "error",
                        "ALIAS_COLLISION",
                        page.relpath,
                        f"ID or alias {name!r} collides with page {previous!r}",
                    )
                )
            else:
                seen_aliases[folded] = page_id

    return pages_by_id, aliases_by_page


def add_reference_findings(
    root: Path,
    schema: WikiSchema,
    pages: list[Page],
    pages_by_id: dict[str, Page],
    findings: list[Finding],
) -> tuple[Counter[str], set[str]]:
    inbound: Counter[str] = Counter()
    raw_root = root / "raw"
    source_refs_by_page: dict[str, list[str]] = {}
    resolved_refs_by_page: dict[str, list[tuple[str, Path]]] = {}
    source_registry: dict[str, Page] = {}
    source_hash_registry: dict[str, tuple[Path, Page]] = {}

    # Resolve all declared sources first so a content page may refer to a source
    # page that appears later in lexical order.
    for page in pages:
        source_refs = list_value(page, "source_refs", findings)
        source_refs_by_page[page.relpath] = source_refs
        if page.page_type in schema.page_types and not source_refs:
            findings.append(
                Finding(
                    "error",
                    "SOURCE_REFS_EMPTY",
                    page.relpath,
                    "Managed content page must declare at least one raw source",
                )
            )
        if len(set(source_refs)) != len(source_refs):
            findings.append(
                Finding(
                    "error",
                    "SOURCE_REF_DUPLICATE",
                    page.relpath,
                    "source_refs must not repeat the same path",
                )
            )

        resolved_refs: list[tuple[str, Path]] = []
        for source_ref in source_refs:
            if Path(source_ref).is_absolute():
                findings.append(
                    Finding(
                        "error",
                        "SOURCE_REF_OUTSIDE_RAW",
                        page.relpath,
                        f"source_refs entry must be root-relative: {source_ref}",
                    )
                )
                continue
            unresolved_candidate = root / source_ref
            candidate = unresolved_candidate.resolve()
            if not resolve_inside(raw_root, candidate):
                findings.append(
                    Finding(
                        "error",
                        "SOURCE_REF_OUTSIDE_RAW",
                        page.relpath,
                        f"source_refs entry escapes raw/: {source_ref}",
                    )
                )
                continue
            current = root
            uses_symlink = False
            for part in Path(source_ref).parts:
                current = current / part
                if current.is_symlink():
                    uses_symlink = True
                    break
            if uses_symlink:
                findings.append(
                    Finding(
                        "error",
                        "SOURCE_REF_SYMLINK_UNSUPPORTED",
                        page.relpath,
                        f"Raw source reference must be a real snapshot, not a symlink: {source_ref}",
                    )
                )
                continue
            if not candidate.is_file():
                findings.append(
                    Finding(
                        "error",
                        "SOURCE_REF_MISSING",
                        page.relpath,
                        f"Raw source does not exist: {source_ref}",
                    )
                )
            else:
                resolved_refs.append((source_ref, candidate))
        resolved_refs_by_page[page.relpath] = resolved_refs

        if page.page_type == "source":
            expected_hash = page.metadata.get("source_sha256", "")
            if not isinstance(expected_hash, str) or not re.fullmatch(
                r"[0-9a-f]{64}", expected_hash
            ):
                findings.append(
                    Finding(
                        "error",
                        "SOURCE_HASH_MISSING",
                        page.relpath,
                        "Source page must contain a lowercase 64-character source_sha256",
                    )
                )
            if len(source_refs) != 1:
                findings.append(
                    Finding(
                        "error",
                        "SOURCE_PRIMARY_REF_COUNT",
                        page.relpath,
                        "Source page must have exactly one primary source_refs entry",
                    )
                )
            if len(source_refs) == 1 and len(resolved_refs) == 1:
                source_key = resolved_refs[0][1].as_posix()
                previous = source_registry.get(source_key)
                if previous is not None:
                    findings.append(
                        Finding(
                            "error",
                            "SOURCE_PAGE_DUPLICATE_RAW",
                            page.relpath,
                            "Raw snapshot is already registered by "
                            f"{previous.relpath}: {source_refs[0]}",
                        )
                    )
                else:
                    source_registry[source_key] = page
                if isinstance(expected_hash, str) and re.fullmatch(
                    r"[0-9a-f]{64}", expected_hash
                ):
                    actual_hash = sha256_file(resolved_refs[0][1])
                    previous_hash_source = source_hash_registry.get(actual_hash)
                    if (
                        previous_hash_source is not None
                        and previous_hash_source[0] != resolved_refs[0][1]
                    ):
                        findings.append(
                            Finding(
                                "warning",
                                "SOURCE_CONTENT_DUPLICATE",
                                page.relpath,
                                "Raw snapshot has identical bytes to "
                                f"{previous_hash_source[1].relpath}: "
                                f"{source_refs[0]}",
                                "Reuse the registered snapshot unless distinct provenance requires an intentional mirror.",
                            )
                        )
                    elif previous_hash_source is None:
                        source_hash_registry[actual_hash] = (
                            resolved_refs[0][1],
                            page,
                        )
                    if actual_hash != expected_hash:
                        findings.append(
                            Finding(
                                "error",
                                "RAW_HASH_MISMATCH",
                                page.relpath,
                                f"Raw snapshot hash changed: {source_refs[0]}",
                                "Do not rewrite raw. Restore the snapshot or ingest the changed source as a new file.",
                            )
                        )

    registered_raw = set(source_registry)

    for page in pages:
        source_refs = source_refs_by_page.get(page.relpath, [])
        resolved_refs = resolved_refs_by_page.get(page.relpath, [])
        declared_raw = {path.as_posix() for _ref, path in resolved_refs}
        depends_on = list_value(page, "depends_on", findings)

        if page.page_type != "source":
            for source_ref, candidate in resolved_refs:
                if candidate.as_posix() not in source_registry:
                    findings.append(
                        Finding(
                            "error",
                            "SOURCE_REF_UNREGISTERED",
                            page.relpath,
                            "Content pages may cite raw snapshots only after a unique "
                            f"source page registers them: {source_ref}",
                        )
                    )

        for dependency in depends_on:
            if dependency not in pages_by_id:
                findings.append(
                    Finding(
                        "error",
                        "DEPENDENCY_MISSING",
                        page.relpath,
                        f"depends_on target does not exist: {dependency}",
                    )
                )
            else:
                inbound[dependency] += 1

        for target in wiki_targets(page.body):
            if target not in pages_by_id:
                findings.append(
                    Finding(
                        "error",
                        "BROKEN_WIKILINK",
                        page.relpath,
                        f"Wiki link target does not exist: {target}",
                    )
                )
            else:
                inbound[target] += 1

        for match in MARKDOWN_LINK_RE.finditer(page.body):
            raw_target = unquote(match.group(1).strip()).split("#", 1)[0]
            if (
                not raw_target
                or raw_target.startswith(("#", "http://", "https://", "mailto:"))
            ):
                continue
            candidate = (page.path.parent / raw_target).resolve()
            if not resolve_inside(root, candidate):
                findings.append(
                    Finding(
                        "error",
                        "LOCAL_LINK_OUTSIDE_WIKI_ROOT",
                        page.relpath,
                        f"Local Markdown link escapes wiki root: {raw_target}",
                    )
                )
            elif not candidate.exists():
                findings.append(
                    Finding(
                        "error",
                        "BROKEN_MARKDOWN_LINK",
                        page.relpath,
                        f"Local Markdown link target does not exist: {raw_target}",
                    )
                )
            elif resolve_inside(raw_root, candidate) and candidate.as_posix() not in declared_raw:
                findings.append(
                    Finding(
                        "error",
                        "RAW_LINK_UNDECLARED",
                        page.relpath,
                        "Raw Markdown link must also appear in this page's "
                        f"source_refs: {raw_target}",
                    )
                )

        literals = sorted(high_signal_literals(page.body))
        source_paths = [path for _ref, path in resolved_refs]
        if literals and source_paths:
            non_text = [
                path
                for path in source_paths
                if path.suffix.casefold() not in TEXT_SOURCE_SUFFIXES
            ]
            if non_text:
                findings.append(
                    Finding(
                        "warning",
                        "EVIDENCE_TEXT_UNAVAILABLE",
                        page.relpath,
                        "Literal drift check skipped because declared evidence includes "
                        "a binary or unsupported source: "
                        + ", ".join(
                            path.relative_to(root).as_posix() for path in non_text
                        ),
                        "Use page/timestamp locators and a reviewed text sidecar when automated literal checks are needed.",
                    )
                )
            else:
                try:
                    source_text = "\n".join(
                        path.read_text(encoding="utf-8") for path in source_paths
                    )
                except UnicodeDecodeError:
                    findings.append(
                        Finding(
                            "warning",
                            "EVIDENCE_TEXT_UNAVAILABLE",
                            page.relpath,
                            "Literal drift check skipped because a declared text source "
                            "is not valid UTF-8",
                            "Preserve the raw snapshot and add a reviewed UTF-8 text sidecar.",
                        )
                    )
                    source_text = ""
                if source_text:
                    evidence = normalized_evidence_text(source_text)
                    for literal in literals:
                        if normalized_evidence_text(literal) not in evidence:
                            findings.append(
                                Finding(
                                    "warning",
                                    "EVIDENCE_LITERAL_NOT_FOUND",
                                    page.relpath,
                                    "High-signal literal not found in declared raw "
                                    f"sources: {literal!r}",
                                    "Check for transcription drift or document the inputs if this is a derived value.",
                                )
                            )

    for page in pages:
        if (
            page.page_id
            and page.page_type not in {"source", "query"}
            and page.metadata.get("status") != "no-material"
            and inbound[page.page_id] == 0
        ):
            findings.append(
                Finding(
                    "warning",
                    "ORPHAN_PAGE",
                    page.relpath,
                    "Page has no inbound page link or dependency",
                )
            )

    return inbound, registered_raw


def add_index_findings(
    root: Path, pages: list[Page], findings: list[Finding]
) -> None:
    index_path = root / "wiki" / "index.md"
    if not index_path.is_file():
        findings.append(
            Finding(
                "error",
                "INDEX_MISSING_FILE",
                "wiki/index.md",
                "Index file does not exist",
            )
        )
        return

    index_text = index_path.read_text(encoding="utf-8")
    targets = wiki_targets(index_text)
    counts = Counter(targets)
    page_ids = {page.page_id for page in pages if page.page_id}

    for page_id in sorted(page_ids):
        if counts[page_id] == 0:
            findings.append(
                Finding(
                    "error",
                    "INDEX_MISSING",
                    "wiki/index.md",
                    f"Managed page is absent from index: {page_id}",
                    "Run wiki_tool.py reindex.",
                )
            )
        elif counts[page_id] > 1:
            findings.append(
                Finding(
                    "error",
                    "INDEX_DUPLICATE",
                    "wiki/index.md",
                    f"Managed page appears {counts[page_id]} times: {page_id}",
                    "Run wiki_tool.py reindex.",
                )
            )

    for target in sorted(set(targets) - page_ids):
        findings.append(
            Finding(
                "error",
                "INDEX_STALE_ENTRY",
                "wiki/index.md",
                f"Index references a missing managed page: {target}",
                "Run wiki_tool.py reindex after reviewing whether the page was intentionally removed.",
            )
        )


def add_log_findings(root: Path, findings: list[Finding]) -> None:
    log_path = root / "wiki" / "log.md"
    if not log_path.is_file():
        findings.append(
            Finding(
                "error",
                "LOG_MISSING_FILE",
                "wiki/log.md",
                "Log file does not exist",
            )
        )
        return
    lines = log_path.read_text(encoding="utf-8").splitlines()
    heading_indexes = [
        index for index, line in enumerate(lines) if line.startswith("## ")
    ]
    seen_operation_results: dict[tuple[str, str], int] = {}
    operation_identities: dict[str, tuple[str, str, int]] = {}
    operation_outcomes: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for position, index in enumerate(heading_indexes):
        line_number = index + 1
        line = lines[index]
        match = LOG_HEADING_RE.fullmatch(line)
        if not match:
            findings.append(
                Finding(
                    "error",
                    "LOG_HEADING_INVALID",
                    "wiki/log.md",
                    f"Invalid operation heading at line {line_number}: {line}",
                )
            )
            continue
        timestamp = match.group(1)
        try:
            if "T" in timestamp:
                datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            else:
                date.fromisoformat(timestamp)
        except ValueError:
            findings.append(
                Finding(
                    "error",
                    "LOG_TIMESTAMP_INVALID",
                    "wiki/log.md",
                    f"Invalid timestamp at line {line_number}: {timestamp}",
                )
            )
        operation = match.group(2)
        if operation not in LOG_OPERATIONS:
            findings.append(
                Finding(
                    "error",
                    "LOG_OPERATION_INVALID",
                    "wiki/log.md",
                    f"Unsupported operation at line {line_number}: {operation}",
                )
            )
        next_index = (
            heading_indexes[position + 1]
            if position + 1 < len(heading_indexes)
            else len(lines)
        )
        block = lines[index + 1 : next_index]
        operation_ids = [
            item.removeprefix("- operation_id: ").strip()
            for item in block
            if item.startswith("- operation_id: ")
        ]
        outcomes = [
            item.removeprefix("- outcome: ").strip()
            for item in block
            if item.startswith("- outcome: ")
        ]
        if len(operation_ids) != 1 or not LOG_OPERATION_ID_RE.fullmatch(
            operation_ids[0] if operation_ids else ""
        ):
            findings.append(
                Finding(
                    "error",
                    "LOG_OPERATION_ID_INVALID",
                    "wiki/log.md",
                    f"Entry at line {line_number} must contain one valid "
                    "'- operation_id: <stable-id>' field",
                )
            )
        if len(outcomes) != 1 or outcomes[0] not in LOG_OUTCOMES:
            findings.append(
                Finding(
                    "error",
                    "LOG_OUTCOME_INVALID",
                    "wiki/log.md",
                    f"Entry at line {line_number} must contain one "
                    "'- outcome: success|failed' field",
                )
            )
        if (
            len(operation_ids) == 1
            and LOG_OPERATION_ID_RE.fullmatch(operation_ids[0])
            and len(outcomes) == 1
            and outcomes[0] in LOG_OUTCOMES
        ):
            operation_id = operation_ids[0]
            outcome = outcomes[0]
            identity = (operation, match.group(3))
            previous_identity = operation_identities.get(operation_id)
            if previous_identity is not None and previous_identity[:2] != identity:
                findings.append(
                    Finding(
                        "error",
                        "LOG_OPERATION_ID_REUSED",
                        "wiki/log.md",
                        f"operation_id {operation_id!r} changes identity between "
                        f"lines {previous_identity[2]} and {line_number}",
                        "Use one operation ID for one operation and subject only.",
                    )
                )
            elif previous_identity is None:
                operation_identities[operation_id] = (
                    operation,
                    match.group(3),
                    line_number,
                )

            prior_outcomes = operation_outcomes[operation_id]
            if outcome == "failed" and any(
                prior == "success" for prior, _prior_line in prior_outcomes
            ):
                success_line = next(
                    prior_line
                    for prior, prior_line in prior_outcomes
                    if prior == "success"
                )
                findings.append(
                    Finding(
                        "error",
                        "LOG_OUTCOME_ORDER_INVALID",
                        "wiki/log.md",
                        f"operation_id {operation_id!r} records failed at line "
                        f"{line_number} after success at line {success_line}",
                        "A completed operation cannot regress; use a new operation ID for a later incident.",
                    )
                )
            operation_outcomes[operation_id].append((outcome, line_number))

            result_key = (operation_id, outcome)
            previous_line = seen_operation_results.get(result_key)
            if previous_line is not None:
                findings.append(
                    Finding(
                        "error",
                        "LOG_OPERATION_RESULT_DUPLICATE",
                        "wiki/log.md",
                        f"Duplicate operation_id/outcome at lines "
                        f"{previous_line} and {line_number}: "
                        f"{operation_id} / {outcome}",
                    )
                )
            else:
                seen_operation_results[result_key] = line_number


def add_workspace_findings(
    root: Path, referenced_raw: set[str], findings: list[Finding]
) -> None:
    if not (root / "WIKI.md").is_file():
        findings.append(
            Finding("error", "SCHEMA_MISSING", "WIKI.md", "Wiki schema is missing")
        )
    agents = root / "AGENTS.md"
    if not agents.is_file():
        findings.append(
            Finding(
                "warning",
                "AGENTS_ENTRY_MISSING",
                "AGENTS.md",
                "No agent entry file points to WIKI.md",
            )
        )
    elif "WIKI.md" not in agents.read_text(encoding="utf-8", errors="ignore"):
        findings.append(
            Finding(
                "warning",
                "AGENTS_NO_WIKI_POINTER",
                "AGENTS.md",
                "Existing AGENTS.md is preserved but does not mention WIKI.md",
            )
        )

    raw_root = root / "raw"
    if not raw_root.exists():
        findings.append(
            Finding(
                "error",
                "RAW_ROOT_MISSING",
                "raw",
                "Raw source directory does not exist",
                "Restore raw/ before treating the wiki as healthy.",
            )
        )
    elif not raw_root.is_dir():
        findings.append(
            Finding(
                "error",
                "RAW_ROOT_NOT_DIRECTORY",
                "raw",
                "Raw source path must be a directory",
            )
        )
    else:
        for path in sorted(raw_root.rglob("*")):
            if path.is_symlink():
                findings.append(
                    Finding(
                        "error",
                        "RAW_SYMLINK_UNSUPPORTED",
                        path.relative_to(root).as_posix(),
                        "Raw snapshots and directories must not be symlinks",
                    )
                )
                continue
            if (
                path.is_file()
                and path.name != ".gitkeep"
                and path.resolve().as_posix() not in referenced_raw
            ):
                findings.append(
                    Finding(
                        "warning",
                        "RAW_UNREGISTERED",
                        path.relative_to(root).as_posix(),
                        "Raw snapshot has no source page",
                    )
                )


def lint(root: Path) -> tuple[list[Finding], list[Page]]:
    findings: list[Finding] = []
    unsafe_control_path = False
    for relative in (
        "AGENTS.md",
        "WIKI.md",
        "wiki",
        "raw",
        "wiki/index.md",
        "wiki/log.md",
    ):
        path = root / relative
        if path.is_symlink():
            unsafe_control_path = True
            findings.append(
                Finding(
                    "error",
                    "WORKSPACE_SYMLINK_UNSUPPORTED",
                    relative,
                    "Wiki control paths must not be symlinks",
                )
            )
    if unsafe_control_path:
        return findings, []
    schema = load_schema(root, findings)
    if schema is None:
        findings.sort(
            key=lambda item: (item.severity != "error", item.path, item.code)
        )
        return findings, []
    pages = parse_pages(root, schema, findings)
    pages_by_id, _aliases = add_contract_findings(root, schema, pages, findings)
    _inbound, referenced_raw = add_reference_findings(
        root, schema, pages, pages_by_id, findings
    )
    add_index_findings(root, pages, findings)
    add_log_findings(root, findings)
    add_workspace_findings(root, referenced_raw, findings)
    findings.sort(key=lambda item: (item.severity != "error", item.path, item.code))
    return findings, pages


def append_operation_result(
    root: Path,
    *,
    operation: str,
    operation_id: str,
    outcome: str,
    subject: str,
    detail: str = "",
) -> bool:
    """Append one valid state transition, returning whether the log changed."""
    log_path = root / "wiki" / "log.md"
    assert_write_target(root, log_path)
    existing_lines = log_path.read_text(encoding="utf-8").splitlines()
    heading_indexes = [
        index for index, line in enumerate(existing_lines) if line.startswith("## ")
    ]
    existing_outcomes: list[str] = []
    for position, index in enumerate(heading_indexes):
        match = LOG_HEADING_RE.fullmatch(existing_lines[index])
        if match is None:
            continue
        next_index = (
            heading_indexes[position + 1]
            if position + 1 < len(heading_indexes)
            else len(existing_lines)
        )
        block = existing_lines[index + 1 : next_index]
        if f"- operation_id: {operation_id}" not in block:
            continue
        existing_operation = match.group(2)
        existing_subject = match.group(3)
        if (existing_operation, existing_subject) != (operation, subject):
            raise ValueError(
                f"operation-id {operation_id!r} is already bound to "
                f"{existing_operation!r} / {existing_subject!r}"
            )
        existing_outcomes.extend(
            item.removeprefix("- outcome: ").strip()
            for item in block
            if item.startswith("- outcome: ")
        )
    if outcome == "failed" and "success" in existing_outcomes:
        raise ValueError(
            f"operation-id {operation_id!r} is already successful; "
            "use a new operation ID for a later failure"
        )
    if outcome in existing_outcomes:
        return False

    entry = f"\n## [{utc_timestamp()}] {operation} | {subject}\n"
    entry += f"\n- operation_id: {operation_id}\n"
    entry += f"- outcome: {outcome}\n"
    if detail:
        entry += f"- detail: {detail}\n"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(entry)
        handle.flush()
        os.fsync(handle.fileno())
    return True


def command_init(args: argparse.Namespace) -> int:
    root = normalize_root(args.root)
    title = clean_one_line(args.title)
    domain = clean_one_line(args.domain)
    if not title or not domain:
        raise ValueError("Wiki title and domain must not be empty")
    if root.exists():
        initialized = (root / "WIKI.md").is_file() and (root / "wiki").is_dir()
        unexpected = sorted(
            entry.name
            for entry in root.iterdir()
            if entry.name not in ALLOWED_INITIAL_ENTRIES
        )
        if unexpected and not initialized and not args.allow_existing:
            raise ValueError(
                "Refusing to initialize a non-empty directory with unrelated "
                "content. Move the wiki to a dedicated root or pass "
                f"--allow-existing after review. Found: {', '.join(unexpected)}"
            )
    root.mkdir(parents=True, exist_ok=True)
    created_dirs: list[str] = []
    for relative in (
        "raw/articles",
        "raw/papers",
        "raw/transcripts",
        "raw/notes",
        "raw/assets",
        "wiki/sources",
        "wiki/entities",
        "wiki/concepts",
        "wiki/syntheses",
        "wiki/queries",
        "wiki/meta",
        "wiki/reports",
    ):
        path = root / relative
        assert_write_target(root, path)
        if not path.exists():
            created_dirs.append(relative)
        path.mkdir(parents=True, exist_ok=True)

    timestamp = utc_timestamp()
    replacements = {
        "TITLE": title,
        "DOMAIN": domain,
        "LANGUAGE": args.language,
        "TIMESTAMP": timestamp,
    }
    created_files: list[str] = []
    preserved_files: list[str] = []
    templates = {
        "AGENTS.md": "AGENTS.md.tmpl",
        "WIKI.md": "WIKI.md.tmpl",
        "wiki/index.md": "index.md.tmpl",
        "wiki/log.md": "log.md.tmpl",
        "wiki/meta/schema-proposals.md": "schema-proposals.md.tmpl",
        "wiki/meta/evolution-log.md": "evolution-log.md.tmpl",
    }
    for relative, template_name in templates.items():
        target = root / relative
        assert_write_target(root, target)
        if write_if_missing(target, render_template(template_name, replacements)):
            created_files.append(relative)
        else:
            preserved_files.append(relative)

    findings, _pages = lint(root)
    counts = Counter(item.severity for item in findings)
    init_outcome = "failed" if counts["error"] else "success"
    log_appended = append_operation_result(
        root,
        operation="init",
        operation_id="init:workspace",
        outcome=init_outcome,
        subject="wiki scaffold",
        detail=(
            f"title={title} domain={domain} "
            f"gate_errors={counts['error']} gate_warnings={counts['warning']}"
        ),
    )
    result = {
        "root": root.as_posix(),
        "created_directories": created_dirs,
        "created_files": created_files,
        "preserved_files": preserved_files,
        "agents_pointer_present": "WIKI.md"
        in (root / "AGENTS.md").read_text(encoding="utf-8", errors="ignore"),
        "init_outcome": init_outcome,
        "lint_errors": counts["error"],
        "lint_warnings": counts["warning"],
        "log_appended": log_appended,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if counts["error"] else 0


def command_hash(args: argparse.Namespace) -> int:
    path = Path(args.path).expanduser().resolve()
    if not path.is_file():
        print(f"Source file does not exist: {path}", file=sys.stderr)
        return 2
    print(sha256_file(path))
    return 0


def command_reindex(args: argparse.Namespace) -> int:
    root = normalize_root(args.root)
    require_existing_wiki_root(root)
    index_path = root / "wiki" / "index.md"
    assert_write_target(root, index_path)
    findings: list[Finding] = []
    schema = load_schema(root, findings)
    pages: list[Page] = []
    if schema is not None:
        pages = parse_pages(root, schema, findings)
        add_contract_findings(root, schema, pages, findings)
    if any(item.severity == "error" for item in findings):
        for item in findings:
            print(f"{item.severity.upper()} {item.code} {item.path}: {item.message}")
        return 1

    if schema is None:
        return 1
    type_order = list(schema.directory_types.values())
    grouped: dict[str, list[Page]] = defaultdict(list)
    for page in pages:
        grouped[page.page_type].append(page)

    lines = [
        "# Wiki Index",
        "",
        "> Generated from managed page frontmatter. Do not hand-maintain entries.",
        "",
        f"Total pages: {len(pages)}",
        "",
    ]
    for page_type in type_order:
        lines.append(f"## {page_type.replace('-', ' ').title()}")
        lines.append("")
        group = sorted(
            grouped.get(page_type, []),
            key=lambda page: str(page.metadata.get("title", "")).casefold(),
        )
        if not group:
            lines.append("_No pages._")
        else:
            for page in group:
                title = clean_one_line(str(page.metadata.get("title", page.page_id)))
                summary = clean_one_line(str(page.metadata.get("summary", "")))
                status = clean_one_line(str(page.metadata.get("status", "")))
                suffix = f" [{status}]" if status != "active" else ""
                lines.append(f"- [[{page.page_id}|{title}]] — {summary}{suffix}")
        lines.append("")

    content = "\n".join(lines).rstrip() + "\n"
    changed = index_path.read_text(encoding="utf-8") != content
    if changed:
        atomic_write(index_path, content)
    print(
        json.dumps(
            {
                "root": root.as_posix(),
                "index": "wiki/index.md",
                "pages": len(pages),
                "changed": changed,
            },
            ensure_ascii=False,
        )
    )
    return 0


def command_log(args: argparse.Namespace) -> int:
    root = normalize_root(args.root)
    require_existing_wiki_root(root)
    log_path = root / "wiki" / "log.md"
    assert_write_target(root, log_path)
    operation = args.operation
    if operation not in LOG_OPERATIONS:
        print(
            f"Unsupported operation {operation!r}; choose from "
            f"{', '.join(sorted(LOG_OPERATIONS))}",
            file=sys.stderr,
        )
        return 2
    subject = clean_one_line(args.subject)
    if not subject:
        print("Log subject must not be empty", file=sys.stderr)
        return 2
    operation_id = clean_one_line(args.operation_id)
    if not LOG_OPERATION_ID_RE.fullmatch(operation_id):
        print(
            "operation-id must be 1-128 characters using letters, numbers, "
            "period, underscore, colon, or hyphen",
            file=sys.stderr,
        )
        return 2
    outcome = args.outcome
    if outcome not in LOG_OUTCOMES:
        print(
            f"Unsupported outcome {outcome!r}; choose from "
            f"{', '.join(sorted(LOG_OUTCOMES))}",
            file=sys.stderr,
        )
        return 2
    detail = clean_one_line(args.detail) if args.detail else ""
    appended = append_operation_result(
        root,
        operation=operation,
        operation_id=operation_id,
        outcome=outcome,
        subject=subject,
        detail=detail,
    )
    print(
        json.dumps(
            {
                "root": root.as_posix(),
                "log": "wiki/log.md",
                "operation": operation,
                "operation_id": operation_id,
                "outcome": outcome,
                "subject": subject,
                "appended": appended,
            },
            ensure_ascii=False,
        )
    )
    return 0


def command_lint(args: argparse.Namespace) -> int:
    root = normalize_root(args.root)
    findings, pages = lint(root)
    counts = Counter(item.severity for item in findings)
    result = {
        "root": root.as_posix(),
        "pages": len(pages),
        "summary": {
            "errors": counts["error"],
            "warnings": counts["warning"],
            "findings": len(findings),
        },
        "findings": [asdict(item) for item in findings],
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for item in findings:
            hint = f" Hint: {item.hint}" if item.hint else ""
            print(
                f"{item.severity.upper()} {item.code} {item.path}: "
                f"{item.message}{hint}"
            )
        print(
            f"Linted {len(pages)} pages: {counts['error']} errors, "
            f"{counts['warning']} warnings"
        )
    return 1 if counts["error"] else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scaffold and validate a local Markdown LLM Wiki"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init", help="Create an idempotent wiki scaffold"
    )
    init_parser.add_argument("root")
    init_parser.add_argument("--title", default="My LLM Wiki")
    init_parser.add_argument("--domain", default="Personal knowledge base")
    init_parser.add_argument("--language", choices=("zh", "en"), default="zh")
    init_parser.add_argument(
        "--allow-existing",
        action="store_true",
        help="Initialize inside a reviewed non-empty directory without overwriting files",
    )
    init_parser.set_defaults(func=command_init)

    hash_parser = subparsers.add_parser(
        "hash", help="Print the SHA-256 of a raw source snapshot"
    )
    hash_parser.add_argument("path")
    hash_parser.set_defaults(func=command_hash)

    reindex_parser = subparsers.add_parser(
        "reindex", help="Rebuild wiki/index.md from page frontmatter"
    )
    reindex_parser.add_argument("root")
    reindex_parser.set_defaults(func=command_reindex)

    log_parser = subparsers.add_parser(
        "log", help="Append a machine-readable operation entry"
    )
    log_parser.add_argument("root")
    log_parser.add_argument("--operation", required=True)
    log_parser.add_argument("--operation-id", required=True)
    log_parser.add_argument(
        "--outcome", choices=tuple(sorted(LOG_OUTCOMES)), required=True
    )
    log_parser.add_argument("--subject", required=True)
    log_parser.add_argument("--detail", default="")
    log_parser.set_defaults(func=command_log)

    lint_parser = subparsers.add_parser(
        "lint", help="Run read-only deterministic wiki checks"
    )
    lint_parser.add_argument("root")
    lint_parser.add_argument("--json", action="store_true")
    lint_parser.set_defaults(func=command_lint)

    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        return int(args.func(args))
    except (OSError, UnicodeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
