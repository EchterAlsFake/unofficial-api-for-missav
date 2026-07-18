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
from typing import AsyncGenerator
from dataclasses import dataclass, fields
from base_api.base import Helper, BaseMedia
from curl_cffi import Response, AsyncSession
from selectolax.lexbor import LexborHTMLParser
from base_api import BaseCore, DownloadConfigHLS
from base_api.modules.type_hints import DownloadReport
from base_api.modules.errors import BotProtectionDetected, InvalidProxy, UnknownError, NetworkRequestError, ResourceGone

from missav_api.modules.errors import (NetworkError, NotFound, UnknownNetworkError, DownloadFailed, BotDetection,
                                ProxyError)
from missav_api.modules.consts import regex_m3u8_js, headers, very_cursed_extractor

from missav_api.modules.type_hints import on_error_hint

BASE_HOST = "client-rapi-missav.recombee.com"
DATABASE_ID = "missav-default"
PUBLIC_TOKEN = "Ikkg568nlM51RHvldlPvc2GzZPE9R4XGzaH9Qj4zK9npbbbTly1gj9K4mgRn0QlV"
# You can change these if you want

logger = logging.getLogger("MissAV API")
logger.addHandler(logging.NullHandler())


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

async def _post(core, path: str, json_body: dict, timeout=9):
    signed_path = _sign_path(path, PUBLIC_TOKEN)
    url = f"https://{BASE_HOST}{signed_path}"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": "https://missav.ws",
        "Referer": "https://missav.ws/",
    }
    resp = await core.fetch(url, json_data=json_body, headers=headers, timeout=timeout, method="POST", get_response=True)
    return resp.json()


async def on_error(url: str, error: Exception, attempt: int) -> bool:
    logger.error(f"URL: {url}, ERROR: {error}, Attempt: {attempt}")

    if isinstance(error, ResourceGone):
        return False

    return True


async def get_html_content(core: BaseCore, url: str) -> str | None | dict:
    try:
        content = await core.fetch(url)
        if isinstance(content, str):
            return content

        if isinstance(content, Response):
            if content.status_code == 404:
                raise NotFound(f"Server returned 404 for: {url}")

    except NetworkRequestError as e:
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
    title: str | None = None
    publish_date: str | None = None
    keywords: str | None = None,
    length: str | None = None
    m3u8_base_url: str | None = None
    thumbnail: str | None = None


    async def _perform_load(self, api: bool, html: bool, anything_else: bool):
        if html:
            await asyncio.gather(self._fetch_html())

    async def _fetch_html(self):
        html_content = await get_html_content(core=self.core, url=self.url)
        assert isinstance(html_content, str)
        data: dict = await asyncio.to_thread(self._extract_from_html, html_content)
        allowed_fields = {field.name for field in fields(self)}
        for key, value in data.items():
            if key in allowed_fields:
                setattr(self, key, value)

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
        return await Video(url=url, core=self.core).load(html=load_html)

    async def search(self, query: str, video_count: int = 50,
                     on_video_error: on_error_hint = on_error,
                     on_page_error: on_error_hint = None,
                     keep_original_order: bool = False, load_html: bool = True,
                     ) -> AsyncGenerator[Video, None]:
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

        videos_concurrency = self.core.configuration.videos_concurrency
        assert videos_concurrency
        cubed_function = partial(very_cursed_extractor, video_urls=video_urls)

        async for result in helper.iterator(target_page_urls=["https://missav.ws/en/"], video_link_extractor=cubed_function,
                                         max_video_concurrency=videos_concurrency, max_page_concurrency=1,
                                         keep_original_order=keep_original_order, fetch_html=load_html,
                                         on_video_error=on_video_error, on_page_error=on_page_error): # Don't ask
            yield result
