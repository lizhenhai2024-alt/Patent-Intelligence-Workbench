# V1.0 Architecture Freeze

## Product goal

V1.0 focuses on five reliable capabilities:

1. Search by text, patent number, or company + technology.
2. Analyze patent families and priorities.
3. Download individual or complete-family PDFs with source fallback.
4. Monitor new publications and new family members for competitors.
5. Store, tag and export patents locally.

Formal novelty search / prior-art opinions are deferred to V2.

## Module order

1. Patent Number Normalizer
2. Company / Patent Ownership Entity Graph
3. Patent Family domain model
4. Provider adapters
5. Search
6. Family analysis
7. Download Center
8. Patent Watch
9. Local Library
10. Desktop UI / Windows packaging

## Core jurisdictions

CN, JP, EP, US, WO, KR.

JP is first-class. Classification storage must support IPC, CPC, FI, F-term and Theme Code.

## Entity graph rule

Company identity is not a flat alias list.

Important relation types include:

- PREVIOUS_NAME / CURRENT_NAME
- PREDECESSOR / SUCCESSOR
- IP_HOLDING_ENTITY
- ACQUIRED_PATENT_PORTFOLIO
- TECHNOLOGY_PREDECESSOR
- ORIGINAL_ASSIGNEE / CURRENT_ASSIGNEE
- SECURITY_INTEREST

SECURITY_INTEREST and UNKNOWN relations are excluded from default company-group expansion.

## Patent family rule

A family is the primary analysis unit. The system must retain both simple-family and INPADOC-family identifiers when available and preserve individual national publications.

A new family and a new member of an existing family are separate Patent Watch events.

## Download rule

Downloads are provider-independent:

primary source -> fallback source -> official source -> recorded failure

A failed member can be retried without redownloading the entire family.

## Release rule

No release build is accepted unless lint and automated tests pass on Windows and Linux.
