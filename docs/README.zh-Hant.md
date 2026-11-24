# Codar Daily

**科搭每日簽到 · 多帳號 · 滾動 24 小時視窗 · 嚴格服務端回讀**

[简体中文](../README.md) · [English](README.en.md) · 繁體中文 · [日本語](README.ja.md) · [한국어](README.ko.md) · [Português (BR)](README.pt-BR.md)

## 功能

`codar_daily.py` 先查詢科搭帳號狀態，只有服務端明確表示本輪未簽到時才提交領取，領取後再次查詢狀態。領取回執本身不算成功。

## 協議

```text
POST https://api.kuaipaper.com/v1/daily-sign/status
POST https://api.kuaipaper.com/v1/daily-sign

Authorization: Bearer <JWT>
Content-Type: application/json
Accept: application/json
User-Agent: node

{"username":"<帳號名>"}
```

狀態只接受 `isSigned`、`signed`、`hasSigned`、`has_signed` 的真布林值。最終結果必須由領取後的新狀態查詢確認。

## 憑據

| 變數 | 必填 | 說明 |
| :--- | :---: | :--- |
| `CODAR_TOKENS` | 二選一 | 多帳號 JWT，逗號或換行分隔 |
| `CODAR_TOKEN` | 二選一 | 單帳號 JWT |
| `CODAR_COOKIES` | 二選一 | 多帳號 Cookie，每行一個 |
| `CODAR_COOKIE` | 二選一 | 單帳號 Cookie |
| `CODAR_USERNAME` | 可選 | 單帳號 Cookie 使用者名稱 |
| `CODAR_READBACK_ATTEMPTS` | 可選 | 回讀次數，預設 `3` |
| `CODAR_READBACK_DELAY` | 可選 | 回讀間隔秒數，預設 `1` |

Token 格式：

```text
主號|<JWT>
小號|<使用者名稱>|<JWT>
```

Cookie 支援 `備註|Cookie` 或 `備註|使用者名稱|Cookie`。Cookie 必須包含科搭存取令牌 JWT，例如 `token`、`access_token`、`accessToken`、`authorization`、`jwt` 或 `codar_token`。

## 執行

```powershell
python -m pip install -r requirements.txt
$env:CODAR_TOKEN = "<JWT>"
python codar_daily.py
```

只查狀態：

```powershell
python codar_daily.py --status
```

青龍命令：`task codar_daily.py`。

## Actions

在 Secrets 中新增 `CODAR_TOKENS`、`CODAR_TOKEN`、`CODAR_COOKIES` 或 `CODAR_COOKIE`。工作流在 push 時跑離線測試，排程每 6 小時檢查一次。滾動 24 小時視窗下，提前執行只會查狀態，不會重複領取。

輸出：

- `codar-report.jsonl`
- `codar-report.json`

## 成功判據

| 結果 | 含義 |
| :--- | :--- |
| `CLAIMED` | 領取後狀態明確為已簽 |
| `ALREADY_CLAIMED` | 執行前已簽 |
| `AVAILABLE` | 只查狀態且明確未簽 |
| `CLAIM_NOT_APPLIED` | 有成功回執，但回讀仍未簽 |
| `READBACK_UNCONFIRMED` | 領取後無法確認狀態 |
| `STATUS_UNRECOGNIZED` | 沒有明確布林狀態 |

退出碼：`0` 全部確認，`1` 至少一個失敗，`2` 配置錯誤。

## 安全

憑據只從環境變數或 GitHub Secrets 讀取。Token、Cookie、JWT 和服務端回顯的敏感值會脫敏。請勿提交認證檔、報告、Token、Cookie、手機號或含敏感資訊的截圖。

## 授權

本專案使用 [MIT](../LICENSE)。使用邊界見 [NOTICE.md](../NOTICE.md)，第三方許可與協議證據見 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。
