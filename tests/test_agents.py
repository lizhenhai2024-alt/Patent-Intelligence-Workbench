import json
import threading
from datetime import date

import httpx
import pytest

from app.agent_tools.tools import open_read_only
from app.agents.definition import DefinitionError, load_definitions, parse_definition
from app.agents.model_profiles import (
    MemorySecretStore,
    ModelProfile,
    ProfileStore,
    key_mismatch_hint,
    load_presets,
)
from app.agents.receipts import check_answer, citations
from app.agents.runtime import AgentRunner, CheckpointDecision
from app.domain.family import PatentPublication
from app.library.store import SQLitePatentLibrary

KEY = "sk-TEST-SECRET-123"

VALID = """+++
id = "demo"
name = "演示"
version = 1
description = "测试用"
tools = ["search_library", "get_publication"]
max_steps = 4
checkpoints = []
output = "report_with_receipts"
+++

## 目标
x
## 步骤
x
## 输出模板
x
"""


def _variant(old, new):
    assert old in VALID
    return VALID.replace(old, new)


# -- definition ------------------------------------------------------------


def test_valid_definition_and_shipped_definitions_load():
    definition = parse_definition(VALID, stem="demo")
    assert definition.tools == ("search_library", "get_publication")
    loaded, errors = load_definitions()
    assert errors == ()
    assert "library_qa" in {d.agent_id for d in loaded}


@pytest.mark.parametrize(
    ("text", "stem", "message"),
    [
        ("## 目标\n", "demo", "TOML"),
        (_variant('id = "demo"', 'id = "Demo-1"'), "demo", "小写"),
        (VALID, "other", "文件名"),
        (_variant('"get_publication"]', '"get_publication", "download_pdf"]'), "demo", "未开放"),
        (_variant("tools = [", "tools = [] #"), "demo", "非空"),
        (_variant("max_steps = 4", "max_steps = 99"), "demo", "max_steps"),
        (_variant("max_steps = 4", "max_step = 4"), "demo", "不认识的字段"),
        (_variant("checkpoints = []", 'checkpoints = ["skip_review"]'), "demo", "checkpoints"),
        (_variant('output = "report_with_receipts"', 'output = "legal_opinion"'), "demo", "output"),
        (_variant("## 输出模板\n", ""), "demo", "输出模板"),
        (_variant('version = 1', 'version = "1"'), "demo", "version"),
    ],
)
def test_definition_rules_refuse_bad_files(text, stem, message):
    with pytest.raises(DefinitionError, match=message):
        parse_definition(text, stem=stem)


def test_user_directory_errors_are_reported_not_loaded(tmp_path):
    (tmp_path / "bad.md").write_text(_variant('id = "demo"', 'id = "bad"').replace(
        "max_steps = 4", "max_steps = 0"), encoding="utf-8")
    (tmp_path / "library_qa.md").write_text(
        _variant('id = "demo"', 'id = "library_qa"'), encoding="utf-8")
    loaded, errors = load_definitions((tmp_path,))
    assert [d.agent_id for d in loaded] == ["library_qa"]
    assert loaded[0].source.startswith("内置")
    assert len(errors) == 2


# -- receipts --------------------------------------------------------------


def test_citation_parsing():
    assert citations("见 [CN120100850A, us20240000001a1] 和 [图1]") == (
        "CN120100850A",
        "US20240000001A1",
    )


def test_receipt_check_rules():
    text = "\n".join(
        (
            "## 结论",
            "- 采用先导阀结构 [US20240000001A1]",
            "- 凭记忆的结论 [US99999999A1]",
            "- 没有引用的结论",
            "- 该方案不构成侵权 [US20240000001A1]",
            "- 失效可能性约 80% [US20240000001A1]",
            "| 方案 | 证据 |",
            "|---|---|",
            "| 先导阀 | [US20240000001A1] |",
            "## 局限与待确认",
            "- 本地库覆盖有限，未读全文",
            "### 细节",
            "- 仍在豁免范围内",
            "## 其他",
            "- 豁免结束后的无引用行",
        )
    )
    check = check_answer(text, {"US20240000001A1"})
    status = {line.text: line.status for line in check.lines}
    assert status["- 采用先导阀结构 [US20240000001A1]"] == "ok"
    assert status["- 凭记忆的结论 [US99999999A1]"] == "unknown_receipt"
    assert status["- 没有引用的结论"] == "uncited"
    assert status["- 该方案不构成侵权 [US20240000001A1]"] == "forbidden"
    assert status["- 失效可能性约 80% [US20240000001A1]"] == "forbidden"
    assert status["| 方案 | 证据 |"] == "exempt"
    assert status["| 先导阀 | [US20240000001A1] |"] == "ok"
    assert status["- 本地库覆盖有限，未读全文"] == "exempt"
    assert status["- 仍在豁免范围内"] == "exempt"
    assert status["- 豁免结束后的无引用行"] == "uncited"
    assert check.flagged_count == 5
    # Lines are flagged, never removed.
    assert len(check.lines) == len(text.splitlines())


