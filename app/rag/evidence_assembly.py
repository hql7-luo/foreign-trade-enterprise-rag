"""Optional bounded sibling selection using unresolved schema fields."""


def assemble_complementary_siblings(question, hits, database, *, max_siblings=3):
    # Section-sized chunks already preserve complete field groups in this public corpus.
    # Keep the extension point explicit; no source-specific sibling rules are imported.
    del question, database, max_siblings
    return hits, {"enabled": False, "added_count": 0, "unresolved_concepts": [], "added": []}
