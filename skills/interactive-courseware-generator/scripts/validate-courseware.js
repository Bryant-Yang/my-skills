#!/usr/bin/env node

const fs = require('node:fs');
const path = require('node:path');

const args = process.argv.slice(2);
const jsonMode = args.includes('--json');
const requireHostBridge = args.includes('--require-host-bridge');
const allowExternalDependencies = args.includes('--allow-external-dependencies');
const fileArg = args.find((arg) => !arg.startsWith('--'));

if (args.includes('--help')) {
  process.stdout.write('Usage: node scripts/validate-courseware.js <courseware.html> [--json] [--require-host-bridge] [--allow-external-dependencies]\n');
  process.exit(0);
}

if (!fileArg) {
  const usage = 'Usage: node scripts/validate-courseware.js <courseware.html> [--json] [--require-host-bridge] [--allow-external-dependencies]';
  if (jsonMode) {
    process.stdout.write(`${JSON.stringify({ ok: false, error: usage }, null, 2)}\n`);
  } else {
    process.stderr.write(`${usage}\n`);
  }
  process.exit(2);
}

const target = path.resolve(fileArg);
if (!fs.existsSync(target) || !fs.statSync(target).isFile()) {
  const message = `File not found: ${target}`;
  if (jsonMode) {
    process.stdout.write(`${JSON.stringify({ ok: false, error: message }, null, 2)}\n`);
  } else {
    process.stderr.write(`${message}\n`);
  }
  process.exit(2);
}

const html = fs.readFileSync(target, 'utf8');
const errors = [];
const warnings = [];
const passes = [];

function issue(bucket, code, message) {
  bucket.push({ code, message });
}

function pass(code, message) {
  passes.push({ code, message });
}

function count(pattern) {
  return [...html.matchAll(pattern)].length;
}

