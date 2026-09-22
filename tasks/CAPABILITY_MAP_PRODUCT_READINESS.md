# Capability Map: Guided engineering intelligence workspace

## Assumptions

1. The first product-readiness release remains a Windows desktop experience over LocalLibrary; it does not replace the existing Search, Reader, Family or Watch pages.
2. AI interpretation is optional and requires an explicit per-request consent plus a user-supplied OpenAI-compatible endpoint, model and key.
3. No provider call, data upload or legal conclusion occurs by default.

| Module id | Responsibility | Depends on |
| --- | --- | --- |
| task-guidance | Workflow-specific purpose, required inputs, output and limits | Existing intelligence workflows |
| library-readiness | Explain whether the selected LocalLibrary can support a task and how to continue | LocalLibrary metadata |
| task-workspace | Guided desktop task selection, validation, results and continuation actions | task-guidance, library-readiness |
| opt-in-ai-interpretation | Send a bounded evidence packet only after explicit consent and render a cited interpretation | task-workspace, ai_packet |
| acceptance-ux | Deterministic workflow and desktop regressions for empty, ready and AI-off states | All modules |

Build order: task-guidance + library-readiness → task-workspace → opt-in-ai-interpretation → acceptance-ux.

The user's instruction to automatically plan and execute authorizes this first product-readiness slice. It deliberately excludes EOU, claim charts, FTO, DFMEA, validation plans and automatic product-performance conclusions.
