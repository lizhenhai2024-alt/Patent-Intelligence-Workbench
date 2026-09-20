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

## Patent family sources

The internal model explicitly distinguishes:

- **DOCDB simple family**: same invention / equivalent publications.
- **INPADOC extended family**: related technical content connected by priority links.

EPO OPS is the primary cross-jurisdiction family source in V1 because it exposes
both the Published Data equivalents service and the dedicated family service.

### Japan

JPO remains a first-class authoritative source for Japanese application data,
including number reference, priority, progress, citation and registration data.

The domestic JPO Patent Information Retrieval API is not treated as the primary
cross-jurisdiction patent-family provider. JPO's separate OPD family API is
optional because new OPD-API user registrations have been closed since
2024-08-09. Family resolution for JP publications therefore uses the same
provider fallback architecture as other jurisdictions, with EPO family data as
the first implemented source and JPO domestic data used for JP validation.

No API credential is stored in the repository. Provider credentials are loaded
from environment variables or local settings only.

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

## Provider fallback rule

Higher layers call a FamilyResolver rather than a provider directly.

The resolver:
1. checks provider capabilities,
2. tries providers in configured order,
3. records each attempt and error,
4. returns the first valid normalized PatentFamily,
5. raises one aggregated error only after all eligible providers fail.

This enables EPO -> future secondary source -> cached/local source fallback
without changing Search, Watch, Family Analysis or UI code.

## Download rule

Downloads are provider-independent:

primary source -> fallback source -> official source -> recorded failure

A failed member can be retried without redownloading the entire family.

## Release rule

No release build is accepted unless lint and automated tests pass on Windows and Linux.
