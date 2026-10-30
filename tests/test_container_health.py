"""Exercise the API probe selected by the shipped Dockerfile."""

from pathlib import Path
import re
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
import pytest

from api import main


@pytest.mark.parametrize("provider_available", [True, False])
def test_container_probe_never_calls_provider(monkeypatch, provider_available):
    dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text()
    api_stage = dockerfile.split("FROM base AS api", 1)[1].split(
        "FROM base AS frontend", 1
    )[0]
    probe = re.search(r"CMD curl -f (http://localhost:8000/\S*)", api_stage)
    assert probe, "API container must declare an HTTP health probe"
    model_client = MagicMock()
    if not provider_available:
        model_client.messages.create.side_effect = RuntimeError("Provider unavailable")
    get_client = MagicMock(return_value=model_client)
    monkeypatch.setattr(main, "get_client", get_client)

    with TestClient(main.app) as client:
        for _ in range(3):
            response = client.get(probe.group(1))
            assert response.status_code == 200
    get_client.assert_not_called()
    model_client.messages.create.assert_not_called()


@pytest.mark.parametrize("provider_available", [True, False])
def test_explicit_provider_diagnostics_remain_available(
    monkeypatch, provider_available
):
    model_client = MagicMock()
    if not provider_available:
        model_client.messages.create.side_effect = RuntimeError("Provider unavailable")
    monkeypatch.setattr(main, "get_client", lambda: model_client)
    with TestClient(main.app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["anthropic_connected"] is provider_available
    assert response.json()["status"] == (
        "healthy" if provider_available else "degraded"
    )
    model_client.messages.create.assert_called_once()
