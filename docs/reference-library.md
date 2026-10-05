# Reference library

The candidate packages 15 original references for multifamily owners and asset
managers. Catalog-only installations include the full corpus and lexical index;
search needs no model, credentials, database, embedding service or network.

```python
from platworks.library import search_library, get_reference
hits = search_library("DSCR debt coverage")
reference = get_reference(hits["results"][0]["id"], version="1.0.0")
```

The same calls are MCP tools. Each reference includes its stable ID, version,
applicability, source links, dated review method and SHA-256. Search includes
those identities; exact retrieval returns the full text and source records.
Ranking is deterministic lexical matching with weighted titles/keywords and
ID tie-breaking. Queries are limited to 500 characters and results to 1–10.
It does not search private files or the live web. Unknown terms can return no hits.

## Review and updates

Version 1.0.0 covers occupancy, NOI, normalization, underwriting assumptions,
property tax, insurance, debt, returns, renovations, account mapping, variance,
month close, corrections, original thesis and attachments. These are original
working references, checked against the linked primary sources and pinned
product contracts on 2026-10-05. **Independent domain review remains pending.**
They do not provide current lender terms, tax determinations or insurance quotes.
House policies are labeled and must be checked for the actual property and year.

Edit `src/platworks/data/library/references.json`. Preserve IDs; increment the
entry and corpus versions when meaning changes. Record the source edition or
commit, check date, method and reviewer evidence accurately. A human sign-off
must have a real reviewer and evidence. Rebuild with:

```bash
python scripts/build_library.py
python scripts/build_library.py --check
```

The wheel includes the corpus and index. Startup verifies that the index matches
the corpus; retrieval returns a content hash so a saved analysis can identify the
exact reference. Only the current version is packaged: retain the wheel or full
retrieved reference for historical reproducibility. Hashes identify bytes; they
are not signatures or proof of subject-matter correctness.

Public prose is Apache-2.0; linked sources retain their rights. Do not add private
operator SOPs, attachments, vendor exports or customer information to this corpus.
Use the [assistant guide](assistant-integrations.md) for private-file workflows.
