# Capability Map: Engineering intelligence workflows

| Module id | Responsibility | Depends on |
| --- | --- | --- |
| analysis-core | Read scoped LocalLibrary records, count verified families, and retain publication receipts | Existing LocalLibrary and taxonomy |
| offline-reports | Render self-contained, traceable landscape and comparison reports | analysis-core |
| search-planning | Preview editable multilingual engineering search terms | Existing technology dictionary |
| watch-review | Review new-family and new-member events without losing provenance | Existing Watch and LocalLibrary |
| desktop-workflows | Give engineers one entry point for the five workflows | offline-reports, search-planning, watch-review |

Build order: analysis-core → offline-reports; search-planning and watch-review → desktop-workflows.

The user's request to plan and automatically deliver the previously agreed workflows authorizes this build order. The existing product specification remains authoritative when a plan detail is ambiguous.
