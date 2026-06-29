# TalentIQ Platform

> AI-powered job hunting, market intelligence, and LinkedIn candidate search — built with React, FastAPI, PostgreSQL, and LangChain.

---

## What it is

TalentIQ is a full-stack SaaS platform that combines three AI agents into one product:

| Agent | What it does |
|-------|-------------|
| **JobHunt** | Scrapes live jobs (Adzuna), matches your resume with ATS scoring, generates cover letters, exports to Excel |
| **JobIntel** | Analyses job market data — skill demand, salary trends, experience levels, company-type breakdown |
| **LinkLens** | Searches LinkedIn at scale using Playwright, extracts candidate profiles, guesses contact emails, exports to Excel |

Every action is persisted to PostgreSQL, so your data compounds over time.

---

## Tech Stack

```
Frontend   React 18 + TypeScript + Vite + Recharts
Backend    FastAPI (async) + SQLAlchemy (async) + Alembic
Database   PostgreSQL 16
AI layer   LangChain + LangChain-Groq (llama3-70b-8192)
Scraping   Adzuna REST API + Playwright (LinkedIn)
Auth       JWT (python-jose) + bcrypt
```

---

## Project Structure

```
talentiq/
├── backend/
│   ├── main.py                   # FastAPI app + CORS + router registration
│   ├── db/
│   │   └── database.py           # Async SQLAlchemy engine + session factory
│   ├── models/
│   │   └── models.py             # All ORM models (User, Job, Resume, Match, Profile…)
│   ├── schemas/
│   │   └── schemas.py            # Pydantic request/response schemas
│   ├── routers/
│   │   ├── auth.py               # Register, login, profile, API keys, admin
│   │   ├── jobhunt.py            # Resume upload, job search, matching, export
│   │   ├── jobintel.py           # Market intelligence runs, analytics, records
│   │   ├── linklens.py           # LinkedIn search, profiles, export
│   │   └── dashboard.py          # Cross-agent stats aggregation
│   ├── agents/
│   │   ├── jobhunt_agent.py      # Job scraping, resume parsing, ATS matching, cover letters
│   │   ├── jobintel_agent.py     # Market analytics engine + LangChain agent
│   │   └── linklens_agent.py     # LinkedIn search URLs, profile parsing, email finder
│   ├── utils/
│   │   └── auth_utils.py         # JWT creation/verification, bcrypt, OAuth2 dep
│   ├── alembic/                  # DB migrations
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx               # Route declarations, PrivateRoute guard
│   │   ├── main.tsx              # React root entry
│   │   ├── index.css             # Full design system (CSS vars, components)
│   │   ├── lib/
│   │   │   └── api.ts            # Axios client + all API call functions
│   │   ├── hooks/
│   │   │   └── useAuth.ts        # Auth context (login, register, logout, refreshUser)
│   │   ├── components/
│   │   │   └── layout/
│   │   │       └── AppLayout.tsx # Sidebar + topbar shell
│   │   └── pages/
│   │       ├── LandingPage.tsx   # Marketing page
│   │       ├── LoginPage.tsx     # Login form
│   │       ├── RegisterPage.tsx  # Registration form
│   │       ├── DashboardPage.tsx # Stats + quick actions
│   │       ├── JobHuntPage.tsx   # Full JobHunt agent UI
│   │       ├── JobIntelPage.tsx  # JobIntel analytics UI
│   │       ├── LinkLensPage.tsx  # LinkLens candidate search UI
│   │       └── SettingsPage.tsx  # Profile, password, API keys, admin
│   ├── package.json
│   ├── vite.config.ts
│   └── Dockerfile
│
└── docker-compose.yml
```

---

## Quick Start

### Option A – Docker Compose (recommended)

```bash
# 1. Clone / place project
cd talentiq

# 2. Copy and edit environment
cp backend/.env.example backend/.env
# Edit: SECRET_KEY, GROQ_API_KEY, etc.

# 3. Start everything
docker compose up --build

# App: http://localhost:5173
# API: http://localhost:8000/docs
```

### Option B – Local development

**Prerequisites:** Python 3.12+, Node 20+, PostgreSQL 16

```bash
# 1. Database
createdb talentiq_db
createuser -P talentiq   # password: talentiq_pass

# 2. Backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium    # for LinkLens
cp .env.example .env           # edit with your keys
uvicorn main:app --reload      # http://localhost:8000

# 3. Frontend (new terminal)
cd frontend
npm install
npm run dev                    # http://localhost:5173
```

---

## API Keys Setup

Go to **Settings → API Keys** after logging in to save your keys:

