import pytest
import logging
from unittest.mock import AsyncMock, MagicMock, patch
from base_api import BaseCore, DownloadConfigHLS
from missav_api.api import Video, DownloadFailed

SAMPLE_HTML_SNIPPET = """<div x-data="{
    baseUrl: 'https://missav.ws/de/rlmp-013-uncensored-leak',
}">
    <div class="plyr plyr--full-ui plyr--video">
        <div class="plyr__controls__item plyr__time--duration plyr__time" aria-label="Duration">1:58:58</div>
        <div class="plyr__video-wrapper">
            <video playsinline="" data-poster="https://fourhoi.com/rlmp-013-uncensored-leak/cover-n.jpg" preload="none" class="player" crossorigin="anonymous" src="blob:https://missav.ws/7f56b603"></video>
        </div>
    </div>
    <div class="under_player"></div>
    <div class="mt-4">
        <h1 class="text-base lg:text-lg text-nord6">RLMP-013 Fertig. Unser Volleyballteam aus fleischsklavischen Müttern. ~Ein schweißtreibendes, saftiges Schwangerschaftscamp, in dem wir ungezügelt in sie hineinspritzen~ - Yuri Oshikawa</h1>
    </div>
</div>"""

SAMPLE_FULL_PAGE_HTML = """<!DOCTYPE html>
<html>
<head>
    <meta property="og:title" content="FC2-PPV-2777644 Test Video">
    <meta property="og:image" content="https://fourhoi.com/fc2-ppv-2777644/cover-n.jpg">
    <meta property="og:video:release_date" content="2022-06-10">
    <meta property="og:video:duration" content="1550">
    <meta name="keywords" content="人妻, 寝取られ, NTR, 巨根">
</head>
<body>
    <video playsinline="" data-poster="https://fourhoi.com/fc2-ppv-2777644/cover-n.jpg" class="player"></video>
    <div class="under_player"></div>
    <h1>FC2-PPV-2777644 Test Video</h1>
    <script type="text/javascript">
        var dummy = 'm3u8|0469e7e38d84|9343|488f|4161|88c7e9f6|com|surrit|https|video';
    </script>
</body>
</html>"""


def test_extract_from_snippet(caplog):
    core = MagicMock(spec=BaseCore)
    video = Video(url="https://missav.ws/de/rlmp-013-uncensored-leak", core=core)

    with caplog.at_level(logging.WARNING):
        data = video._extract_from_html(SAMPLE_HTML_SNIPPET)

    assert data["title"] == "RLMP-013 Fertig. Unser Volleyballteam aus fleischsklavischen Müttern. ~Ein schweißtreibendes, saftiges Schwangerschaftscamp, in dem wir ungezügelt in sie hineinspritzen~ - Yuri Oshikawa"
    assert data["thumbnail"] == "https://fourhoi.com/rlmp-013-uncensored-leak/cover-n.jpg"
    assert data["length"] == "1:58:58"
    assert data["publish_date"] is None
    assert data["keywords"] is None
    assert data["m3u8_base_url"] is None

    # Check that graceful fallbacks logged warnings
    assert "Publish date not found" in caplog.text
    assert "Keywords not found" in caplog.text
    assert "m3u8 base URL not found" in caplog.text


def test_extract_from_full_page():
    core = MagicMock(spec=BaseCore)
    video = Video(url="https://missav.ws/dm13/de/fc2-ppv-2777644", core=core)

    data = video._extract_from_html(SAMPLE_FULL_PAGE_HTML)
    assert data["title"] == "FC2-PPV-2777644 Test Video"
    assert data["thumbnail"] == "https://fourhoi.com/fc2-ppv-2777644/cover-n.jpg"
    assert data["publish_date"] == "2022-06-10"
    assert data["length"] == "1550"
    assert data["keywords"] == "人妻, 寝取られ, NTR, 巨根"
    assert data["m3u8_base_url"] == "https://surrit.com/88c7e9f6-4161-488f-9343-0469e7e38d84/playlist.m3u8"


def test_layout_anchor_warning(caplog):
    core = MagicMock(spec=BaseCore)
    video = Video(url="https://missav.ws/changed-layout", core=core)

    with caplog.at_level(logging.WARNING):
        video._extract_from_html("<div><p>Empty page</p></div>")

    assert "Video container anchor ('video.player' / '.under_player') not found" in caplog.text


def test_direct_surrit_fallback():
    core = MagicMock(spec=BaseCore)
    video = Video(url="https://missav.ws/test", core=core)

    html = """
    <video class="player"></video>
    <div class="under_player"></div>
    <h1>Test</h1>
    <script>
        var urls = ["https://surrit.com/abcdef01-2345-6789-abcd-ef0123456789/seek/_0.jpg"];
    </script>
    """
    data = video._extract_from_html(html)
    assert data["m3u8_base_url"] == "https://surrit.com/abcdef01-2345-6789-abcd-ef0123456789/playlist.m3u8"


@pytest.mark.asyncio
async def test_download_missing_m3u8():
    core = MagicMock(spec=BaseCore)
    video = Video(url="https://missav.ws/test", core=core)
    video.m3u8_base_url = None
    video.title = "Sample"

    config = DownloadConfigHLS(quality="best", path="/tmp")
    with patch.object(Video, "load_fields", new_callable=AsyncMock):
        with pytest.raises(DownloadFailed, match="m3u8 base URL is missing"):
            await video.download(config)
