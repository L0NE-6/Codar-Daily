#!/usr/bin/env python3
"""Codar daily check-in runner with strict server-side readback.

The account API is intentionally small:

    POST https://api.kuaipaper.com/v1/daily-sign/status
    POST https://api.kuaipaper.com/v1/daily-sign

Both calls use an access-token JWT in ``Authorization: Bearer <token>`` and
send ``{"username": "<account>"}``.  A successful claim is only reported when
a fresh status request confirms a boolean signed field.  A claim receipt by
itself is never treated as success.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence
from urllib.parse import unquote

import requests


PROVIDER = "codar"
VERSION = "1.0.0"
DEFAULT_BASE_URL = "https://api.kuaipaper.com"
STATUS_PATH = "/v1/daily-sign/status"
CLAIM_PATH = "/v1/daily-sign"
USER_AGENT = "node"

TOKENS_ENV = "CODAR_TOKENS"
TOKEN_ENV = "CODAR_TOKEN"
COOKIES_ENV = "CODAR_COOKIES"
COOKIE_ENV = "CODAR_COOKIE"
USERNAME_ENV = "CODAR_USERNAME"
READBACK_ATTEMPTS_ENV = "CODAR_READBACK_ATTEMPTS"
READBACK_DELAY_ENV = "CODAR_READBACK_DELAY"

DEFAULT_READBACK_ATTEMPTS = 3
DEFAULT_READBACK_DELAY = 1.0
REQUEST_TIMEOUT = (10, 20)
MAX_RETRY_AFTER = 7 * 24 * 60 * 60
MAX_TOKEN_LENGTH = 8192

SIGNED_FIELDS = ("isSigned", "signed", "hasSigned", "has_signed")
SUCCESS_WORDS = re.compile(r"(?:success|succeeded|成功|领取成功|签到成功)", re.I)
FAILURE_WORDS = re.compile(
    r"(?:failed|failure|error|busy|try\s+again|稍后|失败|繁忙|风控|频繁|维护)",
    re.I,
)
ALREADY_WORDS = re.compile(
    r"(?:"
    r"24\s*小时(?:内)?[^。；;]{0,12}?(?:仅|只能|才)[^。；;]{0,8}?(?:领取|签到)"
    r"|(?:仅|只能)[^。；;]{0,4}(?:领取|签到)?[^。；;]{0,4}(?:一次|1\s*次)"
    r"|once\s+(?:every|in|per)\s+(?:a\s+)?(?:24\s*(?:hours?|h)|day)"
    r"|already\s+(?:claimed|signed|checked\s+in)"
    r"|(?:今日|今天|本次)\s*已经?\s*(?:签到|领取|签过|领过)"
    r"|已经?\s*(?:签到|领取|签过|领过)过?"
    r")",
    re.I,
)
JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")


class ConfigError(ValueError):
    """An account or runner configuration cannot be used."""


class APIError(RuntimeError):
    """A request failed before a server state could be interpreted."""

    def __init__(
        self,
        kind: str,
        message: str,
        *,
        http_status: Optional[int] = None,
        payload: Any = None,
        retry_after: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.http_status = http_status
        self.payload = payload
        self.retry_after = retry_after


@dataclass
class ApiReply:
    status_code: int
    payload: Any
    headers: Mapping[str, str]


@dataclass
class StatusSnapshot:
    state: str
    retry_after: Optional[int] = None
    http_status: Optional[int] = None
    message: str = ""


def emit(payload: Mapping[str, Any], stream: Any = None) -> None:
    """Write one compact JSON object to stdout."""
    target = sys.stdout if stream is None else stream
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), file=target)


def _safe_label(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[\x00-\x1f\x7f|]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text or len(text) > 64:
        return fallback
    if not re.fullmatch(r"[\w .-]+", text, re.UNICODE):
        return fallback
    return text


def _unique(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "")
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _safe_message(value: Any, secrets: Sequence[str], limit: int = 400) -> str:
    text = str(value or "")
    for secret in sorted(_unique(secrets), key=len, reverse=True):
        text = text.replace(secret, "[REDACTED]")
    text = JWT_RE.sub("[REDACTED]", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _message(payload: Any) -> str:
    if not isinstance(payload, Mapping):
        return ""
    for key in ("message", "msg", "error", "detail"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            nested = _message(value)
            if nested:
                return nested
        elif value not in (None, "", False):
            return str(value)
    data = payload.get("data")
    if isinstance(data, Mapping):
        return _message(data)
    return ""


def _as_number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str) and value.strip():
        try:
            number = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _business_codes(payload: Any) -> list[Any]:
    if not isinstance(payload, Mapping):
        return []
    codes: list[Any] = []
    for key in ("code",):
        if key in payload:
            codes.append(payload.get(key))
    for parent in ("data", "detail", "error"):
        nested = payload.get(parent)
        if isinstance(nested, Mapping):
            if "code" in nested:
                codes.append(nested.get("code"))
            deeper = nested.get("error")
            if isinstance(deeper, Mapping) and "code" in deeper:
                codes.append(deeper.get("code"))
    return codes


def _numeric_business_code(payload: Any) -> Optional[int]:
    for raw in _business_codes(payload):
        number = _as_number(raw)
        if number is not None and number.is_integer():
            return int(number)
    return None


def _business_failure(payload: Any) -> bool:
    if not isinstance(payload, Mapping):
        return False
    if payload.get("success") is False:
        return True
    data = payload.get("data")
    if isinstance(data, Mapping) and data.get("success") is False:
        return True
    for raw in _business_codes(payload):
        if isinstance(raw, str) and not _as_number(raw):
            return True
        number = _as_number(raw)
        if number is not None and number != 200:
            return True
    return False


def _is_auth_error(payload: Any) -> bool:
    if isinstance(payload, Mapping):
        for raw in _business_codes(payload):
            number = _as_number(raw)
            if number is not None and int(number) in (401, 403):
                return True
        words = _message(payload).lower()
        if re.search(r"(?:invalid|expired).*(?:token|credential)|登录.*(?:过期|失效)", words):
            return True
    return False


def _is_account_restricted(payload: Any) -> bool:
    if isinstance(payload, Mapping):
        text = json.dumps(payload, ensure_ascii=False, default=str).lower()
        return "account_restricted" in text
    return False


def _header_value(headers: Mapping[str, str], name: str) -> str:
    for key, value in headers.items():
        if str(key).lower() == name.lower():
            return str(value)
    return ""


def _retry_after_from_payload(payload: Any) -> Optional[int]:
    if isinstance(payload, Mapping):
        for key in ("retry_after", "retryAfter"):
            number = _as_number(payload.get(key))
            if number is not None and 0 < number <= MAX_RETRY_AFTER:
                return int(number)
        data = payload.get("data")
        if isinstance(data, Mapping):
            nested = _retry_after_from_payload(data)
            if nested is not None:
                return nested
    return None


def _retry_after(headers: Mapping[str, str], payload: Any) -> Optional[int]:
    stated = _retry_after_from_payload(payload)
    if stated is not None:
        return stated
    raw = _header_value(headers, "Retry-After").strip()
    if raw.isdigit():
        number = int(raw)
        if 0 < number <= MAX_RETRY_AFTER:
            return number
    return None


def _extract_signed(payload: Any) -> Optional[bool]:
    """Read a boolean signed state from the vendor's status envelope."""
    node = payload
    for _ in range(8):
        if isinstance(node, bool):
            return node
        if not isinstance(node, Mapping):
            return None
        named = False
        for key in SIGNED_FIELDS:
            if key not in node:
                continue
            named = True
            value = node.get(key)
            if isinstance(value, bool):
                return value
        if not named:
            nested = node.get("data")
            if isinstance(nested, (Mapping, bool)):
                node = nested
                continue
        return None
    return None


