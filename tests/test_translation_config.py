from app.desktop.translation_config import (
    TranslationSettings,
    delete_translation_settings,
    load_translation_settings,
    save_translation_settings,
)


def test_translation_settings_round_trip(tmp_path):
    path = tmp_path / "translation.json"
    settings = TranslationSettings(
        endpoint="https://translate.example/translate",
        api_key="secret",
    )
    save_translation_settings(path, settings)
    loaded = load_translation_settings(path)
    assert loaded == settings


def test_translation_settings_delete(tmp_path):
    path = tmp_path / "translation.json"
    save_translation_settings(
        path,
        TranslationSettings(endpoint="https://translate.example/translate"),
    )
    delete_translation_settings(path)
    assert load_translation_settings(path) is None
