from app.downloads.naming import family_folder_name, patent_pdf_filename, safe_component


def test_safe_component_replaces_windows_invalid_characters():
    assert safe_component('A:B/C*D?"E') == "A_B_C_D__E"


def test_patent_pdf_filename():
    assert patent_pdf_filename("JP2024000123A") == "JP2024000123A.pdf"
    assert (
        patent_pdf_filename(
            "CN120100850A",
            "一种浮动/密封式电磁阀:减振器",
            year=2025,
            assignee="一汽东机工减振器有限公司",
        )
        == "2025-CN120100850A-一种浮动_密封式电磁阀_减振器-一汽东机工减振器有限公司.pdf"
    )


def test_family_folder_prefers_source_family_id():
    assert (
        family_folder_name(
            source_family_id="12345",
            earliest_priority_number="JP2022000001",
            representative_publication="JP2024000001A",
        )
        == "Family_12345"
    )