def _b64url_json(segment: str) -> Mapping[str, Any]:
    padded = segment + "=" * (-len(segment) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        value = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfigError("access token payload is not valid JSON") from exc
    if not isinstance(value, Mapping):
        raise ConfigError("access token payload is not an object")
    return value


def _token_from_text(raw: Any, *, cookie: bool = False) -> str:
    text = str(raw or "").strip().strip("\"'")
    lowered = text.lower()
    if lowered.startswith("authorization:"):
        text = text.split(":", 1)[1].strip()
        lowered = text.lower()
    if lowered.startswith("bearer "):
        text = text[7:].strip()
    if cookie and text.lower().startswith("cookie:"):
        text = text.split(":", 1)[1].strip()
    if not text or len(text) > MAX_TOKEN_LENGTH:
        raise ConfigError("access token is empty or too long")
    if not re.fullmatch(r"[\x21-\x7e]+", text):
        raise ConfigError("access token contains whitespace or non-ASCII characters")
    parts = text.split(".")
    if len(parts) != 3 or any(not part for part in parts):
        raise ConfigError("access token must be a complete JWT")
    _b64url_json(parts[1])
    return text


def _claims(token: str) -> Mapping[str, Any]:
    return _b64url_json(token.split(".", 1)[1].split(".", 1)[0])


def _username_from_claims(claims: Mapping[str, Any]) -> str:
    value = claims.get("username")
    if not isinstance(value, str):
        return ""
    value = value.strip()
    if not value or len(value) > 128 or any(ord(char) < 32 for char in value):
        return ""
    return value


def _expiry_from_claims(claims: Mapping[str, Any]) -> Optional[int]:
    number = _as_number(claims.get("exp"))
    if number is None:
        return None
    return int(number)


def _cookie_pairs(cookie: str) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for part in cookie.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        key, value = part.split("=", 1)
        pairs.append((key.strip(), unquote(value.strip().strip("\"'"))))
    return pairs


def _token_from_cookie(cookie: str) -> str:
    pairs = _cookie_pairs(cookie)
    preferred = (
        "token",
        "access_token",
        "accesstoken",
        "authorization",
        "jwt",
        "codar_token",
    )
    ordered = sorted(
        pairs,
        key=lambda item: preferred.index(item[0].lower())
        if item[0].lower() in preferred
        else len(preferred),
    )
    for _, value in ordered:
        try:
            return _token_from_text(value, cookie=True)
        except ConfigError:
            continue
    return ""


def _username_from_cookie(cookie: str) -> str:
    for key, value in _cookie_pairs(cookie):
        if key.lower() in ("username", "user_name", "login", "account"):
            if value and len(value) <= 128:
                return value
    return ""


def _prepare_account(account: Mapping[str, Any]) -> dict[str, Any]:
    kind = str(account.get("kind", "")).strip().lower()
    value = str(account.get("value", "") or "").strip()
    if kind not in ("token", "cookie") or not value:
        raise ConfigError("credential is empty or has an unknown type")

    cookie = ""
    if kind == "cookie":
        cookie = value
        if cookie.lower().startswith("cookie:"):
            cookie = cookie.split(":", 1)[1].strip()
        token = _token_from_cookie(cookie)
        if not token:
            raise ConfigError(
                "cookie does not contain a Codar access-token JWT; "
                "use CODAR_TOKENS or include the token cookie"
            )
    else:
        token = _token_from_text(value)

    claims = _claims(token)
    jwt_username = _username_from_claims(claims)
    supplied = str(account.get("username", "") or "").strip()
    if not supplied and kind == "cookie":
        supplied = _username_from_cookie(cookie)
    username = supplied or jwt_username
    if not username:
        raise ConfigError("account username is missing from the JWT and was not supplied")
    if jwt_username and supplied and supplied != jwt_username:
        raise ConfigError("supplied username does not match the JWT username")

    expires = _expiry_from_claims(claims)
    prepared = {
        "note": _safe_label(account.get("note"), "account"),
        "kind": kind,
        "token": token,
        "cookie": cookie,
        "username": username,
        "expires": expires,
        "expired": expires is not None and expires <= int(time.time()),
    }
    prepared["secrets"] = _unique(
        [
            value,
            token,
            "Bearer " + token,
            cookie,
            username,
            *[part for _, part in _cookie_pairs(cookie)],
        ]
    )
    return prepared


def _split_records(raw: str, *, allow_comma: bool = False) -> list[str]:
    records = []
    for line in re.split(r"[\r\n]+", str(raw or "")):
        parts = line.split(",") if allow_comma else [line]
        for part in parts:
            part = part.strip()
            if part and not part.startswith("#"):
                records.append(part)
    return records


def _parse_record(line: str, index: int, kind: str, username: str = "") -> dict[str, str]:
    note = "account_%d" % index
    supplied_username = username
    value = line.strip()
    if "|" in value:
        first, second = value.split("|", 1)
        if "|" in second:
            supplied_username, value = second.split("|", 1)
        else:
            note, value = first, second
    if not value.strip():
        raise ConfigError("account %d has an empty credential" % index)
    return {
        "note": note,
        "username": supplied_username.strip(),
        "kind": kind,
        "value": value.strip(),
    }


def load_accounts(env: Optional[Mapping[str, str]] = None) -> list[dict[str, str]]:
    """Parse multi-account and single-account credentials without logging them."""
    values = os.environ if env is None else env
    token_records = _split_records(str(values.get(TOKENS_ENV, "") or ""), allow_comma=True)
    cookie_records = _split_records(str(values.get(COOKIES_ENV, "") or ""))
    accounts: list[dict[str, str]] = []

    if token_records or cookie_records:
        for index, line in enumerate(token_records, 1):
            accounts.append(_parse_record(line, index, "token"))
        for index, line in enumerate(cookie_records, 1):
            accounts.append(_parse_record(line, index, "cookie"))
    else:
        token = str(values.get(TOKEN_ENV, "") or "").strip()
        cookie = str(values.get(COOKIE_ENV, "") or "").strip()
        username = str(values.get(USERNAME_ENV, "") or "").strip()
        if token:
            accounts.append(
                {"note": "account_1", "username": username, "kind": "token", "value": token}
            )
        if cookie:
            accounts.append(
                {
                    "note": "account_%d" % (len(accounts) + 1),
                    "username": username,
                    "kind": "cookie",
                    "value": cookie,
                }
            )

    if not accounts:
        raise ConfigError(
            "set CODAR_TOKENS/CODAR_TOKEN or CODAR_COOKIES/CODAR_COOKIE"
        )

    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for account in accounts:
        fingerprint = hashlib.sha256(
            ("%s\0%s" % (account["kind"], account["value"])).encode("utf-8")
        ).hexdigest()
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        account["note"] = _safe_label(account.get("note"), "account_%d" % (len(deduped) + 1))
        deduped.append(account)
    return deduped


def _request_headers(account: Mapping[str, Any]) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "Authorization": "Bearer " + str(account["token"]),
    }
    cookie = str(account.get("cookie", "") or "").strip()
    if cookie:
        headers["Cookie"] = cookie
    return headers


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        }
    )
    return session


