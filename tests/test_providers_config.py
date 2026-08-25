from astra.agents.adapter import AgentAdapterLayer, build_providers_from_config
from astra.agents.models import AgentRequest, ExecutionStatus
from astra.agents.providers import CodexProvider, ManualProvider
from astra.ir.models import IRContextPack


class _FakeConfig:
    def __init__(self, providers):
        self._providers = providers

    def get(self, key, default=None):
        if key == "agent.providers":
            return self._providers
        return default


def _pack() -> IRContextPack:
    return IRContextPack(task_summary="t", nodes=(), edges=(), required_files=(), hidden_risks=())


def test_default_build_is_generic_only():
    providers = build_providers_from_config(None)
    assert [p.name for p in providers] == ["generic"]


def test_codex_skipped_when_unavailable(monkeypatch):
    monkeypatch.setattr(CodexProvider, "is_available", staticmethod(lambda: False))
    providers = build_providers_from_config(_FakeConfig(["codex", "manual"]))
    assert [p.name for p in providers] == ["manual"]


def test_manual_provider_with_callback_executes():
    provider = ManualProvider(response_callback=lambda req: f"done: {req.task_description}")
    request = AgentRequest(task_description="fix bug", context_payload={})
    response = provider.execute(request)
    assert response.execution_status == ExecutionStatus.COMPLETED
    assert response.content == "done: fix bug"


def test_manual_provider_without_callback_returns_brief():
    provider = ManualProvider()
    response = provider.execute(AgentRequest(task_description="do thing", context_payload={"nodes": []}))
    assert response.execution_status == ExecutionStatus.PENDING
    assert "Task brief" in response.content


def test_adapter_uses_config():
    layer = AgentAdapterLayer(providers=[ManualProvider(response_callback=lambda req: "human ok")])
    pack = _pack()
    response = layer.execute("analyze", pack)
    assert response.content == "human ok"
    assert response.provider == "manual"


def test_codex_missing_binary_fails_gracefully(monkeypatch):
    monkeypatch.setattr(CodexProvider, "is_available", staticmethod(lambda: False))
    codex = CodexProvider()
    response = codex.execute(AgentRequest(task_description="x", context_payload={}))
    assert response.execution_status == ExecutionStatus.FAILED
    assert "codex-binary-missing" in response.errors
