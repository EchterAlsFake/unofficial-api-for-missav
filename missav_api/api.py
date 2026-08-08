import os
import copy
import time
import uuid
import hmac
import hashlib
import logging
import asyncio

from functools import partial
from urllib.parse import quote
from typing import AsyncGenerator, ClassVar
from dataclasses import dataclass
from curl_cffi import AsyncSession
from selectolax.lexbor import LexborHTMLParser
from base_api.modules.config import IteratorConfig
from base_api import (
    BaseCore,
    BaseMedia,
    DownloadConfigHLS,
    ErrorAction,
    ErrorMode,
    Helper,
    MediaLoadError,
    MediaLoadErrors,
    RetryPolicy,
    ScrapeErrorContext,
    ScrapeResult,
    media_field,
)
from base_api.modules.type_hints import DownloadReport
from base_api.modules.errors import (
    BotProtectionDetected,
    HTTPStatusError,
    InvalidProxy,
    NetworkRequestError,
    RequestRetriesExhausted,
    ResourceGone,
    UnknownError,
)

from missav_api.modules.errors import (NetworkError, NotFound, UnknownNetworkError, DownloadFailed, BotDetection,
                                ProxyError)
from missav_api.modules.consts import regex_m3u8_js, headers, very_cursed_extractor


BASE_HOST = "client-rapi-missav.recombee.com"
DATABASE_ID = "missav-default"
PUBLIC_TOKEN = "Ikkg568nlM51RHvldlPvc2GzZPE9R4XGzaH9Qj4zK9npbbbTly1gj9K4mgRn0QlV"
# You can change these if you want

logger = logging.getLogger("MissAV API")
logger.addHandler(logging.NullHandler())

SCRAPE_RETRY_POLICY = RetryPolicy(max_attempts=3)


def make_iterator_config() -> IteratorConfig:
    return IteratorConfig(
        max_page_concurrency=1,
        load_specific_sources=("html",),
        item_retry=SCRAPE_RETRY_POLICY,
        page_retry=SCRAPE_RETRY_POLICY,
        page_error_mode=ErrorMode.SKIP,
        item_error_handler=None,
        page_error_handler=None,
    )


def _is_resource_gone(error: BaseException) -> bool:
    if isinstance(error, ResourceGone):
        return True
    if isinstance(error, MediaLoadError):
        return _is_resource_gone(error.original_error)
    if isinstance(error, MediaLoadErrors):
        return any(_is_resource_gone(item) for item in error.errors)
    return False


def _sign_path(path: str, token: str) -> str:
    """
    Reproduce _signUrl(path) from the JS:
      1) build "/{databaseId}{path}?frontend_timestamp=UNIX"
      2) HMAC-SHA1 that string with the public token (text)
      3) append &frontend_sign=hexdigest
    """
    ts = int(time.time())
    unsigned = f"/{DATABASE_ID}{path}"
    if "?" in unsigned:
        unsigned += f"&frontend_timestamp={ts}"
    else:
        unsigned += f"?frontend_timestamp={ts}"
    signature = hmac.new(token.encode("utf-8"),
                         unsigned.encode("utf-8"),
                         hashlib.sha1).hexdigest()
    return unsigned + f"&frontend_sign={signature}"

async def _post(core: BaseCore, path: str, json_body: dict, timeout: float = 9) -> dict:
    signed_path = _sign_path(path, PUBLIC_TOKEN)
    url = f"https://{BASE_HOST}{signed_path}"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": "https://missav.ws",
        "Referer": "https://missav.ws/",
    }
    resp = await core.request(
        url,
        json_data=json_body,
        headers=headers,
        timeout=timeout,
        method="POST",
    )
    return resp.json()


async def on_error(context: ScrapeErrorContext) -> ErrorAction:
    logger.error(
        "URL: %s, ERROR: %s, Attempt: %s/%s",
        context.url,
        context.error,
        context.attempt,
        context.max_attempts,
    )

    if _is_resource_gone(context.error):
        return ErrorAction.SKIP

    return ErrorAction.RETRY


async def get_html_content(core: BaseCore, url: str) -> str:
    try:
        return await core.fetch_text(url)

    except HTTPStatusError as e:
        if e.status_code == 404:
            raise NotFound(f"Server returned 404 for: {url}") from e
        raise NetworkError(str(e)) from e

    except (NetworkRequestError, RequestRetriesExhausted) as e:
        raise NetworkError(str(e)) from e

    except InvalidProxy as e:
        raise ProxyError(str(e)) from e

    except BotProtectionDetected as e:
        raise BotDetection(str(e)) from e

    except UnknownError as e:
        raise UnknownNetworkError(str(e)) from e


