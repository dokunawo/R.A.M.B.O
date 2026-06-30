// Node-runnable test for the pure sign-off detector (the frontend has no jest
// runner wired up). Loads the REAL signoff.js source, neutralizes the ESM
// `export` keyword, and exercises isSignoff against the documented edge cases.
//   run:  node rambo-frontend/src/components/signoff.test.mjs
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const src = fs.readFileSync(path.join(here, "signoff.js"), "utf8").replace(/export\s+/g, "");
const { isSignoff } = new Function(src + "\n return { isSignoff };")();

// [utterance, expected]
const SILENT = true, REPLY = false;
const cases = [
  // clear sign-offs -> silent
  ["thanks", SILENT],
  ["thank you", SILENT],
  ["okay thanks", SILENT],
  ["alright thanks rambo", SILENT],
  ["sounds good", SILENT],
  ["got it", SILENT],
  ["will do", SILENT],
  ["appreciate it", SILENT],
  ["right on", SILENT],
  ["perfect", SILENT],
  ["cool", SILENT],
  ["bye", SILENT],
  ["that's all for now", SILENT],
  ["nothing else", SILENT],
  ["i'm good", SILENT],

  // questions -> reply
  ["thanks, what's the weather", REPLY],
  ["got it — can you also check my calendar", REPLY],
  ["how about the strikeouts board", REPLY],
  ["one more thing", REPLY],
  ["cool, what time is it?", REPLY],

  // commands -> reply (instruction, not farewell)
  ["great, send that email", REPLY],
  ["perfect, open the edge dashboard", REPLY],
  ["thanks, play some music", REPLY],

  // continuations ("leading into new info") -> reply
  ["okay so the revenue is up", REPLY],
  ["great the meeting went well", REPLY],
  ["alright let's look at tomorrow's slate", REPLY],

  // look-alikes / traps -> reply (none are sign-offs)
  ["well", REPLY],          // not "we'll", and not a sign-off token
  ["ill", REPLY],           // "ill" (sick) must not read as "i'll"
  ["i'll send that report later", REPLY],  // self-committal but no token + long -> conservative reply

  // empty / junk
  ["", REPLY],
  ["   ", REPLY],
];

let pass = 0, fail = 0;
for (const [text, expected] of cases) {
  const got = isSignoff(text);
  if (got === expected) { pass++; }
  else { fail++; console.log(`FAIL: isSignoff(${JSON.stringify(text)}) = ${got}, expected ${expected}`); }
}
console.log(`\nsignoff: ${pass} passed, ${fail} failed (${cases.length} cases)`);
process.exit(fail ? 1 : 0);
