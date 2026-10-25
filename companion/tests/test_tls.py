"""Host-only TLS rotation. Synthetic certs establish no physical frame trust."""

import asyncio
import hashlib
import ssl
import subprocess

import pytest

from fraimic_backend.__main__ import reload_certificate


@pytest.mark.parametrize(('first_kind', 'second_kind'), [('ec', 'ec'), ('rsa', 'ec'), ('ec', 'rsa')])
async def test_fresh_key_rotation_and_rejected_pair_preserve_active_connection(tmp_path, first_kind, second_kind):
    pairs = []
    for number, kind in enumerate((first_kind, second_kind), 1):
        cert, key = tmp_path / f"cert{number}.pem", tmp_path / f"key{number}.pem"
        key_args = ['-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:prime256v1'] if kind == 'ec' else ['-newkey', 'rsa:2048']
        await asyncio.to_thread(subprocess.run, [
            "openssl", "req", "-x509", *key_args,
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

    writers = []

    async def connect():
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection("127.0.0.1", port, ssl=trust), timeout=3,
        )
        writers.append(writer)
        fingerprint = hashlib.sha256(writer.get_extra_info("ssl_object").getpeercert(binary_form=True)).hexdigest()
        return reader, writer, fingerprint

    try:
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
        reload_certificate(server_tls, *pairs[0])
        fourth_reader, fourth_writer, fourth_fingerprint = await connect()
        assert fourth_fingerprint == first_fingerprint
        second_writer.write(b'active after rollback')
        await second_writer.drain()
        assert await second_reader.readexactly(21) == b'active after rollback'
    finally:
        for writer in writers:
            writer.close()
        await asyncio.gather(*(asyncio.wait_for(writer.wait_closed(), 2) for writer in writers), return_exceptions=True)
        server.close()
        server.abort_clients()
        await server.wait_closed()
