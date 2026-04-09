function parseAuthRecord(record) {
  const userId = record.userId.trim().toLowerCase();
  const seenAt = new Date(record.seenAt).toISOString().slice(0, 10);
  return `${userId}:${seenAt}`;
}

module.exports = { parseAuthRecord };

