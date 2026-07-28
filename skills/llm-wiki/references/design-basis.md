# Design basis

This skill is an original implementation informed by:

- Andrej Karpathy, “LLM Wiki”:
  https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
- Astro-Han, `karpathy-llm-wiki` (MIT):
  https://github.com/Astro-Han/karpathy-llm-wiki
- Ar9av, `obsidian-wiki` (MIT), for source trust boundaries, dry-run audits,
  and progressive retrieval:
  https://github.com/Ar9av/obsidian-wiki
- sametbrr, `llm-wiki-manager` (MIT):
  https://github.com/sametbrr/llm-wiki-manager
- daymade, `llm-wiki-setup` (MIT), for separating a stable mechanism layer
  from an evidence-evolved rule layer:
  https://github.com/daymade/claude-code-skills/tree/main/llm-wiki-setup
- Nous Research, Hermes Agent `llm-wiki` skill (MIT):
  https://github.com/NousResearch/hermes-agent/tree/main/skills/research/llm-wiki
- kepano, `obsidian-skills` (MIT), for portable Obsidian Markdown conventions:
  https://github.com/kepano/obsidian-skills

The implementation deliberately does not copy the large source-adapter stacks
from other projects. Acquisition is delegated to the best available platform or
file skill; this package owns compilation, provenance, navigation, linting, and
evolution.