| Service | Keys needed | Where to get |
|---------|------------|--------------|
| **Adzuna** | `app_id`, `app_key` | [developer.adzuna.com](https://developer.adzuna.com) — free tier |
| **Groq** | `api_key` | [console.groq.com](https://console.groq.com) — free tier |
| **LinkedIn** | `email`, `password` | Your own LinkedIn account |

> Default Adzuna keys are pre-filled in `.env.example` for quick testing.

---

## Database Schema (key tables)

```
users               → all platform users, roles, auth
user_api_keys       → per-user external API keys (encrypted)
resumes             → uploaded resume files + parsed data
job_searches        → every search session with criteria
jobs                → individual job listings from Adzuna
job_matches         → ATS scores, strengths, gaps, cover letters
jobintel_runs       → market intelligence analysis sessions
jobintel_records    → individual enriched job records per run
linklens_searches   → LinkedIn candidate search sessions
linkedin_profiles   → scraped profile data (skills, experience, email)
audit_logs          → full action history per user
```

---

## API Reference

Interactive docs available at `http://localhost:8000/docs`

### Auth
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/register` | Create account |
| POST | `/api/auth/login` | Login → JWT token |
| GET | `/api/auth/me` | Get current user |
| PUT | `/api/auth/me` | Update profile |
| POST | `/api/auth/api-keys` | Save API key |
| GET | `/api/auth/api-keys` | List saved keys |

### JobHunt
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/jobhunt/resume` | Upload resume (PDF/DOCX/TXT) |
| POST | `/api/jobhunt/search` | Search jobs via Adzuna |
| POST | `/api/jobhunt/match` | Match resume to jobs (ATS scoring) |
| GET | `/api/jobhunt/matches` | List all matches |
| GET | `/api/jobhunt/export/{search_id}` | Download Excel export |

### JobIntel
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/jobintel/run` | Start market analysis (async) |
| GET | `/api/jobintel/runs` | List all runs |
| GET | `/api/jobintel/runs/{id}` | Get run status + insights |
| GET | `/api/jobintel/runs/{id}/records` | Get enriched job records |

### LinkLens
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/linklens/search` | Start LinkedIn search (async) |
| GET | `/api/linklens/searches` | List all searches |
| GET | `/api/linklens/searches/{id}` | Get search + profiles |
| GET | `/api/linklens/searches/{id}/export` | Download Excel export |

### Dashboard
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/dashboard/stats` | Aggregated stats across all agents |

---

## Authentication Flow

```
Register / Login
     │
     ▼
POST /api/auth/login
     │ → { access_token, user }
     │
     ▼
Store token in localStorage
     │
     ▼
All subsequent requests include:
Authorization: Bearer <token>
```

First registered user automatically becomes **admin** and gets access to the user management panel in Settings.

---

## LangChain Agent Architecture

Each agent is built as a LangChain `ReActAgent` with domain-specific tools:

```
JobHunt Agent
  ├── Tool: ScrapeJobs     → Adzuna API
  ├── Tool: ParseResume    → text extraction + keyword analysis
  ├── Tool: MatchResume    → ATS scoring (keyword + optional LLM)
  └── Tool: GenerateCover  → template + optional Groq LLM

JobIntel Agent
  ├── Tool: ScrapeJobMarket → Adzuna API
  ├── Tool: AnalyseSkills   → Counter-based analytics
  └── Tool: GenerateReport  → Groq LLM summary

LinkLens Agent
  ├── Tool: SearchLinkedIn  → Playwright URL generation + scraping
  ├── Tool: ScrapeProfile   → BeautifulSoup HTML parsing
  └── Tool: FindEmail       → Pattern-based email guessing
```

When a **Groq API key** is provided, agents switch from keyword-matching to LLM-powered analysis for significantly better quality results.

---

## Extending the Platform

### Add a new agent

1. Create `backend/agents/myagent_agent.py` with your tools
2. Create `backend/routers/myagent.py` with FastAPI routes
3. Register in `backend/main.py`: `app.include_router(myagent.router, prefix="/api/myagent")`
4. Add ORM models in `backend/models/models.py`
5. Add Pydantic schemas in `backend/schemas/schemas.py`
6. Add API calls in `frontend/src/lib/api.ts`
7. Create `frontend/src/pages/MyAgentPage.tsx`
8. Add route in `frontend/src/App.tsx` and nav item in `AppLayout.tsx`

### Switch LLM provider

In `agents/*.py`, swap `ChatGroq` for any LangChain-compatible LLM:
```python
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(api_key="...", model="gpt-4o")
```

---

## Environment Variables

```env
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dbname
SECRET_KEY=your-jwt-secret
ADZUNA_APP_ID=638c0962
ADZUNA_APP_KEY=your-key
GROQ_API_KEY=gsk_...
EMAIL_USER=smtp-email@gmail.com
EMAIL_PASSWORD=gmail-app-password
```

---

## License

MIT
