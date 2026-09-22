# Citation network tasks

- [ ] Add `CITATIONS` provider capability and EPO OPS citation fetch/parse.
  - Acceptance: typed `CitationEdge` objects from a real or fixture OPS response, including malformed-entry handling.
  - Verify: focused unit tests.
- [ ] Add Google Patents citation fallback (fires only when EPO OPS returns nothing).
  - Acceptance: same `CitationEdge` shape, `source_type="GOOGLE_PATENTS"`.
  - Verify: focused unit tests.
- [ ] Add `library_citation` schema, model and store methods.
  - Acceptance: round-trips through SQLite; external (out-of-library) `to_publication` supported.
  - Verify: focused unit tests.
- [ ] Wire citation fetch into LocalLibrary sync (EPO OPS first, fallback second, both kept if both return data).
  - Acceptance: citations populate on sync, are not re-fetched on a report run.
  - Verify: focused unit tests.
- [ ] Add `citation_network` analysis + offline HTML report + desktop entry point.
  - Acceptance: internal/external nodes distinguished, every edge source-labeled, empty-result case shows a caveat not a bare empty graph.
  - Verify: focused tests, full offline audit, diff check.
