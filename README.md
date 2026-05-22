# Financisto Web

Self-hosted personal finance webapp, migrated from the Android app [Financisto](https://github.com/tiberiusteng/financisto1-holo). Designed to run on a home server (Proxmox/Docker) with email integration for automatic transaction import.

## Features

- **Accounts** — Full CRUD, drag & drop reordering, multiple account types (bank, card, cash, etc.)
- **Transactions** — Create, edit, delete with category, payee, notes. Infinite scroll, filters by account/category/date
- **Categories** — Hierarchical tree with subcategories (nested set model)
- **Reports** — Monthly/yearly income vs expense, daily breakdown by category (stacked), savings trend, category pie chart
- **Email Integration** — IMAP worker polls Gmail for bank notifications (Webank, NumiaPay) and creates transactions automatically
- **Import/Export** — Import Financisto `.backup` files, full DB export/import as JSON
- **Backup to S3** — Configurable automatic backup to AWS S3
- **Responsive** — Mobile-first with bottom nav, desktop sidebar. Works on phone and PC
- **Pending transactions** — Uncategorized transactions highlighted with ⏳ indicator

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌──────────────┐
│   Nginx     │────▶│  Flask API  │────▶│ PostgreSQL 16│
│  (frontend) │     │  (backend)  │     │              │
└─────────────┘     └─────────────┘     └──────────────┘
      :80                :5000                :5432
                    ┌─────────────┐
                    │Email Worker │──── Gmail IMAP
                    └─────────────┘
```

- **Frontend**: Vanilla HTML/JS + Chart.js, served by Nginx
- **Backend**: Python Flask REST API
- **Database**: PostgreSQL 16
- **Email Worker**: Python IMAP poller with bank-specific parsers

## Quick Start

```bash
cp .env.example .env
# Edit .env with your Gmail app password and account mapping
docker compose up -d
```

Open http://localhost:8080

## Configuration

### `.env` file

```env
GMAIL_USER=your@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
ACCOUNT_MAP={"bank": 1, "card": 2}
```

### Email Worker

The worker polls Gmail every 5 minutes for emails from configured bank senders. It parses amount, date, and payee from the email body and creates transactions via the API. Deduplication prevents double entries.

Supported email formats:
- **Bank statements** — HTML emails with table containing amount, description, date
- **Card notifications** — Real-time payment notifications with amount and merchant

### S3 Backup

Configure via the web UI (Import section → Backup Automatico S3) or API:
```bash
curl -X POST http://localhost:8080/api/backup/config \
  -H 'Content-Type: application/json' \
  -d '{"enabled": true, "bucket": "my-bucket", "region": "eu-west-1", "access_key": "...", "secret_key": "...", "interval_hours": 24}'
```

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/accounts` | GET, POST | List/create accounts |
| `/api/accounts/:id` | PUT, DELETE | Update/close account |
| `/api/transactions` | GET, POST | List/create transactions |
| `/api/transactions/search` | GET | Filter by account, category, payee, date |
| `/api/transactions/:id` | PUT, DELETE | Update/delete transaction |
| `/api/categories` | GET, POST | List/create categories |
| `/api/categories/tree` | GET | Hierarchical tree |
| `/api/categories/:id/subcategory` | POST | Create subcategory |
| `/api/payees` | GET, POST | List/create payees |
| `/api/stats/monthly` | GET | Monthly income/expense |
| `/api/stats/yearly` | GET | Yearly summary |
| `/api/stats/by-category` | GET | Expense by category |
| `/api/stats/daily-by-category` | GET | Daily stacked by category |
| `/api/stats/savings` | GET | Cumulative savings trend |
| `/api/export` | GET | Human-readable JSON export |
| `/api/db/export` | GET | Full DB export (reimportable) |
| `/api/db/import` | POST | Full DB import |
| `/api/import` | POST | Import Financisto .backup |
| `/api/backup/config` | GET, POST | S3 backup configuration |
| `/api/backup/now` | POST | Trigger immediate backup |

## License

Personal project. Based on data format from [Financisto](https://github.com/tiberiusteng/financisto1-holo) (GPL-2.0).
