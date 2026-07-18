import re

headers = {
    "referer": "https://missav.ws/",
}

regex_m3u8_js = re.compile(r"'m3u8(.*?)video")


def very_cursed_extractor(html_content, video_urls):
    stuff = []
    for url in video_urls:
        stuff.append({"url": url})
        # I know this doesn't seem to make sense, but it does

    return stuff