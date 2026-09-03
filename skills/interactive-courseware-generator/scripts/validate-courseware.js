#!/usr/bin/env node

const fs = require('node:fs');
const path = require('node:path');

const args = process.argv.slice(2);
const jsonMode = args.includes('--json');
const requireHostBridge = args.includes('--require-host-bridge');
const fileArg = args.find((arg) => !arg.startsWith('--'));

if (args.includes('--help')) {
  process.stdout.write('Usage: node scripts/validate-courseware.js <courseware.html> [--json] [--require-host-bridge]\n');
  process.exit(0);
}

if (!fileArg) {
  const usage = 'Usage: node scripts/validate-courseware.js <courseware.html> [--json] [--require-host-bridge]';
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

const configBlock = scriptBlocks.find(
  ({ attrs }) =>
    /\bid\s*=\s*["']courseware-config["']/i.test(attrs) &&
    /\btype\s*=\s*["']application\/json["']/i.test(attrs),
);

let config;
if (!configBlock) {
  issue(errors, 'courseware-config-missing', 'Missing application/json script with id="courseware-config"');
} else {
  try {
    config = JSON.parse(configBlock.content.trim());
    pass('courseware-config-json', 'courseware-config is valid JSON');
  } catch (error) {
    issue(errors, 'courseware-config-json', `courseware-config JSON parse failed: ${error.message}`);
  }
}

if (config && (typeof config !== 'object' || Array.isArray(config))) {
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

      if (typeof variable.default === 'number') {
        if (typeof variable.min !== 'number' || typeof variable.max !== 'number') {
          issue(warnings, 'variable-range', `Numeric variable "${name}" should declare min and max`);
        } else if (variable.min > variable.max) {
          issue(errors, 'variable-range-order', `Variable "${name}" has min greater than max`);
        } else if (variable.default < variable.min || variable.default > variable.max) {
          issue(errors, 'variable-default-range', `Variable "${name}" default is outside min/max`);
        }
      }
    }
    if (seen.size === config.variables.length) {
      pass('variable-names', `${seen.size} unique variable name(s)`);
    }
  }

  if (Array.isArray(config.presets) && config.presets.length > 0) {
    pass('presets', `${config.presets.length} preset(s) declared`);
    const variableNames = new Set((config.variables || []).map((item) => item?.name).filter(Boolean));
    for (const [index, preset] of config.presets.entries()) {
      if (!preset || typeof preset !== 'object' || !preset.variables || typeof preset.variables !== 'object') {
        issue(warnings, 'preset-shape', `presets[${index}] should contain a variables object`);
        continue;
      }
      for (const name of Object.keys(preset.variables)) {
        if (!variableNames.has(name)) {
          issue(errors, 'preset-variable', `Preset ${index} references undeclared variable "${name}"`);
        }
      }
    }
  } else {
    issue(warnings, 'presets', 'No presets declared in courseware-config');
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

const remoteAssetPattern = /<(?:script|link|iframe)\b[^>]*(?:src|href)\s*=\s*["']https?:\/\//gi;
const remoteAssets = count(remoteAssetPattern);
if (remoteAssets > 0) {
  issue(errors, 'remote-assets', `Found ${remoteAssets} remote script, stylesheet, or iframe reference(s)`);
} else {
  pass('remote-assets', 'No remote script, stylesheet, or iframe references found');
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
