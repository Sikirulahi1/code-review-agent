from __future__ import annotations

import hashlib
import hmac

from config import settings


def build_github_signature(payload_body: bytes, secret: str) -> str:
	digest = hmac.new(secret.encode("utf-8"), payload_body, hashlib.sha256).hexdigest()
	return f"sha256={digest}"


def verify_webhook_signature(
	payload_body: bytes,
	signature_header: str | None,
) -> tuple[bool, int, str]:
	secret_value = (
		settings.github_webhook_secret.get_secret_value()
		if settings.github_webhook_secret
		else ""
	)
	if not secret_value:
		return False, 503, "Webhook secret is not configured"

	if not signature_header:
		return False, 403, "Missing X-Hub-Signature-256 header"

	expected_signature = build_github_signature(payload_body, secret_value)
	if not hmac.compare_digest(expected_signature, signature_header):
		return False, 403, "Invalid webhook signature"

	return True, 200, "ok"
