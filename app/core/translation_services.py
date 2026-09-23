"""Common machine-translation services for the patent Reader.

Each service is described once (label, default endpoint, which credentials it
needs) and built into a provider with the same ``translate`` contract.
Request formats checked against each vendor's documentation on 2026-09-23.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass

import httpx

from app.core.openai_compat import http_hint
from app.core.translation import TranslationResult
from app.core.translation_http import (
    DeepLTranslationProvider,
    HttpTranslationProvider,
)


@dataclass(frozen=True, slots=True)
class TranslationService:
    service_id: str
    label: str
    endpoint: str  # default endpoint; "" means the user must enter one
    key_label: str  # "" means no secret needed
    app_id_label: str = ""  # Baidu APPID / Youdao 应用ID / Azure 区域
    app_id_required: bool = False
    endpoint_editable: bool = False


SERVICES: tuple[TranslationService, ...] = (
    TranslationService(
        "deepl_free", "DeepL（免费版）", "https://api-free.deepl.com/v2/translate",
        "DeepL API Key",
    ),
    TranslationService(
        "deepl_pro", "DeepL（专业版）", "https://api.deepl.com/v2/translate", "DeepL API Key"
    ),
    TranslationService(
        "google", "Google 翻译（Cloud Translation）",
        "https://translation.googleapis.com/language/translate/v2", "API Key",
    ),
    TranslationService(
        "azure", "微软翻译（Azure Translator）",
        "https://api.cognitive.microsofttranslator.com", "密钥（Key）",
        app_id_label="区域（全局资源可留空）",
    ),
    TranslationService(
        "baidu", "百度翻译", "https://fanyi-api.baidu.com/api/trans/vip/translate", "密钥",
        app_id_label="APPID", app_id_required=True,
    ),
    TranslationService(
        "youdao", "有道智云翻译", "https://openapi.youdao.com/api", "应用密钥",
        app_id_label="应用ID", app_id_required=True,
    ),
    TranslationService(
        "http", "自定义（LibreTranslate 兼容）", "", "API Key（可选）", endpoint_editable=True
    ),
)
LLM_SERVICE_ID = "llm_profile"
LLM_SERVICE_LABEL = "大模型（AI 模型配置）"

BY_ID = {service.service_id: service for service in SERVICES}
BY_LABEL = {service.label: service for service in SERVICES}


def service_labels() -> tuple[str, ...]:
    return (*(service.label for service in SERVICES), LLM_SERVICE_LABEL)


def normalize_service_id(provider: str, endpoint: str = "") -> str:
    """Map legacy stored provider ids onto the current service ids."""
    if provider == "deepl":
        return "deepl_pro" if "api.deepl.com" in endpoint else "deepl_free"
    return provider


# -- language codes ----------------------------------------------------------

_LANG = {
    # app tag: (baidu, youdao, azure, google)
    "zh-cn": ("zh", "zh-CHS", "zh-Hans", "zh-CN"),
    "zh": ("zh", "zh-CHS", "zh-Hans", "zh-CN"),
    "en": ("en", "en", "en", "en"),
    "ja": ("jp", "ja", "ja", "ja"),
    "ko": ("kor", "ko", "ko", "ko"),
    "de": ("de", "de", "de", "de"),
}
_COLUMN = {"baidu": 0, "youdao": 1, "azure": 2, "google": 3}


def _lang(service: str, language: str) -> str:
    normalized = language.strip().lower()
    if normalized in ("", "auto"):
        return "auto"
    codes = _LANG.get(normalized)
    return codes[_COLUMN[service]] if codes else normalized


def _chunks(text: str, limit: int) -> list[str]:
    """Split on line breaks so each request stays under the vendor's size limit."""
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks or [""]


def _check_http(response: httpx.Response, label: str) -> None:
    if response.is_error:
        status = response.status_code
        raise RuntimeError(
            f"{label}翻译失败：{http_hint(status).split('：')[0]}（HTTP {status}）"
            f"\n原始信息：{response.text[:300]}"
        )


def _result(text: str, name: str, source: str, target: str) -> TranslationResult:
    return TranslationResult(
        text=text, provider=name, source_language=source, target_language=target
    )


# -- providers -----------------------------------------------------------------


