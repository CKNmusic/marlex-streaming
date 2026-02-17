from datetime import datetime, timedelta, timezone

from app.services import ingest_stream_profile as profile_service


def test_parse_stream_profile_extracts_codecs_resolution_and_rates() -> None:
    payload = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h265",
                "width": 3840,
                "height": 2160,
                "avg_frame_rate": "30000/1001",
                "bit_rate": "12000000",
            },
            {
                "codec_type": "audio",
                "codec_name": "aac",
                "channels": "2",
                "sample_rate": "48000",
                "bit_rate": "128000",
            },
        ]
    }

    parsed = profile_service.parse_stream_profile(payload)

    assert parsed is not None
    assert parsed["video_codec"] == "h265"
    assert parsed["audio_codec"] == "aac"
    assert parsed["resolution"] == "3840x2160"
    assert parsed["fps"] == 29.97
    assert parsed["video_bitrate_bps"] == 12000000
    assert parsed["audio_bitrate_bps"] == 128000
    assert parsed["audio_channels"] == 2
    assert parsed["audio_sample_rate"] == 48000


def test_parse_stream_profile_returns_none_for_invalid_payload() -> None:
    assert profile_service.parse_stream_profile({}) is None
    assert profile_service.parse_stream_profile({"streams": "invalid"}) is None


def test_build_probe_stream_url_converts_srt_publish_streamid_to_read() -> None:
    source = "srt://192.168.10.19:9000?streamid=publish:surgwaze/v1/1F0929AC30C7/stream"
    probe = profile_service.build_probe_stream_url(source)
    assert probe == "srt://192.168.10.19:9000?streamid=read:surgwaze/v1/1F0929AC30C7/stream"


def test_stream_profile_cache_expires(monkeypatch) -> None:
    profile_service.clear_stream_profile_cache()
    profile_service.remember_stream_profile(
        "1f0929ac30c7",
        {"resolution": "1920x1080", "video_codec": "h264"},
    )

    cached = profile_service.get_cached_stream_profile("1F0929AC30C7", max_age_sec=60)
    assert cached is not None
    assert cached["resolution"] == "1920x1080"
    assert cached["video_codec"] == "h264"

    now = datetime.now(timezone.utc)
    monkeypatch.setattr(profile_service, "_now_utc", lambda: now + timedelta(seconds=120))
    assert profile_service.get_cached_stream_profile("1F0929AC30C7", max_age_sec=60) is None
