from __future__ import annotations

import json

import shintoki.cli as cli
from shintoki.cli import run


def test_api_serve_runs_uvicorn(monkeypatch) -> None:
    called = {}

    def fake_find_spec(name: str):
        return object()

    def fake_uvicorn_run(app: str, **kwargs) -> None:
        called["app"] = app
        called["kwargs"] = kwargs

    class DummyUvicorn:
        @staticmethod
        def run(app: str, **kwargs) -> None:
            fake_uvicorn_run(app, **kwargs)

    monkeypatch.setattr(cli.importlib.util, "find_spec", fake_find_spec)
    monkeypatch.setattr(cli, "uvicorn", DummyUvicorn(), raising=False)
    monkeypatch.setitem(__import__("sys").modules, "uvicorn", DummyUvicorn())
    code = run(["api", "serve", "--host", "127.0.0.1", "--port", "8012"])

    assert code == 0
    assert called["app"] == "shintoki.api.http:app"
    assert called["kwargs"]["host"] == "127.0.0.1"
    assert called["kwargs"]["port"] == 8012


def test_api_serve_missing_dependency_returns_code_2(capsys, monkeypatch) -> None:
    def fake_find_spec(name: str):
        if name == "uvicorn":
            return None
        return object()

    monkeypatch.setattr(cli.importlib.util, "find_spec", fake_find_spec)
    code = run(["--format", "json", "api", "serve"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 2
    assert payload["ok"] is False
    assert payload["issues"][0]["code"] == "missing_api_dependencies"
