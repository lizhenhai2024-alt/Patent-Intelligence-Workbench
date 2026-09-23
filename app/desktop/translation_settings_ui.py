"""Settings → 翻译设置: common MT services plus 大模型 (shared AI model profiles).

Secrets (API keys / 密钥) live in the same secret store as AI model profiles
(Windows Credential Manager), never in translation.json.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from app.core.translation import UnconfiguredTranslationProvider
from app.core.translation_http import CachedTranslationProvider, LlmTranslationProvider
from app.core.translation_services import (
    BY_ID,
    BY_LABEL,
    LLM_SERVICE_ID,
    LLM_SERVICE_LABEL,
    SERVICES,
    build_provider,
    normalize_service_id,
    service_labels,
)
from app.desktop.translation_config import (
    TranslationSettings,
    delete_translation_settings,
    load_translation_settings,
    save_translation_settings,
)

# Pre-2026-09-23 translation.json provider ids that called an LLM vendor directly.
LEGACY_LLM_PROVIDERS = {"openai", "deepseek", "qwen", "glm", "kimi", "doubao", "mimo"}
_SECRET_PREFIX = "翻译/"
_DEFAULT_ENDPOINTS = {service.endpoint for service in SERVICES if service.endpoint}


def _label_for(settings: TranslationSettings | None) -> str:
    if settings is None:
        return BY_ID["deepl_free"].label
    if settings.provider == LLM_SERVICE_ID or settings.provider in LEGACY_LLM_PROVIDERS:
        return LLM_SERVICE_LABEL
    service = BY_ID.get(normalize_service_id(settings.provider, settings.endpoint))
    return service.label if service else BY_ID["http"].label


def status_text(settings: TranslationSettings | None) -> str:
    if settings is None:
        return "翻译服务：未配置"
    if settings.provider == LLM_SERVICE_ID:
        return f"翻译服务：大模型（AI 模型配置“{settings.model_profile}”）"
    if settings.provider in LEGACY_LLM_PROVIDERS:
        return (
            "翻译服务：旧版大模型配置仍在使用（API Key 以明文保存在 translation.json）；"
            "请选择一个 AI 模型配置后重新保存"
        )
    return f"翻译服务：{_label_for(settings)}（已配置）"


def _secret_name(service_id: str) -> str:
    return _SECRET_PREFIX + service_id


def build_translation_section(app, parent, **pack_options) -> None:
    settings = load_translation_settings(app.translation_settings_path)
    frame = ttk.LabelFrame(parent, text="翻译设置", padding=12)
    frame.pack(fill="x", **pack_options)
    app.translation_provider_var = tk.StringVar(value=_label_for(settings))
    app.translation_endpoint_var = tk.StringVar(value=settings.endpoint if settings else "")
    app.translation_api_key_var = tk.StringVar()
    app.translation_app_id_var = tk.StringVar(value=settings.app_id if settings else "")
    app.translation_model_var = tk.StringVar(value=settings.model if settings else "")
    app.translation_profile_var = tk.StringVar(value=settings.model_profile if settings else "")
    app.translation_status_var = tk.StringVar(value=status_text(settings))
    app.translation_key_label_var = tk.StringVar(value="API Key")
    app.translation_app_id_label_var = tk.StringVar(value="APPID")
    app._translation_last_service = app.translation_provider_var.get()

    ttk.Label(frame, text="服务类型").grid(row=0, column=0, sticky="w")
    combo = ttk.Combobox(
        frame,
        textvariable=app.translation_provider_var,
        values=service_labels(),
        state="readonly",
        width=30,
    )
    combo.grid(row=1, column=0, padx=(0, 10), pady=(0, 8), sticky="w")
    combo.bind("<<ComboboxSelected>>", lambda _e: app._on_translation_provider_changed())
    app.translation_service_combo = combo
    ttk.Label(
        frame,
        text=(
            "DeepL / Google / 微软 / 百度 / 有道：填对应平台的密钥即可，接口地址自动填好；"
            "自定义：LibreTranslate 兼容接口；大模型：使用上方“AI 模型配置”中的一个配置。"
        ),
        style="Subtle.TLabel",
        wraplength=760,
    ).grid(row=1, column=1, columnspan=4, sticky="w")

    ttk.Label(frame, text="接口地址").grid(row=2, column=0, sticky="w")
    app.translation_endpoint_entry = ttk.Entry(
        frame, textvariable=app.translation_endpoint_var, width=52
    )
    app.translation_endpoint_entry.grid(row=3, column=0, padx=(0, 10), sticky="ew")
    ttk.Label(frame, textvariable=app.translation_app_id_label_var).grid(
        row=2, column=1, sticky="w"
    )
    app.translation_app_id_entry = ttk.Entry(
        frame, textvariable=app.translation_app_id_var, width=22
    )
    app.translation_app_id_entry.grid(row=3, column=1, padx=(0, 10), sticky="ew")
    ttk.Label(frame, textvariable=app.translation_key_label_var).grid(
        row=2, column=2, sticky="w"
    )
    app.translation_api_key_entry = ttk.Entry(
        frame, textvariable=app.translation_api_key_var, show="●", width=26
    )
    app.translation_api_key_entry.grid(row=3, column=2, padx=(0, 10), sticky="ew")
    ttk.Label(frame, text="AI 模型配置（大模型）").grid(row=2, column=3, sticky="w")
    app.translation_profile_combo = ttk.Combobox(
        frame, textvariable=app.translation_profile_var, state="readonly", width=24
    )
    app.translation_profile_combo.grid(row=3, column=3, padx=(0, 10), sticky="ew")

    buttons = ttk.Frame(frame)
    buttons.grid(row=4, column=0, columnspan=5, sticky="w", pady=(10, 0))
    ttk.Button(buttons, text="保存翻译配置", command=app.save_translation_settings).pack(
        side="left"
    )
    ttk.Button(buttons, text="删除翻译配置", command=app.delete_translation_settings).pack(
        side="left", padx=8
    )
    ttk.Label(buttons, textvariable=app.translation_status_var, style="Subtle.TLabel").pack(
        side="left", padx=8
    )
    for column in range(4):
        frame.columnconfigure(column, weight=1)


def apply_service_state(app) -> None:
    label = app.translation_provider_var.get()
    llm = label == LLM_SERVICE_LABEL
    service = BY_LABEL.get(label)
    needs_app_id = bool(service and service.app_id_label)
    app.translation_endpoint_entry.state(["disabled"] if llm else ["!disabled"])
    app.translation_api_key_entry.state(["disabled"] if llm else ["!disabled"])
    app.translation_app_id_entry.state(["!disabled"] if needs_app_id else ["disabled"])
    app.translation_profile_combo.state(["!disabled", "readonly"] if llm else ["disabled"])
    app.translation_key_label_var.set(service.key_label if service else "API Key")
    app.translation_app_id_label_var.set(
        service.app_id_label if needs_app_id else "APPID / 区域（不需要）"
    )
    if llm and not app.translation_profile_var.get():
        names = app.translation_profile_combo.cget("values")
        if names:
            app.translation_profile_var.set(names[0])


def on_service_changed(app) -> None:
    label = app.translation_provider_var.get()
    if label != app._translation_last_service:
        # Credentials belong to one vendor: never carry them over to another.
        app.translation_api_key_var.set("")
        app.translation_app_id_var.set("")
    app._translation_last_service = label
    service = BY_LABEL.get(label)
    current = app.translation_endpoint_var.get().strip()
    if service is not None and service.endpoint:
        app.translation_endpoint_var.set(service.endpoint)
    elif service is not None and current in _DEFAULT_ENDPOINTS:
        app.translation_endpoint_var.set("")  # custom: drop another vendor's address
    elif service is None:
        app.translation_endpoint_var.set("")
    apply_service_state(app)


def reload_provider(app) -> None:
    settings = load_translation_settings(app.translation_settings_path)
    app.translation_provider = UnconfiguredTranslationProvider()
    if settings is None:
        return
    try:
        if settings.provider == LLM_SERVICE_ID:
            profile = app.model_profiles.get(settings.model_profile)
            base = LlmTranslationProvider(
                endpoint=profile.chat_url,
                api_key=app.model_profiles.api_key(profile.name) or "",
                model=profile.model,
                auth_style=profile.auth_style,
            )
        elif settings.provider in LEGACY_LLM_PROVIDERS:
            base = LlmTranslationProvider(
                endpoint=settings.endpoint, api_key=settings.api_key, model=settings.model
            )
        else:
            service_id = normalize_service_id(settings.provider, settings.endpoint)
            key = settings.api_key or app.model_profiles.secrets.get(_secret_name(service_id))
            base = build_provider(
                service_id, endpoint=settings.endpoint, api_key=key or "", app_id=settings.app_id
            )
    except (KeyError, ValueError):
        return
    app.translation_provider = CachedTranslationProvider(
        provider=base, cache_path=app.translation_cache_path
    )


def save(app) -> None:
    label = app.translation_provider_var.get()
    if label == LLM_SERVICE_LABEL:
        name = app.translation_profile_var.get().strip()
        try:
            profile = app.model_profiles.get(name)
        except KeyError:
            messagebox.showinfo(
                "缺少配置", "请先在上方“AI 模型配置”中保存一个配置，再在这里选择它。"
            )
            return
        if not app.model_profiles.api_key(profile.name):
            messagebox.showinfo("缺少配置", f"AI 模型配置“{profile.name}”还没有 API Key。")
            return
        settings = TranslationSettings(
            endpoint="", provider=LLM_SERVICE_ID, model_profile=profile.name
        )
    else:
        service = BY_LABEL[label]
        new_key = app.translation_api_key_var.get().strip()
        stored = app.model_profiles.secrets.get(_secret_name(service.service_id)) or ""
        key = new_key or stored
        endpoint = app.translation_endpoint_var.get().strip() or service.endpoint
        app_id = app.translation_app_id_var.get().strip()
        try:
            build_provider(service.service_id, endpoint=endpoint, api_key=key, app_id=app_id)
        except ValueError as exc:
            messagebox.showinfo("缺少配置", str(exc))
            return
        if new_key:
            app.model_profiles.secrets.set(_secret_name(service.service_id), new_key)
        settings = TranslationSettings(
            endpoint=endpoint, provider=service.service_id, app_id=app_id
        )
    save_translation_settings(app.translation_settings_path, settings)
    app.translation_api_key_var.set("")
    app._reload_translation_provider()
    app.translation_status_var.set(status_text(settings))
    app._set_status("翻译服务配置已保存")


def delete(app) -> None:
    settings = load_translation_settings(app.translation_settings_path)
    if settings is not None and settings.provider in BY_ID:
        app.model_profiles.secrets.delete(_secret_name(settings.provider))
    delete_translation_settings(app.translation_settings_path)
    app.translation_provider_var.set(BY_ID["deepl_free"].label)
    app._translation_last_service = app.translation_provider_var.get()
    app.translation_endpoint_var.set(BY_ID["deepl_free"].endpoint)
    app.translation_api_key_var.set("")
    app.translation_app_id_var.set("")
    app.translation_profile_var.set("")
    apply_service_state(app)
    app._reload_translation_provider()
    app.translation_status_var.set("翻译服务：未配置")
    app._set_status("翻译服务配置已删除")
