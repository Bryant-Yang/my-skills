#!/usr/bin/env node

const path = require('node:path');
const { spawnSync } = require('node:child_process');

const skillDir = path.resolve(__dirname, '..');
const validator = path.join(skillDir, 'scripts', 'validate-courseware.js');
const fixturesDir = path.join(__dirname, 'fixtures');

function runFixture(name, extraArgs = []) {
  const result = spawnSync(process.execPath, [validator, path.join(fixturesDir, `${name}.html`), '--json', ...extraArgs], {
    encoding: 'utf8',
  });
  if (result.error) throw result.error;
  let report;
  try {
    report = JSON.parse(result.stdout);
  } catch (error) {
    throw new Error(`${name}: validator did not return JSON: ${error.message}`);
  }
  return { exitCode: result.status, report };
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function errorCodes(report) {
  return report.errors.map(({ code }) => code).sort();
}

for (const name of ['minimal-valid-courseware', 'minimal-valid-enum-courseware']) {
  const { exitCode, report } = runFixture(name);
  assert(exitCode === 0, `${name}: expected exit 0, got ${exitCode}`);
  assert(report.ok === true, `${name}: expected ok=true`);
  assert(report.summary.errors === 0, `${name}: expected zero errors`);
  assert(report.summary.warnings === 0, `${name}: expected zero warnings`);
}

const invalidCases = {
  'invalid-courseware': [
    'controls',
    'courseware-config-count',
    'doctype-count',
    'viewport',
    'visualization',
  ],
  'invalid-config-courseware': ['courseware-config-shape'],
  'invalid-schema-courseware': [
    'courseware-topic',
    'host-bridge-type',
    'preset-value-option',
    'preset-value-range',
    'variable-control',
    'variable-default-option',
    'variable-default-range',
    'variable-options-duplicate',
    'variable-step',
    'variable-unit',
  ],
  'remote-dependency-courseware': ['external-dependencies'],
};

for (const [name, expectedCodes] of Object.entries(invalidCases)) {
  const { exitCode, report } = runFixture(name);
  assert(exitCode === 1, `${name}: expected exit 1, got ${exitCode}`);
  assert(report.ok === false, `${name}: expected ok=false`);
  assert(
    JSON.stringify(errorCodes(report)) === JSON.stringify([...expectedCodes].sort()),
    `${name}: unexpected errors ${JSON.stringify(errorCodes(report))}`,
  );
}

const remoteReport = runFixture('remote-dependency-courseware').report;
assert(
  remoteReport.errors[0].message.includes('Found 5 external'),
  'remote-dependency-courseware: expected quoted and unquoted assets, fetch, import, and Worker references to be detected',
);

const allowedExternal = runFixture('remote-dependency-courseware', ['--allow-external-dependencies']);
assert(allowedExternal.exitCode === 0, 'explicit external dependency allowance should exit 0');
assert(allowedExternal.report.ok === true, 'explicit external dependency allowance should keep ok=true');
assert(
  allowedExternal.report.warnings.some(({ code }) => code === 'external-dependencies-approved'),
  'explicit external dependency allowance should remain visible as a warning',
);

process.stdout.write('validator regression fixtures passed: 2 valid, 4 invalid, explicit external opt-in\n');