function checkExact(pattern, expected, code, label) {
  const actual = count(pattern);
  if (actual === expected) {
    pass(code, `${label}: ${actual}`);
  } else {
    issue(errors, code, `${label} should appear ${expected} time(s), found ${actual}`);
  }
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function isPlainObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function isFiniteNumber(value) {
  return typeof value === 'number' && Number.isFinite(value);
}

function alignsToStep(value, min, step) {
  if (![value, min, step].every(isFiniteNumber) || step <= 0) return false;
  const offset = (value - min) / step;
  return Math.abs(offset - Math.round(offset)) < 1e-9;
}

if (html.trim().length === 0) {
  issue(errors, 'empty-file', 'HTML file is empty');
}

checkExact(/<!doctype\s+html\b[^>]*>/gi, 1, 'doctype-count', 'DOCTYPE');
checkExact(/<html\b[^>]*>/gi, 1, 'html-open-count', 'Opening html tag');
checkExact(/<\/html\s*>/gi, 1, 'html-close-count', 'Closing html tag');
checkExact(/<body\b[^>]*>/gi, 1, 'body-open-count', 'Opening body tag');
checkExact(/<\/body\s*>/gi, 1, 'body-close-count', 'Closing body tag');

if (/<meta\b[^>]*name\s*=\s*["']viewport["'][^>]*>/i.test(html)) {
  pass('viewport', 'Viewport meta tag found');
} else {
  issue(errors, 'viewport', 'Missing viewport meta tag');
}

if (/<(?:canvas|svg)\b/i.test(html)) {
  pass('visualization', 'Canvas or SVG visualization found');
} else {
  issue(errors, 'visualization', 'Missing Canvas or SVG visualization');
}

if (/<(?:input|select|button|textarea)\b/i.test(html)) {
  pass('controls', 'Interactive controls found');
} else {
  issue(errors, 'controls', 'No interactive input, select, button, or textarea found');
}

const scriptBlocks = [];
const scriptPattern = /<script\b([^>]*)>([\s\S]*?)<\/script\s*>/gi;
for (const match of html.matchAll(scriptPattern)) {
  scriptBlocks.push({ attrs: match[1], content: match[2] });
}

const configBlocks = scriptBlocks.filter(
  ({ attrs }) =>
    /\bid\s*=\s*["']courseware-config["']/i.test(attrs) &&
    /\btype\s*=\s*["']application\/json["']/i.test(attrs),
);
const configBlock = configBlocks[0];

let config;
if (configBlocks.length !== 1) {
  issue(
    errors,
    'courseware-config-count',
    `Expected exactly one application/json script with id="courseware-config", found ${configBlocks.length}`,
  );
}
if (configBlock) {
  try {
    config = JSON.parse(configBlock.content.trim());
    pass('courseware-config-json', 'courseware-config is valid JSON');
  } catch (error) {
    issue(errors, 'courseware-config-json', `courseware-config JSON parse failed: ${error.message}`);
  }
} else {
  config = undefined;
}

if (config !== undefined && !isPlainObject(config)) {
  issue(errors, 'courseware-config-shape', 'courseware-config must be a JSON object');
  config = undefined;
}

if (config) {
  if (config.schemaVersion === 1) {
    pass('config-schema-version', 'courseware-config schemaVersion is 1');
  } else {
    issue(errors, 'config-schema-version', `courseware-config schemaVersion must be 1, found ${JSON.stringify(config.schemaVersion)}`);
  }

  if (config.kind === 'simulation') {
    pass('courseware-kind', 'courseware-config kind is simulation');
  } else {
    issue(errors, 'courseware-kind', `courseware-config kind must be "simulation", found ${JSON.stringify(config.kind)}`);
  }

  if (typeof config.topic === 'string' && /^[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*$/.test(config.topic)) {
    pass('courseware-topic', `courseware-config topic is a stable slug: ${config.topic}`);
  } else {
    issue(errors, 'courseware-topic', 'courseware-config topic must be a non-empty lowercase English slug');
  }

  if ('hostBridge' in config && typeof config.hostBridge !== 'boolean') {
    issue(errors, 'host-bridge-type', 'courseware-config hostBridge must be boolean when present');
  }

  if (!Array.isArray(config.variables) || config.variables.length === 0) {
    issue(errors, 'variables', 'courseware-config.variables must be a non-empty array');
  } else {
    const seen = new Set();
    for (const [index, variable] of config.variables.entries()) {
      if (!variable || typeof variable !== 'object' || Array.isArray(variable)) {
        issue(errors, 'variable-shape', `variables[${index}] must be an object`);
        continue;
      }

      const name = typeof variable.name === 'string' ? variable.name.trim() : '';
      if (!name) {
        issue(errors, 'variable-name', `variables[${index}] is missing a non-empty name`);
        continue;
      }
      if (seen.has(name)) {
        issue(errors, 'variable-duplicate', `Duplicate variable name: ${name}`);
      }
      seen.add(name);

      if (typeof variable.control !== 'string' || variable.control.trim() === '') {
        issue(errors, 'variable-control', `Variable "${name}" is missing a non-empty control`);
      }

      const escaped = escapeRegExp(name);
      const idHook = new RegExp(`\\bid\\s*=\\s*["']${escaped}-(?:slider|control|input)["']`, 'i');
      const dataHook = new RegExp(`\\bdata-var\\s*=\\s*["']${escaped}["']`, 'i');
      if (!idHook.test(html) && !dataHook.test(html)) {
        issue(
          warnings,
          'variable-dom-hook',
          `Variable "${name}" has no stable id (${name}-slider/control/input) or data-var hook`,
        );
      }

      if (Array.isArray(variable.options)) {
        if (variable.options.length === 0) {
          issue(errors, 'variable-options', `Enum variable "${name}" must declare at least one option`);
        } else if (new Set(variable.options.map((value) => JSON.stringify(value))).size !== variable.options.length) {
          issue(errors, 'variable-options-duplicate', `Enum variable "${name}" contains duplicate options`);
        }
        if (!variable.options.some((value) => Object.is(value, variable.default))) {
          issue(errors, 'variable-default-option', `Enum variable "${name}" default is not present in options`);
        }
      } else {
        const numericFields = ['min', 'max', 'step', 'default'];
        for (const field of numericFields) {
          if (!isFiniteNumber(variable[field])) {
            issue(errors, 'variable-numeric-field', `Numeric variable "${name}" must declare finite ${field}`);
          }
        }
        if (typeof variable.unit !== 'string') {
          issue(errors, 'variable-unit', `Numeric variable "${name}" must declare unit as a string`);
        }
        if (isFiniteNumber(variable.step) && variable.step <= 0) {
          issue(errors, 'variable-step', `Numeric variable "${name}" step must be greater than zero`);
        }
        if (isFiniteNumber(variable.min) && isFiniteNumber(variable.max) && variable.min > variable.max) {
          issue(errors, 'variable-range-order', `Variable "${name}" has min greater than max`);
        } else if (
          isFiniteNumber(variable.default) &&
          isFiniteNumber(variable.min) &&
          isFiniteNumber(variable.max) &&
          (variable.default < variable.min || variable.default > variable.max)
        ) {
          issue(errors, 'variable-default-range', `Variable "${name}" default is outside min/max`);
        }
        if (
          isFiniteNumber(variable.default) &&
          isFiniteNumber(variable.min) &&
          isFiniteNumber(variable.step) &&
          variable.step > 0 &&
          !alignsToStep(variable.default, variable.min, variable.step)
        ) {
          issue(errors, 'variable-default-step', `Variable "${name}" default does not align with step from min`);
        }
      }
    }
    if (seen.size === config.variables.length) {
      pass('variable-names', `${seen.size} unique variable name(s)`);
    }
  }

  if (config.presets === undefined || (Array.isArray(config.presets) && config.presets.length === 0)) {
    issue(warnings, 'presets', 'No presets declared in courseware-config');
  } else if (!Array.isArray(config.presets)) {
    issue(errors, 'presets-shape', 'courseware-config presets must be an array when present');
  } else {
    pass('presets', `${config.presets.length} preset(s) declared`);
    const variableNames = new Set((config.variables || []).map((item) => item?.name).filter(Boolean));
    for (const [index, preset] of config.presets.entries()) {
      if (!isPlainObject(preset) || !isPlainObject(preset.variables)) {
        issue(errors, 'preset-shape', `presets[${index}] must contain a variables object`);
        continue;
      }
      if (typeof preset.name !== 'string' || preset.name.trim() === '') {
        issue(errors, 'preset-name', `presets[${index}] must declare a non-empty name`);
      }
      if (Object.keys(preset.variables).length === 0) {
        issue(errors, 'preset-variables-empty', `presets[${index}].variables must not be empty`);
      }
      for (const name of Object.keys(preset.variables)) {
        if (!variableNames.has(name)) {
          issue(errors, 'preset-variable', `Preset ${index} references undeclared variable "${name}"`);
          continue;
        }
        const variable = config.variables.find((item) => item?.name === name);
        const value = preset.variables[name];
        if (Array.isArray(variable.options) && !variable.options.some((option) => Object.is(option, value))) {
          issue(errors, 'preset-value-option', `Preset ${index} uses an invalid option for variable "${name}"`);
        } else if (
          !Array.isArray(variable.options) &&
          (!isFiniteNumber(value) || value < variable.min || value > variable.max)
        ) {
          issue(errors, 'preset-value-range', `Preset ${index} value for variable "${name}" is outside its numeric range`);
        } else if (
          !Array.isArray(variable.options) &&
          !alignsToStep(value, variable.min, variable.step)
        ) {
          issue(errors, 'preset-value-step', `Preset ${index} value for variable "${name}" does not align with step from min`);
        }
      }
    }
  }
}

const hostBridgeRequired = requireHostBridge || config?.hostBridge === true;
if (hostBridgeRequired) {
  if (/addEventListener\s*\(\s*["']message["']/i.test(html)) {
    pass('message-listener', 'postMessage listener found');
  } else {
    issue(errors, 'message-listener', 'Missing window message event listener for declared host bridge');
  }

  for (const type of [
    'COURSEWARE_SET_STATE',
    'COURSEWARE_HIGHLIGHT',
    'COURSEWARE_ANNOTATE',
    'COURSEWARE_REVEAL',
  ]) {
    if (html.includes(type)) {
      pass(`message-${type.toLowerCase()}`, `${type} handler token found`);
    } else {
      issue(errors, `message-${type.toLowerCase()}`, `Missing ${type} handler token`);
    }
  }
} else {
  pass('host-bridge-optional', 'Host bridge is not declared or required');
}

function isEmbeddedReference(value) {
  const normalized = value.trim().toLowerCase();
  return normalized === '' || normalized.startsWith('data:') || normalized.startsWith('blob:') || normalized.startsWith('#') || normalized === 'about:blank';
}

const externalReferences = [];
const referencedElementPattern = /<(?:script|link|iframe|img|audio|video|source|track|embed|object)\b([^>]*)>/gi;
for (const elementMatch of html.matchAll(referencedElementPattern)) {
  const attributePattern = /\b(srcset|src|href|poster|data)\s*=\s*(?:(["'])(.*?)\2|([^\s"'=<>`]+))/gi;
  for (const attributeMatch of elementMatch[1].matchAll(attributePattern)) {
    const attributeName = attributeMatch[1];
    const attributeValue = attributeMatch[3] ?? attributeMatch[4] ?? '';
    const values = attributeName.toLowerCase() === 'srcset' && !attributeValue.trim().toLowerCase().startsWith('data:')
      ? attributeValue.split(',').map((item) => item.trim().split(/\s+/)[0])
      : [attributeValue];
    if (values.some((value) => !isEmbeddedReference(value))) externalReferences.push('element');
  }
}

const cssUrlPattern = /url\(\s*["']?([^"')]+)["']?\s*\)/gi;
for (const match of html.matchAll(cssUrlPattern)) {
  if (!isEmbeddedReference(match[1])) externalReferences.push('css-url');
}
for (const match of html.matchAll(/@import\s+(?!url\()["']([^"']+)["']/gi)) {
  if (!isEmbeddedReference(match[1])) externalReferences.push('css-import');
}

const requestPatterns = [
  /\bfetch\s*\(\s*["'`]([^"'`]+)["'`]/gi,
  /\bimport\s*\(\s*["'`]([^"'`]+)["'`]/gi,
  /\bimport\s+(?:[^"'`]*?\s+from\s*)?["'`]([^"'`]+)["'`]/gi,
  /\bnew\s+(?:Worker|SharedWorker)\s*\(\s*["'`]([^"'`]+)["'`]/gi,
  /\bimportScripts\s*\(\s*["'`]([^"'`]+)["'`]/gi,
  /\bnavigator\.serviceWorker\.register\s*\(\s*["'`]([^"'`]+)["'`]/gi,
  /\bnew\s+URL\s*\(\s*["'`]([^"'`]+)["'`]/gi,
  /\bnew\s+(?:WebSocket|EventSource)\s*\(\s*["'`]([^"'`]+)["'`]/gi,
  /\.open\s*\(\s*["'`](?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)["'`]\s*,\s*["'`]([^"'`]+)["'`]/gi,
  /\bnavigator\.sendBeacon\s*\(\s*["'`]([^"'`]+)["'`]/gi,
];
for (const pattern of requestPatterns) {
  for (const match of html.matchAll(pattern)) {
    if (!isEmbeddedReference(match[1])) externalReferences.push('network-request');
  }
}

if (externalReferences.length > 0 && !allowExternalDependencies) {
  issue(errors, 'external-dependencies', `Found ${externalReferences.length} external asset or network request reference(s)`);
} else if (externalReferences.length > 0) {
  issue(warnings, 'external-dependencies-approved', `Allowed ${externalReferences.length} external reference(s) by explicit flag; list them in the verification report`);
} else {
  pass('external-dependencies', 'No static external asset or network request references found');
}

const fixedCanvasSize = [...html.matchAll(/<canvas\b[^>]*>/gi)].some(
  ([tag]) => /\bwidth\s*=\s*["']?\d+/i.test(tag) && /\bheight\s*=\s*["']?\d+/i.test(tag),
);
const responsiveCanvasSignal = /(?:ResizeObserver|devicePixelRatio|getBoundingClientRect|clientWidth|clientHeight|addEventListener\s*\(\s*["']resize["'])/;
if (fixedCanvasSize && !responsiveCanvasSignal.test(html)) {
  issue(warnings, 'fixed-canvas-size', 'Canvas has fixed width and height without a detected responsive resize strategy');
}

if (/requestAnimationFrame\s*\(/.test(html)) {
  pass('animation-frame', 'requestAnimationFrame found');
} else {
  issue(warnings, 'animation-frame', 'No requestAnimationFrame call found; verify whether animation is required');
}

if (/\baria-(?:label|labelledby)\s*=/i.test(html) || /<label\b/i.test(html)) {
  pass('accessible-labels', 'Label or ARIA labeling found');
} else {
  issue(warnings, 'accessible-labels', 'No label or aria-label/aria-labelledby found');
}

if (/(?:keydown|keyup|KeyboardEvent|event\.key)/.test(html)) {
  pass('keyboard', 'Keyboard interaction code found');
} else {
  issue(warnings, 'keyboard', 'No keyboard interaction code detected');
}

for (const [index, block] of scriptBlocks.entries()) {
  if (/\btype\s*=\s*["']application\/json["']/i.test(block.attrs)) continue;
  if (/\bsrc\s*=/i.test(block.attrs)) continue;
  if (/\btype\s*=\s*["']module["']/i.test(block.attrs)) {
    issue(warnings, 'module-script-syntax', `Inline module script ${index + 1} was not syntax-checked`);
    continue;
  }
  try {
    // Parse only. The function body is not executed.
    new Function(block.content);
  } catch (error) {
    issue(warnings, 'inline-script-syntax', `Inline script ${index + 1} failed conservative syntax parsing: ${error.message}`);
  }
}

const report = {
  schemaVersion: 1,
  file: target,
  ok: errors.length === 0,
  summary: {
    errors: errors.length,
    warnings: warnings.length,
    passes: passes.length,
  },
  errors,
  warnings,
  passes,
  limits: [
    'Static validation does not execute the page.',
    'Visual layout, runtime behavior, selector visibility, and domain correctness require separate checks.',
  ],
};

if (jsonMode) {
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
} else {
  process.stdout.write(`${report.ok ? 'PASS' : 'FAIL'} ${target}\n`);
  process.stdout.write(`errors=${errors.length} warnings=${warnings.length} passes=${passes.length}\n`);
  for (const item of errors) process.stdout.write(`ERROR ${item.code}: ${item.message}\n`);
  for (const item of warnings) process.stdout.write(`WARN  ${item.code}: ${item.message}\n`);
}

process.exit(report.ok ? 0 : 1);
