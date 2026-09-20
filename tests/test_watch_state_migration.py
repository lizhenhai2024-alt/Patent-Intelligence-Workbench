import sqlite3

from app.watch.models import WatchRule
from app.watch.state import SQLiteWatchStateStore


def test_old_watch_rule_schema_gets_cadence_column(tmp_path):
    path = tmp_path / "watch.db"
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE watch_rule (
            rule_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            company_group TEXT NOT NULL,
            technology_terms_json TEXT NOT NULL,
            jurisdictions_json TEXT NOT NULL,
            enabled INTEGER NOT NULL,
            lookback_days INTEGER NOT NULL,
            notify_on_first_run INTEGER NOT NULL
        )
        """
    )
    connection.commit()
    connection.close()

    store = SQLiteWatchStateStore(path)
    columns = {
        row["name"]
        for row in store.connection.execute("PRAGMA table_info(watch_rule)").fetchall()
    }

    assert "cadence_hours" in columns

    rule = WatchRule("r1", "Rule 1", "testco", cadence_hours=48)
    store.upsert_rule(rule)
    assert store.get_rule("r1").cadence_hours == 48
    store.close()
