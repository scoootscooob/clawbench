// audit.js — audit log line builder.
//
// NOTE: audit entries preserve the original userId capitalization (audit logs
// must be forensically accurate) and use a minute-precision timestamp
// (so "who did what when" is disambiguated across a single day).
// This is deliberately different from auth.js and report.js which use
// lowercase userIds and day-only dates.

function buildAuditLine(entry) {
  const userId = entry.userId.trim(); // preserve original case for audit
  const d = new Date(entry.seenAt);
  // YYYY-MM-DD HH:MM in UTC
  const iso = d.toISOString();
  const stamp = `${iso.slice(0, 10)} ${iso.slice(11, 16)}`;
  return `${stamp} ${userId} ${entry.action}`;
}

module.exports = { buildAuditLine };
