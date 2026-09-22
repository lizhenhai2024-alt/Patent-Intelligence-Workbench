# Citation network implementation plan

1. Add `ProviderCapability.CITATIONS` and `EpoOpsProvider.fetch_citations` + `parse_citations_xml`.
   - Checkpoint: unit test parses a saved sample OPS biblio-with-citations XML fixture into typed `CitationEdge` objects.
2. Add a narrow Google Patents citation fallback reusing existing HTML parsing patterns.
   - Checkpoint: unit test parses a saved sample Google Patents page fragment for its Citations/Cited-by sections.
3. Add `library_citation` table + `LibraryCitation` model + store read/write methods.
   - Checkpoint: SQLite round-trip test; foreign-key/index behavior verified; external (non-library) `to_publication` values persist without error.
4. Wire citation fetch into the existing LocalLibrary sync/enrichment step (EPO OPS first, Google Patents fallback, both recorded if both return data).
   - Checkpoint: sync test shows citations populated once and not re-fetched on a second sync within the same session.
5. Add `analysis.citation_network()` + offline HTML graph rendering + desktop entry point alongside the existing five workflows.
   - Checkpoint: focused tests, full offline audit, `git diff --check`.

## Boundaries

- Always: preserve existing search/family/download/watch behavior untouched; new table is additive only.
- Ask only if needed: adding a data source beyond EPO OPS/Google Patents; changing the existing sync flow's timing/triggers.
- Never: fetch citations synchronously inside report generation; never infer a citation relationship not explicitly returned by a provider.
