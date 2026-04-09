function filterNotes(notes, query) {
  const needle = query.trim();
  return notes.filter((note) => note.title.includes(needle) || note.body.includes(needle));
}

module.exports = { filterNotes };

