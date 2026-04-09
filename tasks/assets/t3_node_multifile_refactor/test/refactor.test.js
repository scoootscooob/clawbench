const test = require("node:test");
const assert = require("node:assert/strict");

const { parseAuthRecord, buildReportRow } = require("../src/index");

test("parses auth record with normalized user id and date", () => {
  assert.equal(parseAuthRecord({ userId: " Alice ", seenAt: "2026-04-01T08:10:00Z" }), "alice:2026-04-01");
});

test("builds report row with matching normalization", () => {
  assert.equal(
    buildReportRow({ userId: " Alice ", seenAt: "2026-04-01T08:10:00Z", status: "ok" }),
    "2026-04-01,alice,ok",
  );
});

