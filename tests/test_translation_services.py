import hashlib

import httpx
import pytest

from app.core import translation_services as ts


class Recorder:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        request = httpx.Request("POST", url)
        status, body = self.reply
        return httpx.Response(status, json=body, request=request)


def test_baidu_signs_md5_of_appid_q_salt_secret(monkeypatch):
    rec = Recorder((200, {"trans_result": [{"src": "a", "dst": "一"}, {"src": "b", "dst": "二"}]}))
    monkeypatch.setattr(ts.httpx, "post", rec)
    result = ts.BaiduTranslationProvider(app_id="APP", secret="KEY").translate("a\nb")
    assert result.text == "一\n二"
    data = rec.calls[0][1]["data"]
    assert data["to"] == "zh" and data["from"] == "auto"
    expected = hashlib.md5(("APP" + data["q"] + data["salt"] + "KEY").encode()).hexdigest()
    assert data["sign"] == expected


def test_baidu_error_code_is_explained(monkeypatch):
    monkeypatch.setattr(
        ts.httpx, "post", Recorder((200, {"error_code": "54001", "error_msg": "Invalid Sign"}))
    )
    with pytest.raises(RuntimeError, match="签名错误"):
        ts.BaiduTranslationProvider(app_id="APP", secret="KEY").translate("x")


def test_youdao_signs_sha256_with_truncated_input(monkeypatch):
    rec = Recorder((200, {"errorCode": "0", "translation": ["译文"]}))
    monkeypatch.setattr(ts.httpx, "post", rec)
    text = "A damper comprising a pilot valve and a spring"
    assert ts.YoudaoTranslationProvider(app_key="K", app_secret="S").translate(text).text == "译文"
    data = rec.calls[0][1]["data"]
    sign_input = text[:10] + str(len(text)) + text[-10:]
    expected = hashlib.sha256(
        ("K" + sign_input + data["salt"] + data["curtime"] + "S").encode()
    ).hexdigest()
    assert data["sign"] == expected and data["signType"] == "v3" and data["to"] == "zh-CHS"


def test_azure_headers_region_and_language(monkeypatch):
    rec = Recorder((200, [{"translations": [{"text": "你好", "to": "zh-Hans"}]}]))
    monkeypatch.setattr(ts.httpx, "post", rec)
    out = ts.AzureTranslationProvider(api_key="K", region="eastasia").translate("hello")
    url, kwargs = rec.calls[0]
    assert out.text == "你好"
    assert url.endswith("/translate")
    assert kwargs["params"] == {"api-version": "3.0", "to": "zh-Hans"}
    assert kwargs["headers"] == {
        "Ocp-Apim-Subscription-Key": "K",
        "Ocp-Apim-Subscription-Region": "eastasia",
    }
    assert kwargs["json"] == [{"Text": "hello"}]


def test_google_key_in_query_and_parse(monkeypatch):
    rec = Recorder((200, {"data": {"translations": [{"translatedText": "阻尼器"}]}}))
    monkeypatch.setattr(ts.httpx, "post", rec)
    assert ts.GoogleTranslationProvider(api_key="G").translate("damper").text == "阻尼器"
    kwargs = rec.calls[0][1]
    assert kwargs["params"] == {"key": "G"}
    assert kwargs["json"] == {"q": "damper", "target": "zh-CN", "format": "text"}


def test_http_errors_are_chinese(monkeypatch):
    monkeypatch.setattr(ts.httpx, "post", Recorder((401, {"error": "bad"})))
    with pytest.raises(RuntimeError, match="API Key 无效"):
        ts.GoogleTranslationProvider(api_key="G").translate("x")


def test_long_text_is_chunked_on_line_breaks():
    text = "\n".join(["段落" * 300] * 5)
    chunks = ts._chunks(text, 1800)
    assert all(len(c) <= 1800 for c in chunks)
    assert "\n".join(chunks) == text


def test_build_provider_requires_credentials_and_maps_legacy_deepl():
    with pytest.raises(ValueError, match="APPID"):
        ts.build_provider("baidu", endpoint="", api_key="k", app_id="")
    with pytest.raises(ValueError, match="DeepL API Key"):
        ts.build_provider("deepl_free", endpoint="", api_key="", app_id="")
    assert ts.normalize_service_id("deepl", "https://api.deepl.com/v2/translate") == "deepl_pro"
    assert (
        ts.normalize_service_id("deepl", "https://api-free.deepl.com/v2/translate") == "deepl_free"
    )
    assert (
        ts.build_provider("http", endpoint="https://lt.example/translate", api_key="").name
        == "HTTP_TRANSLATE"
    )
