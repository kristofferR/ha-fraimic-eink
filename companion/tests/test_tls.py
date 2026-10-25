"""Host-only TLS rotation. Synthetic certs establish no physical frame trust."""

import asyncio
import hashlib
import ssl
import subprocess

import pytest

from fraimic_backend.__main__ import reload_certificate


async def test_fresh_key_rotation_and_rejected_pair_preserve_active_connection(tmp_path):
    pairs = []
    for number in (1, 2):
        cert, key = tmp_path / f"cert{number}.pem", tmp_path / f"key{number}.pem"
        await asyncio.to_thread(subprocess.run, [
            "openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1",
            "-keyout", str(key), "-out", str(cert), "-sha256", "-days", "1", "-nodes",
            "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1",
        ], check=True, capture_output=True)
        pairs.append((str(cert), str(key)))
    server_tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_tls.minimum_version = ssl.TLSVersion.TLSv1_2
    reload_certificate(server_tls, *pairs[0])
    trust = ssl.create_default_context()
    for cert, _ in pairs:
        trust.load_verify_locations(cert)
    trust.maximum_version = ssl.TLSVersion.TLSv1_2
    finished = []

    async def echo(reader, writer):
        try:
            while data := await reader.read(128):
                writer.write(data)
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
            finished.append(True)

    server = await asyncio.start_server(echo, "127.0.0.1", 0, ssl=server_tls)
    port = server.sockets[0].getsockname()[1]

    async def connect():
        reader, writer = await asyncio.open_connection("127.0.0.1", port, ssl=trust)
        fingerprint = hashlib.sha256(writer.get_extra_info("ssl_object").getpeercert(binary_form=True)).hexdigest()
        return reader, writer, fingerprint

    async with server:
        first_reader, first_writer, first_fingerprint = await connect()
        reload_certificate(server_tls, *pairs[1])
        second_reader, second_writer, second_fingerprint = await connect()
        assert first_fingerprint != second_fingerprint
        first_writer.write(b"active job")
        await first_writer.drain()
        assert await first_reader.readexactly(10) == b"active job"
        with pytest.raises(ssl.SSLError):
            reload_certificate(server_tls, pairs[0][0], pairs[1][1])
        third_reader, third_writer, third_fingerprint = await connect()
        assert third_fingerprint == second_fingerprint
        for writer in (first_writer, second_writer, third_writer):
            writer.close()
            await writer.wait_closed()
