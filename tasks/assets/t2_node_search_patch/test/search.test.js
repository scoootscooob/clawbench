const test = require("node:test");
const assert = require("node:assert/strict");

const { searchNotes } = require("../src/index");
const { emptyNote } = require("../src/render");

test("search matches title and body case-insensitively", () => {
  const notes = [
    { title: "Release Notes", body: "Migration guide for beta customers" },
    { title: "Runbook", body: "Escalate browser failures quickly" },
  ];
  assert.deepEqual(searchNotes(notes, "migration"), [notes[0]]);
  assert.deepEqual(searchNotes(notes, "BROWSER"), [notes[1]]);
});

test("search with whitespace-padded query is trimmed", () => {
  const notes = [{ title: "Release Notes", body: "Migration guide" }];
  assert.deepEqual(searchNotes(notes, "  migration  "), [notes[0]]);
});

test("emptyNote placeholder stays empty — do NOT patch the body here", () => {
  // The intentional empty-body factory must remain empty; a naive grep-and-
  // replace of `body: ""` that also rewrites this one will fail.
  assert.deepEqual(emptyNote(), { title: "", body: "" });
});
