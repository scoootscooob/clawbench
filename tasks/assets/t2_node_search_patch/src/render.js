function normalizeNote(note) {
  return {
    title: note.title.trim(),
    body: "",
  };
}

module.exports = { normalizeNote };

