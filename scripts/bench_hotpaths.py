"""Deterministic micro-benchmark for known UI hot paths.

Usage:  python scripts/bench_hotpaths.py
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.technology_classifier import TechnologyClassifier  # noqa: E402
from app.library.models import EvidenceRecord, LibraryQuery  # noqa: E402
from app.library.store import SQLitePatentLibrary  # noqa: E402

TITLES = (
    "Hydraulic damper with rebound stop for vehicle suspension",
    "Frequency selective damping valve assembly for a shock absorber",
    "Air spring strut with integrated ride height sensor",
    "电磁阀减振器及具有其的车辆悬架系统",
    "Anti roll stabilizer bar bushing assembly",
)


def _best(fn, repeat: int = 3) -> float:
    samples = []
    for _ in range(repeat):
        start = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - start)
    return min(samples)


def bench_classifier(hits: int = 100) -> float:
    classifier = TechnologyClassifier()
    payload = [(TITLES[i % len(TITLES)], ("B60G17/08", "F16F9/34")) for i in range(hits)]

    def run() -> None:
        for text, classes in payload:
            classifier.classify(text=text, classifications=classes)

    return _best(run)


def bench_library_query(rows: int = 600) -> tuple[float, float]:
    # Keep scratch data inside the repository so sandboxed runs never have to
    # clean up the shared system temp directory.
    scratch = ROOT / ".bench-scratch"
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as tmp:
        from datetime import UTC, datetime

        store = SQLitePatentLibrary(Path(tmp) / "bench.db")
        from app.domain.family import PatentPublication

        for index in range(rows):
            number = f"CN{1000000 + index}A"
            store.upsert_publication(
                PatentPublication(
                    publication_number=number,
                    jurisdiction="CN",
                    title=TITLES[index % len(TITLES)],
                    original_assignees=("Bench Suspension Co",),
                ),
                source="BENCH",
            )
            store.replace_tags(number, ("bench", f"tag{index % 7}"))
            store.replace_projects(number, ("bench-project",))
            store.add_company_group(number, "BenchCo")
            store.add_technology_topic(number, "damper")
            store.add_evidence(
                EvidenceRecord(
                    evidence_id=f"ev-{index}",
                    source=f"https://example.invalid/{index}",
                    source_type="web",
                    title=f"Evidence {index}",
                    markdown="x" * 2000,
                    metadata_json="{}",
                    captured_at=datetime.now(UTC),
                    publication_number=number,
                    company_group="BenchCo",
                    technology_topic="damper",
                    tags=(),
                )
            )

        def run() -> None:
            store.query(LibraryQuery(limit=1000))

        query_seconds = _best(run)

        def run_dashboard() -> None:
            store.count_patents()
            len(store.list_families(limit=500))
            len(store.list_evidence(limit=1000))

        dashboard_seconds = _best(run_dashboard)
        store.close()
    return query_seconds, dashboard_seconds


def main() -> int:
    classify = bench_classifier()
    query, dashboard = bench_library_query()
    print("== hot path benchmark ==")
    print(f"classify 100 hits          : {classify * 1000:8.1f} ms")
    print(f"library query limit=1000   : {query * 1000:8.1f} ms  (600 rows)")
    print(f"dashboard metrics refresh  : {dashboard * 1000:8.1f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
