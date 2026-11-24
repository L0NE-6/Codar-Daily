# Third-Party Notices

This repository contains an independently written Python implementation of the
Codar daily check-in flow. Credentials are supplied at runtime and are not
included in the repository.

The protocol evidence reviewed for this implementation is recorded below so
that request paths, authentication headers, request bodies, status fields, and
readback rules remain auditable. No source code from either evidence project
was copied or vendored into `codar_daily.py`.

## magpie-plugin-codar

- Repository: <https://github.com/MisonL/magpie-plugin-codar>
- Fixed commit: `2651dbcb4ce50ada3411e59a136f01fb1a267cf3`
- License: MIT
- Copyright: `Copyright (c) 2026 MisonL`
- Evidence used: `POST /v1/daily-sign/status`, `POST /v1/daily-sign`,
  `Authorization: Bearer`, `{"username": ...}`, `isSigned`/`signed`/
  `hasSigned`/`has_signed`, `retry_after`, and the rolling 24-hour window.

MIT License

Copyright (c) 2026 MisonL

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Agent2Providers Codar provider

- Repository: <https://github.com/ProvidersPlugin/Agent2Providers>
- Fixed commit: `b35b163d01fc3effb30ae40a012fd657fdc0a54d`
- Package license at the reviewed commit: AGPL-3.0-only
- Relevant paths: `wasm/codar/src/checkin.rs`, `wasm/codar/src/network.rs`,
  `wasm/codar/src/endpoints.rs`, `wasm/codar/src/token.rs`,
  `wasm/codar/src/credentials.rs`, `wasm/codar/src/account.rs`
- Evidence used: status-before-claim ordering, strict status-after-claim
  verification, `User-Agent: node`, JSON request bodies, and the
  `isSigned`/`signed`/`hasSigned`/`has_signed` readback rule.

The reviewed package contains its own third-party notices under
`wasm/codar/licenses/`. Those files remain in the evidence project and are not
relicensed by this repository.

## Runtime dependencies

- `requests` is installed from PyPI under its own license.

## Trademarks

Codar, SpeedAI, and related names or marks belong to their respective owners.
This independent repository is not affiliated with or endorsed by them.
