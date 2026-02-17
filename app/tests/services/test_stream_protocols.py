from app.services.stream_protocols import (
    build_ingest_url_for_protocol,
    is_supported_ingest_protocol,
    resolve_stream_port,
)


def test_stream_protocols_support_srt_ingest_url_and_port_defaults() -> None:
    ingest_url = build_ingest_url_for_protocol(
        "srt",
        host="127.0.0.1",
        stream_name="surgwaze/v1/ABC123/stream",
    )
    assert ingest_url == "srt://127.0.0.1:9000?streamid=publish:surgwaze/v1/ABC123/stream"

    ingest_url_with_pass = build_ingest_url_for_protocol(
        "srt",
        host="127.0.0.1",
        stream_name="surgwaze/v1/ABC123/stream",
        srt_passphrase="secret123",
        srt_pbkeylen=32,
    )
    assert ingest_url_with_pass == (
        "srt://127.0.0.1:9000?"
        "streamid=publish:surgwaze/v1/ABC123/stream&passphrase=secret123&pbkeylen=32"
    )

    port = resolve_stream_port("srt://127.0.0.1/surgwaze/v1/device/stream")
    assert port == 9000


def test_stream_protocols_supported_ingest_set() -> None:
    assert is_supported_ingest_protocol("rtmp") is True
    assert is_supported_ingest_protocol("srt") is True
    assert is_supported_ingest_protocol("udp") is False
