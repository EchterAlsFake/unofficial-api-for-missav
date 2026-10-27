# Changelog

## 2.6.2 — 2026-10-27

- Preserve query tokens and escaped slashes in direct HLS playlist URLs.
- Give default clients their own runtime configuration instead of changing shared client settings.
- Reject invalid search counts before making a request and close search streams when callers stop early.
- Close CLI sessions and stop reporting failed downloads as completed.
- Access challenges can still prevent requests; this release does not bypass them.
- Use the published `eaf-base-api>=4.2.5` dependency.

