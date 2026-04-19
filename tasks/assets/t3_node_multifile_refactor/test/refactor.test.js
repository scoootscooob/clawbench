const test = require("node:test");
const assert = require("node:assert/strict");

const { parseAuthRecord, buildReportRow, buildAuditLine } = require("../src/index");

test("auth: normalizes user id to lowercase, date to day-only UTC", () => {
  assert.equal(
    parseAuthRecord({ userId: " Alice ", seenAt: "2026-04-01T08:10:00Z" }),
    "alice:2026-04-01",
  );
});

test("report: normalizes user id to lowercase, date to day-only UTC", () => {
  assert.equal(
    buildReportRow({ userId: " Alice ", seenAt: "2026-04-01T08:10:00Z", status: "ok" }),
    "2026-04-01,alice,ok",
  );
});

test("audit: PRESERVES user id case, date is minute-precision UTC", () => {
  // Divergent requirement from auth/report: audit logs keep original case
  // (forensic accuracy) and include minute-precision timestamps so
  // same-day events are disambiguated. Any shared helper must accommodate
  // both normalization modes without duplicating parsing logic.
  assert.equal(
    buildAuditLine({ userId: " Alice ", seenAt: "2026-04-01T08:10:00Z", action: "login" }),
    "2026-04-01 08:10 Alice login",
  );
});

test("audit: distinguishes same-day events by minute", () => {
  assert.equal(
    buildAuditLine({ userId: "Bob", seenAt: "2026-04-01T08:10:59Z", action: "download" }),
    "2026-04-01 08:10 Bob download",
  );
  assert.equal(
    buildAuditLine({ userId: "Bob", seenAt: "2026-04-01T08:45:03Z", action: "download" }),
    "2026-04-01 08:45 Bob download",
  );
});
