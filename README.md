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
python -m app.seed
uvicorn app.main:app --reload --port 8000
```

Docs: http://localhost:8000/docs

## Demo operability

From the workspace root, start the full demo stack with:

```powershell
.\scripts\demo.ps1
```

Use `-SkipInstall` when dependencies and seed data are already prepared:

```powershell
.\scripts\demo.ps1 -SkipInstall
```

After the services are ready, run the backend smoke flow:

```powershell
cd NusaWalletBackend
.\.venv\Scripts\python.exe scripts\smoke_demo.py
```

The smoke flow checks backend + AI health, demo login, wallet retrieval, public
payment checkout rendering, sandbox payment, FX advisory, conversion, and
conversion idempotency.

## Minimal deploy hardening

Development defaults are optimized for the hackathon demo. For a deployed
environment, set:

```env
APP_ENV=production
JWT_SECRET=<long-random-secret>
CORS_ALLOW_ORIGINS=https://your-mobile-web-origin.example
AUTO_CREATE_TABLES=false
DATABASE_URL=postgresql+psycopg2://...
AI_SERVICE_URL=https://your-ai-service.example
```

When `APP_ENV=production`, the app refuses to start with the demo JWT secret,
wildcard CORS, or automatic table creation. Swagger/OpenAPI routes are also
disabled in production mode. Use migrations, not `Base.metadata.create_all`, for
schema changes outside the demo environment.

## Demo Credentials

| Nama | Email | Password |
|------|-------|----------|
| John Doe | john.doe@example.com | password123 |
| Sarah Wijaya | sarah.wijaya@example.com | password123 |

John Doe memiliki wallet IDR (75jt), USD (2,855), EUR (1,950).
Sarah Wijaya memiliki wallet IDR (45jt), USD (2,070), SGD (2,350).

## Authentication

- `POST /auth/login` accepts JSON with either (`email` + `password`) or
  (`phone` + `password`) for the mobile client.
- `POST /auth/token` accepts OAuth2 form data (`username` + `password`) for Swagger.
- Protected endpoints expect `Authorization: Bearer <access_token>`.

To authorize all protected endpoints in Swagger, click **Authorize** and fill:

- `username`: `john.doe@example.com` or `sarah.wijaya@example.com`
- `password`: `password123`
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
