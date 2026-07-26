<h1 align="center">MissAV API</h1>
<p align="center"><em>An asynchronous Python API wrapper and scraper for missav.ws</em></p>

<div align="center">
    <a href="https://pepy.tech/project/missAV_api"><img src="https://static.pepy.tech/badge/missAV_api" alt="Downloads"></a> +
    <a href="https://pepy.tech/project/unofficial-api-for-missav"><img src="https://static.pepy.tech/badge/unofficial-api-for-missav" alt="Downloads"></a>
    <a href="https://echteralsfake.me/ci/unofficial-api-for-missav/badge.svg"><img src="https://echteralsfake.me/ci/unofficial-api-for-missav/badge.svg" alt="Sync API Tests"/></a>
    </div>

# Disclaimer
> [!IMPORTANT]
> This is an unofficial and unaffiliated project. Please read the full disclaimer before use:
> **[DISCLAIMER.md](https://github.com/EchterAlsFake/API_Docs/blob/master/Disclaimer.md)**
>
> By using this project you agree to comply with the target site's rules, copyright/licensing requirements,
> and applicable laws. Do not use it to bypass access controls or scrape at disruptive rates.

---

# Features

| Category | Details |
|---|---|
| **Video Fetching** | Fetch video objects with metadata scraped directly from HTML |
| **Video Downloading** | HLS-based downloading with configurable quality (`best`, `half`, `worst`, or specific resolutions) |
| **Video Search** | Search videos by query with support for pagination and concurrency control |
| **Async-First** | Fully asynchronous (`async` / `await`) built on top of `asyncio` |
| **Built-in Caching** | Automatic response caching with configurable limits to reduce redundant network requests |
| **Type Safety** | Comprehensive type hinting and `dataclass`-based models throughout |

#### Networking Features

The networking layer is provided by the [`eaf_base_api`](https://github.com/EchterAlsFake/eaf_base_api) package and is fully configurable through `RuntimeConfig`:

| Feature | Description |
|---|---|
| **HTTP/1.1, HTTP/2, HTTP/3** | Configurable HTTP version (`v1`, `v2`, `v3` — defaults to HTTP/3) |
| **Browser Impersonation** | Built-in browser fingerprint impersonation via `curl_cffi` (defaults to Chrome) |
| **Custom JA3 Fingerprint** | Override the TLS fingerprint with a custom JA3 string for advanced use cases |
| **Proxy Support** | All proxy types supported (HTTP, HTTPS, SOCKS4, SOCKS5) |
| **Proxy Authentication** | Username/password authentication for proxies |
| **Bandwidth Limiting** | Set a maximum download speed in MB/s (e.g., `2.0`, `3.5`) |
| **DNS over HTTPS** | Route DNS queries over HTTPS for privacy and bypassing DNS-level blocks |
| **SSL Verification** | Toggle SSL certificate verification on or off |
| **Request Delay** | Configurable delay between requests to respect rate limits |
| **Concurrency Control** | Tune video and page concurrency independently for optimal throughput |

---

# Supported Platforms
This API has been tested and confirmed working on:

- Windows 11 (x64) 
- macOS Sequoia (x86_64)
- Linux (Arch) (x86_64)
- Android 16 (aarch64)

---

# Installation

```bash
pip install unofficial-api-for-missav
```

---

# Quickstart

### Have a look at the [Documentation](https://docs.echteralsfake.me/missav) for more details

```python
import asyncio
from missav_api import Client, DownloadConfigHLS

async def main():
    # Initialize a Client object
    client = Client()
    
    # Fetch a video
    video_object = await client.get_video("<insert_url_here>")
    
    # Information from Video objects
    print(video_object.title)

    # Download the video
    config = DownloadConfigHLS(quality="best", path="./") # More options in the documentation
    await video_object.download(config)

if __name__ == "__main__":
    asyncio.run(main())
```

---

# Support the Project ❤️

I develop all my projects entirely for free because I enjoy it and want to keep them accessible.
If you find my work useful, please consider supporting me with a small donation — even 1 € makes a big difference and keeps me motivated!

### ☕ Ko-fi
<a href="https://ko-fi.com/EchterAlsFake">https://ko-fi.com/EchterAlsFake</a>

### 💳 PayPal
<a href="https://paypal.me/EchterAlsFake">https://paypal.me/EchterAlsFake</a>

### 🪙 Crypto (350+ currencies supported)
<a href="https://nowpayments.io/donation?api_key=65b1acaf-735d-4d4b-b3d6-c2237c0b57e3" target="_blank" rel="noreferrer noopener">
   <img src="https://nowpayments.io/images/embeds/donation-button-black.svg" alt="Crypto donation button by NOWPayments">
</a>

---

# Contribution
Do you see any issues or having some feature requests? Simply open an Issue or talk
in the discussions.

Pull requests are also welcome.

# License
This API is licensed under the AGPLv3. See the `LICENSE` file for details.

> [!CAUTION]
> **Using this in a proprietary application?**
> Under the AGPLv3, if you integrate, modify, or host this API as part of your application (even over a network), you must open-source your entire application's code under the AGPL. 
>
> If you want to use this API without open-sourcing your own code, you must purchase a commercial license.
> 
> **For commercial licensing, contact:** EchterAlsFakeBS@proton.me
