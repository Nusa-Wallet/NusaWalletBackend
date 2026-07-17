# NusaWallet Backend (Core API)

FastAPI **modular monolith** — core wallet service: auth, multi-currency
wallets, double-entry ledger, payment links, dan FX settlement.
AI service (FX advisory + fraud) jalan terpisah di [NusaWalletAI](../NusaWalletAI).

## Struktur

```
app/
  core/        config, database, security (JWT, bcrypt)
  models/      User, Wallet, LedgerEntry, PaymentLink
  schemas/     Pydantic request/response
  services/    ledger (double-entry), fx (rate lookup)
  modules/     auth | wallet | payment_link | settlement | insights
  main.py      app factory + router mounts
  seed.py      demo data
```

Saldo tidak disimpan -- dihitung dari immutable ledger_entries (double-entry).

## Run (dev)

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python -m app.seed        # demo@nusawallet.id / password123
uvicorn app.main:app --reload --port 8000
```

Docs: http://localhost:8000/docs

## Authentication

- `POST /auth/login` accepts JSON (`email` + `password`) for the mobile client.
- `POST /auth/token` accepts OAuth2 form data (`username` + `password`) for Swagger.
- Protected endpoints expect `Authorization: Bearer <access_token>`.

To authorize all protected endpoints in Swagger, click **Authorize** and fill:

- `username`: the account email, for example `demo@nusawallet.id`
- `password`: the account password, for example `password123`
- `client_id` and `client_secret`: leave blank

Swagger calls `/auth/token`, stores the returned JWT, and sends it automatically to
every endpoint marked with the lock icon.

## Key endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | /auth/register, /auth/login | Register and JSON login |
| POST | /auth/token | OAuth2 form login for Swagger |
| GET  | /wallets | balances per currency |
| GET  | /wallets/{ccy}/history | ledger history |
| POST | /settlement/convert | FX conversion |
| POST | /payment-links | create payment link |
| POST | /payment-links/{code}/pay | simulate payment |
| GET  | /insights/fx-advisory | proxy ke AI advisory |
