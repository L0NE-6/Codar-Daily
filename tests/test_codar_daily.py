import base64
import importlib.util
import json
import sys
import time
import unittest
from pathlib import Path
from urllib.parse import urlsplit


SOURCE = Path(__file__).resolve().parents[1] / "codar_daily.py"
SPEC = importlib.util.spec_from_file_location("codar_daily_test", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def b64url(value):
    raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def make_token(username="alice", exp_offset=3600, **claims):
    payload = {"username": username, "exp": int(time.time()) + exp_offset}
    payload.update(claims)
    return "%s.%s.signature" % (b64url({"alg": "none"}), b64url(payload))


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=None, headers=None):
        self.status_code = status_code
        self.payload = payload
        self.text = text
        self.headers = headers or {}

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class FakeSession:
    def __init__(self, routes):
        self.routes = {key: list(value) if isinstance(value, list) else value for key, value in routes.items()}
        self.calls = []
        self.closed = False

    def request(self, method, url, **kwargs):
        path = urlsplit(url).path
        self.calls.append(
            {
                "method": method,
                "url": url,
                "path": path,
                "headers": dict(kwargs.get("headers", {})),
                "json": kwargs.get("json"),
            }
        )
        route = self.routes.get(path)
        if callable(route):
            return route(method, url, **kwargs)
        if isinstance(route, list):
            if not route:
                return FakeResponse(500, {"message": "route exhausted"})
            return route.pop(0)
        if isinstance(route, FakeResponse):
            return route
        return FakeResponse(500, {"message": "unexpected path %s" % path})

    def close(self):
        self.closed = True