# -- model profiles --------------------------------------------------------


def test_presets_are_https_with_known_auth_and_mimo_uses_api_key():
    presets = {p.preset_id: p for p in load_presets()}
    assert {"openai", "anthropic", "deepseek", "qwen", "kimi", "glm", "doubao", "mimo"} <= set(
        presets
    )
    for preset in presets.values():
        assert preset.auth_style in {"bearer", "api-key"}
        assert preset.preset_id == "custom" or preset.base_url.startswith("https://")
    mimo = presets["mimo"]
    assert "mimo-v2.6-pro" in mimo.suggested_models
    profile = ModelProfile("MiMo", "mimo", mimo.base_url, mimo.auth_style, "mimo-v2.6-pro")
    assert profile.auth_headers(KEY) == {"api-key": KEY}
    assert profile.chat_url == "https://api.xiaomimimo.com/v1/chat/completions"


def test_profile_validation():
    with pytest.raises(ValueError, match="HTTPS"):
        ModelProfile("x", "custom", "http://example.com/v1", "bearer", "m")
    ModelProfile("local", "custom", "http://localhost:8000/v1", "bearer", "m")
    with pytest.raises(ValueError, match="认证方式"):
        ModelProfile("x", "custom", "https://example.com/v1", "basic", "m")
    with pytest.raises(ValueError, match="模型名称"):
        ModelProfile("x", "custom", "https://example.com/v1", "bearer", " ")


def test_profile_store_never_writes_keys(tmp_path):
    store = ProfileStore(tmp_path / "model_profiles.json", MemorySecretStore())
    profile = ModelProfile("DeepSeek", "deepseek", "https://api.deepseek.com/v1", "bearer", "m")
    store.save(profile, KEY)
    assert KEY not in (tmp_path / "model_profiles.json").read_text(encoding="utf-8")
    assert store.get("DeepSeek") == profile
    assert store.api_key("DeepSeek") == KEY
    store.delete("DeepSeek")
    assert store.list() == ()
    assert store.api_key("DeepSeek") is None


# -- runtime ---------------------------------------------------------------


@pytest.fixture
def tools(tmp_path):
    path = tmp_path / "workbench.db"
    store = SQLitePatentLibrary(path)
    store.upsert_publication(
        PatentPublication(
            publication_number="CN120000001A",
            jurisdiction="CN",
            title="减振器先导阀",
            publication_date=date(2025, 3, 4),
        )
    )
    store.add_company_group("CN120000001A", "kyb")
    store.close()
    library_tools = open_read_only(path)
    yield library_tools
    library_tools.store.close()


def _call(name, arguments, call_id="c1"):
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
    }


