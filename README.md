<div align="center">

<sub><strong>L0NE-6 · CODAR DAILY</strong></sub>

# Codar Daily

**科搭每日签到 · 多账号 · 滚动 24 小时窗口 · 严格服务端回读**

> 当前版本：**v1.0.0**（2026-11-24） · 单文件自包含 · 不把 HTTP 200 或领取回执当成最终成功

[简体中文](README.md) · [English](docs/README.en.md) · [繁體中文](docs/README.zh-Hant.md) · [日本語](docs/README.ja.md) · [한국어](docs/README.ko.md) · [Português (BR)](docs/README.pt-BR.md)

🔁 多账号隔离 · 🧾 JSONL 报告 · ✅ 服务端回读 · 🛡️ 凭据脱敏 · 🐧 青龙友好 · ☁️ GitHub Actions · 🧪 离线测试

<img src="https://img.shields.io/badge/Python-3.9%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" />
<img src="https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20Qinglong-4EAA25?style=for-the-badge" />
<img src="https://img.shields.io/badge/Deploy-Actions-2088FF?style=for-the-badge&logo=githubactions&logoColor=white" />
<img src="https://img.shields.io/badge/License-MIT-F472B6?style=for-the-badge" />

[✨ 速览](#quick-overview) · [🔐 凭据](#credentials) · [🐧 青龙](#qinglong) · [☁️ Actions](#actions) · [✅ 成功判据](#success) · [📊 输出](#output) · [🧠 原则](#design) · [🚫 边界](#usage-policy) · [✦ 星轨](#star-trail)

</div>

---

<a id="usage-policy"></a>
## 🚫 使用边界与转载声明

> [!IMPORTANT]
> **官方版本永久免费。禁止倒卖。** 未经作者书面许可，禁止付费包装、搬运引流、冒充作者，或使用作者身份与收款码制造官方授权假象。

本仓库、脚本、部署说明和 Release 下载始终免费公开。禁止把本项目包装为付费资源、内部版、独家版、会员权益、收费课程、代部署服务或包更新服务；禁止搬运到其他账号、群组、频道、网盘、电商和付费平台进行涨粉、截流、倒卖或引流；禁止删除作者与版权信息后冒充原创。

完整规则见 **[NOTICE.md](NOTICE.md)**。

---

<a id="quick-overview"></a>
## ✨ 30 秒速览

| 维度 | 说明 |
| :--- | :--- |
| **做什么** | 检查 Codar 当前滚动 24 小时窗口是否已签到，未签时提交一次并回读。 |
| **输入** | `CODAR_TOKENS` / `CODAR_COOKIES` 多账号，或单账号 `CODAR_TOKEN` / `CODAR_COOKIE`。 |
| **输出** | 每账号一条 JSON、最后一条汇总 JSON、签到前后状态和领取回执。 |
| **部署** | Windows、Linux、青龙面板、GitHub Actions。 |
| **依赖** | Python 3.9+；运行时仅依赖 `requests`。 |
| **成功判据** | 领取后服务端状态明确变为已签；单次 HTTP 200 或 claim 回执不算最终成功。 |

---

<a id="features"></a>
## ✨ 功能

Codar Daily 是 L0NE-6 独立维护的单文件签到脚本，只做一件事：检查科搭账号本轮是否已经签到，能签就签，签完再从服务端读回确认。

| 能力 | 说明 |
| :--- | :--- |
| 多账号 | `CODAR_TOKENS` / `CODAR_COOKIES` 按行或逗号拆分，逐账号隔离执行 |
| 单账号 | `CODAR_TOKEN` / `CODAR_COOKIE` |
| 认证 | `Authorization: Bearer <JWT>`；Cookie 输入可同时携带 Cookie 头 |
| 状态 | 只认 `isSigned`、`signed`、`hasSigned`、`has_signed` 的真实布尔值 |
| 领取 | 只有服务端状态明确为未签到时才 `POST /v1/daily-sign` |
| 回读 | 领取后再次查询状态；未读到已签状态时返回失败或未确认 |
| 输出 | 每账号一行 JSON，最后一行汇总；可直接转成 JSON 数组 |
| 调度 | Windows、Linux、青龙、GitHub Actions |
| 安全 | Token、Cookie、JWT 和回包回显统一脱敏 |

---

<a id="protocol"></a>
## 🔁 协议与流程

脚本固定使用科搭账号接口：

```text
POST https://api.kuaipaper.com/v1/daily-sign/status
  Authorization: Bearer <JWT>
  Content-Type: application/json
  body: {"username":"<账号名>"}

POST https://api.kuaipaper.com/v1/daily-sign
  Authorization: Bearer <JWT>
  Content-Type: application/json
  body: {"username":"<账号名>"}
```

流程：

```text
初始 status
  ├─ signed=true  -> ALREADY_CLAIMED，不提交领取
  ├─ signed=false -> 提交 claim -> 再次 status
  └─ 状态不明确   -> STATUS_UNRECOGNIZED，不提交领取

领取后 status
  ├─ signed=true  -> CLAIMED / ALREADY_CLAIMED
  ├─ signed=false -> CLAIM_NOT_APPLIED / CLAIM_CONFLICT
  └─ 无法确认     -> READBACK_UNCONFIRMED
```

科搭签到窗口是滚动 24 小时，不是自然日零点。脚本不会根据本地时间推断“今天签过了”，只使用服务端状态。

### 状态字段

服务端返回 `data` 为布尔值，或返回包含以下任一字段的对象：

- `isSigned`
- `signed`
- `hasSigned`
- `has_signed`

字段必须是 JSON 布尔值。字符串 `"true"`、`"false"`、数字和 `null` 都不算明确状态。

### 领取回执

`code:200`、`success:true`、`签到成功` 等只作为领取回执，不作为最终成功依据。最终结论必须来自领取后的状态查询。

---

<a id="credentials"></a>
## 🔐 凭据

凭据只通过环境变量或 GitHub Secrets 注入。不要把真实 Token、Cookie、JWT、手机号或认证文件写进仓库。

### 变量总表

| 变量 | 必填 | 说明 |
| :--- | :---: | :--- |
| `CODAR_TOKENS` | 二选一 | 多账号 JWT，换行或逗号分隔 |
| `CODAR_TOKEN` | 二选一 | 单账号 JWT |
| `CODAR_COOKIES` | 二选一 | 多账号 Cookie，每行一个 |
| `CODAR_COOKIE` | 二选一 | 单账号 Cookie |
| `CODAR_USERNAME` | 可选 | 单账号 Cookie 的用户名；Token 通常可从 JWT 读取 |
| `CODAR_READBACK_ATTEMPTS` | 可选 | 领取后状态回读次数，默认 `3`，范围 `1..10` |
| `CODAR_READBACK_DELAY` | 可选 | 回读间隔秒数，默认 `1`，范围 `0..30` |

### Token 写法

`CODAR_TOKENS` 每行一个账号，支持：

```text
备注|JWT
备注|用户名|JWT
JWT
```

示例：

```text
主号|eyJ...
小号|eyJ...
```

也支持逗号分隔：

```text
主号|eyJ...,小号|eyJ...
```

Token 必须是完整 JWT。脚本会读取 JWT 的 `username` 和 `exp`：

- `username` 用于请求体；
- `exp` 已过期时直接返回 `AUTH_EXPIRED`，不发送请求；
- 如果行内显式写了用户名，必须与 JWT 的 `username` 一致。

### Cookie 写法

`CODAR_COOKIES` 每行一个账号：

```text
备注|Cookie
备注|用户名|Cookie
Cookie
```

Cookie 必须包含科搭访问令牌，常见键名：

```text
token
access_token
accessToken
authorization
jwt
codar_token
```

如果 Cookie 中没有 JWT，脚本会返回 `CONFIG_ERROR`，不会盲目提交领取。

### 从哪里获取

从你自己的科搭登录会话中读取当前访问令牌：

- Windows 桌面端配置通常在 `%USERPROFILE%\.codar\config.json`；
- 字段为 `provider.speedai.token`；
- 也可以从已登录请求的 `Authorization: Bearer ...` 中取得；
- 只读取你自己的凭据，不要把认证文件上传到仓库。

---

<a id="quickstart"></a>
## 🚀 快速开始

### Windows PowerShell

```powershell
python -m pip install -r requirements.txt

$env:CODAR_TOKEN = "<完整 JWT>"
python codar_daily.py
```

多账号：

```powershell
$env:CODAR_TOKENS = @"
主号|<JWT_1>
小号|<JWT_2>
"@
python codar_daily.py
```

只查状态，不领取：

```powershell
python codar_daily.py --status
```

### Linux / macOS

```bash
python3 -m pip install -r requirements.txt
export CODAR_TOKEN='<完整 JWT>'
python3 codar_daily.py
```

### 青龙面板

| 步骤 | 操作 |
| :---: | :--- |
| 1 | 安装依赖：`pip3 install requests` |
| 2 | 上传 `codar_daily.py` 到青龙脚本目录 |
| 3 | 添加 `CODAR_TOKENS` 或 `CODAR_TOKEN`，也可使用 Cookie 变量 |
| 4 | 新建定时任务，命令填 `task codar_daily.py` |
| 5 | 建议每 6 小时运行一次，例如 `17 */6 * * *` |

青龙任务请使用 `task codar_daily.py`，确保面板环境变量被注入。

---

<a id="actions"></a>
<a id="qinglong"></a>
## 🐧 青龙面板部署

1. 依赖管理安装 `requests`；
2. 上传 `codar_daily.py`；
3. 环境变量新增 `CODAR_TOKENS` / `CODAR_COOKIES`，单账号可用 `CODAR_TOKEN` / `CODAR_COOKIE`；
4. 新建定时任务，命令填 `task codar_daily.py`；
5. 建议每天固定运行一次，具体时间按账号使用习惯调整。

> 青龙任务优先使用 `task codar_daily.py`，确保面板环境变量被注入。

---

## ☁️ GitHub Actions

内置工作流：[`.github/workflows/codar.yml`](.github/workflows/codar.yml)。

| 事件 | 行为 |
| :--- | :--- |
| `push` 到 `main` | 运行离线测试、编译和 Ruff |
| `schedule` | 每 6 小时检查一次，先测试再领取 |
| `workflow_dispatch` | 手动执行同一流程 |

定时表达式：

```text
17 */6 * * *
```

这是 UTC 时间，对应北京时间 `01:17 / 07:17 / 13:17 / 19:17`。滚动 24 小时窗口下，多跑几次只会增加状态查询，不会重复领取。

### Secrets

进入 **Settings → Secrets and variables → Actions**，按需添加：

| Secret | 必填 | 值 |
| :--- | :---: | :--- |
| `CODAR_TOKENS` | 二选一 | 多账号 JWT |
| `CODAR_TOKEN` | 二选一 | 单账号 JWT |
| `CODAR_COOKIES` | 二选一 | 多账号 Cookie |
| `CODAR_COOKIE` | 二选一 | 单账号 Cookie |
| `CODAR_USERNAME` | 可选 | 单账号 Cookie 用户名 |

未配置任何凭据时，定时领取会输出明确的跳过 notice，不会把配置缺失伪装成领取成功。

每次运行会尝试上传：

- `codar-report.jsonl`：原始逐行 JSON；
- `codar-report.json`：完整 JSON 数组。

---

<a id="output"></a>
## ⌨️ 命令行与输出

标准输出是 JSON Lines：每个账号一行，最后一行是汇总。

```json
{"provider":"codar","account":"主号","result":"CLAIMED","ok":true,"server_confirmed":true,"before_state":"unsigned","after_state":"signed","claimed":true,"message":"服务端回读已确认本轮签到"}
{"provider":"codar","version":"1.0.0","mode":"claim","accounts":1,"success":1,"failed":0,"results":[...]}
```

### 单账号字段

| 字段 | 说明 |
| :--- | :--- |
| `account` | 脱敏后的账号标签 |
| `credential_kind` | `token` 或 `cookie` |
| `result` | 结果码 |
| `ok` | 是否达到可信成功条件 |
| `claimed` | 服务端当前是否确认已领取 |
| `server_confirmed` | 是否有服务端状态回读确认 |
| `before_state` | 领取前状态 |
| `after_state` | 回读后的状态 |
| `claim_signal` | 领取回执分类 |
| `http_status` | 最后一次关键请求的 HTTP 状态 |
| `retry_after` | 服务端给出的下次可领取秒数 |
| `credit` | 回执中可解析的积分，仅作证据，不作为成功依据 |
| `message` | 脱敏后的说明 |

---

## 🧭 结果码

| 结果码 | 成功 | 含义 |
| :--- | :---: | :--- |
| `CLAIMED` | ✅ | 领取后状态回读为已签 |
| `ALREADY_CLAIMED` | ✅ | 运行前或领取回执后状态回读为已签 |
| `AVAILABLE` | ✅ | 只查状态，服务端明确未签 |
| `CLAIM_NOT_APPLIED` | ❌ | 领取回执成功，但回读仍为未签 |
| `CLAIM_CONFLICT` | ❌ | 回执称已领取，但回读仍为未签 |
| `READBACK_UNCONFIRMED` | ❌ | 领取后无法确认状态 |
| `STATUS_UNRECOGNIZED` | ❌ | 初始状态没有明确布尔值 |
| `AUTH_EXPIRED` | ❌ | Token 过期、Cookie 失效或认证失败 |
| `ACCOUNT_RESTRICTED` | ❌ | 服务端限制账号 API 访问 |
| `RATE_LIMITED` | ❌ | HTTP 429 限流 |
| `BUSINESS_ERROR` | ❌ | 业务失败 |
| `HTTP_ERROR` | ❌ | 非 2xx HTTP 失败 |
| `INVALID_JSON` | ❌ | 接口没有返回 JSON |
| `REDIRECT` | ❌ | 接口返回重定向，脚本不跟随 |
| `NETWORK_ERROR` | ❌ | 网络异常 |
| `UNKNOWN_RESULT` | ❌ | 领取回执不明确 |
| `CONFIG_ERROR` | ❌ | 环境变量或凭据格式错误 |
| `INTERNAL_ERROR` | ❌ | 本地运行异常 |

退出码：

| 退出码 | 含义 |
| :---: | :--- |
| `0` | 所有账号均为可信成功 |
| `1` | 至少一个账号失败或回读未确认 |
| `2` | 未配置凭据或配置格式错误 |

---

<a id="success"></a>
## ✅ 成功判据

本项目不把“脚本跑了”“HTTP 200”“claim 返回 success”单独当成成功。

| 场景 | 必须满足 |
| :--- | :--- |
| 运行前已领取 | 初始状态明确为已签 |
| 新领取 | 领取后状态明确为已签 |
| 领取回执已领取 | 领取后状态明确为已签 |
| 领取回执成功但状态未变 | 判为 `CLAIM_NOT_APPLIED` |
| 领取后状态无法识别 | 判为 `READBACK_UNCONFIRMED` |

服务端状态是唯一最终判据。

---

<a id="privacy"></a>
## 🔒 隐私与安全

- 运行时只从环境变量读取凭据；
- 不把 Token、Cookie、JWT 写入磁盘；
- 不把凭据上传为 Actions artifact；
- 不打印请求头或完整回包；
- 服务端回显凭据时会替换为 `[REDACTED]`；
- 账号之间使用独立 Session；
- 单个账号失败不会阻断后续账号。

请勿提交：

```text
*token*.txt
*cookie*.txt
auth.json
login_result.json
codar-report.json
codar-report.jsonl
```

---

<a id="testing"></a>
## 🧪 离线测试

```powershell
python -m unittest discover -s tests -p "test_codar_daily.py" -v
python -m compileall -q codar_daily.py tests
ruff check codar_daily.py tests
```

测试使用 fake session 和 fake response：

- 不读取真实账号；
- 不访问真实领取接口；
- 覆盖状态已签、领取后回读、回执成功但未落账、网络中断后回读、状态未知、Cookie、JWT 过期、多账号隔离、凭据脱敏、JSONL 和配置错误。

离线测试通过只证明代码路径正确，不代表某个真实账号今天已经领取成功。

---

<a id="design"></a>
## 🧠 设计原则

- **滚动窗口语义**：按服务端 24 小时签到状态判断，不把自然日写死在本地；
- **状态机先行**：只有明确 `signed=false` 才提交领取；
- **服务端回读**：领取后必须再次读取已签状态；
- **账号隔离**：每个账号独立 Session 和错误边界；
- **诚实失败**：未知状态、回执成功但未落账、登录失效分别报告；
- **凭据脱敏**：Token、Cookie、JWT 和回包回显不进入日志；
- **最小依赖**：运行时仅依赖 `requests`。

---

## 📁 目录结构

```text
Codar-Daily/
├── .github/workflows/codar.yml
├── assets/
│   ├── donate-alipay.jpg
│   └── donate-wechat.png
├── docs/
│   ├── README.en.md
│   ├── README.zh-Hant.md
│   ├── README.ja.md
│   ├── README.ko.md
│   └── README.pt-BR.md
├── tests/test_codar_daily.py
├── codar_daily.py
├── CHANGELOG.md
├── LICENSE
├── NOTICE.md
├── THIRD_PARTY_NOTICES.md
├── pyproject.toml
├── requirements.txt
└── README.md
```

---

## 📦 版本与发布

- 当前版本：`v1.0.0`（2026-11-24）；
- 每次协议、状态字段或脚本行为变化单独发布版本；
- Release 附带完整 ZIP、单文件脚本和 `SHA256SUMS.txt`；
- 公开包不包含 Token、Cookie、JWT、报告或运行日志。

下载页：<https://github.com/L0NE-6/Codar-Daily/releases>

---

## ☕ 支持与投喂

脚本完全免费，无广告、无功能限制。如果它确实帮你省了时间，欢迎自愿赞赏；不影响任何功能，也不影响 Issue 响应。

<p align="center">
  <img src="assets/donate-wechat.png" width="260" alt="微信赞赏码" />
  &nbsp;&nbsp;&nbsp;&nbsp;
  <img src="assets/donate-alipay.jpg" width="260" alt="支付宝收款码" />
</p>
<p align="center"><sub>微信支付（左） | 支付宝（右）</sub></p>

> 收款码仅用于向作者自愿赞赏。任何第三方以代下载、代部署、内部资源或会员群为由收费，均与作者无关。

---

## ⚠️ 免责声明

本项目用于个人学习和合法的个人自动化。科搭的活动规则、接口、账号资格和积分口径由服务方决定；使用前请确认对应服务条款，并自行承担账号、网络、活动和接口变化带来的风险。

完整使用边界见 [NOTICE.md](NOTICE.md)。第三方许可与协议证据说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

---

## 💬 反馈与贡献

- [提交 Issue](https://github.com/L0NE-6/Codar-Daily/issues)
- [发起 Pull Request](https://github.com/L0NE-6/Codar-Daily/pulls)

反馈问题时，请附脱敏后的请求字段、签到前后状态、HTTP 状态和复现步骤。不要上传真实 JWT、Cookie、账号名或完整运行日志。

---

<a id="star-trail"></a>
## ✦ 星轨 Star Trail

<a href="https://star-history.com/#L0NE-6/Codar-Daily&Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=L0NE-6/Codar-Daily&type=Date&theme=dark" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=L0NE-6/Codar-Daily&type=Date" />
    <img alt="Codar Daily Star Trail" src="https://api.star-history.com/svg?repos=L0NE-6/Codar-Daily&type=Date" />
  </picture>
</a>

---

<div align="center">
  <sub>L0NE-6 · CODAR DAILY &nbsp;|&nbsp; 点个 <b>Star</b>，让下一轮签到有迹可循 ✨</sub>
</div>
