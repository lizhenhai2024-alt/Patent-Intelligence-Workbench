from datetime import UTC, datetime

from app.domain.family import PatentPublication
from app.library.store import SQLitePatentLibrary
from app.watch.models import WatchRule
from app.watch.state import SQLiteWatchStateStore


def test_library_and_watch_tables_coexist_in_one_sqlite_database(tmp_path):
    path = tmp_path / "workbench.db"
    library = SQLitePatentLibrary(path)
    watch = SQLiteWatchStateStore(path)

    library.upsert_publication(
        PatentPublication(
            publication_number="EP1000000A1",
            jurisdiction="EP",
        ),
        source="TEST",
        seen_at=datetime(2026, 9, 20, 8, 0, tzinfo=UTC),
    )
    watch.upsert_rule(
        WatchRule(
            rule_id="zf-damper",
            name="ZF damper",
            company_group="zf",
        )
    )

    assert library.count_patents() == 1
    assert watch.get_rule("zf-damper") is not None

    table_names = {
        row["name"]
        for row in library.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "library_publication" in table_names
    assert "watch_rule" in table_names

    library.close()
    watch.close()
