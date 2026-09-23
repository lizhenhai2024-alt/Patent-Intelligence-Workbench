"""Test-session safety net: never touch the user's real application data.

Several desktop UI tests build the app with ``DesktopRuntime.create()``, which
defaults to %LOCALAPPDATA%\\PatentIntelligenceWorkbench. Until 2026-09-23 one of
them created a "Test Rule <timestamp>" watch rule in the real database on every
test run. PIW_DATA_DIR redirects AppPaths.default() to a throwaway folder.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def _isolate_app_data(tmp_path_factory):
    previous = os.environ.get("PIW_DATA_DIR")
    os.environ["PIW_DATA_DIR"] = str(tmp_path_factory.mktemp("piw-app-data"))
    yield
    if previous is None:
        os.environ.pop("PIW_DATA_DIR", None)
    else:
        os.environ["PIW_DATA_DIR"] = previous
