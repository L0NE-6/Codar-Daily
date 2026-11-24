# Codar Daily

**Codar 일일 체크인 · 다중 계정 · 24시간 롤링 · 엄격한 서버 재확인**

[简体中文](../README.md) · [English](README.en.md) · [繁體中文](README.zh-Hant.md) · [日本語](README.ja.md) · 한국어 · [Português (BR)](README.pt-BR.md)

## 기능

`codar_daily.py`는 Codar 계정 상태를 확인하고 서버가 현재 롤링 창을 미체크인으로 명시한 경우에만 신청합니다. 신청 후 상태를 다시 읽으며, 신청 응답만으로 성공을 선언하지 않습니다.

## 프로토콜

```text
POST https://api.kuaipaper.com/v1/daily-sign/status
POST https://api.kuaipaper.com/v1/daily-sign

Authorization: Bearer <JWT>
Content-Type: application/json
Accept: application/json
User-Agent: node

{"username":"<account>"}
```

상태는 `isSigned`, `signed`, `hasSigned`, `has_signed`의 실제 JSON boolean만 인정합니다. 최종 결과는 신청 후 새 상태 조회로 확인합니다.

## 자격 증명

| 변수 | 필수 | 설명 |
| :--- | :---: | :--- |
| `CODAR_TOKENS` | 택1 | 여러 JWT, 쉼표 또는 줄바꿈 구분 |
| `CODAR_TOKEN` | 택1 | 단일 JWT |
| `CODAR_COOKIES` | 택1 | 여러 Cookie, 한 줄에 하나 |
| `CODAR_COOKIE` | 택1 | 단일 Cookie |
| `CODAR_USERNAME` | 선택 | 단일 Cookie 사용자 이름 |
| `CODAR_READBACK_ATTEMPTS` | 선택 | 재확인 횟수, 기본 `3` |
| `CODAR_READBACK_DELAY` | 선택 | 재확인 간격, 기본 `1`초 |

Token 형식:

```text
main|<JWT>
second|<username>|<JWT>
```

Cookie는 `note|Cookie` 또는 `note|username|Cookie` 형식입니다. Cookie에는 `token`, `access_token`, `accessToken`, `authorization`, `jwt`, `codar_token` 같은 키로 JWT가 있어야 합니다.

## 실행

```powershell
python -m pip install -r requirements.txt
$env:CODAR_TOKEN = "<JWT>"
python codar_daily.py
```

상태만 확인:

```powershell
python codar_daily.py --status
```

Qinglong 명령: `task codar_daily.py`.

## GitHub Actions

Secrets에 `CODAR_TOKENS`, `CODAR_TOKEN`, `CODAR_COOKIES`, `CODAR_COOKIE` 중 하나 이상을 추가합니다. push에서는 오프라인 테스트를 실행하고, 스케줄에서는 6시간마다 확인합니다. 24시간 롤링 창에서는 일찍 실행해도 상태만 읽습니다.

출력:

- `codar-report.jsonl`
- `codar-report.json`

## 성공 기준

| 결과 | 의미 |
| :--- | :--- |
| `CLAIMED` | 신청 후 상태가 명확히 서명됨 |
| `ALREADY_CLAIMED` | 실행 전부터 서명됨 |
| `AVAILABLE` | 상태 조회에서 미서명 확인 |
| `CLAIM_NOT_APPLIED` | 신청 응답은 있으나 상태가 미서명 |
| `READBACK_UNCONFIRMED` | 신청 후 상태를 확인할 수 없음 |
| `STATUS_UNRECOGNIZED` | 명확한 boolean 상태가 없음 |

종료 코드: `0` 전체 확인, `1` 하나 이상 실패, `2` 설정 오류.

## 보안

자격 증명은 환경 변수 또는 GitHub Secrets에서만 읽습니다. Token, Cookie, JWT 및 서버가 되돌려준 자격 증명은 마스킹합니다. 인증 파일, 보고서, Token, Cookie, 전화번호 또는 민감한 스크린샷을 커밋하지 마십시오.

## 라이선스

로컬 구현은 [MIT](../LICENSE)입니다. 사용 경계는 [NOTICE.md](../NOTICE.md), 제3자 라이선스와 프로토콜 근거는 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)를 확인하십시오.
