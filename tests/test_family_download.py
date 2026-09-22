import asyncio
import json
from datetime import date

from app.domain.family import FamilyType, PatentFamily, PatentPublication, PriorityClaim
from app.downloads.base import DownloadError, PdfPayload
from app.downloads.family import FamilyDownloader
from app.downloads.manager import DownloadManager


class StatefulProvider:
    name = "STATEFUL"

    def __init__(self, failing=None):
        self.failing = set(failing or [])
        self.calls = {}

    def supports(self, publication):
        return True

    async def fetch_pdf(self, publication):
        self.calls[publication.canonical] = self.calls.get(publication.canonical, 0) + 1
        if publication.canonical in self.failing:
            raise DownloadError("temporary failure")
        return PdfPayload(
            provider=self.name,
            source_url=f"https://example.test/{publication.canonical}.pdf",
            data=b"%PDF-1.7\nfamily-test\n%%EOF",
        )


def _family():
    priority = PriorityClaim(
        number="JP2022000456",
        country="JP",
        priority_date=date(2022, 3, 4),
    )
    return PatentFamily(
        family_type=FamilyType.DOCDB_SIMPLE,
        source="TEST",
        source_family_id="F-100",
        members=[
            PatentPublication(
                publication_number="JP2024000123A",
                jurisdiction="JP",
                title="Adaptive damper valve",
                publication_date=date(2024, 1, 10),
                original_assignees=("Example Corp",),
                priorities=(priority,),
            ),
            PatentPublication(
                publication_number="US20240123456A1",
                jurisdiction="US",
                priorities=(priority,),
            ),
        ],
    )


def test_family_downloader_writes_country_folders_and_manifest(tmp_path):
    provider = StatefulProvider()
    downloader = FamilyDownloader(DownloadManager([provider]))

    summary = asyncio.run(downloader.download_family(_family(), tmp_path))

    assert summary.succeeded == 2
    assert summary.failed == 0
    assert (
        summary.family_folder
        / "JP"
        / "2024-JP2024000123A-Adaptive damper valve-Example Corp.pdf"
    ).is_file()
    assert (summary.family_folder / "US" / "US20240123456A1.pdf").is_file()

    payload = json.loads(summary.manifest_path.read_text(encoding="utf-8"))
    assert payload["source_family_id"] == "F-100"
    assert payload["earliest_priority"]["number"] == "JP2022000456"
    assert len(payload["downloads"]) == 2


def test_retry_failed_only_does_not_redownload_prior_success(tmp_path):
    provider = StatefulProvider(failing={"US20240123456A1"})
    downloader = FamilyDownloader(DownloadManager([provider]))
    family = _family()

    first = asyncio.run(downloader.download_family(family, tmp_path))

    assert first.succeeded == 1
    assert first.failed == 1
    assert provider.calls["JP2024000123A"] == 1
    assert provider.calls["US20240123456A1"] == 1

    provider.failing.clear()
    second = asyncio.run(
        downloader.download_family(
            family,
            tmp_path,
            retry_failed_only=True,
        )
    )

    assert second.succeeded == 2
    assert second.failed == 0
    assert provider.calls["JP2024000123A"] == 1
    assert provider.calls["US20240123456A1"] == 2
    jp_record = next(
        item for item in second.members if item.publication_number == "JP2024000123A"
    )
    assert jp_record.from_cache is True


def test_family_downloader_reports_member_progress(tmp_path):
    provider = StatefulProvider(failing={"US20240123456A1"})
    downloader = FamilyDownloader(DownloadManager([provider]))
    updates = []

    summary = asyncio.run(
        downloader.download_family(
            _family(),
            tmp_path,
            on_progress=updates.append,
        )
    )

    assert summary.succeeded == 1
    assert summary.failed == 1
    assert [(item.completed, item.total) for item in updates] == [(1, 2), (2, 2)]
    assert updates[0].publication_number == "JP2024000123A"
    assert updates[0].status == "success"
    assert updates[1].publication_number == "US20240123456A1"
    assert updates[1].status == "failed"


class UnsupportedProvider:
    """Provider that never supports any publication."""

    name = "UNSUPPORTED"

    def supports(self, publication):
        return False

    async def fetch_pdf(self, publication):
        raise AssertionError("should not be called")


