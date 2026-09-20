"""Optional credentialed smoke test for EPO OPS.

This script is intentionally separate from normal CI so external availability,
quota and credentials do not make the offline release gate flaky.
"""

from __future__ import annotations

import asyncio
import os

from app.core.patent_number import normalize_patent_number
from app.domain.family import FamilyType
from app.providers.epo_ops import EpoOpsProvider


async def run() -> int:
    key = os.getenv("EPO_OPS_KEY")
    secret = os.getenv("EPO_OPS_SECRET")
    if not key or not secret:
        print("SKIP: EPO_OPS_KEY / EPO_OPS_SECRET are not configured.")
        return 0

    provider = EpoOpsProvider(
        consumer_key=key,
        consumer_secret=secret,
        timeout_seconds=45,
    )
    publication = normalize_patent_number("EP1000000A1")

    page = await provider.lookup_publication(publication)
    if not page.hits:
        raise RuntimeError("EPO OPS publication lookup returned no hits.")

    family = await provider.get_family(
        publication,
        FamilyType.DOCDB_SIMPLE,
    )
    if not family.members:
        raise RuntimeError("EPO OPS simple-family lookup returned no members.")

    print(
        "PASS: EPO OPS publication + family smoke; "
        f"hits={len(page.hits)}, family_members={len(family.members)}"
    )
    return 0


def main() -> int:
    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(main())
