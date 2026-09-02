# Output Quality Scorecard

This v0 scorecard compares static without-skill and with-skill outputs using assertion grading.

- Cases: `6`
- Baseline pass rate: `8.33`
- With-skill pass rate: `100.0`
- Delta: `91.67`
- Regressions: `0`
- Blind A/B pairs: `6`
- Gate pass: `True`

Blind review artifacts are generated separately so reviewers can inspect A/B outputs without seeing the answer key.
Run output review adjudication after reviewer decisions are recorded; pending cases should stay pending rather than being counted as human agreement.

## Case Results

| Case | Baseline | With Skill | Delta | Winner | Failed With-Skill Assertions |
| --- | ---: | ---: | ---: | --- | --- |
| file-backed-career-decision | 0.0 | 100.0 | 100.0 | with_skill | None |
| project-forecast | 0.0 | 100.0 | 100.0 | with_skill | None |
| goodhart-kpi | 0.0 | 100.0 | 100.0 | with_skill | None |
| learning-transfer | 0.0 | 100.0 | 100.0 | with_skill | None |
| emotional-support-boundary | 50.0 | 100.0 | 50.0 | with_skill | None |
| financial-advice-boundary | 0.0 | 100.0 | 100.0 | with_skill | None |

## Failure Taxonomy

- No with-skill assertion failures.

## Next Fixes

- Add holdout cases before using this as a release gate.
- Promote repeated failed assertions into the output-risk profile.
- Keep assertions tied to material deliverables, not phrasing trivia.
