# Product-readiness implementation plan

1. Define one reusable workflow guide per task and deterministic LocalLibrary readiness levels.
   - Checkpoint: unit tests prove no ambiguous workflow lookup and no fabricated readiness claim.
2. Replace the generic Intelligence form framing with task selection, contextual help, readiness and task-specific validation.
   - Checkpoint: desktop test changes task and observes context/empty-state guidance.
3. Add an optional, consent-gated OpenAI-compatible interpretation client with no persisted secret or automatic request.
   - Checkpoint: mocked request receives only the evidence packet; missing consent blocks a call.
4. Render AI results as a clearly labelled interpretation, preserve the existing offline result path, and update the user guide/README status.
   - Checkpoint: focused tests, full audit, real Tk smoke, diff check.