class CodarDailyTests(unittest.TestCase):
    def setUp(self):
        self.token = make_token("alice")

    def account(self, value=None, kind="token", username=""):
        return {
            "note": "main",
            "kind": kind,
            "value": self.token if value is None else value,
            "username": username,
        }

    def test_status_already_skips_claim_and_sends_exact_contract(self):
        session = FakeSession(
            {
                MODULE.STATUS_PATH: [
                    FakeResponse(payload={"code": 200, "data": {"isSigned": True}})
                ]
            }
        )
        result = MODULE.check_account(self.account(), session_factory=lambda: session)

        self.assertEqual("ALREADY_CLAIMED", result["result"])
        self.assertTrue(result["ok"])
        self.assertTrue(result["server_confirmed"])
        self.assertEqual(1, len(session.calls))
        call = session.calls[0]
        self.assertEqual("POST", call["method"])
        self.assertEqual(MODULE.DEFAULT_BASE_URL + MODULE.STATUS_PATH, call["url"])
        self.assertEqual({"username": "alice"}, call["json"])
        self.assertEqual("Bearer " + self.token, call["headers"]["Authorization"])
        self.assertEqual("application/json", call["headers"]["Content-Type"])
        self.assertEqual("node", call["headers"]["User-Agent"])
        self.assertTrue(session.closed)

    def test_claim_requires_post_claim_server_status(self):
        session = FakeSession(
            {
                MODULE.STATUS_PATH: [
                    FakeResponse(payload={"code": 200, "data": {"isSigned": False}}),
                    FakeResponse(payload={"code": 200, "data": {"isSigned": True}}),
                ],
                MODULE.CLAIM_PATH: [
                    FakeResponse(payload={"code": 200, "message": "签到成功"})
                ],
            }
        )
        result = MODULE.check_account(self.account(), session_factory=lambda: session)

        self.assertEqual("CLAIMED", result["result"])
        self.assertTrue(result["ok"])
        self.assertTrue(result["server_confirmed"])
        self.assertEqual(3, len(session.calls))
        self.assertEqual(MODULE.STATUS_PATH, session.calls[0]["path"])
        self.assertEqual(MODULE.CLAIM_PATH, session.calls[1]["path"])
        self.assertEqual(MODULE.STATUS_PATH, session.calls[2]["path"])

    def test_claim_receipt_without_signed_readback_is_not_success(self):
        session = FakeSession(
            {
                MODULE.STATUS_PATH: [
                    FakeResponse(payload={"code": 200, "data": {"isSigned": False}}),
                    FakeResponse(payload={"code": 200, "data": {"isSigned": False}}),
                ],
                MODULE.CLAIM_PATH: [
                    FakeResponse(payload={"code": 200, "message": "签到成功"})
                ],
            }
        )
        result = MODULE.check_account(
            self.account(),
            session_factory=lambda: session,
            readback_attempts=1,
        )

        self.assertEqual("CLAIM_NOT_APPLIED", result["result"])
        self.assertFalse(result["ok"])
        self.assertFalse(result["server_confirmed"])

    def test_unknown_readback_is_not_success(self):
        session = FakeSession(
            {
                MODULE.STATUS_PATH: [
                    FakeResponse(payload={"code": 200, "data": {"isSigned": False}}),
                    FakeResponse(payload={"code": 200, "data": {}}),
                ],
                MODULE.CLAIM_PATH: [
                    FakeResponse(payload={"code": 200, "message": "签到成功"})
                ],
            }
        )
        result = MODULE.check_account(
            self.account(),
            session_factory=lambda: session,
            readback_attempts=1,
        )

        self.assertEqual("READBACK_UNCONFIRMED", result["result"])
        self.assertFalse(result["ok"])

    def test_network_claim_can_still_be_confirmed_by_server_status(self):
        def fail_claim(*args, **kwargs):
            raise MODULE.requests.ConnectionError("connection dropped")

        session = FakeSession(
            {
                MODULE.STATUS_PATH: [
                    FakeResponse(payload={"code": 200, "data": {"isSigned": False}}),
                    FakeResponse(payload={"code": 200, "data": {"isSigned": True}}),
                ],
                MODULE.CLAIM_PATH: fail_claim,
            }
        )
        result = MODULE.check_account(self.account(), session_factory=lambda: session)

        self.assertEqual("CLAIMED", result["result"])
        self.assertTrue(result["ok"])
        self.assertTrue(result["server_confirmed"])

    def test_unknown_initial_status_never_claims(self):
        session = FakeSession(
            {MODULE.STATUS_PATH: [FakeResponse(payload={"code": 200, "data": {}})]}
        )
        result = MODULE.check_account(self.account(), session_factory=lambda: session)

        self.assertEqual("STATUS_UNRECOGNIZED", result["result"])
        self.assertEqual(1, len(session.calls))
        self.assertNotIn(MODULE.CLAIM_PATH, [call["path"] for call in session.calls])

    def test_status_mode_is_read_only(self):
        session = FakeSession(
            {
                MODULE.STATUS_PATH: [
                    FakeResponse(payload={"code": 200, "data": {"signed": False}})
                ]
            }
        )
        result = MODULE.check_account(
            self.account(),
            mode="status",
            session_factory=lambda: session,
        )

        self.assertEqual("AVAILABLE", result["result"])
        self.assertTrue(result["ok"])
        self.assertEqual(1, len(session.calls))

    def test_cookie_with_embedded_jwt_uses_cookie_and_bearer_headers(self):
        cookie = "session=abc; token=%s; username=alice" % self.token
        session = FakeSession(
            {
                MODULE.STATUS_PATH: [
                    FakeResponse(payload={"code": 200, "data": {"hasSigned": True}})
                ]
            }
        )
        result = MODULE.check_account(
            self.account(value=cookie, kind="cookie"),
            session_factory=lambda: session,
        )

        self.assertEqual("ALREADY_CLAIMED", result["result"])
        self.assertEqual(cookie, session.calls[0]["headers"]["Cookie"])
        self.assertEqual("Bearer " + self.token, session.calls[0]["headers"]["Authorization"])

    def test_multi_cookie_records_are_loaded_without_leaking_values(self):
        second = make_token("second")
        accounts = MODULE.load_accounts(
            {
                MODULE.COOKIES_ENV: (
                    "first|session=a; token=%s\n"
                    "second|session=b; token=%s"
                )
                % (self.token, second)
            }
        )
        self.assertEqual(2, len(accounts))
        self.assertEqual("first", accounts[0]["note"])
        self.assertEqual("second", accounts[1]["note"])
        self.assertEqual("alice", MODULE._prepare_account(accounts[0])["username"])
        self.assertEqual("second", MODULE._prepare_account(accounts[1])["username"])

    def test_cookie_without_jwt_is_config_error(self):
        result = MODULE.check_account(
            self.account(value="session=only", kind="cookie"),
            session_factory=lambda: self.fail("session must not be created"),
        )
        self.assertEqual("CONFIG_ERROR", result["result"])

    def test_username_mismatch_is_config_error(self):
        result = MODULE.check_account(
            self.account(username="bob"),
            session_factory=lambda: self.fail("session must not be created"),
        )
        self.assertEqual("CONFIG_ERROR", result["result"])

    def test_expired_token_does_not_call_network(self):
        token = make_token("alice", exp_offset=-60)
        result = MODULE.check_account(
            self.account(value=token),
            session_factory=lambda: self.fail("session must not be created"),
        )
        self.assertEqual("AUTH_EXPIRED", result["result"])

    def test_auth_error_is_visible(self):
        session = FakeSession(
            {
                MODULE.STATUS_PATH: [
                    FakeResponse(401, {"code": 401, "message": "invalid token"})
                ]
            }
        )
        result = MODULE.check_account(self.account(), session_factory=lambda: session)
        self.assertEqual("AUTH_EXPIRED", result["result"])
        self.assertFalse(result["ok"])

    def test_rate_limit_is_visible(self):
        session = FakeSession(
            {MODULE.STATUS_PATH: [FakeResponse(429, {"message": "slow down"})]}
        )
        result = MODULE.check_account(self.account(), session_factory=lambda: session)
        self.assertEqual("RATE_LIMITED", result["result"])
        self.assertFalse(result["ok"])

    def test_retry_after_is_preserved(self):
        session = FakeSession(
            {
                MODULE.STATUS_PATH: [
                    FakeResponse(
                        payload={
                            "code": 200,
                            "data": {"isSigned": True, "retry_after": 3600},
                        }
                    )
                ]
            }
        )
        result = MODULE.check_account(self.account(), session_factory=lambda: session)
        self.assertEqual(3600, result["retry_after"])

    def test_top_level_retry_after_and_boolean_data_are_supported(self):
        session = FakeSession(
            {
                MODULE.STATUS_PATH: [
                    FakeResponse(payload={"code": 200, "data": True, "retry_after": 7200})
                ]
            }
        )
        result = MODULE.check_account(self.account(), session_factory=lambda: session)
        self.assertEqual("ALREADY_CLAIMED", result["result"])
        self.assertEqual(7200, result["retry_after"])

    def test_already_claim_receipt_and_signed_readback(self):
        session = FakeSession(
            {
                MODULE.STATUS_PATH: [
                    FakeResponse(payload={"code": 200, "data": {"isSigned": False}}),
                    FakeResponse(payload={"code": 200, "data": {"isSigned": True}}),
                ],
                MODULE.CLAIM_PATH: [
                    FakeResponse(
                        payload={
                            "code": 400,
                            "message": "24小时内仅可领取一次",
                            "data": {"retry_after": 3600},
                        }
                    )
                ],
            }
        )
        result = MODULE.check_account(self.account(), session_factory=lambda: session)
        self.assertEqual("ALREADY_CLAIMED", result["result"])
        self.assertTrue(result["ok"])

    def test_already_claim_receipt_conflicts_with_unsigned_readback(self):
        session = FakeSession(
            {
                MODULE.STATUS_PATH: [
                    FakeResponse(payload={"code": 200, "data": {"isSigned": False}}),
                    FakeResponse(payload={"code": 200, "data": {"isSigned": False}}),
                ],
                MODULE.CLAIM_PATH: [
                    FakeResponse(payload={"code": 400, "message": "24小时内仅可领取一次"})
                ],
            }
        )
        result = MODULE.check_account(
            self.account(),
            session_factory=lambda: session,
            readback_attempts=1,
        )
        self.assertEqual("CLAIM_CONFLICT", result["result"])
        self.assertFalse(result["ok"])

    def test_business_error_can_be_overridden_only_by_signed_readback(self):
        session = FakeSession(
            {
                MODULE.STATUS_PATH: [
                    FakeResponse(payload={"code": 200, "data": {"isSigned": False}}),
                    FakeResponse(payload={"code": 200, "data": {"isSigned": True}}),
                ],
                MODULE.CLAIM_PATH: [
                    FakeResponse(500, {"code": 500, "message": "token %s busy" % self.token})
                ],
            }
        )
        result = MODULE.check_account(self.account(), session_factory=lambda: session)
        self.assertEqual("CLAIMED", result["result"])
        self.assertTrue(result["ok"])
        self.assertNotIn(self.token, result["message"])

    def test_invalid_json_is_reported(self):
        session = FakeSession(
            {
                MODULE.STATUS_PATH: [
                    FakeResponse(
                        payload=ValueError("bad json"),
                        text="<html>bad gateway</html>",
                    )
                ]
            }
        )
        result = MODULE.check_account(self.account(), session_factory=lambda: session)
        self.assertEqual("INVALID_JSON", result["result"])
        self.assertFalse(result["ok"])

    def test_redirect_is_not_followed(self):
        session = FakeSession(
            {MODULE.STATUS_PATH: [FakeResponse(302, {"message": "moved"})]}
        )
        result = MODULE.check_account(self.account(), session_factory=lambda: session)
        self.assertEqual("REDIRECT", result["result"])
        self.assertFalse(result["ok"])

    def test_multi_account_isolation_and_jsonl_summary(self):
        first = make_token("first", exp_offset=-60)
        second = make_token("second")
        session = FakeSession(
            {
                MODULE.STATUS_PATH: [
                    FakeResponse(payload={"code": 200, "data": {"isSigned": True}})
                ]
            }
        )
        lines = []
        code = MODULE.main(
            [],
            env={
                MODULE.TOKENS_ENV: "%s\nsecond|%s" % (first, second),
                MODULE.READBACK_ATTEMPTS_ENV: "1",
            },
            session_factory=lambda: session,
            output=lines.append,
            sleep=lambda _: None,
        )

        self.assertEqual(1, code)
        self.assertEqual(3, len(lines))
        self.assertEqual("AUTH_EXPIRED", lines[0]["result"])
        self.assertEqual("ALREADY_CLAIMED", lines[1]["result"])
        self.assertEqual(1, lines[2]["success"])
        self.assertEqual(1, lines[2]["failed"])

    def test_token_records_accept_comma_separators(self):
        first = make_token("first")
        second = make_token("second")
        accounts = MODULE.load_accounts({MODULE.TOKENS_ENV: "%s, %s" % (first, second)})
        self.assertEqual(2, len(accounts))
        self.assertEqual("first", MODULE._prepare_account(accounts[0])["username"])
        self.assertEqual("second", MODULE._prepare_account(accounts[1])["username"])

    def test_main_no_credentials_returns_config_error(self):
        lines = []
        code = MODULE.main([], env={}, output=lines.append, sleep=lambda _: None)
        self.assertEqual(2, code)
        self.assertEqual("CONFIG_ERROR", lines[0]["result"])
        self.assertEqual(1, lines[1]["failed"])

    def test_jsonl_output_is_parseable_and_redacted(self):
        token = self.token
        session = FakeSession(
            {
                MODULE.STATUS_PATH: [
                    FakeResponse(payload={"code": 200, "data": {"isSigned": False}}),
                    FakeResponse(payload={"code": 200, "data": {"isSigned": False}}),
                ],
                MODULE.CLAIM_PATH: [
                    FakeResponse(
                        payload={
                            "code": 200,
                            "message": "claim success token=%s" % token,
                        }
                    )
                ],
            }
        )
        lines = []
        MODULE.main(
            [],
            env={MODULE.TOKEN_ENV: token, MODULE.READBACK_ATTEMPTS_ENV: "1"},
            session_factory=lambda: session,
            output=lines.append,
            sleep=lambda _: None,
        )
        serialized = "\n".join(json.dumps(item, ensure_ascii=False) for item in lines)
        self.assertNotIn(token, serialized)
        self.assertEqual(2, len(lines))
        for item in lines:
            self.assertIsInstance(json.loads(json.dumps(item)), dict)

    def test_status_signed_false_does_not_need_claim_in_status_mode(self):
        session = FakeSession(
            {
                MODULE.STATUS_PATH: [
                    FakeResponse(payload={"code": 200, "data": {"has_signed": False}})
                ]
            }
        )
        result = MODULE.check_account(
            self.account(),
            mode="status",
            session_factory=lambda: session,
        )
        self.assertEqual("AVAILABLE", result["result"])
        self.assertEqual(1, len(session.calls))

    def test_claim_success_with_explicit_failure_is_not_success(self):
        session = FakeSession(
            {
                MODULE.STATUS_PATH: [
                    FakeResponse(payload={"code": 200, "data": {"isSigned": False}}),
                    FakeResponse(payload={"code": 200, "data": {"isSigned": False}}),
                ],
                MODULE.CLAIM_PATH: [
                    FakeResponse(
                        payload={"code": 200, "success": False, "message": "签到成功"}
                    )
                ],
            }
        )
        result = MODULE.check_account(
            self.account(),
            session_factory=lambda: session,
            readback_attempts=1,
        )
        self.assertEqual("BUSINESS_ERROR", result["result"])
        self.assertFalse(result["ok"])

    def test_unexpected_session_failure_is_isolated(self):
        def broken_session():
            raise RuntimeError("session setup failed")

        result = MODULE.check_account(self.account(), session_factory=broken_session)
        self.assertEqual("INTERNAL_ERROR", result["result"])
        self.assertFalse(result["ok"])

    def test_six_language_docs_keep_source_attribution_out_of_readmes(self):
        root = SOURCE.parent
        docs = [
            root / "README.md",
            root / "docs" / "README.en.md",
            root / "docs" / "README.zh-Hant.md",
            root / "docs" / "README.ja.md",
            root / "docs" / "README.ko.md",
            root / "docs" / "README.pt-BR.md",
        ]
        for path in docs:
            self.assertTrue(path.is_file(), path)
            text = path.read_text(encoding="utf-8")
            for forbidden in ("参考", "移植", "上游", "reference", "upstream"):
                self.assertNotIn(forbidden, text.lower())

    def test_third_party_notice_records_both_fixed_commits(self):
        text = (SOURCE.parent / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        self.assertIn("2651dbcb4ce50ada3411e59a136f01fb1a267cf3", text)
        self.assertIn("b35b163d01fc3effb30ae40a012fd657fdc0a54d", text)


if __name__ == "__main__":
    unittest.main()
