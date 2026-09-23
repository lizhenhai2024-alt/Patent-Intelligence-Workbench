"""Model presets and user model profiles for in-app agents (Agent track M2).

Profiles are stored as JSON without API keys. Keys live in a SecretStore:
Windows Credential Manager on the desktop, memory-only elsewhere.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from importlib import resources
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

import httpx

from app.core.openai_compat import chat_completions_url, http_hint

AUTH_STYLES = ("bearer", "api-key")


@dataclass(frozen=True, slots=True)
class ModelPreset:
    preset_id: str
    name: str
    base_url: str
    auth_style: str
    suggested_models: tuple[str, ...] = ()


def load_presets() -> tuple[ModelPreset, ...]:
    text = resources.files("app.resources").joinpath("model_presets.json").read_text("utf-8")
    return tuple(
        ModelPreset(
            preset_id=item["id"],
            name=item["name"],
            base_url=item["base_url"],
            auth_style=item["auth_style"],
            suggested_models=tuple(item.get("suggested_models", ())),
        )
        for item in json.loads(text)["presets"]
    )


@dataclass(frozen=True, slots=True)
class ModelProfile:
    name: str
    preset_id: str
    base_url: str
    auth_style: str
    model: str
    temperature: float = 0.2

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("请填写配置名称")
        _check_base_url(self.base_url)
        if self.auth_style not in AUTH_STYLES:
            raise ValueError(f"认证方式只能是：{'、'.join(AUTH_STYLES)}")
        if not self.model.strip():
            raise ValueError("请填写模型名称")
        if not 0 <= self.temperature <= 2:
            raise ValueError("temperature 必须在 0 到 2 之间")

    @property
    def chat_url(self) -> str:
        return chat_completions_url(self.base_url)

    @property
    def host(self) -> str:
        return urlparse(self.base_url).hostname or ""

    def auth_headers(self, api_key: str) -> dict[str, str]:
        key = api_key.strip()
        if not key:
            raise ValueError(f"模型配置“{self.name}”缺少 API Key")
        if self.auth_style == "api-key":
            return {"api-key": key}
        return {"Authorization": f"Bearer {key}"}


def _check_base_url(value: str) -> None:
    parsed = urlparse(value.strip())
    local_http = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme not in {"https", "http"} or not parsed.netloc or (
        parsed.scheme == "http" and not local_http
    ):
        raise ValueError("接口地址必须使用 HTTPS；本机 localhost 可使用 HTTP")


def key_mismatch_hint(base_url: str, api_key: str) -> str:
    """Catch the one known key/endpoint mix-up: MiMo sk- (pay-as-you-go) vs tp- (Token Plan)."""
    host = urlparse(base_url).hostname or ""
    key = api_key.strip()
    if host == "api.xiaomimimo.com" and key.startswith("tp-"):
        return "这是小米 MiMo Token Plan 的 Key（tp- 开头），请改选“小米 MiMo Token Plan”预设"
    token_plan = host.startswith("token-plan-") and host.endswith(".xiaomimimo.com")
    if token_plan and key.startswith("sk-"):
        return "这是小米 MiMo 按量付费的 Key（sk- 开头），请改选“小米 MiMo（按量付费）”预设"
    return ""


def models_url(base_url: str) -> str:
    url = base_url.strip().rstrip("/")
    if url.endswith("/chat/completions"):
        url = url[: -len("/chat/completions")]
    return url + "/models"


def fetch_models(
    base_url: str,
    auth_style: str,
    api_key: str,
    *,
    client: httpx.Client | None = None,
) -> tuple[str, ...]:
    """List model ids from the provider's OpenAI-compatible GET /models."""
    _check_base_url(base_url)
    probe = ModelProfile("probe", "custom", base_url, auth_style, "probe")
    http = client or httpx.Client(timeout=20.0)
    try:
        response = http.get(models_url(base_url), headers=probe.auth_headers(api_key))
        response.raise_for_status()
        items = response.json()["data"]
        ids = sorted(
            {str(item["id"]) for item in items if isinstance(item, dict) and item.get("id")}
        )
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        raise ValueError(f"获取模型列表失败：{http_hint(status)}（HTTP {status}）") from None
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"获取模型列表失败：该接口不提供模型列表或返回格式无法识别（{exc}）"
        ) from None
    if not ids:
        raise ValueError("获取模型列表失败：接口返回的列表为空")
    return tuple(ids)


class SecretStore(Protocol):
    persistent: bool

    def get(self, profile_name: str) -> str | None: ...

    def set(self, profile_name: str, secret: str) -> None: ...

    def delete(self, profile_name: str) -> None: ...


class MemorySecretStore:
    """Keys kept only for the current process (non-Windows and tests)."""

    persistent = False

    def __init__(self) -> None:
        self._secrets: dict[str, str] = {}

    def get(self, profile_name: str) -> str | None:
        return self._secrets.get(profile_name)

    def set(self, profile_name: str, secret: str) -> None:
        self._secrets[profile_name] = secret

    def delete(self, profile_name: str) -> None:
        self._secrets.pop(profile_name, None)


class ProfileStore:
    """Profiles in a JSON file (never keys); keys in the SecretStore."""

    def __init__(self, path: str | Path, secrets: SecretStore) -> None:
        self.path = Path(path)
        self.secrets = secrets

    def list(self) -> tuple[ModelProfile, ...]:
        if not self.path.is_file():
            return ()
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return tuple(ModelProfile(**item) for item in payload.get("profiles", ()))

    def get(self, name: str) -> ModelProfile:
        for profile in self.list():
            if profile.name == name:
                return profile
        raise KeyError(name)

    def save(self, profile: ModelProfile, api_key: str | None = None) -> None:
        profiles = [p for p in self.list() if p.name != profile.name] + [profile]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"profiles": [asdict(p) for p in sorted(profiles, key=lambda p: p.name)]}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
        if api_key and api_key.strip():
            self.secrets.set(profile.name, api_key.strip())

    def delete(self, name: str) -> None:
        remaining = [p for p in self.list() if p.name != name]
        payload = {"profiles": [asdict(p) for p in remaining]}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
        self.secrets.delete(name)

    def api_key(self, name: str) -> str | None:
        return self.secrets.get(name)
