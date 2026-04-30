#!/usr/bin/env python3
"""Minimal TCP broadcast relay for CoT XML demo.

Listens on HOST:PORT and broadcasts any received data to all other
connected clients. This allows cot-gateway (publisher) and
tak-client-sim (subscriber) to exchange CoT XML without a real TAK Server.

Usage:
    python3 scripts/tak_relay.py [--host HOST] [--port PORT]

Default: 127.0.0.1:8089 (matches cot-gateway tak_server config)
"""
from __future__ import annotations

import argparse
import asyncio
import sys

_clients: set[asyncio.StreamWriter] = set()


async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    peer = writer.get_extra_info("peername")
    print(f"[relay] connected  : {peer}", flush=True)
    _clients.add(writer)
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            dead: set[asyncio.StreamWriter] = set()
            for c in list(_clients):
                if c is writer:
                    continue
                try:
                    c.write(data)
                    await c.drain()
                except OSError:
                    dead.add(c)
            _clients.difference_update(dead)
    finally:
        print(f"[relay] disconnected: {peer}", flush=True)
        _clients.discard(writer)
        try:
            writer.close()
            await writer.wait_closed()
        except OSError:
            pass


async def _main(host: str, port: int) -> None:
    server = await asyncio.start_server(_handle, host, port)
    addr = server.sockets[0].getsockname()
    print(f"[relay] listening on {addr[0]}:{addr[1]} — press Ctrl+C to stop", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Minimal TCP broadcast relay for CoT XML")
    ap.add_argument("--host", default="127.0.0.1", help="Listen address (default: 127.0.0.1)")
    ap.add_argument("--port", type=int, default=8089, help="Listen port (default: 8089)")
    args = ap.parse_args()
    try:
        asyncio.run(_main(args.host, args.port))
    except KeyboardInterrupt:
        sys.exit(0)
