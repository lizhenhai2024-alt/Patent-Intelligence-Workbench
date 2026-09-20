from app.core.patent_number import normalize_patent_number
from app.downloads.source_catalog import DownloadSourceCatalog


def test_jp_official_sources_are_exposed_without_claiming_auto_pdf_api():
    catalog = DownloadSourceCatalog.default()
    hints = catalog.hints_for(normalize_patent_number("JP2024000123A"))

    assert hints[0].name == "J-PlatPat"
    assert hints[0].access_mode == "MANUAL"
    assert hints[0].document_type == "PUBLICATION_PDF"
    assert hints[1].name == "JPO Patent Information Retrieval API"
    assert hints[1].access_mode == "REGISTERED"
    assert hints[1].document_type == "APPLICATION_DOCUMENTS_XML_ZIP"


def test_cn_official_sources_include_publication_and_registered_bulk_routes():
    catalog = DownloadSourceCatalog.default()
    hints = catalog.hints_for(normalize_patent_number("CN115123456A"))

    assert [hint.access_mode for hint in hints] == ["MANUAL", "REGISTERED"]
    assert hints[0].name == "CNIPA Patent Publication System"


def test_wo_policy_does_not_model_patentscope_as_automated_robot_source():
    catalog = DownloadSourceCatalog.default()
    hints = catalog.hints_for(normalize_patent_number("WO2024123456A1"))

    assert hints[0].name == "WIPO PATENTSCOPE"
    assert hints[0].access_mode == "MANUAL"
    assert hints[1].access_mode == "LICENSED"
