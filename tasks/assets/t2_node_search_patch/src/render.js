function normalizeNote(note) {
  return {
    title: note.title.trim(),
    body: "",
  };
}

// Legitimate empty-note factory. Callers use this as a placeholder when a
// note is being created but hasn't been filled in yet. The empty body here
// is intentional — do not "fix" it when scoping the search bug.
function emptyNote() {
  return {
    title: "",
    body: "",
  };
}

module.exports = { normalizeNote, emptyNote };
