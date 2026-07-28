# Governed evolution

Use this file for changes to the wiki contract rather than ordinary content.

## Why evolution is controlled

An LLM-maintained wiki needs to learn from experience, but letting each session
rewrite the schema creates drift. Evolution therefore uses evidence, proposals,
migrations, and validation.

## Trigger

Create a schema proposal when:

- the same maintenance defect appears at least twice;
- a page type repeatedly fails to represent important knowledge;
- retrieval misses have observable examples;
- a naming or taxonomy convention repeatedly causes duplicates;
- the user states a durable new convention;
- a tool or scale boundary has actually been reached.

Do not evolve the schema from one aesthetic preference or one unusual source.

## Proposal format

Append to `wiki/meta/schema-proposals.md`:

```markdown
## [YYYY-MM-DD] <proposal title>

- Status: proposed | approved | rejected | applied
- Evidence: <log entries, lint findings, or user instruction>
- Problem: <observable failure>
- Contract change: <precise before and after>
- Impact: <files, page types, tools>
- Migration: <bounded deterministic steps>
- Validation: <positive check and negative probe>
- Rollback: <how to restore the previous contract>
- Decision owner: user | named owner
```

## Decision boundary

- A direct user instruction such as "以后都按这个规则" is approval.
- Additive clarification with no data migration may be applied in the current
  task when the user's intent is explicit.
- Taxonomy rewrites, ID changes, directory moves, provenance weakening, or
  multi-page migrations require explicit approval after showing impact.
- The agent never approves its own semantic conflict resolution.

## Apply

1. Ensure the proposal is approved.
2. Capture the current git diff or another recoverable snapshot.
3. Update `WIKI.md` as the single schema truth.
4. If compatibility changes, increment `schema_version`.
5. Apply the smallest migration. Never touch existing raw files.
6. Add or update a deterministic lint rule where possible.
7. Run a negative probe and confirm the rule fails.
8. Remove the probe, update page/index data only as required by the migration,
   and rerun lint successfully.
9. Append to `wiki/meta/evolution-log.md`.
10. Append one idempotent `schema-evolve` success/failure result to
    `wiki/log.md`.

## Learn without bloating the schema

Promote durable rules, not incident stories. Keep detailed evidence in the
proposal/evolution log and write only the generalized convention into `WIKI.md`.
If a rule cannot be checked mechanically, label its authority:

- deterministic gate;
- inferential review criterion;
- human acceptance decision.

Do not disguise a semantic judgment as a linter guarantee.

## Retrieval evolution

Start with index plus full-text search. Add a derived retrieval layer only after
recorded misses show the need. Before adoption define:

- the corpus it indexes;
- rebuild and freshness behavior;
- how results link back to Markdown truth;
- a small retrieval eval set;
- failure fallback to index plus `rg`;
- uninstall/rebuild procedure.

Never make vector state the only copy of knowledge.

## Scheduled evolution

"Runs continuously" is an operational claim. It is true only when all of these
exist and are inspectable:

- a concrete scheduler or long-running process;
- persisted run state and logs;
- an owner and failure notification path;
- concurrency control;
- cancellation and rollback;
- source/network permission boundaries.

Without them, describe the workflow as manually invokable, not autonomous.
