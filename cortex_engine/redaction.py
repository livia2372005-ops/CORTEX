"""CORTEX Centralized Redaction and Sanitization Layer.

Sanitizes metadata, payloads, and command strings to prevent secret leakage
(API keys, tokens, passwords, private keys, authorization headers) from entering
canonical activity logs or event storage.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set, Union


# Common secret patterns
RE_PATTERNS = [
    # GitHub PATs
    re.compile(r"(?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{20,}", re.IGNORECASE),
    # OpenAI / Anthropic / Generic AI keys
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}", re.IGNORECASE),
    # AWS Access Keys
    re.compile(r"(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}"),
    # Bearer tokens
    re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
    # Private Keys (PEM block)
    re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+PRIVATE KEY-----"),
    # Generic key-value secret assignments (e.g. password=xyz, token=abc)
    re.compile(
        r"(?i)\b(password|passwd|secret|token|api_key|apikey|auth|access_token|private_key|key_pat)\s*[:=]\s*['\"]?([^'\"\s\t\n\r,;&]{6,})['\"]?"
    ),
]

SENSITIVE_KEY_NAMES: Set[str] = {
    "password",
    "passwd",
    "secret",
    "token",
    "key_pat",
    "pat",
    "api_key",
    "apikey",
    "auth",
    "access_token",
    "private_key",
    "authorization",
    "secret_key",
    "client_secret",
}


def redact_text(text: str) -> str:
    """Sanitize and replace detected secrets in raw string content."""
    if not isinstance(text, str) or not text:
        return text

    sanitized = text
    # 1. Redact specific regex patterns
    for pattern in RE_PATTERNS[:-1]:
        sanitized = pattern.sub("[REDACTED]", sanitized)

    # 2. Redact key-value pairs while preserving key name
    kv_pattern = RE_PATTERNS[-1]
    sanitized = kv_pattern.sub(r"\1=[REDACTED]", sanitized)

    return sanitized


def redact_data(data: Any, max_depth: int = 10) -> Any:
    """Recursively sanitize dictionary, list, or primitive data structures."""
    if max_depth <= 0:
        return "[TRUNCATED_DEPTH]"

    if isinstance(data, dict):
        cleaned_dict: Dict[str, Any] = {}
        for k, v in data.items():
            key_str = str(k).lower()
            # If the dictionary key itself matches a sensitive name, redact its entire value
            if any(sensitive in key_str for sensitive in SENSITIVE_KEY_NAMES):
                cleaned_dict[k] = "[REDACTED]"
            else:
                cleaned_dict[k] = redact_data(v, max_depth=max_depth - 1)
        return cleaned_dict

    elif isinstance(data, (list, tuple, set)):
        return [redact_data(item, max_depth=max_depth - 1) for item in data]

    elif isinstance(data, str):
        return redact_text(data)

    elif isinstance(data, (int, float, bool)) or data is None:
        return data

    else:
        # For other objects, sanitize string representation
        return redact_text(str(data))


def normalize_prompt(prompt: str) -> str:
    """Deterministically normalize prompt text for fingerprint hashing."""
    if not isinstance(prompt, str) or not prompt:
        return ""
    # Strip leading/trailing whitespace, collapse multiple spaces/newlines, lowercase
    cleaned = " ".join(prompt.strip().split())
    return cleaned.lower()


def compute_prompt_hash(prompt: str) -> Optional[str]:
    """Compute deterministic SHA-256 fingerprint of normalized prompt."""
    if not isinstance(prompt, str) or not prompt.strip():
        return None
    import hashlib
    norm = normalize_prompt(prompt)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()

