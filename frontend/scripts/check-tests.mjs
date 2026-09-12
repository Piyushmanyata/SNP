import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const results = JSON.parse(readFileSync("test-results.json", "utf8"));
assert(results.success && results.numPassedTests > 0, "Tests must pass and execute assertions");
assert.equal(results.numPendingTests, 0, "CI does not permit skipped tests");
assert.equal(results.numTodoTests, 0, "CI does not permit unimplemented tests");
