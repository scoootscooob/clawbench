function buildReportRow(entry) {
  const userId = entry.userId.trim().toLowerCase();
  const seenAt = new Date(entry.seenAt).toISOString().slice(0, 10);
  return `${seenAt},${userId},${entry.status}`;
}

module.exports = { buildReportRow };