@dataclass(slots=True)
class GoogleTranslationProvider:
    api_key: str
    endpoint: str = BY_ID["google"].endpoint
    timeout_seconds: float = 30.0
    name: str = "GOOGLE"

    def translate(self, text, *, source_language="auto", target_language="zh-CN"):
        body = {"q": text, "target": _lang("google", target_language), "format": "text"}
        source = _lang("google", source_language)
        if source != "auto":
            body["source"] = source
        response = httpx.post(
            self.endpoint, params={"key": self.api_key}, json=body, timeout=self.timeout_seconds
        )
        _check_http(response, "Google ")
        try:
            translated = response.json()["data"]["translations"][0]["translatedText"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise RuntimeError("Google 翻译返回格式无法识别。") from exc
        return _result(translated, self.name, source_language, target_language)


@dataclass(slots=True)
class AzureTranslationProvider:
    api_key: str
    region: str = ""
    endpoint: str = BY_ID["azure"].endpoint
    timeout_seconds: float = 30.0
    name: str = "AZURE"

    def translate(self, text, *, source_language="auto", target_language="zh-CN"):
        params = {"api-version": "3.0", "to": _lang("azure", target_language)}
        source = _lang("azure", source_language)
        if source != "auto":
            params["from"] = source
        headers = {"Ocp-Apim-Subscription-Key": self.api_key}
        if self.region.strip():
            headers["Ocp-Apim-Subscription-Region"] = self.region.strip()
        parts = []
        for chunk in _chunks(text, 40000):
            response = httpx.post(
                self.endpoint.rstrip("/") + "/translate",
                params=params,
                headers=headers,
                json=[{"Text": chunk}],
                timeout=self.timeout_seconds,
            )
            _check_http(response, "微软")
            try:
                parts.append(response.json()[0]["translations"][0]["text"])
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                raise RuntimeError("微软翻译返回格式无法识别。") from exc
        return _result("\n".join(parts), self.name, source_language, target_language)


@dataclass(slots=True)
class BaiduTranslationProvider:
    app_id: str
    secret: str
    endpoint: str = BY_ID["baidu"].endpoint
    timeout_seconds: float = 30.0
    name: str = "BAIDU"

    def translate(self, text, *, source_language="auto", target_language="zh-CN"):
        parts = []
        for chunk in _chunks(text, 1800):
            salt = uuid.uuid4().hex[:10]
            # sign = MD5(appid + q + salt + 密钥); q is not URL-encoded when signing.
            sign = hashlib.md5(
                (self.app_id + chunk + salt + self.secret).encode("utf-8")
            ).hexdigest()
            response = httpx.post(
                self.endpoint,
                data={
                    "q": chunk,
                    "from": _lang("baidu", source_language),
                    "to": _lang("baidu", target_language),
                    "appid": self.app_id,
                    "salt": salt,
                    "sign": sign,
                },
                timeout=self.timeout_seconds,
            )
            _check_http(response, "百度")
            data = response.json()
            if "error_code" in data and str(data["error_code"]) != "52000":
                raise RuntimeError(
                    f"百度翻译失败：错误码 {data['error_code']}（{data.get('error_msg', '')}）"
                    "；54001 表示签名错误，请检查 APPID 和密钥"
                )
            try:
                parts.append("\n".join(item["dst"] for item in data["trans_result"]))
            except (KeyError, TypeError) as exc:
                raise RuntimeError("百度翻译返回格式无法识别。") from exc
        return _result("\n".join(parts), self.name, source_language, target_language)


@dataclass(slots=True)
class YoudaoTranslationProvider:
    app_key: str
    app_secret: str
    endpoint: str = BY_ID["youdao"].endpoint
    timeout_seconds: float = 30.0
    name: str = "YOUDAO"

    def translate(self, text, *, source_language="auto", target_language="zh-CN"):
        parts = []
        for chunk in _chunks(text, 4500):
            salt = uuid.uuid4().hex
            curtime = str(int(time.time()))
            # input = q (≤20 chars) or first 10 + length + last 10.
            sign_input = chunk if len(chunk) <= 20 else f"{chunk[:10]}{len(chunk)}{chunk[-10:]}"
            sign = hashlib.sha256(
                (self.app_key + sign_input + salt + curtime + self.app_secret).encode("utf-8")
            ).hexdigest()
            response = httpx.post(
                self.endpoint,
                data={
                    "q": chunk,
                    "from": _lang("youdao", source_language),
                    "to": _lang("youdao", target_language),
                    "appKey": self.app_key,
                    "salt": salt,
                    "sign": sign,
                    "signType": "v3",
                    "curtime": curtime,
                },
                timeout=self.timeout_seconds,
            )
            _check_http(response, "有道")
            data = response.json()
            if str(data.get("errorCode")) != "0":
                raise RuntimeError(
                    f"有道翻译失败：错误码 {data.get('errorCode')}；"
                    "202 表示签名错误，108 表示应用ID无效"
                )
            try:
                parts.append("\n".join(data["translation"]))
            except (KeyError, TypeError) as exc:
                raise RuntimeError("有道翻译返回格式无法识别。") from exc
        return _result("\n".join(parts), self.name, source_language, target_language)


def build_provider(service_id: str, *, endpoint: str, api_key: str, app_id: str = ""):
    """Build the provider for a non-LLM service; raises ValueError when incomplete."""
    service = BY_ID.get(service_id)
    if service is None:
        raise ValueError(f"未知的翻译服务：{service_id}")
    url = endpoint.strip() or service.endpoint
    if not url:
        raise ValueError("请填写翻译接口地址")
    if service.key_label and not service.key_label.endswith("（可选）") and not api_key.strip():
        raise ValueError(f"{service.label}需要填写{service.key_label}")
    if service.app_id_required and not app_id.strip():
        raise ValueError(f"{service.label}需要填写{service.app_id_label}")
    key = api_key.strip()
    if service_id in ("deepl_free", "deepl_pro"):
        return DeepLTranslationProvider(api_key=key, endpoint=url)
    if service_id == "google":
        return GoogleTranslationProvider(api_key=key, endpoint=url)
    if service_id == "azure":
        return AzureTranslationProvider(api_key=key, region=app_id.strip(), endpoint=url)
    if service_id == "baidu":
        return BaiduTranslationProvider(app_id=app_id.strip(), secret=key, endpoint=url)
    if service_id == "youdao":
        return YoudaoTranslationProvider(app_key=app_id.strip(), app_secret=key, endpoint=url)
    return HttpTranslationProvider(endpoint=url, api_key=key or None)