def _request_json(
    session: Any,
    method: str,
    path: str,
    account: Mapping[str, Any],
    body: Optional[Mapping[str, Any]],
) -> ApiReply:
    try:
        response = session.request(
            method,
            DEFAULT_BASE_URL + path,
            headers=_request_headers(account),
            json=dict(body or {}),
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise APIError(
            "NETWORK_ERROR",
            _safe_message(exc, account.get("secrets", ())),
        ) from exc
    except Exception as exc:
        raise APIError(
            "NETWORK_ERROR",
            _safe_message(exc, account.get("secrets", ())),
        ) from exc

    try:
        status_code = int(getattr(response, "status_code", 0) or 0)
    except (TypeError, ValueError):
        status_code = 0
    headers = getattr(response, "headers", {}) or {}
    if not isinstance(headers, Mapping):
        headers = {}
    if 300 <= status_code < 400:
        raise APIError("REDIRECT", "接口返回重定向，已停止请求", http_status=status_code)
    if status_code == 0:
        raise APIError("NETWORK_ERROR", "接口没有返回 HTTP 状态")

    try:
        payload = response.json()
    except Exception as exc:
        text = str(getattr(response, "text", "") or "")
        detail = _safe_message(text or exc, account.get("secrets", ()))
        raise APIError(
            "INVALID_JSON",
            "接口未返回 JSON" + (": " + detail if detail else ""),
            http_status=status_code,
        ) from exc
    return ApiReply(status_code=status_code, payload=payload, headers=headers)


def _status_from_reply(reply: ApiReply, secrets: Sequence[str]) -> StatusSnapshot:
    status = reply.status_code
    payload = reply.payload
    if _is_account_restricted(payload):
        raise APIError(
            "ACCOUNT_RESTRICTED",
            "账号 API 访问受限（account_restricted）",
            http_status=status,
            payload=payload,
        )
    if status in (401, 403) or _is_auth_error(payload):
        raise APIError(
            "AUTH_EXPIRED",
            "登录已过期或凭据无效",
            http_status=status,
            payload=payload,
        )
    if status == 429:
        raise APIError(
            "RATE_LIMITED",
            "请求被限流",
            http_status=status,
            payload=payload,
            retry_after=_retry_after(reply.headers, payload),
        )
    if not 200 <= status < 300 or _business_failure(payload):
        words = _safe_message(_message(payload), secrets) or "状态接口异常"
        raise APIError("BUSINESS_ERROR", words, http_status=status, payload=payload)

    signed = _extract_signed(payload)
    retry_after = _retry_after(reply.headers, payload)
    if signed is True:
        return StatusSnapshot("signed", retry_after, status, _safe_message(_message(payload), secrets))
    if signed is False:
        return StatusSnapshot("unsigned", retry_after, status, _safe_message(_message(payload), secrets))
    return StatusSnapshot("unknown", retry_after, status, _safe_message(_message(payload), secrets))


def _query_status(
    session: Any,
    account: Mapping[str, Any],
) -> StatusSnapshot:
    reply = _request_json(
        session,
        "POST",
        STATUS_PATH,
        account,
        {"username": account["username"]},
    )
    return _status_from_reply(reply, account.get("secrets", ()))


def _poll_status(
    session: Any,
    account: Mapping[str, Any],
    *,
    attempts: int,
    delay: float,
    sleep: Callable[[float], None],
) -> tuple[StatusSnapshot, Optional[APIError]]:
    last: Optional[StatusSnapshot] = None
    last_error: Optional[APIError] = None
    for index in range(max(1, attempts)):
        try:
            last = _query_status(session, account)
            last_error = None
        except APIError as exc:
            last_error = exc
            if exc.kind in ("AUTH_EXPIRED", "ACCOUNT_RESTRICTED", "CONFIG_ERROR"):
                break
        if last is not None and last.state == "signed":
            break
        if index + 1 < max(1, attempts):
            sleep(delay)
    return last or StatusSnapshot("unknown"), last_error


def _claim_signal(reply: ApiReply, secrets: Sequence[str]) -> tuple[str, str, Optional[int]]:
    status = reply.status_code
    payload = reply.payload
    words = _safe_message(_message(payload), secrets)
    retry_after = _retry_after(reply.headers, payload)
    if _is_account_restricted(payload):
        return "ACCOUNT_RESTRICTED", "账号 API 访问受限（account_restricted）", retry_after
    if status in (401, 403) or _is_auth_error(payload):
        return "AUTH_EXPIRED", "登录已过期或凭据无效", retry_after
    if status == 429:
        return "RATE_LIMITED", "请求被限流", retry_after

    code = _numeric_business_code(payload)
    success_flag = isinstance(payload, Mapping) and payload.get("success") is True
    data = payload.get("data") if isinstance(payload, Mapping) else None
    if isinstance(data, Mapping) and data.get("success") is True:
        success_flag = True
    explicit_failure = (
        isinstance(payload, Mapping)
        and (
            payload.get("success") is False
            or (isinstance(data, Mapping) and data.get("success") is False)
        )
    )
    has_success_word = bool(SUCCESS_WORDS.search(words))
    has_failure_word = bool(FAILURE_WORDS.search(words))
    already = bool(ALREADY_WORDS.search(words))

    if explicit_failure:
        return "BUSINESS_ERROR", words or "领取接口返回失败", retry_after
    if has_failure_word and not has_success_word:
        kind = "BUSINESS_ERROR" if status < 500 else "HTTP_ERROR"
        return kind, words or "领取失败", retry_after
    if success_flag or has_success_word:
        return "SUCCESS", words or "服务端返回领取回执", retry_after
    if already:
        return "ALREADY", words or "服务端表示本轮已领取", retry_after
    if code == 200:
        return "SUCCESS", words or "服务端返回成功业务码", retry_after
    if code == 400 and retry_after:
        return "ALREADY", words or "服务端表示本轮已领取", retry_after
    if status >= 400 or _business_failure(payload):
        return "BUSINESS_ERROR", words or "领取接口返回失败", retry_after
    return "UNKNOWN", words or "领取回执没有明确成功信号", retry_after


def _failure_from_error(error: APIError, account: Mapping[str, Any], before_state: str) -> dict[str, Any]:
    return _result(
        account,
        error.kind,
        False,
        _safe_message(error.message, account.get("secrets", ())),
        before_state=before_state,
        http_status=error.http_status,
        retry_after=error.retry_after,
    )


def _result(
    account: Mapping[str, Any],
    result: str,
    ok: bool,
    message: str,
    *,
    before_state: str = "",
    after_state: str = "",
    server_confirmed: bool = False,
    claimed: bool = False,
    http_status: Optional[int] = None,
    claim_signal: str = "",
    retry_after: Optional[int] = None,
    credit: Optional[float] = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "provider": PROVIDER,
        "account": _safe_label(account.get("note"), "account"),
        "credential_kind": str(account.get("kind", "")),
        "result": result,
        "ok": ok,
        "claimed": claimed,
        "server_confirmed": server_confirmed,
        "before_state": before_state,
        "after_state": after_state,
        "claim_signal": claim_signal,
        "http_status": http_status,
        "retry_after": retry_after,
        "message": message,
    }
    if credit is not None:
        record["credit"] = credit
    return record


def _extract_credit(payload: Any) -> Optional[float]:
    if not isinstance(payload, Mapping):
        return None
    candidates = [payload.get("granted")]
    data = payload.get("data")
    if isinstance(data, Mapping):
        candidates.extend([data.get("granted"), data.get("credit"), data.get("points")])
    for value in candidates:
        number = _as_number(value)
        if number is not None and number >= 0:
            return number
    return None


def check_account(
    account: Mapping[str, Any],
    *,
    mode: str = "claim",
    session_factory: Callable[[], Any] = make_session,
    sleep: Callable[[float], None] = time.sleep,
    readback_attempts: int = DEFAULT_READBACK_ATTEMPTS,
    readback_delay: float = DEFAULT_READBACK_DELAY,
) -> dict[str, Any]:
    """Process one account. All failures become a structured result."""
    try:
        prepared = _prepare_account(account)
    except ConfigError as exc:
        return _result(account, "CONFIG_ERROR", False, str(exc))

    if prepared["expired"]:
        return _result(
            prepared,
            "AUTH_EXPIRED",
            False,
            "访问令牌已过期，请在科搭重新登录",
            before_state="expired",
        )

    session = None
    try:
        session = session_factory()
        initial, initial_error = _poll_status(
            session,
            prepared,
            attempts=1,
            delay=0,
            sleep=sleep,
        )
        if initial_error is not None:
            return _failure_from_error(initial_error, prepared, initial.state)
        if initial.state == "signed":
            return _result(
                prepared,
                "ALREADY_CLAIMED",
                True,
                "服务端状态确认本轮已签到，未重复提交领取",
                before_state="signed",
                after_state="signed",
                server_confirmed=True,
                claimed=True,
                http_status=initial.http_status,
                retry_after=initial.retry_after,
            )
        if initial.state != "unsigned":
            return _result(
                prepared,
                "STATUS_UNRECOGNIZED",
                False,
                "状态接口没有返回明确的 isSigned/signed/hasSigned/has_signed 布尔值",
                before_state=initial.state,
                http_status=initial.http_status,
                retry_after=initial.retry_after,
            )
        if mode == "status":
            return _result(
                prepared,
                "AVAILABLE",
                True,
                "服务端状态确认本轮尚未签到，查询模式未提交领取",
                before_state="unsigned",
                after_state="unsigned",
                http_status=initial.http_status,
                retry_after=initial.retry_after,
            )

        claim_reply: Optional[ApiReply] = None
        claim_error: Optional[APIError] = None
        try:
            claim_reply = _request_json(
                session,
                "POST",
                CLAIM_PATH,
                prepared,
                {"username": prepared["username"]},
            )
        except APIError as exc:
            claim_error = exc

        claim_signal = "NETWORK_ERROR"
        claim_message = ""
        claim_retry = None
        if claim_reply is not None:
            claim_signal, claim_message, claim_retry = _claim_signal(
                claim_reply,
                prepared.get("secrets", ()),
            )
        elif claim_error is not None:
            claim_message = _safe_message(claim_error.message, prepared.get("secrets", ()))
            claim_retry = claim_error.retry_after
            if claim_error.kind == "NETWORK_ERROR":
                claim_signal = "NETWORK_ERROR"
            elif claim_error.kind == "INVALID_JSON":
                claim_signal = "INVALID_JSON"
            elif claim_error.kind == "REDIRECT":
                claim_signal = "REDIRECT"
            else:
                claim_signal = claim_error.kind

        after, after_error = _poll_status(
            session,
            prepared,
            attempts=readback_attempts,
            delay=readback_delay,
            sleep=sleep,
        )
        credit = _extract_credit(claim_reply.payload) if claim_reply is not None else None
        if after.state == "signed":
            result = "ALREADY_CLAIMED" if claim_signal == "ALREADY" else "CLAIMED"
            return _result(
                prepared,
                result,
                True,
                "服务端回读已确认本轮签到"
                + ("；领取回执=已领取" if claim_signal == "ALREADY" else ""),
                before_state="unsigned",
                after_state="signed",
                server_confirmed=True,
                claimed=True,
                http_status=after.http_status,
                claim_signal=claim_signal,
                retry_after=after.retry_after,
                credit=credit,
            )

        if after.state == "unsigned":
            if claim_signal == "SUCCESS":
                return _result(
                    prepared,
                    "CLAIM_NOT_APPLIED",
                    False,
                    "领取回执没有转化为服务端签到状态",
                    before_state="unsigned",
                    after_state="unsigned",
                    http_status=after.http_status,
                    claim_signal=claim_signal,
                    retry_after=after.retry_after,
                    credit=credit,
                )
            if claim_signal == "ALREADY":
                return _result(
                    prepared,
                    "CLAIM_CONFLICT",
                    False,
                    "领取回执称已领取，但服务端状态仍为未签到",
                    before_state="unsigned",
                    after_state="unsigned",
                    http_status=after.http_status,
                    claim_signal=claim_signal,
                    retry_after=after.retry_after,
                    credit=credit,
                )
            if claim_signal in (
                "AUTH_EXPIRED",
                "ACCOUNT_RESTRICTED",
                "RATE_LIMITED",
                "BUSINESS_ERROR",
                "HTTP_ERROR",
                "NETWORK_ERROR",
                "INVALID_JSON",
                "REDIRECT",
            ):
                return _result(
                    prepared,
                    claim_signal,
                    False,
                    claim_message or "领取请求失败",
                    before_state="unsigned",
                    after_state="unsigned",
                    http_status=after.http_status,
                    claim_signal=claim_signal,
                    retry_after=after.retry_after or claim_retry,
                    credit=credit,
                )
            return _result(
                prepared,
                "UNKNOWN_RESULT",
                False,
                "领取回执不明确，服务端状态仍为未签到",
                before_state="unsigned",
                after_state="unsigned",
                http_status=after.http_status,
                claim_signal=claim_signal,
                retry_after=after.retry_after,
                credit=credit,
            )

        if after_error is not None and after_error.kind in (
            "AUTH_EXPIRED",
            "ACCOUNT_RESTRICTED",
        ):
            return _failure_from_error(after_error, prepared, "unsigned")
        if claim_signal in (
            "AUTH_EXPIRED",
            "ACCOUNT_RESTRICTED",
            "RATE_LIMITED",
            "BUSINESS_ERROR",
            "HTTP_ERROR",
            "NETWORK_ERROR",
            "INVALID_JSON",
            "REDIRECT",
        ):
            return _result(
                prepared,
                claim_signal,
                False,
                claim_message or "领取请求失败",
                before_state="unsigned",
                after_state=after.state,
                http_status=claim_reply.status_code if claim_reply is not None else None,
                claim_signal=claim_signal,
                retry_after=claim_retry,
                credit=credit,
            )
        return _result(
            prepared,
            "READBACK_UNCONFIRMED",
            False,
            "领取后未能从服务端确认签到状态",
            before_state="unsigned",
            after_state=after.state,
            http_status=after.http_status,
            claim_signal=claim_signal,
            retry_after=after.retry_after,
            credit=credit,
        )
    except Exception as exc:
        return _result(
            prepared,
            "INTERNAL_ERROR",
            False,
            _safe_message(exc, prepared.get("secrets", ())),
        )
    finally:
        close = getattr(session, "close", None)
        if callable(close):
            close()


def build_summary(results: Sequence[Mapping[str, Any]], mode: str) -> dict[str, Any]:
    success = sum(1 for result in results if result.get("ok") is True)
    return {
        "provider": PROVIDER,
        "version": VERSION,
        "mode": mode,
        "accounts": len(results),
        "success": success,
        "failed": len(results) - success,
        "results": [dict(result) for result in results],
    }


def _env_int(env: Mapping[str, str], name: str, default: int, low: int, high: int) -> int:
    raw = str(env.get(name, "") or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError("%s must be an integer" % name) from exc
    if not low <= value <= high:
        raise ConfigError("%s must be between %d and %d" % (name, low, high))
    return value


def _env_float(env: Mapping[str, str], name: str, default: float) -> float:
    raw = str(env.get(name, "") or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError("%s must be a number" % name) from exc
    if not 0 <= value <= 30:
        raise ConfigError("%s must be between 0 and 30" % name)
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Codar daily check-in runner")
    parser.add_argument(
        "--status",
        action="store_true",
        help="query status only; never submit a claim",
    )
    parser.add_argument(
        "action",
        nargs="?",
        choices=("status",),
        help=argparse.SUPPRESS,
    )
    return parser


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    env: Optional[Mapping[str, str]] = None,
    session_factory: Callable[[], Any] = make_session,
    output: Callable[[Mapping[str, Any]], None] = emit,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    args = build_parser().parse_args(argv)
    values = os.environ if env is None else env
    mode = "status" if args.status or args.action == "status" else "claim"
    try:
        accounts = load_accounts(values)
        attempts = _env_int(
            values,
            READBACK_ATTEMPTS_ENV,
            DEFAULT_READBACK_ATTEMPTS,
            1,
            10,
        )
        delay = _env_float(values, READBACK_DELAY_ENV, DEFAULT_READBACK_DELAY)
    except ConfigError as exc:
        result = _result(
            {"note": "config", "kind": "config"},
            "CONFIG_ERROR",
            False,
            str(exc),
        )
        output(result)
        output(build_summary([result], mode))
        return 2

    results = []
    for account in accounts:
        result = check_account(
            account,
            mode=mode,
            session_factory=session_factory,
            sleep=sleep,
            readback_attempts=attempts,
            readback_delay=delay,
        )
        results.append(result)
        output(result)
    summary = build_summary(results, mode)
    output(summary)
    return 0 if summary["failed"] == 0 else 1


def _configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    _configure_utf8_stdio()
    sys.exit(main())
