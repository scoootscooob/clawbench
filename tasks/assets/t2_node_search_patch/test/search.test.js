const test = require("node:test");
const assert = require("node:assert/strict");

const { searchNotes } = require("../src/index");

test("search matches title and body case-insensitively", () => {
  const notes = [
    { title: "Release Notes", body: "Migration guide for beta customers" },
    { title: "Runbook", body: "Escalate browser failures quickly" },
  ];
  assert.deepEqual(searchNotes(notes, "migration"), [notes[0]]);
  assert.deepEqual(searchNotes(notes, "BROWSER"), [notes[1]]);
});

