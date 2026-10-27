import pytest
from unittest.mock import AsyncMock, patch
from base_api import config
from missav_api import api


@pytest.mark.asyncio
async def test_default_client_does_not_change_global_impersonation():
    original = config.impersonation
    client = api.Client()
    try:
        assert config.impersonation == original
        assert client.core.configuration is not config
    finally:
        await client.core.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, -1])
async def test_invalid_search_count_does_not_request(count):
    client = object.__new__(api.Client)
    client.core = object()
    with patch.object(api, "_post", new_callable=AsyncMock) as post:
        with pytest.raises(ValueError):
            async for _ in client.search("test", video_count=count):
                pass
        post.assert_not_awaited()


@pytest.mark.asyncio
async def test_cli_closes_session_and_reports_false_download(capsys, tmp_path):
    from unittest.mock import AsyncMock, MagicMock
    from base_api import BaseCore
    from base_api.modules.config import RuntimeConfig

    core = BaseCore(RuntimeConfig())
    video = MagicMock(title="Example", length="10", url="https://example.com/video")
    video.load_fields = AsyncMock()
    video.download = AsyncMock(return_value=False)
    client = MagicMock()
    client.get_video = AsyncMock(return_value=video)
    with (
        patch.object(api, "BaseCore", return_value=core),
        patch.object(api, "Client", return_value=client),
    ):
        await api.run_main(
            ["--download", "https://example.com/video", "--output", str(tmp_path)]
        )
    assert core.session is None
    output = capsys.readouterr().out
    assert "Download complete:" not in output
    assert "Done ->" not in output
    assert "Download did not complete" in output


@pytest.mark.parametrize("path", ["/test/", "/test/?count=2"])
def test_frontend_request_signing_preserves_query(path):
    import hashlib, hmac
    from urllib.parse import parse_qs, urlsplit

    with patch.object(api.time, "time", return_value=1234567890):
        signed = api._sign_path(path, "public-token")
    unsigned, signature = signed.rsplit("&frontend_sign=", 1)
    assert (
        signature
        == hmac.new(b"public-token", unsigned.encode(), hashlib.sha1).hexdigest()
    )
    assert parse_qs(urlsplit(signed).query)["frontend_timestamp"] == ["1234567890"]


@pytest.mark.asyncio
async def test_search_stream_closes_on_early_stop():
    from types import SimpleNamespace

    closed = []

    async def source():
        try:
            yield SimpleNamespace(succeeded=True)
            yield SimpleNamespace(succeeded=True)
        finally:
            closed.append(True)

    client = object.__new__(api.Client)
    client.core = object()
    with (
        patch.object(
            api, "_post", AsyncMock(return_value={"recomms": [{"id": "example"}]})
        ),
        patch.object(api, "scrape_stream", side_effect=lambda **kwargs: source()),
    ):
        stream = client.search("test", video_count=1)
        await anext(stream)
        await stream.aclose()
    assert closed == [True]


@pytest.mark.parametrize(
    "url",
    [
        "https://cdn.example/playlist.m3u8?token=abc&expires=123",
        "https://cdn.example/master.m3u8?token=abc",
        "https:\\/\\/cdn.example\\/playlist.m3u8?token=abc",
    ],
)
def test_signed_hls_url_is_preserved(url):
    video = api.Video(url="https://missav.ws/en/example", core=object())
    data = video._extract_from_html('<script>source="' + url + '";</script>')
    assert data["m3u8_base_url"] == url.replace("\\/", "/")
