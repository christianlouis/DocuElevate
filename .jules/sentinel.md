## 2025-02-14 - SSRF vulnerability in webhook outgoing requests
**Vulnerability:** Found an SSRF vulnerability where outgoing webhook requests could hit private IPs or metadata endpoints (e.g. 169.254.169.254).
**Learning:** This existed because the `url` parameter provided for webhooks (`app/utils/webhook.py` and `app/utils/user_notification.py`) was not being checked before being passed to `requests.post()` or `httpx.post()`.
**Prevention:** Make sure to always validate URL scheme and hostname with `is_private_ip()` and block known cloud metadata endpoints before doing outgoing network requests based on dynamic values.
