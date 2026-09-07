import os
import copy
import time
import uuid
import hmac
import hashlib
import logging
import asyncio
import argparse

from base_api.modules.static_functions import str_to_bool
from functools import partial
from urllib.parse import quote
from typing import AsyncGenerator, ClassVar, Any
from dataclasses import dataclass
from curl_cffi import AsyncSession
from selectolax.lexbor import LexborHTMLParser
from base_api.modules.config import IteratorConfig, RuntimeConfig
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
    is_resource_gone,
    default_on_error,
    scrape_stream,
    make_iterator_config as _base_make_iterator_config,
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


def make_iterator_config(
    load_specific_sources: tuple[str, ...] = ("html",),
    *,
    max_page_concurrency: int | None = 1,
    **kwargs: Any,
) -> IteratorConfig:
    return _base_make_iterator_config(
        load_specific_sources=load_specific_sources,
        max_page_concurrency=max_page_concurrency,
        **kwargs,
    )


_is_resource_gone = is_resource_gone
on_error = default_on_error


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
    def __init__(self, core: BaseCore | None = None):
        if core is None:
            core = BaseCore()
        self.core = core
        self.core.configuration.impersonation = "safari17_2_ios" # Required
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

        stream = scrape_stream(
            core=self.core,
            constructor=Video,
            target_page_urls=["https://missav.ws/en/"],
            item_extractor=cubed_function,
            iterator_config=iterator_config,
        )
        async for result in stream:
            yield result


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MissAV API Command Line Interface")
    parser.add_argument("--download", metavar="URL", type=str, help="URL to download from")
    parser.add_argument("--quality", metavar="best|half|worst", type=str, default="best", help="The video quality (best, half, worst)")
    parser.add_argument("--file", metavar="FILE", type=str, help="(Optional) Specify a file with URLs (separated with new lines)")
    parser.add_argument("--output", metavar="DIR", type=str, required=True, help="The output path (with filename or directory)")
    parser.add_argument("--no-title", metavar="True,False", type=str, nargs="?", const="True", default="False",
                        help="Whether to apply video title automatically to output path or not")
    return parser


async def run_main(args_list: list[str] | None = None):
    parser = create_parser()
    args = parser.parse_args(args_list)
    no_title = str_to_bool(args.no_title) if isinstance(args.no_title, str) else bool(args.no_title)
    config = DownloadConfigHLS(quality=args.quality, path=args.output, no_title=no_title)

    urls: list[str] = []
    if args.download:
        urls.append(args.download)
    if args.file:
        with open(args.file, "r") as f:
            urls.extend([line.strip() for line in f if line.strip()])

    if not urls:
        parser.print_help()
        return

    client = Client()
    for url in urls:
        print(f"Fetching video information for: {url}")
        try:
            video = await client.get_video(url, load_html=True)
            title = getattr(video, "title", None) or url
            print(f"Starting download for: {title}")
            await video.download(configuration=config)
            print(f"Download complete: {title}")
        except Exception as e:
            print(f"Error downloading {url}: {e}")


def main():
    try:
        asyncio.run(run_main())
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")


if __name__ == "__main__":
    main()

