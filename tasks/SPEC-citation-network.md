# Spec: Citation network (forward/backward)

## Objective

Give an R&D engineer a way to see which publications a family builds on (backward citations) and which later publications cite it back (forward citations), rendered as an offline HTML graph reusing the existing report style, with every edge traceable to the provider that supplied it. This is P0 item 1 from `tasks/SPEC-market-benchmark-backlog.md`.

## Data source decision (resolves prior discussion)

EPO OPS is configured for this user, so it is the primary source: `references-cited` bibliographic data, official/INPADOC-backed, broadest jurisdiction coverage. Google Patents (`google_patents_search.py`) is fallback-only, used exactly where it already sits in the existing search fallback chain — never the primary source for a new authoritative-data feature. Every stored citation edge records its `source_type` (`EPO_OPS` or `GOOGLE_PATENTS`) and `source_ref`, reusing the same provenance pattern as `library_provenance` (`app/library/models.py` `LibrarySource`, `app/library/store.py` `library_provenance` table) rather than inventing a new mechanism.

Citations are fetched and stored once, at LocalLibrary sync/enrichment time — not re-fetched live every time a report is generated — for the same reproducibility reason `filing_date`-based metrics are metadata-only today. A report that includes citation data must state which source(s) supplied it and must not claim completeness EPO OPS itself doesn't claim (18-month publication delay applies to any source; pre-2000 non-EP/US jurisdictions may have partial digitization).

## Tech stack and commands

Python 3.12, existing SQLite/Tkinter application, standard-library HTML and `xml.etree.ElementTree` (already used in `app/providers/epo_ops.py`). Run `python scripts/ai_self_audit.py --full`, `python -m pytest tests/test_epo_ops.py tests/test_local_patent_index.py tests/test_intelligence_workflows.py -q`, and `git diff --check`.

## Project structure

- `app/providers/base.py`: add `ProviderCapability.CITATIONS`.
- `app/providers/epo_ops.py`: add `EpoOpsProvider.fetch_citations(publication_number)` and a `parse_citations_xml(xml_text)` parser that reads `references-cited` / `patcit` elements from the OPS biblio-constituent response (extends the existing biblio-retrieval path used by `parse_publication_biblio_xml`, not a new endpoint family).
- `app/providers/google_patents.py` or `google_patents_search.py`: a narrow `fetch_citations` fallback that reads the same "Citations"/"Cited by" sections the existing PDF-discovery code already parses HTML for.
- `app/library/store.py`: new `library_citation` table (see below).
- `app/library/models.py`: `LibraryCitation` dataclass (from_publication, to_publication, direction, source_type, source_ref, first_seen_at).
- `app/intelligence/analysis.py`: a `citation_network(scope)` function building a graph from `library_citation` joined with `library_publication` (known-in-library nodes) plus external nodes labeled "not in local library."
- `app/intelligence/report.py`: reuse the existing offline HTML report renderer to draw the graph (simple SVG/HTML node-link rendering, no new runtime dependency).
- `tests/`: `test_epo_ops.py` gets a citation-parsing fixture test; `test_intelligence_workflows.py` gets a citation-network report test with deterministic SQLite fixtures.

## Schema addition

```sql
CREATE TABLE IF NOT EXISTS library_citation (
    from_publication TEXT NOT NULL,
    to_publication TEXT NOT NULL,
    direction TEXT NOT NULL,         -- 'CITES' (from cites to) or 'CITED_BY'
    source_type TEXT NOT NULL,       -- 'EPO_OPS' | 'GOOGLE_PATENTS'
    source_ref TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    PRIMARY KEY(from_publication, to_publication, direction, source_type),
    FOREIGN KEY(from_publication)
        REFERENCES library_publication(publication_number)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_library_citation_to
    ON library_citation(to_publication);
```

`to_publication` is intentionally **not** a foreign key to `library_publication` — a cited/citing publication is very often outside the user's LocalLibrary, and the report must show it as an external reference rather than silently dropping it or erroring.

## Code style

Follow existing patterns: immutable typed dataclasses, deterministic sorting, `Metric`/`SearchPage`-style result objects. Example:

```python
CitationEdge(
    from_publication="US20240003399A1",
    to_publication="EP3800353A1",
    direction=CitationDirection.CITES,
    source_type="EPO_OPS",
    source_ref="OPS biblio-retrieval",
)
```

## Testing strategy

- XML fixture test proving `parse_citations_xml` extracts `references-cited` entries correctly and skips malformed/self-referencing entries.
- SQLite round-trip test: store edges, reopen the database, confirm they persist with source attribution intact.
- Report test: two publications in LocalLibrary citing each other plus one external citation → graph shows both internal and external nodes, each edge labeled with its source, and a completeness caveat line is always present.
- Negative test: a publication with zero returned citations renders "no citation data returned by <source>," never a bare empty graph that reads as "no citations exist."

## Boundaries

- Always: attribute every edge to the provider that supplied it; prefer EPO OPS over Google Patents when both return data for the same edge; never silently merge conflicting citation data from two sources into one edge without keeping both source records.
- Ask only if needed: a third citation data source beyond EPO OPS/Google Patents.
- Never: treat an empty or partial citation result as proof no citations exist; never fabricate a citation edge; never let citation count alone imply a novelty/value judgment (ties into the existing "no probability framing" boundary from `docs/AI_PRODUCT_SPEC.md`).

## Success criteria

1. A LocalLibrary publication with EPO OPS-sourced citation data shows a forward/backward citation graph with every edge traceable to `EPO_OPS`.
2. When EPO OPS returns nothing for a publication but Google Patents does, the edge is stored and labeled `GOOGLE_PATENTS`, and the report visually/textually distinguishes it from EPO OPS-sourced edges.
3. Citation data is fetched at sync time and reused on repeat report generation without a new network call (reproducible reports).
4. `python scripts/ai_self_audit.py --full` and the focused test files pass; `git diff --check` is clean.
