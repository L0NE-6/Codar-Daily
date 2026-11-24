# Codar Daily

**Check-in diário do Codar · várias contas · janela móvel de 24 horas · leitura estrita no servidor**

[简体中文](../README.md) · [English](README.en.md) · [繁體中文](README.zh-Hant.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · Português (BR)

## O que faz

`codar_daily.py` consulta o status da conta Codar, só envia o pedido quando o
servidor informa explicitamente que a janela atual está sem check-in e consulta
o status novamente depois. A resposta do pedido, sozinha, nunca é tratada como
sucesso.

## Protocolo

```text
POST https://api.kuaipaper.com/v1/daily-sign/status
POST https://api.kuaipaper.com/v1/daily-sign

Authorization: Bearer <JWT>
Content-Type: application/json
Accept: application/json
User-Agent: node

{"username":"<account>"}
```

O leitor aceita `isSigned`, `signed`, `hasSigned` e `has_signed` somente como
booleanos JSON reais. O resultado final vem de uma nova consulta de status.

## Credenciais

| Variável | Obrigatória | Descrição |
| :--- | :---: | :--- |
| `CODAR_TOKENS` | uma opção | Vários JWTs, separados por vírgula ou linha |
| `CODAR_TOKEN` | uma opção | Um JWT |
| `CODAR_COOKIES` | uma opção | Vários cookies, um por linha |
| `CODAR_COOKIE` | uma opção | Um cookie |
| `CODAR_USERNAME` | opcional | Usuário para um cookie único |
| `CODAR_READBACK_ATTEMPTS` | opcional | Tentativas de leitura, padrão `3` |
| `CODAR_READBACK_DELAY` | opcional | Intervalo entre leituras, padrão `1` s |

Formato de token:

```text
principal|<JWT>
secundaria|<username>|<JWT>
```

Cookies usam `nota|Cookie` ou `nota|username|Cookie`. O cookie deve conter um
JWT em uma chave como `token`, `access_token`, `accessToken`, `authorization`,
`jwt` ou `codar_token`.

## Execução

```powershell
python -m pip install -r requirements.txt
$env:CODAR_TOKEN = "<JWT>"
python codar_daily.py
```

Somente status:

```powershell
python codar_daily.py --status
```

Comando no Qinglong: `task codar_daily.py`.

## GitHub Actions

Adicione `CODAR_TOKENS`, `CODAR_TOKEN`, `CODAR_COOKIES` ou `CODAR_COOKIE` nos
Secrets. O workflow executa testes offline no push e verifica a cada seis horas
no agendamento. Na janela móvel de 24 horas, uma execução antecipada apenas lê
o status.

Relatórios:

- `codar-report.jsonl`
- `codar-report.json`

## Sucesso

| Resultado | Significado |
| :--- | :--- |
| `CLAIMED` | Status pós-pedido confirma check-in |
| `ALREADY_CLAIMED` | Status já confirmava check-in |
| `AVAILABLE` | Consulta encontrou janela sem check-in |
| `CLAIM_NOT_APPLIED` | Pedido respondeu, mas o status continuou sem check-in |
| `READBACK_UNCONFIRMED` | Não foi possível confirmar o status |
| `STATUS_UNRECOGNIZED` | Não há boolean de status explícito |

Códigos de saída: `0` tudo confirmado, `1` alguma falha, `2` erro de
configuração.

## Segurança

As credenciais são lidas somente de variáveis de ambiente ou GitHub Secrets.
Tokens, cookies, JWTs e valores ecoados pelo servidor são mascarados. Não
envie arquivos de autenticação, relatórios, tokens, cookies, telefones ou
capturas com dados sensíveis.

## Licença

Implementação local: [MIT](../LICENSE). Limites de uso:
[NOTICE.md](../NOTICE.md). Licenças de terceiros e evidências do protocolo:
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).
