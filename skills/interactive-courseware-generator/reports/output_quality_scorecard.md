# Recorded Fixture Contract Scorecard

This scorecard checks hand-authored baseline and with-skill fixture text against required-string assertions. It does not contain model runs and is not a release gate.

- Cases: `5`
- Baseline fixture pass rate: `0.0`
- With-skill fixture pass rate: `100.0`
- Fixture delta: `100.0`
- Fixture regressions: `0`
- Blind A/B pairs: `5`
- Release gate: `False`

Blind review artifacts are generated separately so reviewers can inspect A/B outputs without seeing the answer key.
Run output review adjudication after reviewer decisions are recorded; pending cases should stay pending rather than being counted as human agreement.

## Case Results

| Case | Baseline Fixture | With-Skill Fixture | Delta | Fixture Winner | Failed Fixture Assertions |
| --- | ---: | ---: | ---: | --- | --- |
| build-interactive-page | 0.0 | 100.0 | 100.0 | with_skill | None |
| prompt-only-mode | 0.0 | 100.0 | 100.0 | with_skill | None |
| repair-existing-page | 0.0 | 100.0 | 100.0 | with_skill | None |
| domain-correctness-boundary | 0.0 | 100.0 | 100.0 | with_skill | None |
| near-neighbor-static-deck | 0.0 | 100.0 | 100.0 | with_skill | None |

## Failure Taxonomy

- No with-skill assertion failures.

## Next Evidence

- Run provider-backed with-skill and baseline cases, capture timing and grading, and add holdout cases before considering a release gate.
- Promote repeated failed assertions into the output-risk profile.
- Keep assertions tied to material deliverables, not phrasing trivia.
