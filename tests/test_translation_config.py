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


def test_translation_settings_defaults_to_http_provider_for_legacy_config(tmp_path):
    path = tmp_path / "translation.json"
    path.write_text(
        '{"endpoint": "https://translate.example/translate", "api_key": "secret"}',
        encoding="utf-8",
    )
    loaded = load_translation_settings(path)
    assert loaded.provider == "http"


def test_translation_settings_round_trip_with_deepl_provider(tmp_path):
    path = tmp_path / "translation.json"
    settings = TranslationSettings(
        endpoint="https://api-free.deepl.com/v2/translate",
        api_key="secret",
        provider="deepl",
    )
    save_translation_settings(path, settings)
    loaded = load_translation_settings(path)
    assert loaded == settings


def test_translation_settings_round_trip_with_llm_provider_and_model(tmp_path):
    path = tmp_path / "translation.json"
    settings = TranslationSettings(
        endpoint="https://api.deepseek.com/chat/completions",
        api_key="secret",
        provider="deepseek",
        model="deepseek-chat",
    )
    save_translation_settings(path, settings)
    loaded = load_translation_settings(path)
    assert loaded == settings


def test_translation_settings_defaults_model_to_empty_for_legacy_config(tmp_path):
    path = tmp_path / "translation.json"
    path.write_text(
        '{"endpoint": "https://translate.example/translate", "provider": "http"}',
        encoding="utf-8",
    )
    loaded = load_translation_settings(path)
    assert loaded.model == ""


def test_translation_settings_round_trip_with_mimo_provider(tmp_path):
    path = tmp_path / "translation.json"
    settings = TranslationSettings(
        endpoint="https://api.xiaomimimo.com/v1/chat/completions",
        api_key="secret",
        provider="mimo",
        model="mimo-v2.6-flash",
    )
    save_translation_settings(path, settings)
    loaded = load_translation_settings(path)
    assert loaded == settings
