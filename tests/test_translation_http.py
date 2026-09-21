from pathlib import Path

import httpx

from app.core.translation_http import CachedTranslationProvider, HttpTranslationProvider


def test_http_translation_provider_parses_libretranslate_response(monkeypatch):
    def fake_post(url, *, json, timeout):
        assert url == "https://translate.example/translate"
        assert json["target"] == "zh-CN"
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"translatedText": "液压减振器"}, request=request)

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = HttpTranslationProvider("https://translate.example/translate")
    result = provider.translate("hydraulic damper")
    assert result.text == "液压减振器"
    assert result.provider == "HTTP_TRANSLATE"


def test_cached_translation_provider_reuses_disk_cache(monkeypatch, tmp_path: Path):
    calls = {"count": 0}

    def fake_translate(self, text, *, source_language="auto", target_language="zh-CN"):
        calls["count"] += 1
        from app.core.translation import TranslationResult

        return TranslationResult(
            text="先导阀",
            provider=self.name,
            source_language=source_language,
            target_language=target_language,
        )

    monkeypatch.setattr(HttpTranslationProvider, "translate", fake_translate)
    cached = CachedTranslationProvider(
        provider=HttpTranslationProvider("https://translate.example/translate"),
        cache_path=tmp_path / "translation-cache.json",
    )
    first = cached.translate("pilot valve")
    second = cached.translate("pilot valve")

    assert first.text == "先导阀"
    assert second.text == "先导阀"
    assert second.provider.endswith(":cache")
    assert calls["count"] == 1
