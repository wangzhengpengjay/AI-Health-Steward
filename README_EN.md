# AI Health Steward

[中文文档](README.md)

> Self-hosted, privacy-first family AI health steward. Multimodal AI structures medical reports and lab results into per-person health profiles, with AI consultation, metric trends, checkup recommendations, risk self-assessment, and more. All data stays on your server.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Online Page](https://img.shields.io/badge/Online%20Page-online-brightgreen)](https://wangzhengpengjay.github.io/AI-Health-Steward/)

---

## Why this project

Most health apps are black boxes: your lab results, diagnoses, and medications get uploaded to someone else's cloud and monetized. **AI Health Steward is the opposite.**

- **Your data never leaves your server** — health records, reports, and profiles live entirely on hardware you control
- **One instance serves your whole family** — multi-member with fully isolated data
- **Bring your own AI** — plug in any OpenAI-compatible model (GPT-4o, DeepSeek, etc.) or run fully offline with a local LLM (Ollama)
- **Mobile too** — Capacitor iOS/Android apps, pairing code binding, secure public access

> A health record is the most sensitive data you own. It should not be a product. It should live on your shelf.

---

## Core Features

- **Multimodal Report Import** — upload photos of medical reports; AI extracts structured key metrics
- **Person-Level Health Profile** — basic info / physiological metrics / diagnoses / medications / allergies / lifestyle / family history
- **AI Health Consultation** — answers grounded in your actual profile data, not a generic chatbot
- **Metric Trend Visualization** — blood pressure / glucose / heart rate / weight trends with abnormal markers and critical-value alerts
- **Personalized Checkup Recommendations** — 1+X+Y framework for customized checkup plans
- **Risk Self-Assessment** — 9 built-in scales (PHQ-9 / GAD-7 / diabetes / cardiovascular / insomnia / hypertension / dyslipidemia / AD8 / stroke)
- **Proactive Health Agent** — scheduled patrol engine, rule + AI dual-layer inference, auto-push health reminders
- **Follow-up / Medication Reminders** — auto-generated todo tasks based on critical values, abnormal metrics, medications
- **Periodic Health Summaries** — auto weekly/monthly/yearly reports with trends, anomalies, and follow-up items
- **Feishu / Lark Integration** — multiple bots, one per family member; WebSocket for text Q&A and image parsing
- **Mobile App** — Capacitor WebView, pairing code binding, secure public network access

---

## Quick Start

### Prerequisites

- Docker 20.10+ and docker-compose v2+
- Model API Key (OpenAI-compatible endpoint, e.g., GPT-4o / DeepSeek)
- Minimum: 2 CPU cores / 2GB RAM / 10GB disk

### Deployment

```bash
# 1. Clone the repository
git clone https://github.com/zhengpengwangjay/AI-Health-Steward.git
cd AI-Health-Steward

# 2. Copy environment config and fill in credentials
cp .env.example .env
# Edit .env — at minimum, set MULTIMODAL_API_KEY and TEXT_API_KEY

# 3. Sync config to backend/.env
cp .env backend/.env

# 4. Create user data directory
mkdir -p userdata

# 5. Build and start (production mode)
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d

# 6. Access
# WebUI: http://localhost:5173
# API Docs: http://localhost:18000/docs
```

> Development mode (hot-reload): use `docker compose up -d`. Both modes share the same database and user data.

### Mobile Connection

After deployment, configure public access in the WebUI settings:

1. Open **Settings → Mobile Device Pairing**
2. Choose a fixed domain scheme (Cloudflare Tunnel / Caddy / Tailscale)
3. Follow the guided setup to configure a fixed address
4. Generate a pairing code, enter the address and code in the mobile app

See the setup guide panel in the settings page for detailed steps.

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.12 + FastAPI |
| Frontend | React 18 + Vite + TypeScript + TailwindCSS |
| Database | PostgreSQL 16 + pgvector |
| Mobile | Capacitor (iOS / Android) |
| AI | OpenAI-compatible API (multimodal/text) + Ollama (local LLM) |
| Deployment | Docker Compose |

---

## Project Structure

```
AI-Health-Steward/
├── backend/                 # Python FastAPI backend
│   ├── app/
│   │   ├── api/routes/      # API routes (members/metrics/chat/reports/checkup/profile/settings/feishu/scales/tasks/summaries/pairing)
│   │   ├── core/            # Config, database, auth/rate-limit, security
│   │   ├── models/          # SQLAlchemy models (family/health/feishu/assessments/tasks/summaries/paired_devices)
│   │   ├── services/        # Business logic (consultation/extraction/checkup/feishu/memory/tasks/summaries/patrol_engine)
│   │   │   └── tools/       # AI tools (function calling)
│   │   ├── prompts/         # AI prompt templates
│   │   └── providers/       # Model provider abstraction (multimodal/text/local/embedding)
│   ├── alembic/             # Database migrations
│   └── tests/               # Unit tests
├── frontend/                # React frontend (WebUI)
│   └── src/
│       ├── components/      # UI components
│       ├── pages/           # Pages
│       ├── stores/          # Zustand state management
│       └── lib/             # API client
├── docker-compose.yml       # Development deployment (hot-reload)
├── docker-compose.prod.yml  # Production deployment (no hot-reload)
├── .env.example             # Environment variable template
└── README.md
```

---

## Privacy

- **Data Storage**: All health data is stored on your local server — nothing is uploaded to the cloud automatically
- **Model API Calls**: Conversation content and report images are sent to your configured model API provider. For fully offline operation, configure a local LLM (e.g., Ollama)
- **Data Export**: Users can export all health data (JSON format) anytime
- **Data Deletion**: Supports single-record deletion and full-member deletion (soft delete, hard delete after 30 days)
- **Mobile Pairing**: Pairing tokens stored in iOS Keychain / Android Keystore, never uploaded to any third party

---

## Contributing

Issues and PRs are welcome! Please read the [Contributing Guide](CONTRIBUTING.md) first.

## Documentation

- [Deployment Guide](DEPLOYMENT.md) — Docker setup, configuration, Feishu bot setup
- [Developer Guide](DEVELOPMENT.md) — Architecture, extension guides
- [Privacy Statement](PRIVACY.md) — Data storage and model API boundaries

## License

[MIT](LICENSE)
