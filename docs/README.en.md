# Codar Daily

**Codar daily check-in · multi-account · rolling 24-hour window · strict server readback**

[简体中文](../README.md) · English · [繁體中文](README.zh-Hant.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Português (BR)](README.pt-BR.md)

## What it does

`codar_daily.py` checks the Codar account status, claims only when the server
explicitly says the current rolling window is unsigned, and then reads the
status again. A claim response by itself is never treated as success.

## Protocol

```text
POST https://api.kuaipaper.com/v1/daily-sign/status
POST https://api.kuaipaper.com/v1/daily-sign

Authorization: Bearer <JWT>
Content-Type: application/json
Accept: application/json
User-Agent: node

{"username":"<account>"}
```

The status reader accepts `isSigned`, `signed`, `hasSigned`, and `has_signed`
only as real JSON booleans. The final result is based on a fresh status request
after the claim.

## Credentials

| Variable | Required | Description |
| :--- | :---: | :--- |
| `CODAR_TOKENS` | one of | Multiple JWTs, comma or newline separated |
| `CODAR_TOKEN` | one of | One JWT |
| `CODAR_COOKIES` | one of | Multiple cookies, one per line |
| `CODAR_COOKIE` | one of | One cookie |
| `CODAR_USERNAME` | optional | Username for a single cookie input |
| `CODAR_READBACK_ATTEMPTS` | optional | Status readback attempts, default `3` |
| `CODAR_READBACK_DELAY` | optional | Delay between readbacks, default `1` second |

Token record formats:

```text
main|<JWT>
second|<username>|<JWT>
```

Cookie records use the same `note|value` or `note|username|value` form. A
cookie must contain a Codar access-token JWT under a key such as `token`,
`access_token`, `accessToken`, `authorization`, `jwt`, or `codar_token`.

## Run

```powershell
python -m pip install -r requirements.txt
$env:CODAR_TOKEN = "<JWT>"
python codar_daily.py
```

Status only:

```powershell
python codar_daily.py --status
```

Linux / macOS:

```bash
python3 -m pip install -r requirements.txt
export CODAR_TOKEN='<JWT>'
python3 codar_daily.py
```

Qinglong command: `task codar_daily.py`.

## GitHub Actions

Add one or more of `CODAR_TOKENS`, `CODAR_TOKEN`, `CODAR_COOKIES`, and
`CODAR_COOKIE` under repository Secrets. The included workflow runs offline
tests on push and checks every six hours on schedule. The rolling 24-hour
window means an early run is harmless: it only reads the status.

Reports:

- `codar-report.jsonl`
- `codar-report.json`

## Success

| Result | Meaning |
| :--- | :--- |
| `CLAIMED` | Post-claim status is explicitly signed |
| `ALREADY_CLAIMED` | Status was already signed |
| `AVAILABLE` | Status-only mode found an unsigned window |
| `CLAIM_NOT_APPLIED` | Claim receipt arrived but status stayed unsigned |
| `READBACK_UNCONFIRMED` | Post-claim status could not be confirmed |
| `STATUS_UNRECOGNIZED` | No explicit boolean status |

Exit codes: `0` all confirmed, `1` at least one failure, `2` configuration
error.

## Security

Credentials are read only from environment variables or GitHub Secrets. Tokens,
cookies, JWTs, and credentials echoed by the server are redacted. Reports are
written as JSONL; per-account sessions are isolated.

Do not commit authentication files, reports, tokens, cookies, phone numbers, or
screenshots containing them.

## License and notice

Local implementation: [MIT](../LICENSE). Usage boundaries:
[NOTICE.md](../NOTICE.md). Third-party license and protocol evidence:
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).
