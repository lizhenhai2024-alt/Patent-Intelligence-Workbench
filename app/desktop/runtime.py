"""Compose backend services used by the desktop shell."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.company_registry import CompanyRegistry
from app.core.technology_dictionary import TechnologyDictionary
from app.desktop.credentials import CredentialStore, DesktopCredentialStore, EpoOpsCredentials
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
    family_downloader: FamilyDownloader
    credential_store: CredentialStore
    search_service: SearchService | None = None
    family_resolver: FamilyResolver | None = None
    watch_scheduler: PatentWatchScheduler | None = None
    search_status: str = "EPO OPS 未配置"
    credential_source: str | None = None

    @classmethod
    def create(
        cls,
        paths: AppPaths | None = None,
        credential_store: CredentialStore | None = None,
    ) -> DesktopRuntime:
        resolved_paths = (paths or AppPaths.default()).ensure()
        library_store = SQLitePatentLibrary(resolved_paths.library_db)
        watch_store = SQLiteWatchStateStore(resolved_paths.watch_db)

        if not watch_store.list_rules():
            seed_watch_templates(
                watch_store,
                default_v1_watch_templates(),
            )

        runtime = cls(
            paths=resolved_paths,
            library_store=library_store,
            library_service=PatentLibraryService(library_store),
            watch_store=watch_store,
            family_downloader=FamilyDownloader(build_default_download_manager()),
            credential_store=credential_store or DesktopCredentialStore(),
        )
        runtime.reload_network_services()
        return runtime

    def reload_network_services(self) -> None:
        credentials = self.credential_store.load_epo_ops()
        if credentials is None:
            self.search_service = None
            self.family_resolver = None
            self.watch_scheduler = None
            self.credential_source = None
            self.search_status = (
                "EPO OPS 未配置：请在 Settings 中填写 Consumer Key / Secret"
            )
            return

        self._configure_epo(credentials)

    def save_epo_credentials(
        self,
        consumer_key: str,
        consumer_secret: str,
    ) -> None:
        self.credential_store.save_epo_ops(consumer_key, consumer_secret)
        self._configure_epo(
            EpoOpsCredentials(
                consumer_key=consumer_key.strip(),
                consumer_secret=consumer_secret.strip(),
                source="windows-credential-manager",
            )
        )

    def delete_epo_credentials(self) -> None:
        self.credential_store.delete_epo_ops()
        self.reload_network_services()

    def current_epo_credentials(self) -> EpoOpsCredentials | None:
        return self.credential_store.load_epo_ops()

    def _configure_epo(self, credentials: EpoOpsCredentials) -> None:
        epo = EpoOpsProvider(
            consumer_key=credentials.consumer_key,
            consumer_secret=credentials.consumer_secret,
        )
        self.search_service = SearchService(
            provider=epo,
            company_registry=CompanyRegistry.default(),
            technology_dictionary=TechnologyDictionary.default(),
        )
        self.family_resolver = FamilyResolver([epo])
        def archive_watch_event(rule, event) -> None:
            self.library_service.ingest_watch_event(
                event,
                company_group=rule.company_group,
                technology_topics=rule.technology_terms,
            )

        watch_engine = PatentWatchEngine(
            search_service=self.search_service,
            family_resolver=self.family_resolver,
            state_store=self.watch_store,
            event_sink=archive_watch_event,
        )
        self.watch_scheduler = PatentWatchScheduler(
            engine=watch_engine,
            state_store=self.watch_store,
        )
        self.credential_source = credentials.source
        source_label = {
            "windows-credential-manager": "Windows Credential Manager",
            "environment": "环境变量",
        }.get(credentials.source, credentials.source)
        self.search_status = f"EPO OPS 已配置（{source_label}）"

    def close(self) -> None:
        self.library_store.close()
        self.watch_store.close()
