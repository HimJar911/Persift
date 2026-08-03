// P1.5+ regression checker — every real bug found via live testing or
// replay becomes a permanent entry in interpreter_regressions.json, and
// this script confirms BOTH implementations (interpreter_p14.py and
// extension/filler_utils.js's classifyField()) still classify it
// correctly. Run this before committing any change to
// _FIELD_PATTERNS/FIELD_PATTERNS, alongside replay.py — the same way you'd
// run a test suite before a commit that touches shared logic.
//
// Run: node corpus_analysis/check_regressions.js
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { execFileSync } = require('child_process');

const BASE = __dirname;

// ---- Load the JS implementation in a minimal sandbox (same approach as
// P1.5's offline/live agreement check) ----
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

// Minimal field object — regression entries only carry a label today, so
// this only exercises the label tier (tier 3), which is where every
// regression entry so far originated. If a future regression involves
// autocomplete/id/placeholder, extend this shape and the JSON schema
// together.
function toFieldObject(label) {
  return { label, id: '', autocomplete: '', placeholder: '', section: '', nearbyText: '', htmlType: 'text', required: false };
}

function classifyJs(label) {
  const classified = sandbox.classifyField(toFieldObject(label), 'text');
  if (!classified || classified.startsWith('__structural_')) return null;
  return classified.split('__')[0];
}

// ---- Load regression entries ----
const entries = JSON.parse(fs.readFileSync(path.join(BASE, 'interpreter_regressions.json'), 'utf8'));

// ---- Run the Python implementation via a one-shot subprocess ----
const pyScript = `
import json, sys
sys.path.insert(0, ${JSON.stringify(BASE)})
from interpreter_p14 import interpret

entries = json.loads(sys.stdin.read())
results = []
for e in entries:
    pred = interpret({"label": e["label"], "id": "", "ac": "", "placeholder": "", "section": None, "nearby": "", "itype": "text", "req": False})
    results.append(pred.get("category"))
print(json.dumps(results))
`;
const pyOut = execFileSync('python', ['-c', pyScript], { input: JSON.stringify(entries), encoding: 'utf8' });
const pyResults = JSON.parse(pyOut);

// ---- Compare both implementations against expected_capability ----
let failures = 0;
entries.forEach((entry, i) => {
  const jsCategory = classifyJs(entry.label);
  const pyCategory = pyResults[i];
  const expected = entry.expected_capability;

  const jsOk = jsCategory === expected;
  const pyOk = pyCategory === expected;

  if (!jsOk || !pyOk) {
    failures++;
    console.log(`FAIL [${entry.source}]: "${entry.label.slice(0, 70)}..."`);
    console.log(`  expected: ${expected}`);
    if (!jsOk) console.log(`  JS got:   ${jsCategory} (WRONG)`);
    if (!pyOk) console.log(`  Python got: ${pyCategory} (WRONG)`);
  } else {
    console.log(`PASS [${entry.source}]: ${expected}`);
  }
});

console.log(`\n${entries.length - failures}/${entries.length} regression entries pass on both implementations.`);
process.exit(failures > 0 ? 1 : 0);
