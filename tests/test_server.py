from unittest.mock import MagicMock

from askanu_rag.config import Settings
from askanu_rag.server import run


def test_production_server_uses_cloud_run_port_and_safe_defaults(monkeypatch) -> None:
    monkeypatch.setattr(
        Settings,
        "from_environment",
        classmethod(lambda cls: Settings(environment="production", port=9090)),
    )
    start = MagicMock()
    monkeypatch.setattr("askanu_rag.server.uvicorn.run", start)

    run()

    start.assert_called_once_with(
        "askanu_rag.main:create_configured_app",
        factory=True,
        host="0.0.0.0",
        port=9090,
        log_level="info",
        proxy_headers=True,
        forwarded_allow_ips="*",
        access_log=False,
        server_header=False,
        date_header=False,
    )


def test_server_uses_local_default_port_when_port_is_absent(monkeypatch) -> None:
    monkeypatch.setattr(
        Settings,
        "from_environment",
        classmethod(lambda cls: Settings()),
    )
    start = MagicMock()
    monkeypatch.setattr("askanu_rag.server.uvicorn.run", start)

    run()

    assert start.call_args.kwargs["port"] == 8081
