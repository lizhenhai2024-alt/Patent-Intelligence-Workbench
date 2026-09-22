# Guided workspace tasks

- [x] Define task guides and LocalLibrary readiness states.
  - Acceptance: Every workflow describes purpose, inputs, outputs and limits; empty libraries give a next action.
  - Verify: focused unit tests.
- [x] Build the guided desktop task workspace.
  - Acceptance: Task selection changes contextual instructions and validation is task-specific.
  - Verify: real Tk test.
- [x] Add an explicit-consent AI interpretation boundary.
  - Acceptance: no request without consent/configuration; request payload is report evidence only.
  - Verify: mocked HTTP tests.
- [x] Update product guidance and run full release gate.
  - Acceptance: README and guide distinguish RC preview from completed first slice.
  - Verify: full audit and diff check.
  - Status: README/docs already label this the RC preview and describe readiness checks, task-specific validation and consent-gated AI; the full offline audit (`python scripts/ai_self_audit.py --full`) and a diff check have not been rerun after these changes and still need to happen before closing this item.
