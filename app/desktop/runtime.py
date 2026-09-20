"""Compose backend services used by the desktop shell."""

from __future__ import annotations

import os
from dataclasses import dataclass

from app.core.company_registry import CompanyRegistry
from app.core.technology_dictionary import TechnologyDictionary
from app.desktop.paths import AppPaths
from app.downloads.factory import build_default_download_manager
from app.downloads.family import FamilyDownloader
from app.library.service import PatentLibraryService
from app.library.store import SQLitePatentLibrary
from app.providers.epo_ops import EpoOpsProvider
from app.services.family_resolver import FamilyResolver
from app.services.search_service import SearchService
from app.watch.engine import PatentWatchEngine
from app.watch.scheduler import PatentWatchScheduler
from app.watch.state import SQLiteWatchStateStore
from app.watch.templates import default_v1_watch_templates, seed_watch_templates


@dataclass(slots=True)
class DesktopRuntime:
    paths: AppPaths
    library_store: SQLitePatentLibrary
    library_service: PatentLibraryService
    watch_store: SQLiteWatchStateStore
    search_service: SearchService | None
    family_resolver: FamilyResolver | None
    family_downloader: FamilyDownloader
    watch_scheduler: PatentWatchScheduler | None
    search_status: str

    @classmethod
    def create(cls, paths: AppPaths | None = None) -> DesktopRuntime:
        resolved_paths = (paths or AppPaths.default()).ensure()
        library_store = SQLitePatentLibrary(resolved_paths.library_db)
        watch_store = SQLiteWatchStateStore(resolved_paths.watch_db)

        if not watch_store.list_rules():
            seed_watch_templates(
                watch_store,
                default_v1_watch_templates(),
            )

        family_downloader = FamilyDownloader(build_default_download_manager())
        epo_key = os.getenv("EPO_OPS_KEY")
        epo_secret = os.getenv("EPO_OPS_SECRET")
        search_service: SearchService | None = None
        family_resolver: FamilyResolver | None = None
        watch_scheduler: PatentWatchScheduler | None = None

        if epo_key and epo_secret:
            epo = EpoOpsProvider(
                consumer_key=epo_key,
                consumer_secret=epo_secret,
            )
            search_service = SearchService(
                provider=epo,
                company_registry=CompanyRegistry.default(),
                technology_dictionary=TechnologyDictionary.default(),
            )
            family_resolver = FamilyResolver([epo])
            watch_engine = PatentWatchEngine(
                search_service=search_service,
                family_resolver=family_resolver,
                state_store=watch_store,
            )
            watch_scheduler = PatentWatchScheduler(
                engine=watch_engine,
                state_store=watch_store,
            )
            search_status = "EPO OPS 已配置"
        else:
            search_status = "EPO OPS 未配置：设置 EPO_OPS_KEY / EPO_OPS_SECRET"

        return cls(
            paths=resolved_paths,
            library_store=library_store,
            library_service=PatentLibraryService(library_store),
            watch_store=watch_store,
            search_service=search_service,
            family_resolver=family_resolver,
            family_downloader=family_downloader,
            watch_scheduler=watch_scheduler,
            search_status=search_status,
        )

    def close(self) -> None:
        self.library_store.close()
        self.watch_store.close()
