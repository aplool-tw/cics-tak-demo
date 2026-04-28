"""TAK Server stub for PoC development.

Accepts TLS connections on :8089 (the canonical TAK Server CoT input port)
and logs every newline-delimited CoT XML message to stdout. Optionally writes
each event to a JSONL file for later replay/inspection.

This is NOT a real TAK Server. It is a self-contained drop-in for environments
where the official TAK Server image (which requires a TAK.gov account) is not
available. It covers the only behavior the CoT Gateway depends on: accepting
TLS connections + ingesting NDJSON-framed XML.

For production, swap this stub for the real TAK Server image as documented in
infra/tak-server/README.md.

Usage:
    python3 stub_server.py \
        --host 0.0.0.0 --port 8089 \
        --cert /certs/takserver.crt --key /certs/takserver.key \
        --ca   /certs/ca.crt \
        --output-dir /var/log/tak-stub
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import ssl
import sys
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("tak-stub")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


class CotStub:
    def __init__(
        self,
        host: str,
        port: int,
        ssl_ctx: ssl.SSLContext | None,
        output_dir: Path | None,
    ) -> None:
        self.host = host
        self.port = port
        self.ssl_ctx = ssl_ctx
        self.output_dir = output_dir
        self.connections = 0
        self.messages = 0
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)

    async def handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer = writer.get_extra_info("peername")
        cipher = writer.get_extra_info("cipher")
        peer_cert = writer.get_extra_info("peercert")
        self.connections += 1
        client_id = f"{peer[0]}:{peer[1]}" if peer else "unknown"
        logger.info(
            json.dumps(
                {
                    "event": "client_connected",
                    "peer": client_id,
                    "cipher": cipher[0] if cipher else None,
                    "client_cert_subject": (
                        peer_cert.get("subject") if peer_cert else None
                    ),
                    "timestamp": _now_iso(),
                }
            )
        )

        try:
            while not reader.at_eof():
                line = await reader.readline()
                if not line:
                    break
                payload = line.decode("utf-8", errors="replace").rstrip("\n")
                if not payload.strip():
                    continue
                self.messages += 1
                logger.info(
                    json.dumps(
                        {
                            "event": "cot_received",
                            "peer": client_id,
                            "bytes": len(line),
                            "payload": payload,
                            "timestamp": _now_iso(),
                        }
                    )
                )
                if self.output_dir:
                    out = self.output_dir / "cot.ndjson"
                    out.open("a", encoding="utf-8").write(
                        json.dumps(
                            {
                                "peer": client_id,
                                "received_at": _now_iso(),
                                "payload": payload,
                            }
                        )
                        + "\n"
                    )
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        except ssl.SSLError as exc:
            logger.warning(
                json.dumps(
                    {
                        "event": "ssl_error",
                        "peer": client_id,
                        "error": str(exc),
                        "timestamp": _now_iso(),
                    }
                )
            )
        finally:
            logger.info(
                json.dumps(
                    {
                        "event": "client_disconnected",
                        "peer": client_id,
                        "timestamp": _now_iso(),
                    }
                )
            )
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def serve_forever(self) -> None:
        server = await asyncio.start_server(
            self.handle, host=self.host, port=self.port, ssl=self.ssl_ctx
        )
        scheme = "TLS" if self.ssl_ctx else "PLAIN"
        logger.info(
            json.dumps(
                {
                    "event": "stub_listening",
                    "host": self.host,
                    "port": self.port,
                    "scheme": scheme,
                    "timestamp": _now_iso(),
                }
            )
        )
        async with server:
            await server.serve_forever()


def _build_ssl_context(
    cert: str, key: str, ca: str | None, require_client_cert: bool
) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=cert, keyfile=key)
    if ca:
        ctx.load_verify_locations(cafile=ca)
        ctx.verify_mode = (
            ssl.CERT_REQUIRED if require_client_cert else ssl.CERT_OPTIONAL
        )
    else:
        ctx.verify_mode = ssl.CERT_NONE
    ctx.check_hostname = False
    return ctx


def main() -> int:
    p = argparse.ArgumentParser(prog="tak-stub")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8089)
    p.add_argument("--cert", help="Server cert PEM")
    p.add_argument("--key", help="Server key PEM")
    p.add_argument("--ca", help="CA bundle PEM (enables client cert verification)")
    p.add_argument(
        "--require-client-cert",
        action="store_true",
        help="Require valid client certificate (mTLS); ignored if --ca not set",
    )
    p.add_argument(
        "--no-ssl",
        action="store_true",
        help="Run plaintext (development only; --cert/--key ignored)",
    )
    p.add_argument(
        "--output-dir", help="Optional directory; appends each CoT to cot.ndjson"
    )
    args = p.parse_args()

    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(message)s",
        stream=sys.stdout,
    )

    ssl_ctx: ssl.SSLContext | None
    if args.no_ssl:
        ssl_ctx = None
    else:
        if not (args.cert and args.key):
            print("--cert and --key are required unless --no-ssl is set", file=sys.stderr)
            return 2
        ssl_ctx = _build_ssl_context(
            args.cert, args.key, args.ca, args.require_client_cert
        )

    output = Path(args.output_dir) if args.output_dir else None
    stub = CotStub(args.host, args.port, ssl_ctx, output)

    loop = asyncio.new_event_loop()

    def _shutdown() -> None:
        logger.info(
            json.dumps({"event": "shutdown_requested", "timestamp": _now_iso()})
        )
        for task in asyncio.all_tasks(loop):
            task.cancel()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _shutdown)
        except NotImplementedError:
            pass

    try:
        loop.run_until_complete(stub.serve_forever())
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        loop.close()
        logger.info(
            json.dumps(
                {
                    "event": "shutdown_complete",
                    "connections": stub.connections,
                    "messages": stub.messages,
                    "timestamp": _now_iso(),
                }
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
