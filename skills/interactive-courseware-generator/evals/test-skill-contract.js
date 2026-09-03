#!/usr/bin/env node

const fs = require('node:fs');
const path = require('node:path');

const skillDir = path.resolve(__dirname, '..');

function read(relativePath) {
  return fs.readFileSync(path.join(skillDir, relativePath), 'utf8');
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function parseJson(relativePath) {
  return JSON.parse(read(relativePath));
}

function sameJson(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

function parseJsonLines(relativePath) {
  return read(relativePath).trim().split('\n').map((line) => JSON.parse(line));
}

function defaultPrompt(yaml) {
  const match = yaml.match(/^\s*default_prompt:\s*"([^"]+)"\s*$/m);
  return match?.[1];
}

const skill = read('SKILL.md');
const suite = read('references/course-suite-framework.md');
const framework = read('references/generation-framework.md');
const gates = read('references/quality-gates.md');
const triggerCases = parseJson('evals/trigger_cases.json');
const manifest = parseJson('manifest.json');
const skillIr = parseJson('reports/skill-ir.json');
const intent = parseJson('reports/intent-context.json');
const semanticConfig = parseJson('evals/semantic_config.json');
const systemModel = read('reports/system-model.md');
const interfaceYaml = read('agents/interface.yaml');
const openaiYaml = read('agents/openai.yaml');
const outputCases = parseJsonLines('evals/output/cases.jsonl');
const blindPack = parseJson('reports/output_blind_review_pack.json');
const scorecard = parseJson('reports/output_quality_scorecard.json');

for (const reference of [...skill.matchAll(/\]\((references\/[^)]+)\)/g)].map((match) => match[1])) {
  assert(fs.existsSync(path.join(skillDir, reference)), `missing referenced file: ${reference}`);
}

assert(skill.includes('2–4 个概念页'), 'SKILL.md should define the compact suite page budget');
assert(skill.includes('不同因果模型'), 'SKILL.md should allow distinct causal models to create separate pages');
assert(skill.includes('不要把术语数量直接等同于页数'), 'SKILL.md should reject term-driven pagination');
assert(skill.includes('一个问题、一个主要操作、一个核心现象、一个结论'), 'SKILL.md should define the four-beat page contract');
assert(skill.includes('最小真实命令、代码或配置'), 'SKILL.md should require practical usage for technical topics');
assert(skill.includes('目录页改做导航与链接检查'), 'SKILL.md should exempt the index page from simulation validation');
assert(skill.includes('普通 `<a>` 导航不属于资源依赖'), 'SKILL.md should distinguish navigation from external resources');
assert(!skill.includes('在每个 HTML 内嵌'), 'SKILL.md must not require simulation config on the index page');
assert(!skill.includes('对每个 HTML 运行'), 'SKILL.md must not run the simulation validator on the index page');
assert(!skill.includes('前三页'), 'SKILL.md should not assume a three-page MQTT-derived suite');

assert(suite.includes('index.html'), 'course suite framework should define an index entrypoint');
assert(suite.includes('先备关系决定页面顺序，但不是分页的唯一理由'), 'course suite framework should not require prerequisite dependency for every split');
assert(suite.includes('同一变量的档位'), 'course suite framework should keep comparable modes on one page');
assert(suite.includes('默认界面只保留'), 'course suite framework should define progressive disclosure');
assert(suite.includes('综合实验只在'), 'course suite framework should make the capstone conditional');
assert(suite.includes('不必伪造 `courseware-config`'), 'course suite framework should validate index navigation separately');
assert(!suite.includes('前三页'), 'course suite framework should not assume a three-page MQTT-derived suite');

assert(framework.includes('{{realWorldScenario}}'), 'generation prompt should include a real-world scenario field');
assert(framework.includes('{{practicalUsage}}'), 'generation prompt should include a practical usage field');
assert(
  framework.includes('学习问题、因果模型、观察对象和先备关系'),
  'generation framework should use all four pagination signals',
);
assert(gates.includes('认知负担检查'), 'quality gates should include cognitive-load review');
assert(gates.includes('紧凑课件组检查'), 'quality gates should include suite-level review');
assert(gates.includes('普通 `<a>` 页间导航不按外部资源处理'), 'quality gates should allow local page navigation');
assert(gates.includes('不要求满足模拟器 validator'), 'quality gates should exempt index pages from simulation validation');

assert(manifest.version === '1.1.0', 'manifest should declare the evolved skill version');
assert(manifest.factory_components.includes('evals'), 'manifest should include the contract eval component');
assert(
  semanticConfig.fallback_positive_concepts.includes('course_suite'),
  'semantic config should route compact suite requests',
);
assert(
  Math.abs(Object.values(semanticConfig.positive_concepts).reduce((sum, concept) => sum + concept.weight, 0) - 1) < 1e-9,
  'semantic positive concept weights should sum to 1',
);
assert(skillIr.resources.references.includes('references/course-suite-framework.md'), 'skill IR should list the suite framework');
assert(
  intent.constraints.some((item) => item.includes('学习问题、因果模型、观察对象和先备关系')),
  'intent context should preserve all pagination signals',
);
assert(
  systemModel.includes('学习问题、因果模型、观察对象和先备关系'),
  'system model should preserve all pagination signals',
);
assert(
  sameJson(skillIr.trigger_surface.should_trigger, triggerCases.should_trigger),
  'skill IR should mirror should-trigger cases',
);
assert(
  sameJson(skillIr.trigger_surface.should_not_trigger, triggerCases.should_not_trigger),
  'skill IR should mirror should-not-trigger cases',
);
assert(
  sameJson(skillIr.trigger_surface.edge_cases, triggerCases.near_neighbor),
  'skill IR should mirror near-neighbor cases',
);
assert(defaultPrompt(interfaceYaml), 'generic adapter should declare a default prompt');
assert(
  defaultPrompt(interfaceYaml) === defaultPrompt(openaiYaml),
  'generic and OpenAI adapters should use the same default prompt',
);

const staticDeckCase = outputCases.find(({ id }) => id === 'near-neighbor-static-deck');
assert(staticDeckCase, 'recorded fixtures should keep the static-deck near-neighbor case');
assert(
  staticDeckCase.with_skill_output.includes('单页或紧凑课件组') &&
    staticDeckCase.with_skill_output.includes('不负责静态幻灯片'),
  'recorded fixture should state the current courseware boundary',
);
assert(
  !staticDeckCase.with_skill_output.includes('只负责一页'),
  'recorded fixture must not preserve the retired single-page-only boundary',
);
const blindDeckPair = blindPack.pairs.find(({ case_id: caseId }) => caseId === staticDeckCase.id);
assert(
  [blindDeckPair?.variant_a.output, blindDeckPair?.variant_b.output].includes(staticDeckCase.with_skill_output),
  'blind fixture pack should mirror the current static-deck output',
);
const scorecardDeck = scorecard.results.find(({ id }) => id === staticDeckCase.id);
assert(scorecardDeck?.with_skill_fixture.failed_count === 0, 'scorecard should pass the current static-deck fixture');

assert(
  triggerCases.should_trigger.some((prompt) => prompt.includes('一套 MQTT 入门 HTML 课件')),
  'trigger evals should cover compact protocol courseware',
);
assert(
  triggerCases.should_trigger.some((prompt) => prompt.includes('降低干扰')),
  'trigger evals should cover simplifying an existing courseware page',
);

process.stdout.write('skill contract regression passed: suite planning, four-beat layout, practical usage, cognitive-load gates\n');
