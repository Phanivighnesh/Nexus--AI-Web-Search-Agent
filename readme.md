# ⚡ Nexus — AI Web Search Agent

> A production-ready AI chat application that searches the web in real-time and synthesises intelligent answers. Built for deployment on Vercel via GitHub.

![Nexus](https://img.shields.io/badge/Nexus-AI%20Web%20Search-6366f1?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python)
![Flask](https://img.shields.io/badge/Flask-3.0-000000?style=for-the-badge&logo=flask)
![Vercel](https://img.shields.io/badge/Vercel-Ready-000000?style=for-the-badge&logo=vercel)

---

## Architecture

```
nexus-agent/
├── run.py                        ← Entry point (dev + gunicorn + Vercel)
├── vercel.json                   ← Vercel deployment config
├── requirements.txt              ← Python dependencies
├── .env.example                  ← Environment variable template
├── .gitignore                    ← Excludes .env, __pycache__, venv
├── README.md
│
├── app/
│   ├── __init__.py               ← Flask app factory
│   ├── config.py                 ← Pydantic-validated env config
│   ├── routes.py                 ← REST API (search, session, prefs, key validation)
│   ├── middleware.py             ← CORS, rate limiting, error handlers
│   │
│   ├── agent/
│   │   ├── models.py             ← Pydantic request/response models
│   │   ├── search.py             ← DuckDuckGo web + news search
│   │   ├── llm.py                ← Groq LLM client
│   │   └── orchestrator.py      ← Agent pipeline
│   │
│   └── utils/
│       ├── logger.py             ← Structured logging
│       ├── cache.py              ← TTL query cache
│       └── session_store.py     ← In-memory session + conversation store
│
└── static/
    └── index.html                ← Full SPA frontend (served by Flask)
```

---

## Quick Start

### 1. Clone

```bash
git clone https://github.com/your-username/nexus-agent.git
cd nexus-agent
```

### 2. Install

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure

```bash
cp .env.example .env.local
```

Edit `.env.local` — set at minimum:

```env
GROQ_API_KEY=gsk_your_key_here
FLASK_SECRET_KEY=any-random-string-here
```

> **Free Groq key:** [console.groq.com/keys](https://console.groq.com/keys) — no credit card needed.

### 4. Run

```bash
python run.py
# → http://localhost:7860
```

---

## API Key Security

Nexus supports **two modes** for API key handling:

### Mode 1 — Server key (Vercel env variable)
Set `GROQ_API_KEY` in Vercel's environment variables dashboard. All users share it. Key never touches the browser.

### Mode 2 — User key (browser localStorage)
Users enter their own Groq key in the Settings panel. It's stored in their browser's `localStorage` and sent per-request via the `X-Api-Key` header. **The key is never stored server-side.**

**Resolution order per request:**
```
1. X-Api-Key request header  (user's browser key — highest priority)
2. GROQ_API_KEY env variable (server/Vercel key)
3. Missing → 401 with prompt to add key in Settings
```

---

## Vercel Deployment

### Step 1 — Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/your-username/nexus-agent.git
git push -u origin main
```

### Step 2 — Import in Vercel

1. Go to [vercel.com/new](https://vercel.com/new)
2. Import your GitHub repository
3. Vercel auto-detects `vercel.json`

### Step 3 — Set Environment Variables

In Vercel dashboard → **Settings → Environment Variables**, add:

| Variable | Value | Notes |
|---|---|---|
| `GROQ_API_KEY` | `gsk_...` | Optional — users can supply their own |
| `FLASK_SECRET_KEY` | random 32-char hex | Required |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Optional |

> **Generate secret key:**
> ```python
> python -c "import secrets; print(secrets.token_hex(32))"
> ```

### Step 4 — Deploy

Push any commit to `main` → Vercel auto-deploys.

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/search` | Run AI web search |
| `POST` | `/api/validate-key` | Validate a Groq API key |
| `GET`  | `/api/session` | Get session + conversation list |
| `GET`/`PATCH` | `/api/preferences` | Read / update preferences |
| `POST` | `/api/conversations` | Create new conversation |
| `GET`  | `/api/conversations/:id` | Load conversation |
| `DELETE` | `/api/conversations/:id` | Delete conversation |
| `PATCH` | `/api/conversations/:id/rename` | Rename conversation |
| `GET`  | `/api/health` | Service health check |
| `GET`  | `/api/models` | List available models |

---

## Tech Stack

| Layer | Technology | Cost |
|---|---|---|
| LLM | Groq llama-3.3-70b-versatile | Free tier |
| Search | DuckDuckGo (ddgs) | Free |
| Backend | Python 3.11+ / Flask 3 | Free |
| Validation | Pydantic v2 | Free |
| Deployment | Vercel | Free tier |

---

## Security Notes

- ✅ API keys validated server-side only
- ✅ Browser-stored keys sent via `X-Api-Key` header over HTTPS
- ✅ No keys in source code or GitHub
- ✅ HTTP-only session cookies
- ✅ Per-IP rate limiting (30 req/min)
- ✅ Input validation via Pydantic
- ✅ `.env` files excluded from git

---

## License

MIT — use freely, attribution appreciated.
