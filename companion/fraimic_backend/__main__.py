"""Run the private listener. SIGHUP reloads TLS without cancelling active jobs."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import ssl
from pathlib import Path

from aiohttp import web

from .model import Device, origin
from .server import Backend, create_app, create_bridge_app


def reload_certificate(context: ssl.SSLContext, cert: str, key: str) -> None:
    """Atomically select a fresh context for subsequent TLS handshakes."""
    candidate = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    candidate.minimum_version = context.minimum_version
    candidate.load_cert_chain(cert, key)

    def select_certificate(
        connection: ssl.SSLObject | ssl.SSLSocket, _hostname: str | None, _initial: ssl.SSLContext,
    ) -> None:
        connection.context = candidate

    # Loading into the old context retains certificates of other key types.
    # A fresh context also makes EC-to-RSA rollback replace the selected leaf.
    context.sni_callback = select_certificate


async def run(config_path: Path) -> None:
    config = json.loads(config_path.read_text())
    public_url = origin(config["public_url"], https=True)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    cert, key = config["certificate"], config["private_key"]
    context.load_cert_chain(cert, key)
    backend = Backend([Device(**d) for d in config["devices"]], public_url,
                      Path(config.get("database", "/data/backend.sqlite3")))
    runner = web.AppRunner(create_app(backend), access_log=None, shutdown_timeout=10,
                           handler_cancellation=True)
    await runner.setup()
    bridge = web.AppRunner(create_bridge_app(backend), access_log=None,
                           shutdown_timeout=10, handler_cancellation=True)
    site = web.TCPSite(runner, config.get("bind", "127.0.0.1"),
                       config.get("port", 8443), ssl_context=context)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    def reload_tls() -> None:
        try:
            reload_certificate(context, cert, key)
            logging.getLogger(__name__).info("TLS certificate reloaded")
        except (OSError, ssl.SSLError):
            logging.getLogger(__name__).error("TLS reload failed; check private certificate files")

    loop.add_signal_handler(signal.SIGHUP, reload_tls)
    try:
        await bridge.setup()
        await web.TCPSite(bridge, config.get("bridge_bind", "127.0.0.1"),
                          config.get("bridge_port", 8080)).start()
        await site.start()
        await stop.wait()
    finally:
        await bridge.cleanup()
        await runner.cleanup()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(run(args.config))


if __name__ == "__main__":
    main()