class FakeModel:
    """Scripted OpenAI-compatible endpoint that records every request."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(
            {"headers": dict(request.headers), "json": json.loads(request.content)}
        )
        reply = self.replies.pop(0)
        if isinstance(reply, int):
            return httpx.Response(reply, text=f"bad key {KEY}")
        return httpx.Response(200, json={"choices": [{"message": reply}]})


def _runner(definition, tools, fake, tmp_path, **kwargs):
    profile = ModelProfile("MiMo", "mimo", "https://api.xiaomimimo.com/v1", "api-key", "mimo-x")
    client = httpx.Client(transport=httpx.MockTransport(fake))
    return AgentRunner(
        definition, profile, KEY, tools, log_dir=tmp_path / "runs", http_client=client, **kwargs
    )


def _definition(**changes):
    text = VALID
    for old, new in changes.items():
        text = text.replace(old, new)
    return parse_definition(text, stem="demo")


def test_normal_run_with_receipts_reasoning_and_log(tools, tmp_path):
    fake = FakeModel(
        [
            {
                "role": "assistant",
                "content": None,
                "reasoning_content": "先查 KYB",
                "tool_calls": [_call("search_library", {"company": "KYB"})],
            },
            {
                "role": "assistant",
                "content": "## 结论\n- KYB 有先导阀方案 [CN120000001A]\n- 凭记忆 [US99999999A1]",
            },
        ]
    )
    result = _runner(_definition(), tools, fake, tmp_path).run("KYB 的阀？")
    assert result.status == "completed"
    assert result.receipts == ("CN120000001A",)
    assert result.check.flagged_count == 1
    # MiMo profile: api-key header, never Authorization.
    headers = fake.requests[0]["headers"]
    assert headers["api-key"] == KEY and "authorization" not in headers
    # The assistant turn with reasoning_content is sent back unchanged.
    second = fake.requests[1]["json"]["messages"]
    assert second[2]["reasoning_content"] == "先查 KYB"
    assert second[3]["role"] == "tool" and "CN120000001A" in second[3]["content"]
    # Tools offered are exactly the whitelist.
    offered = [t["function"]["name"] for t in fake.requests[0]["json"]["tools"]]
    assert offered == ["search_library", "get_publication"]
    log_text = result.log_path.read_text(encoding="utf-8")
    assert KEY not in log_text
    assert "先查 KYB" in log_text


def test_tool_outside_whitelist_is_refused(tools, tmp_path):
    fake = FakeModel(
        [
            {"role": "assistant", "tool_calls": [_call("run_landscape", {})]},
            {"role": "assistant", "content": "## 局限与待确认\n- 无数据"},
        ]
    )
    result = _runner(_definition(), tools, fake, tmp_path).run("q")
    tool_message = fake.requests[1]["json"]["messages"][3]
    assert "白名单" in tool_message["content"]
    assert result.receipts == ()


def test_step_limit_forces_final_answer_without_tools(tools, tmp_path):
    loop = {"role": "assistant", "tool_calls": [_call("search_library", {})]}
    fake = FakeModel([loop, loop, {"role": "assistant", "content": "## 局限与待确认\n- 不完整"}])
    result = _runner(
        _definition(**{"max_steps = 4": "max_steps = 2"}), tools, fake, tmp_path
    ).run("q")
    assert result.status == "step_limit"
    assert result.steps == 2
    assert "tools" not in fake.requests[-1]["json"]


def test_search_terms_checkpoint_pauses_and_uses_edited_terms(tools, tmp_path):
    seen = []

    def on_checkpoint(kind, payload):
        seen.append((kind, payload))
        if kind == "final":
            return CheckpointDecision(True, payload)
        return CheckpointDecision(True, "先导阀\npilot valve")

    fake = FakeModel(
        [
            {"role": "assistant", "tool_calls": [_call("search_library", {"text": "阀"})]},
            {
                "role": "assistant",
                "tool_calls": [_call("propose_search_terms", {"terms": ["阀"]}, "c2")],
            },
            {
                "role": "assistant",
                "tool_calls": [_call("search_library", {"text": "先导阀"}, "c3")],
            },
            {"role": "assistant", "content": "- 先导阀方案 [CN120000001A]"},
        ]
    )
    definition = _definition(
        **{"checkpoints = []": 'checkpoints = ["confirm_search_terms", "confirm_before_final"]'}
    )
    result = _runner(definition, tools, fake, tmp_path, on_checkpoint=on_checkpoint).run("q")
    assert "propose_search_terms" in fake.requests[1]["json"]["messages"][3]["content"]
    assert json.loads(fake.requests[2]["json"]["messages"][5]["content"]) == {
        "approved_terms": ["先导阀", "pilot valve"]
    }
    assert [kind for kind, _ in seen] == ["search_terms", "final"]
    assert result.status == "completed"
    assert result.check.flagged_count == 0


def test_cancel_at_checkpoint_and_cancel_event(tools, tmp_path):
    fake = FakeModel(
        [{"role": "assistant", "tool_calls": [_call("propose_search_terms", {"terms": ["x"]})]}]
    )
    definition = _definition(**{"checkpoints = []": 'checkpoints = ["confirm_search_terms"]'})
    result = _runner(
        definition, tools, fake, tmp_path, on_checkpoint=lambda k, p: CheckpointDecision(False)
    ).run("q")
    assert result.status == "cancelled"
    event = threading.Event()
    event.set()
    cancelled = _runner(_definition(), tools, FakeModel([]), tmp_path, cancel_event=event).run("q")
    assert cancelled.status == "cancelled"


def test_model_http_error_keeps_partial_log_without_key(tools, tmp_path):
    fake = FakeModel([{"role": "assistant", "tool_calls": [_call("search_library", {})]}, 401])
    result = _runner(_definition(), tools, fake, tmp_path).run("q")
    assert result.status == "error"
    assert "401" in result.error and KEY not in result.error
    assert "API Key 无效" in result.error and "MiMo" in result.error
    log_text = result.log_path.read_text(encoding="utf-8")
    assert KEY not in log_text and '"search_library"' in log_text


def test_windows_ai_secret_store_uses_one_credential_per_profile(monkeypatch):
    from app.desktop import credentials

    vault = {}
    monkeypatch.setattr(credentials, "_windows_read_generic", lambda target: vault.get(target))
    def write(target, user, secret):
        vault[target] = (user, secret)

    monkeypatch.setattr(credentials, "_windows_write_generic", write)
    monkeypatch.setattr(credentials, "_windows_delete_generic", lambda t: vault.pop(t, None))
    store = credentials.WindowsAISecretStore()
    store.set("小米 MiMo", f" {KEY} ")
    assert vault == {"PatentIntelligenceWorkbench/AI/小米 MiMo": ("小米 MiMo", KEY)}
    assert store.get("小米 MiMo") == KEY
    with pytest.raises(ValueError):
        store.set("x", " ")
    store.delete("小米 MiMo")
    assert store.get("小米 MiMo") is None


def test_mimo_token_plan_presets_and_key_mismatch_hint():
    presets = {p.preset_id: p for p in load_presets()}
    assert presets["mimo_tp_cn"].base_url == "https://token-plan-cn.xiaomimimo.com/v1"
    assert presets["mimo_tp_cn"].auth_style == "api-key"
    assert "Token Plan" in key_mismatch_hint(presets["mimo"].base_url, "tp-abc")
    assert "按量付费" in key_mismatch_hint(presets["mimo_tp_cn"].base_url, "sk-abc")
    assert key_mismatch_hint(presets["mimo_tp_cn"].base_url, "tp-abc") == ""
    assert key_mismatch_hint(presets["deepseek"].base_url, "sk-abc") == ""


def test_deepseek_preset_suggests_the_models_its_api_accepts():
    presets = {p.preset_id: p for p in load_presets()}
    assert presets["deepseek"].suggested_models == ("deepseek-flash", "deepseek-v4-pro")


def test_chat_completions_url_accepts_base_or_full_url():
    from app.core.openai_compat import chat_completions_url

    full = "https://api.deepseek.com/v1/chat/completions"
    assert chat_completions_url("https://api.deepseek.com/v1") == full
    assert chat_completions_url("https://api.deepseek.com/v1/") == full
    assert chat_completions_url(full) == full


def test_report_interpretation_accepts_base_url_and_explains_401(monkeypatch):
    from datetime import UTC, datetime

    from app.intelligence import ai_interpreter
    from app.intelligence.analysis import AnalysisReport

    seen = {}

    def fake_post(url, **kwargs):
        seen["url"] = url
        request = httpx.Request("POST", url)
        return httpx.Response(401, text='{"error":"bad key"}', request=request)

    monkeypatch.setattr(ai_interpreter.httpx, "post", fake_post)
    settings = ai_interpreter.AIInterpretationSettings(
        endpoint="https://api.deepseek.com/v1", model="deepseek-flash", api_key=KEY, consent=True
    )
    report = AnalysisReport("t", "landscape", "s", datetime.now(UTC), (), (), ())
    with pytest.raises(ai_interpreter.AIInterpretationError, match="API Key 无效"):
        ai_interpreter.OpenAICompatibleInterpreter(settings).interpret(report)
    assert seen["url"] == "https://api.deepseek.com/v1/chat/completions"


def test_fetch_models_uses_get_models_with_the_profile_auth_style():
    from app.agents.model_profiles import fetch_models

    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        return httpx.Response(200, json={"data": [{"id": "b-model"}, {"id": "a-model"}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    models = fetch_models("https://api.xiaomimimo.com/v1", "api-key", KEY, client=client)
    assert models == ("a-model", "b-model")
    assert seen["url"] == "https://api.xiaomimimo.com/v1/models"
    assert seen["headers"]["api-key"] == KEY

    failing = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401)))
    with pytest.raises(ValueError, match="API Key 无效"):
        fetch_models("https://api.deepseek.com/v1", "bearer", KEY, client=failing)


def test_report_interpretation_sends_api_key_header_for_mimo(monkeypatch):
    from datetime import UTC, datetime

    from app.intelligence import ai_interpreter
    from app.intelligence.analysis import AnalysisReport

    seen = {}

    def fake_post(url, *, headers, json, timeout):
        seen["headers"] = headers
        request = httpx.Request("POST", url)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "解读"}}]}, request=request
        )

    monkeypatch.setattr(ai_interpreter.httpx, "post", fake_post)
    settings = ai_interpreter.AIInterpretationSettings(
        endpoint="https://api.xiaomimimo.com/v1",
        model="mimo-v2.6-flash",
        api_key=KEY,
        consent=True,
        auth_style="api-key",
    )
    report = AnalysisReport("t", "landscape", "s", datetime.now(UTC), (), (), ())
    assert ai_interpreter.OpenAICompatibleInterpreter(settings).interpret(report) == "解读"
    assert seen["headers"] == {"api-key": KEY}
