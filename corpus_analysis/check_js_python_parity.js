// Durable Python <-> JS classifier agreement check — promotes the scratch
// script built during P1.5 (which found a real bug: the JS
// react_select_required_shim check tested the wrong field property and
// silently never fired) into a permanent, re-runnable tool instead of
// something rebuilt from scratch every time classification logic changes.
//
// Samples N real fields from the corpus, runs BOTH
// corpus_analysis/interpreter_p14.py's interpret() and
// extension/filler_utils.js's classifyField() against each, and reports
// any disagreement. Re-run this any time either implementation changes —
// per corpus_analysis/INTERPRETER_SPEC.md's shared-spec discipline, they
// must independently satisfy the same spec, and this is how you verify
// they still do after an edit.
//
// Run: node corpus_analysis/check_js_python_parity.js [sampleSize] [seed] [--json-out=<path>]
//
// --json-out=<path> is an additive harness-support flag (test_pipeline/checkpoint/
// gate.py needs this, added up front per joyful-sprouting-swan.md's gate.py
// spec, not as a "fix" to this script's own behavior). Writes a structured
// JSON summary to <path> in addition to the normal console output — console
// output and exit code are completely unchanged, this is purely additive.
// gate.py runs this script twice against the SAME fixed seed (pre-fix and
// post-fix against a scratch copy) and diffs the two JSON summaries: post
// must not introduce any disagreement that wasn't already present pre-fix.
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { execFileSync } = require('child_process');

const BASE = __dirname;

const rawArgs = process.argv.slice(2);
const positionalArgs = rawArgs.filter(function (a) { return a.indexOf('--') !== 0; });
const jsonOutArg = rawArgs.filter(function (a) { return a.indexOf('--json-out=') === 0; })[0];
const jsonOutPath = jsonOutArg ? jsonOutArg.slice('--json-out='.length) : null;

const sampleSize = parseInt(positionalArgs[0], 10) || 200;
const seed = parseInt(positionalArgs[1], 10) || Date.now();

// ---- Load the JS implementation in a minimal sandbox ----
const src = fs.readFileSync(path.join(BASE, '..', 'extension', 'filler_utils.js'), 'utf8');
const sandbox = {
  document: { querySelectorAll: () => [], getElementById: () => null, body: {} },
  window: {},
  chrome: { runtime: { sendMessage: () => {} } },
  console,
  Node: { TEXT_NODE: 3 },
  CSS: { escape: (s) => s },
  MutationObserver: function () { this.observe = () => {}; this.disconnect = () => {}; },
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(src, sandbox);

// Maps the corpus compact schema (h/tag/itype/htype/name/id/ac/role/req/
// vis/label/lstrat/section/nearby/opts/desc/placeholder) to the live
// Field object's property names.
function toFieldObject(f) {
  return {
    label: f.label || '',
    id: f.id || '',
    autocomplete: f.ac || '',
    placeholder: f.placeholder || '',
    section: f.section || '',
    nearbyText: f.nearby || '',
    htmlType: f.htype || '',
    required: f.req === true,
  };
}

function classifyJs(f) {
  const classified = sandbox.classifyField(toFieldObject(f), f.itype || 'text');
  if (!classified) return { category: null, action: null };
  if (classified.startsWith('__structural_')) {
    return { category: null, action: classified.slice('__structural_'.length).split('__')[0] };
  }
  return { category: classified.split('__')[0], action: null };
}

// ---- Sample real fields via a Python subprocess (reuses the same
// deterministic-seed random.sample() pattern used throughout
// corpus_analysis/) and get Python's classifications in the same call ----
const pyScript = `
import json, random
with open("oc_compact_full_v2.json", encoding="utf-8") as f:
    companies = json.load(f)
all_fields = []
for c in companies:
    all_fields.extend(c["fields"])
random.seed(${seed})
sample = random.sample(all_fields, min(${sampleSize}, len(all_fields)))

from interpreter_p14 import interpret
results = []
for f in sample:
    pred = interpret(f)
    results.append({"field": f, "category": pred.get("category"), "action": pred.get("action")})
print(json.dumps(results))
`;
const pyOut = execFileSync('python', ['-c', pyScript], { cwd: BASE, encoding: 'utf8', maxBuffer: 100 * 1024 * 1024 });
const pyResults = JSON.parse(pyOut);

// ---- Compare ----
let agree = 0;
const disagreements = [];
for (const r of pyResults) {
  const js = classifyJs(r.field);
  const same = js.category === r.category && js.action === r.action;
  if (same) agree++;
  else disagreements.push({ field: r.field, python: { category: r.category, action: r.action }, js });
}

console.log(`sample size: ${pyResults.length} (seed=${seed})`);
console.log(`agreement: ${agree}/${pyResults.length}`);
if (disagreements.length) {
  console.log(`\n${disagreements.length} disagreement(s):`);
  disagreements.slice(0, 20).forEach(d => {
    console.log(`  label=${JSON.stringify((d.field.label || '').slice(0, 80))} id=${JSON.stringify(d.field.id)} itype=${d.field.itype}`);
    console.log(`    python: category=${d.python.category} action=${d.python.action}`);
    console.log(`    js:     category=${d.js.category} action=${d.js.action}`);
  });
  if (disagreements.length > 20) console.log(`  ... and ${disagreements.length - 20} more`);
}

if (jsonOutPath) {
  const disagreementSummaries = disagreements.map(function (d) {
    const label = d.field.label || '';
    const id = d.field.id || '';
    const itype = d.field.itype || '';
    return {
      key: [label, id, itype].join('|'),
      label: label,
      id: id,
      itype: itype,
      python: d.python,
      js: d.js,
    };
  });
  const summary = {
    sampleSize: pyResults.length,
    seed: seed,
    agree: agree,
    total: pyResults.length,
    // Keyed by a stable identity (label+id+itype) rather than array index —
    // gate.py diffs two separate runs' disagreement sets, and array order
    // isn't guaranteed to be meaningful for that comparison even though
    // sample content is (same seed = same sample() draw).
    disagreements: disagreementSummaries,
  };
  fs.writeFileSync(jsonOutPath, JSON.stringify(summary, null, 2), 'utf8');
}

process.exit(disagreements.length > 0 ? 1 : 0);
