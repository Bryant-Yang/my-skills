# Artifact Design Profile

Skill: `interactive-courseware-generator`
Design system: `review studio`

## Primary Artifact Direction

**Code, CLI, or implementation guide**

Execution-focused technical artifact with environment assumptions, copyable commands, expected outputs, and side effects made explicit.

## Matched Artifact Families

### Code, CLI, or implementation guide
- Matched keywords: code, script, command, 代码, 脚本, 接口
- Score: `6`
- Direction: Execution-focused technical artifact with environment assumptions, copyable commands, expected outputs, and side effects made explicit.

### Tutorial or guide
- Matched keywords: tutorial, course, 课程
- Score: `3`
- Direction: Progressive instructional layout with domain-specific section names, short success checks, and examples close to the user's real input.

### Report or brief
- Matched keywords: 报告
- Score: `1`
- Direction: High-trust editorial report with a clear first-screen thesis, compact evidence blocks, and decisions separated from supporting detail.

### Review viewer
- Matched keywords: 对比
- Score: `1`
- Direction: Side-by-side reviewer studio with explicit tradeoffs, evidence readiness, and fast paths for approving, blocking, or requesting one focused fix.

### Screenshot or visual evidence
- Matched keywords: screenshot
- Score: `1`
- Direction: Evidence-led visual artifact that records source, viewport, crop intent, and the exact region the reader should inspect.

## Layout Patterns To Prefer

- prerequisites
- commands
- expected output
- failure handling
- rollback or cleanup
- opening promise
- task-specific sections
- worked example

## Design Tokens

### Type
- Use a distinctive display face or serif for major claims when the artifact is editorial.
- Use a restrained sans for dense body text and technical details.
- Use mono only for metadata, paths, commands, labels, and evidence tags.

### Color
- Choose colors from the artifact's domain, brand, or evidence mood.
- Do not default to Kami parchment, purple gradients, or generic SaaS blue unless the content justifies it.
- Keep accent color limited to decisions, active states, risk, or section anchors.

### Spacing
- Prefer clear grid rhythm over floating decorative cards.
- Increase whitespace around decisions and shrink whitespace around supporting metadata.
- Split dense content instead of shrinking type or adding scroll traps.

### Components
- Use cards for grouped evidence, tables for comparisons, callouts for decisions, and timelines for sequence.
- Avoid cards inside cards.
- Keep reviewer-only detail visible but visually quieter than user-facing guidance.

## Quality Gates

- Name the working directory and required inputs for commands.
- Mark destructive, networked, or external side-effect operations.
- Prefer the smallest runnable snippet over broad framework scaffolding.
- Replace generic headings with learner- and domain-specific headings.
- Pair every major step with a visible success check.
- Do not add screenshots unless they are real, current, and action-relevant.
- Keep the first screen useful without requiring the reader to parse every detail.
- Use tables only for comparisons; move explanations below the table.

## Anti-Patterns

- Do not copy Kami's fixed parchment background as a default.
- Do not use generic purple gradients, glass cards, or stock SaaS hero sections unless the content calls for them.
- Do not let Markdown tables become the default shape for every comparison or explanation.
- Do not turn reviewer evidence into user-facing clutter.
- Do not invent screenshots, citations, charts, or UI states.

## Reviewer Note

Use this profile to judge whether the generated artifacts feel designed for their job, not merely rendered.