class SelectiveProvider:
    """Provider that supports only JP publications."""

    name = "SELECTIVE"

    def supports(self, publication):
        return publication.jurisdiction == "JP"

    async def fetch_pdf(self, publication):
        return PdfPayload(
            provider=self.name,
            source_url=f"https://example.test/{publication.canonical}.pdf",
            data=b"%PDF-1.7\nselective-test\n%%EOF",
        )


def _family_with_unsupported_jurisdiction():
    priority = PriorityClaim(
        number="JP2022000456",
        country="JP",
        priority_date=date(2022, 3, 4),
    )
    return PatentFamily(
        family_type=FamilyType.DOCDB_SIMPLE,
        source="TEST",
        source_family_id="F-200",
        members=[
            PatentPublication(
                publication_number="JP2024000123A",
                jurisdiction="JP",
                title="Damper valve",
                publication_date=date(2024, 1, 10),
                original_assignees=("Example Corp",),
                priorities=(priority,),
            ),
            PatentPublication(
                publication_number="BR112024001234A2",
                jurisdiction="BR",
                title="Brazilian family member",
                priorities=(priority,),
            ),
            PatentPublication(
                publication_number="ES1234567T3",
                jurisdiction="ES",
                title="Spanish family member",
                priorities=(priority,),
            ),
        ],
    )


def test_unsupported_jurisdiction_marked_unsupported_not_failed(tmp_path):
    """BR/ES members should be 'unsupported', not 'failed'."""
    provider = StatefulProvider()
    downloader = FamilyDownloader(DownloadManager([provider]))
    family = _family_with_unsupported_jurisdiction()

    summary = asyncio.run(downloader.download_family(family, tmp_path))

    assert summary.succeeded == 1
    assert summary.failed == 0
    assert summary.unsupported == 2

    br_member = next(
        m for m in summary.members if m.publication_number == "BR112024001234A2"
    )
    assert br_member.status == "unsupported"
    assert "jurisdiction" in (br_member.error or "").lower() or "unsupported" in (
        br_member.error or ""
    ).lower()

    es_member = next(
        m for m in summary.members if m.publication_number == "ES1234567T3"
    )
    assert es_member.status == "unsupported"

    jp_member = next(
        m for m in summary.members if m.publication_number == "JP2024000123A"
    )
    assert jp_member.status == "success"


def test_all_providers_unsupported_marks_member_unsupported(tmp_path):
    """When no provider supports a publication, status should be 'unsupported'."""
    downloader = FamilyDownloader(DownloadManager([UnsupportedProvider()]))
    family = _family()

    summary = asyncio.run(downloader.download_family(family, tmp_path))

    assert summary.succeeded == 0
    assert summary.failed == 0
    assert summary.unsupported == 2

    for member in summary.members:
        assert member.status == "unsupported"


def test_mixed_supported_and_unsupported_providers(tmp_path):
    """SelectiveProvider supports JP only; US should be 'unsupported', not 'failed'."""
    downloader = FamilyDownloader(DownloadManager([SelectiveProvider()]))
    family = _family()

    summary = asyncio.run(downloader.download_family(family, tmp_path))

    assert summary.succeeded == 1
    assert summary.failed == 0
    assert summary.unsupported == 1

    jp_member = next(
        m for m in summary.members if m.publication_number == "JP2024000123A"
    )
    assert jp_member.status == "success"

    us_member = next(
        m for m in summary.members if m.publication_number == "US20240123456A1"
    )
    assert us_member.status == "unsupported"


def test_actual_download_failure_still_marked_failed(tmp_path):
    """A provider that supports but errors should still yield status='failed'."""
    provider = StatefulProvider(failing={"US20240123456A1"})
    downloader = FamilyDownloader(DownloadManager([provider]))
    family = _family()

    summary = asyncio.run(downloader.download_family(family, tmp_path))

    assert summary.succeeded == 1
    assert summary.failed == 1
    assert summary.unsupported == 0

    us_member = next(
        m for m in summary.members if m.publication_number == "US20240123456A1"
    )
    assert us_member.status == "failed"


def test_unsupported_members_written_to_manifest(tmp_path):
    """Unsupported members should still appear in family.json."""
    downloader = FamilyDownloader(DownloadManager([UnsupportedProvider()]))
    family = _family()

    summary = asyncio.run(downloader.download_family(family, tmp_path))

    payload = json.loads(summary.manifest_path.read_text(encoding="utf-8"))
    assert len(payload["downloads"]) == 2
    statuses = {d["publication_number"]: d["status"] for d in payload["downloads"]}
    assert all(s == "unsupported" for s in statuses.values())