@dataclass(kw_only=True, slots=True)
class Video(BaseMedia):
    url: str
    core: BaseCore
    title: str | None = media_field("html")
    publish_date: str | None = media_field("html")
    keywords: str | None = media_field("html")
    length: str | None = media_field("html")
    m3u8_base_url: str | None = media_field("html")
    thumbnail: str | None = media_field("html")

    loader_methods: ClassVar[dict[str, str]] = {"html": "_load_html"}

    async def _load_html(self) -> dict[str, object]:
        html_content = await get_html_content(core=self.core, url=self.url)
        return await asyncio.to_thread(self._extract_from_html, html_content)

    @staticmethod
    def _extract_from_html(html_content: str) -> dict:
        parser = LexborHTMLParser(html_content)
        title = parser.css_first("meta[property='og:title']").attributes.get("content")
        keywords = parser.css_first("meta[name='keywords']").attributes.get("content")
        thumbnail = parser.css_first("meta[property='og:image']").attributes.get("content")
        publish_date = parser.css_first("meta[property='og:video:release_date']").attributes.get("content")
        length = parser.css_first("meta[property='og:video:duration']").attributes.get("content")

        javascript_content = regex_m3u8_js.search(html_content).group(1)
        url_parts = javascript_content.split("|")[::-1]
        url = f"{url_parts[1]}://{url_parts[2]}.{url_parts[3]}/{url_parts[4]}-{url_parts[5]}-{url_parts[6]}-{url_parts[7]}-{url_parts[8]}/playlist.m3u8"
        m3u8_base_url = url

        return {
            "title": title,
            "publish_date": publish_date,
            "m3u8_base_url": m3u8_base_url,
            "thumbnail": thumbnail,
            "keywords": keywords,
            "length": length,
        }


    async def download(self, configuration: DownloadConfigHLS) -> bool | DownloadReport:
        """
        :param configuration:
        :return:
        """
        await self.load_fields("m3u8_base_url", "title")
        config = copy.deepcopy(configuration)
        config.m3u8_base_url = self.m3u8_base_url

        if not config.no_title:
            config.path = os.path.join(config.path, f"{self.title}.mp4")

        try:
            return await self.core.download(configuration=config)
        except Exception as e:
            raise DownloadFailed(str(e))


class Client:
    def __init__(self, core: BaseCore = BaseCore()):
        self.core = core
        self.core.initialize_session()
        assert isinstance(self.core.session, AsyncSession)
        self.core.session.headers.update(headers)

    async def get_video(self, url: str, load_html: bool = True) -> Video:
        """Returns the video object"""
        video = Video(url=url, core=self.core)
        if load_html:
            await video.load_sources("html")
        return video

    async def search(
        self,
        query: str,
        video_count: int = 50,
        iterator_config: IteratorConfig | None = None,
    ) -> AsyncGenerator[ScrapeResult[Video], None]:
        """
        Mirrors: POST /search/users/{userId}/items/
        Body fields follow the snippet’s Recombee client (searchQuery, count, scenario, filter, booster, logic, etc.)
        """
        helper = Helper(constructor=Video, core=self.core)

        return_properties = True
        user_id = f"anon_{uuid.uuid4().hex[:16]}"
        path = f"/search/users/{quote(user_id, safe='')}/items/"
        body = {
            "searchQuery": query.strip(),
            "count": video_count,
            "cascadeCreate": True,
            "returnProperties": return_properties,
        }

        body = {k: v for k, v in body.items() if v is not None}
        data = await _post(path=path, json_body=body, timeout=9, core=self.core)
        videos = data.get("recomms", [])
        video_urls = []
        for video in videos:
            video_urls.append(f"https://missav.ws/en/{video['id']}")

        cubed_function = partial(very_cursed_extractor, video_urls=video_urls)

        if iterator_config is None:
            iterator_config = make_iterator_config()

        stream = helper.iterator(
            target_page_urls=["https://missav.ws/en/"],
            item_extractor=cubed_function,
            iterator_config=iterator_config,
        )
        async with stream:
            async for result in stream:
                yield result
