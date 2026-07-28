# Architecture and page contract

Read this file when initializing a wiki, creating a new page type, or auditing
the structural contract.

## Default tree

```text
<wiki-root>/
├── AGENTS.md
├── WIKI.md
├── raw/
│   ├── articles/
│   ├── papers/
│   ├── transcripts/
│   ├── notes/
│   └── assets/
└── wiki/
    ├── index.md
    ├── log.md
    ├── sources/
    ├── entities/
    ├── concepts/
    ├── syntheses/
    ├── queries/
    ├── meta/
    │   ├── schema-proposals.md
    │   └── evolution-log.md
    └── reports/
```

The taxonomy is a starting point. Domain-specific directories may replace it,
but keep page directories one level below `wiki/` unless a measured scale
problem justifies deeper routing.

`reports/` contains generated audit output and is excluded from the content
index. `meta/` contains governance records and is also excluded from the content
index.

## Machine-readable schema

`WIKI.md` is not only prose. Its frontmatter is the machine source for the
supported schema version, managed directory-to-type mappings, and status
values:

```yaml
---
schema_version: 1
title: My Wiki
language: zh
managed_directory_types:
  - sources=source
  - entities=entity
  - concepts=concept
status_values:
  - active
  - contested
  - needs-review
---
```

Each page type maps to exactly one directory, and one mapping must retain the
reserved `source` type. The helper scans only direct `*.md` children of declared
managed directories. Nested managed pages are rejected instead of being
silently mixed with another wiki or generated documentation. A contract change
that the installed helper cannot interpret must fail closed until the helper or
wiki is migrated.

## Managed page frontmatter

Every page under `wiki/sources`, `wiki/entities`, `wiki/concepts`,
`wiki/syntheses`, or `wiki/queries` uses this YAML subset:

```yaml
---
id: transformer-architecture
title: Transformer Architecture
type: concept
summary: Attention-based sequence architecture and its core trade-offs.
status: active
created: 2026-07-26
updated: 2026-07-26
source_refs:
  - raw/papers/attention-is-all-you-need.pdf
depends_on:
  - source-attention-is-all-you-need
aliases:
  - transformer
tags:
  - architecture
---
```

Rules:

- `id` is lowercase kebab-case, globally unique, and equals the filename stem.
- `type` is `source`, `entity`, `concept`, `synthesis`, or `query`.
- `summary` is one plain-text line used to rebuild `index.md`; it must not
  contain wiki-link delimiters.
- `status` is `active`, `contested`, `superseded`, `needs-review`, or
  `no-material`.
- Dates use ISO `YYYY-MM-DD`.
- Lists use YAML block-list syntax. The bundled parser intentionally supports a
  small, readable subset rather than all YAML.
- `source_refs` contains paths relative to the wiki root and must stay inside
  `raw/`.
- Exactly one `source` page registers each raw snapshot. A non-source page may
  cite the raw path only after that registration exists.
- Byte-identical snapshots at different raw paths produce a duplicate-content
  warning. Reuse the existing registered snapshot unless distinct provenance
  makes an intentional mirror necessary.
- `depends_on` contains page IDs, not filenames or titles.
- `aliases` must not collide with another page ID or alias.
- A source page has exactly one primary `source_refs` entry and adds:

  ```yaml
  source_sha256: <sha256 of the complete raw snapshot>
  ```

## Page body

A source page normally contains:

```markdown
# Title

## Source metadata

- Author:
- Published:
- Captured:
- Original URL:
- Locator notes:

## Summary

## Key claims

## Evidence map

## Connections

## Open questions
```

Entity and concept pages normally contain:

```markdown
# Title

## Current synthesis

## Evidence

## Disputes and uncertainty

## Connections

## Open questions
```

Synthesis pages additionally separate supporting evidence, counter-evidence,
interpretation, and limitations.

## Provenance

Frontmatter source lists are necessary but not sufficient. Put citations close
to the claims they support:

```markdown
The reported evaluation used 8 GPUs for 12 hours
([raw source](../../raw/papers/example.md), "Training setup").
```

For PDFs use page numbers; for video/audio use timestamps; for tables use
sheet/table/row locators; for webpages use section headings or a short evidence
quote. Preserve the source's exact representation for important values. If a
derived value is shown, include its inputs.

Hash verification works for every source format. Literal drift checking reads
only reviewed UTF-8 text formats. For a PDF, image, audio, archive, or other
binary source, the linter emits `EVIDENCE_TEXT_UNAVAILABLE` rather than treating
binary bytes as text. Add a separately reviewed UTF-8 sidecar as its own raw
snapshot/source page when automated literal checking is valuable; keep the
original binary as primary evidence.

Inference is allowed when useful, but label it:

```markdown
**Inference:** This suggests ..., based on [[source-a]] and [[source-b]].
```

The bundled linter uses hashes plus high-signal literal matching as a drift
detector. It cannot prove semantic entailment, source authority, or correct
interpretation. Those remain inferential review criteria, with important
conflicts decided by the user.

## Links and navigation

Use Obsidian-compatible wiki links between managed pages:

```markdown
[[transformer-architecture]]
[[transformer-architecture|Transformers]]
```

Use ordinary relative Markdown links for raw files. The index is generated from
frontmatter, so page summaries should remain concise and accurate.

## Write authority

- A new ingest may create a raw snapshot.
- After creation, raw content is immutable.
- The agent may create and revise managed wiki pages.
- Query is read-only unless the user asks to persist the result.
- Semantic conflict resolution is a human acceptance decision; the agent
  preserves and explains evidence.
- Git commits, pushes, sync, publication, and remote upload require explicit
  user authorization.

Immutability here is an operating rule with hash-based detection after a source
page is registered. Use filesystem permissions or repository review if the
environment needs preventative enforcement.

## Operation log

`wiki/log.md` is append-only. Every operation heading is followed by:

```markdown
- operation_id: ingest:abc123
- outcome: success
```

Operation IDs are stable across retries and are permanently bound to one
operation/subject pair. The same ID may have one `failed` and a later `success`
result; it may not regress from `success` to `failed`. An identical
ID/outcome pair is written only once. A later incident gets a new operation ID.
This makes retry closure observable without silently swallowing another
operation or duplicating success records.
