const { filterNotes } = require("./search");
const { normalizeNote } = require("./render");

function searchNotes(notes, query) {
  return filterNotes(notes.map(normalizeNote), query);
}

module.exports = { searchNotes };

