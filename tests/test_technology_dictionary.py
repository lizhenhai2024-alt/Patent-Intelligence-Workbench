from app.core.technology_dictionary import TechnologyDictionary


def test_default_dictionary_maps_chinese_query_to_multiple_epo_concepts():
    dictionary = TechnologyDictionary.default()

    groups = dictionary.expand(
        "外置先导阀背压控制减振器",
        provider_name="EPO_OPS",
    )

    assert ("pilot valve", "solenoid valve", "external control valve") in groups
    assert ("back pressure", "back pressure chamber") in groups
    assert ("shock absorber", "damper") in groups


def test_japanese_alias_can_trigger_english_epo_search_terms():
    dictionary = TechnologyDictionary.default()

    groups = dictionary.expand(
        "減衰力調整式緩衝器",
        provider_name="EPO_OPS",
    )

    assert (
        "electronically controlled damper",
        "variable damping force",
        "continuous damping control",
        "semi active damper",
    ) in groups
