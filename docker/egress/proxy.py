"""Minimal provider-scoped HTTPS CONNECT proxy; no TLS interception or content logging."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import socket
from datetime import UTC, datetime

MAX_HEADER = 8192
BUFFER = 65536
ALLOWED_HOST = os.environ["HARNESSLAB_ALLOWED_CONNECT_HOST"].casefold().rstrip(".")
ALLOWED_PORT = int(os.environ.get("HARNESSLAB_ALLOWED_CONNECT_PORT", "443"))


def now() -> str:
    return datetime.now(UTC).isoformat()


def safe_log(host: str, port: int, start: str, up: int, down: int, result: str) -> None:
    public_host = ALLOWED_HOST if host == ALLOWED_HOST else "UNDECLARED"
    print(
        json.dumps(
            {
                "hostname": public_host,
                "port": port,
                "started_at": start,
                "ended_at": now(),
                "bytes_upstream": up,
                "bytes_downstream": down,
                "result": result,
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        flush=True,
    )


async def resolve_global(host: str) -> str:
    loop = asyncio.get_running_loop()
    records = await loop.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    addresses = {record[4][0] for record in records}
    if not addresses:
        raise ValueError("provider DNS returned no addresses")
    parsed = tuple(ipaddress.ip_address(value) for value in addresses)
    if any(not value.is_global or value.is_loopback or value.is_link_local for value in parsed):
        raise ValueError("provider DNS resolved outside global address space")
    return str(sorted(parsed, key=lambda value: (value.version, int(value)))[0])


async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> int:
    total = 0
    try:
        while data := await reader.read(BUFFER):
            total += len(data)
            writer.write(data)
            await writer.drain()
    finally:
        writer.close()
    return total


async def handle(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter) -> None:
    started = now()
    host = "invalid"
    port = 0
    upstream = downstream = 0
    result = "denied"
    try:
        header = await client_reader.readuntil(b"\r\n\r\n")
        if len(header) > MAX_HEADER:
            raise ValueError("CONNECT header too large")
        request_line = header.split(b"\r\n", 1)[0].decode("ascii", errors="strict")
        method, authority, version = request_line.split(" ")
        if method != "CONNECT" or version not in {"HTTP/1.0", "HTTP/1.1"}:
            raise ValueError("only HTTPS CONNECT is supported")
        host, port_raw = authority.rsplit(":", 1)
        host = host.casefold().rstrip(".")
        port = int(port_raw)
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError("IP literals are forbidden")
        if host != ALLOWED_HOST or port != ALLOWED_PORT or port != 443:
            raise ValueError("undeclared CONNECT destination")
        target_ip = await resolve_global(host)
        upstream_reader, upstream_writer = await asyncio.open_connection(target_ip, port)
        client_writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await client_writer.drain()
        upstream, downstream = await asyncio.gather(
            pipe(client_reader, upstream_writer), pipe(upstream_reader, client_writer)
        )
        result = "allowed"
    except Exception:
        if not client_writer.is_closing():
            client_writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
            await client_writer.drain()
        client_writer.close()
    finally:
        safe_log(host, port, started, upstream, downstream, result)


async def main() -> None:
    server = await asyncio.start_server(handle, "0.0.0.0", 8080)
    async with server:
        await server.serve_forever()


asyncio.run(main())
