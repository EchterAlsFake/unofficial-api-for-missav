import re

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://missav.ws/",
    "Origin": "https://missav.ws",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "cross-site",
    "Accept": "*/*"}


regex_m3u8_js = re.compile(r"'m3u8(.*?)video")


def very_cursed_extractor(html_content, video_urls):
    stuff = []
    for url in video_urls:
        stuff.append({"url": url})
        # I know this doesn't seem to make sense, but it does

    return stuff