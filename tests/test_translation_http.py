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


def test_deepl_translation_provider_parses_response_and_omits_auto_source(monkeypatch):
    from app.core.translation_http import DeepLTranslationProvider

    captured = {}

    def fake_post(url, *, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            json={"translations": [{"detected_source_language": "JA", "text": "先导阀"}]},
            request=request,
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = DeepLTranslationProvider(api_key="secret")
    result = provider.translate("パイロットバルブ", source_language="auto", target_language="zh-CN")

    assert result.text == "先导阀"
    assert result.provider == "DEEPL"
    assert captured["json"]["target_lang"] == "ZH"
    assert "source_lang" not in captured["json"]
    assert captured["headers"]["Authorization"] == "DeepL-Auth-Key secret"


def test_deepl_translation_provider_maps_explicit_source_language(monkeypatch):
    from app.core.translation_http import DeepLTranslationProvider

    captured = {}

    def fake_post(url, *, json, headers, timeout):
        captured["json"] = json
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            json={"translations": [{"text": "阻尼阀"}]},
            request=request,
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = DeepLTranslationProvider(api_key="secret")
    provider.translate("Dämpferventil", source_language="de", target_language="zh-CN")

    assert captured["json"]["source_lang"] == "DE"


def test_llm_translation_provider_sends_chat_completion_and_parses_reply(monkeypatch):
    from app.core.translation_http import LlmTranslationProvider

    captured = {}

    def fake_post(url, *, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        request = httpx.Request("POST", url)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "先导阀"}}]},
            request=request,
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = LlmTranslationProvider(
        endpoint="https://api.deepseek.com/chat/completions",
        api_key="secret",
        model="deepseek-chat",
    )
    result = provider.translate("pilot valve", target_language="zh-CN")

    assert result.text == "先导阀"
    assert result.provider == "LLM_TRANSLATE"
    assert captured["json"]["model"] == "deepseek-chat"
    assert "中文" in captured["json"]["messages"][0]["content"]
    assert captured["headers"]["Authorization"] == "Bearer secret"


def test_llm_translation_provider_rejects_malformed_response(monkeypatch):
    from app.core.translation_http import LlmTranslationProvider

    def fake_post(url, *, json, headers, timeout):
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"unexpected": "shape"}, request=request)

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = LlmTranslationProvider(
        endpoint="https://api.openai.com/v1/chat/completions",
        api_key="secret",
        model="gpt-4o-mini",
    )
    try:
        provider.translate("pilot valve")
    except RuntimeError as exc:
        assert "格式无法识别" in str(exc)
    else:
        raise AssertionError("expected RuntimeError for malformed response")
