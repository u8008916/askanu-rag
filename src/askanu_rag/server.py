"""Cloud Run-compatible production process entrypoint."""

import uvicorn

from askanu_rag.config import Settings


def run() -> None:
    """Start the configured app on Cloud Run's process environment."""

    settings = Settings.from_environment()
    uvicorn.run(
        "askanu_rag.main:create_configured_app",
        factory=True,
        host="0.0.0.0",
        port=settings.port,
        log_level=settings.log_level,
        proxy_headers=True,
        forwarded_allow_ips="*",
        access_log=False,
        server_header=False,
        date_header=False,
    )


if __name__ == "__main__":
    run()
