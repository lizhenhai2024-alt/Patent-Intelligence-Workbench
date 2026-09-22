# Market-benchmark feature backlog

## Objective

Compare the Patent Intelligence Workbench's current scope (V1.0 core + Engineering-intelligence RC preview) against mainstream commercial patent-analytics platforms (PatSnap/智慧芽, incoPat, Clarivate Derwent Innovation, Questel Orbit Intelligence, Cypris, The Lens) and notable open-source patent tooling (PQAI, PatZilla, PatentInspector, awesome-patent-retrieval), and propose feature additions that fit this product's stated purpose and boundaries. This is a backlog for review, not an approved plan — each item still needs its own SPEC/plan/todo set before implementation, per this repo's existing planning pattern.

## Method

Web research on 2025-2026 vendor comparison articles and GitHub project READMEs (see Sources at the end). Every candidate feature was checked against `docs/AI_PRODUCT_SPEC.md` section "Boundaries" and each existing task file's "Never" list before inclusion.

## Gap analysis: what mainstream tools have that this product does not

| Capability seen in mainstream tools | Vendors/projects | Fits this product's LocalLibrary-first, offline, no-legal-conclusion positioning? |
| --- | --- | --- |
| Citation network (forward/backward) visualization | PatSnap, Derwent Innovation, PatentInspector, Gephi-based OSS workflows | Yes — deterministic graph over stored publication data already in LocalLibrary |
| Explainable patent value/strength score | PatSnap, incoPat ("价值度"), Innography | Yes, if reframed as a transparent weighted metric (family size, remaining term, citation count, claim count) with full formula and receipts — never a black-box "probability" |
| Technology landscape clustering / patent map | PatSnap heatmaps, Derwent ThemeScape | Partially — TF-IDF/CPC-based local clustering is feasible offline; semantic-embedding clustering would need a model dependency decision |
| Claim feature breakdown (element-by-element) | Derwent Innovation, most claim-chart tools | Yes as a *technical-feature checklist per claim*, explicitly not a claim chart / infringement mapping |
| Remaining patent term / expiry view | Orbit Intelligence, Derwent | Yes — read-only, derived from filing/grant date + jurisdiction term rules, no legal conclusion |
| Multilingual full-text machine translation in Reader | Derwent (curated), PatSnap | Partially there already (`app/core/translation_http.py`); extend to full-text Reader view for JP/KR/CN sources |
| Custom/user-extensible taxonomy | Derwent custom taxonomies, incoPat tagging | Yes — the existing `technology_taxonomy.json` is static; a user-editable overlay fits the "engineer knows their domain best" positioning |
| Data-quality cleanup (name normalization, de-dup) | OpenRefine (used alongside PatSnap/Derwent exports) | Yes — LocalLibrary ingest already resolves companies; add a review/cleanup pass for near-duplicate assignee spellings and malformed dates |
| "Chat with patents" / evidence-grounded Q&A | PatSnap Bot, Cypris AI monitoring | Already directionally covered by the opt-in `ai_interpreter.py`; extend its scope to per-publication Q&A under the same consent/evidence-packet rule |
| SEP (standard-essential patent) analytics | IPlytics | No — not relevant to damper/CDC/suspension engineering; explicitly out of scope |
| Litigation analytics | PatSnap, Derwent, PatentSight | No — needs an external litigation data source this product does not have and should not fabricate; out of scope |
| Formal FTO / infringement / novelty conclusions | incoPat "三性分析", most commercial suites' "risk score" | No — directly conflicts with this repo's existing "Never: generate legal opinions" boundary |
| Multi-user collaboration / shared workspace | PatSnap, Cypris | No for now — this is a single-user offline desktop tool; would require a server/sync architecture decision outside this backlog |
| Docketing / annuity fee management | Orbit Intelligence, phpIP | No — this is IP-department/paralegal tooling, not an engineering research aid; explicitly out of scope for this user |

## Proposed additions, by priority

### P0 — natural extensions of the existing five workflows, no new data source needed

1. **Citation network view.** Build forward/backward citation edges from LocalLibrary records already resolved by `analysis.py`; render as a static offline HTML graph (reuse the existing offline-report renderer, no new runtime dependency needed beyond what's already used for HTML reports). Gives engineers a way to see which patents a family builds on and who cites it back.
2. **Transparent technology-strength metric.** A `Metric`-style deterministic score combining known-family size, citation count, remaining term and claim count, each weight and input published alongside the number (same receipts pattern as existing metrics) — not framed as value/probability, framed as "coverage indicators."
3. **Claim feature checklist.** For a selected publication, split independent claims into individually labeled technical features (structure/valve path/control variable, in this domain's own vocabulary) — pure decomposition, no comparison against another patent or product, so it stays inside the existing "no claim chart / no infringement" boundary.
4. **Remaining-term view.** Read-only expiry estimate per jurisdiction from filing/grant date, clearly labeled as an estimate requiring the legal record for confirmation.

### P1 — meaningful but need a small design decision first

5. **Technology landscape clustering/map.** Offline clustering (CPC/IPC + keyword based, no external embedding API) to complement the existing distribution tables with a 2-D map view; needs a decision on which clustering method keeps results deterministic and explainable per this repo's style rules.
6. **User-editable technology taxonomy overlay.** Let an engineer add/rename technology nodes on top of `technology_taxonomy.json` without losing the shipped baseline — needs a decision on how overlay vs. baseline conflicts are resolved and shown in reports.
7. **Full-text Reader translation.** Extend the existing translation HTTP client from search/metadata into the Reader's full claims/description view for CN/JP/KR sources.
8. **LocalLibrary data-quality pass.** A reviewable list of likely duplicate assignee spellings, malformed dates, and orphaned records, with user-approved merges — never an automatic silent merge.
9. **Per-publication AI Q&A.** Extend `ai_interpreter.py`'s consent/evidence-packet model from whole-report interpretation to a single-publication Q&A, keeping the same "no request without consent" and "evidence-only payload" rules.

### Explicitly out of scope (conflicts with existing product boundaries or user profile)

- Formal FTO, infringement, novelty/inventive-step ("三性") conclusions, or any risk/probability score implying a legal opinion.
- Litigation analytics (no data source, and legal-conclusion adjacent).
- SEP/standards-essential-patent analytics (wrong technology domain).
- Docketing, annuity/fee management, multi-user collaboration workspace (this is a single-user engineering research tool, not IP-department case management).

## Sources

- PatSnap vs Derwent vs Orbit comparison: https://www.patsnap.com/resources/blog/articles/patsnap-vs-derwent-vs-orbit-patent-visualization-tools-comparison-2025/
- PatSnap alternatives / feature comparison: https://cypris.ai/insights/patsnap-alternatives-8-tools-for-patent-research-intelligence
- awesome-patent-retrieval (open-source list): https://github.com/mahesh-maan/awesome-patent-retrieval
- 6 open-source IP tools (PQAI, PatZilla, phpIP, OpenRefine, Gephi, Plotly): https://projectpq.ai/6-open-source-ip-tools-that-inventors-and-patent-professionals-must-know-about/
- PatentInspector (open-source patent analysis web app): https://github.com/KonstantinosPetrakis/PatentInspector
- incoPat platform overview: https://www.lib.szu.edu.cn/er/incoPat

## Next step

Pick which P0 items to turn into a real `SPEC-*.md` + `plan-*.md` + `todo-*.md` set, following this repo's existing planning pattern (boundaries, verification strategy, capability map, build order) before any code is written.
