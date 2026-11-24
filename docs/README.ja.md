# Codar Daily

**Codar デイリーチェックイン · 複数アカウント · 24 時間ローリング · 厳密なサーバー再確認**

[简体中文](../README.md) · [English](README.en.md) · [繁體中文](README.zh-Hant.md) · 日本語 · [한국어](README.ko.md) · [Português (BR)](README.pt-BR.md)

## 機能

`codar_daily.py` は Codar アカウントの状態を確認し、サーバーが現在のローリングウィンドウを未チェックインと明示した場合だけ申請します。申請後にもう一度状態を取得し、申請応答だけでは成功にしません。

## プロトコル

```text
POST https://api.kuaipaper.com/v1/daily-sign/status
POST https://api.kuaipaper.com/v1/daily-sign

Authorization: Bearer <JWT>
Content-Type: application/json
Accept: application/json
User-Agent: node

{"username":"<account>"}
```

状態は `isSigned`、`signed`、`hasSigned`、`has_signed` の真の JSON boolean だけを採用します。最終結果は申請後の再取得で確認します。

## 認証情報

| 変数 | 必須 | 説明 |
| :--- | :---: | :--- |
| `CODAR_TOKENS` | いずれか | 複数 JWT。カンマまたは改行区切り |
| `CODAR_TOKEN` | いずれか | 単一 JWT |
| `CODAR_COOKIES` | いずれか | 複数 Cookie。1 行に 1 個 |
| `CODAR_COOKIE` | いずれか | 単一 Cookie |
| `CODAR_USERNAME` | 任意 | 単一 Cookie 用ユーザー名 |
| `CODAR_READBACK_ATTEMPTS` | 任意 | 再確認回数。既定 `3` |
| `CODAR_READBACK_DELAY` | 任意 | 再確認間隔。既定 `1` 秒 |

Token の形式：

```text
main|<JWT>
second|<username>|<JWT>
```

Cookie は `note|Cookie` または `note|username|Cookie` 形式です。Cookie には `token`、`access_token`、`accessToken`、`authorization`、`jwt`、`codar_token` などのキーで JWT が必要です。

## 実行

```powershell
python -m pip install -r requirements.txt
$env:CODAR_TOKEN = "<JWT>"
python codar_daily.py
```

状態確認のみ：

```powershell
python codar_daily.py --status
```

Qinglong コマンド：`task codar_daily.py`。

## GitHub Actions

Secrets に `CODAR_TOKENS`、`CODAR_TOKEN`、`CODAR_COOKIES`、`CODAR_COOKIE` のいずれかを追加します。push ではオフラインテスト、スケジュールでは 6 時間ごとに確認します。24 時間ローリングのため、早い実行は状態確認だけで終わります。

出力：

- `codar-report.jsonl`
- `codar-report.json`

## 成功条件

| 結果 | 意味 |
| :--- | :--- |
| `CLAIMED` | 申請後の状態が明確に署名済み |
| `ALREADY_CLAIMED` | 実行前から署名済み |
| `AVAILABLE` | 状態確認のみで未署名を確認 |
| `CLAIM_NOT_APPLIED` | 申請応答はあるが状態が未署名のまま |
| `READBACK_UNCONFIRMED` | 申請後の状態を確認できない |
| `STATUS_UNRECOGNIZED` | 明確な boolean 状態がない |

終了コード：`0` 全確認、`1` 1 件以上失敗、`2` 設定エラー。

## セキュリティ

認証情報は環境変数または GitHub Secrets からのみ読み取ります。Token、Cookie、JWT、サーバーが返した認証情報はマスクします。認証ファイル、レポート、Token、Cookie、電話番号、敏感なスクリーンショットをコミットしないでください。

## ライセンス

ローカル実装は [MIT](../LICENSE)。利用境界は [NOTICE.md](../NOTICE.md)、第三者ライセンスとプロトコル根拠は [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) を参照してください。
