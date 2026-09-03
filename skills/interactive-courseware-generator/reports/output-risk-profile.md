# Output Risk Profile

Skill: `interactive-courseware-generator`

## Why This Exists

Generated skills often fail in small output details: generic headings, cluttered citations, fragile screenshots, weak Markdown rendering, or missing execution assumptions. This profile predicts the most likely output mistakes before the skill is used heavily.

## Matched Risk Families

### Code and command safety
- Matched keywords: script, 代码, 脚本, 接口
- Score: `4`

### Tutorial quality
- Matched keywords: course, 课程
- Score: `2`

### Markdown readability
- Matched keywords: md, 报告
- Score: `2`

### Citation and footnote clutter
- Matched keywords: reference
- Score: `1`

### Screenshot and visual capture
- Matched keywords: 视觉
- Score: `1`

## Likely Output Mistakes

- Commands can omit environment assumptions, working directory, or rollback notes.
- Code snippets can look runnable while missing required inputs.
- Generic section headings make the tutorial feel templated instead of fitted to the learner's task.
- Steps may explain what to do without naming the exact check that proves the step worked.
- Tables can render as dense grids with weak hierarchy or poor mobile readability.
- Long bullets can make the output look complete while hiding the actual decision logic.
- A topic outline can be mistaken for a page plan, producing one page per term or mode.
- Titles, goals, scenarios, controls, presets, metrics, traces, and explanations can all compete on the initial screen.
- Abstract definitions can crowd out the concrete problem and the smallest real command, code, or configuration needed to use the concept.

## Output Constraints To Apply

- Name the working directory, required inputs, and expected output for each command.
- Mark destructive or external side-effect operations explicitly.
- Write headings from the user's domain nouns and desired outcome, not from generic labels like Overview or Key Points.
- Pair each major step with a visible success check or expected intermediate output.
- Use tables only when comparison is the main job; otherwise prefer compact cards or grouped bullets.
- Keep table cells short and move explanations below the table.
- Keep each page to one learner question, one primary action, one visual focus, and one conclusion.
- Put commands, derivations, full rules, and protocol traces behind clearly named progressive disclosure.
- Reuse one concrete scenario across pages and keep same-model comparisons on one page.

## Self-Repair Checks

- Scan each command for cwd, input, output, and side-effect assumptions.
- Remove speculative error handling that is not tied to a real failure mode.
- Replace generic H2/H3 headings with task-specific headings before final output.
- Scan every numbered step for a missing verification cue.
- Preview whether each table still reads well when columns are narrow.
- Convert any table with paragraph-length cells into bullets or cards.
- Count independent learner questions rather than vocabulary terms when deciding page count.
- Inspect the initial viewport and remove any region that does not help the learner act or interpret the core result.
- Confirm technical courseware explains both what the concept is for and how to use it in a minimal real environment.

## Reviewer Note

Use this report before deepening the package and again before approving example outputs.
