# 🏥 AI Health Steward

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)
[![Docker](https://img.shields.io/badge/deploy-Docker%20Compose-2496ed.svg?style=for-the-badge)](DEPLOYMENT.md)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB.svg?style=for-the-badge)](backend)
[![React](https://img.shields.io/badge/React-18-61DAFB.svg?style=for-the-badge)](frontend)

[中文文档](README.md) · [Online Page](https://wangzhengpengjay.github.io/AI-Health-Steward/)

> **Most health apps are black boxes. Your lab results, diagnoses, and medications get uploaded to someone else's cloud and monetized. AI Health Steward is the opposite — data stays on your server, AI is your choice, and your phone connects too.**

---

## ✨ Core Capabilities

| What you want | Traditional apps | AI Health Steward |
|---|---|---|
| Medical report interpretation | Manual data entry | Upload a photo, AI extracts structured metrics |
| AI health consultation | Generic chatbot | Answers grounded in your actual health profile |
| Metric trend tracking | Manual logs + limited charts | BP/glucose/heart rate/weight trends + critical alerts |
| Checkup recommendations | Generic packages | Personalized 1+X+Y plan based on your profile |
| Risk self-assessment | Download separate apps | 9 built-in scales (PHQ-9/GAD-7/diabetes/cardiovascular...) |
| Mobile access | Must use vendor cloud | Self-hosted server + pairing code, no third party |
| Data ownership | Data belongs to the vendor | Data lives on your own hardware |

---

## 🚀 Quick Start

```bash
git clone https://github.com/zhengpengwangjay/AI-Health-Steward.git
cd AI-Health-Steward
cp .env.example .env          # Fill in your API key
cp .env backend/.env
mkdir -p userdata
docker compose -f docker-compose.prod.yml up -d

# Open http://localhost:5173 to get started
```

**Prerequisites**: Docker 20.10+ · Model API key (OpenAI-compatible, e.g. DeepSeek/GPT-4o) · 2 cores 2GB minimum

### 📱 Mobile Connection

After deployment, generate a pairing code in settings, enter the address + code on your phone. Supports Cloudflare Tunnel / Caddy / Tailscale for public access — full setup guide in the settings page.

---

## 🧠 Why this project

A pile of medical reports at home, forgotten after reading. Want AI to help interpret them, but don't want to upload family lab results to a stranger's server.

**So I built a health steward that runs on my own computer:**

- 🔒 **Data never leaves your server** — health records on your hardware, not a SaaS database
- 🏠 **One instance, whole family** — multi-member with isolated data
- 🤖 **AI is your choice** — plug in GPT-4o / DeepSeek / Ollama, cloud or local
- 📱 **Mobile too** — Capacitor iOS/Android apps, pairing code binding, secure public access
- 💰 **Zero cost** — MIT open source, no subscriptions, no paywalls

---

## 🏗️ Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Backend | Python 3.12 + FastAPI | Async performance, auto API docs |
| Frontend | React 18 + Vite + TypeScript + TailwindCSS | Modern dev experience, hot reload |
| Database | PostgreSQL 16 + pgvector | RAG vector search for report semantics |
| Mobile | Capacitor | 95% code reuse from web, one codebase for iOS/Android |
| AI | OpenAI-compatible API + Ollama | Cloud (DeepSeek/GPT-4o) or fully offline |

---

## 📦 Project Structure

```
AI-Health-Steward/
├── backend/                 # Python FastAPI backend
│   ├── app/
│   │   ├── api/routes/      # 14 API modules (chat/reports/profile/pairing/feishu...)
│   │   ├── core/            # Security · auth · rate limiting · reference ranges
│   │   ├── models/          # Data models (including paired devices)
│   │   ├── services/        # Business logic (AI consultation/extraction/patrol engine)
│   │   └── providers/       # Model abstraction (multimodal/text/local/embedding)
│   └── alembic/             # Database migrations
├── frontend/                # React frontend (WebUI)
│   └── src/
│       ├── components/      # MobileNav · MobileHeader · ChatBubble...
│       ├── pages/           # 12 pages
│       ├── stores/          # Zustand state management
│       └── lib/             # API client + pairing client
├── docker-compose.yml       # Development (hot reload)
├── docker-compose.prod.yml  # Production (24/7 stable)
└── .env.example             # Config template (keys are placeholders)
```

---

## 🔐 Privacy Boundaries

| Data | Where it goes | Your control |
|---|---|---|
| Health records, reports, profiles | **Your server** | ✅ Export/delete anytime |
| Conversation content, report images | **Your chosen model API** | ✅ Use Ollama for full offline |
| Pairing tokens | **Phone Keychain/Keystore** | ✅ Revoke devices anytime |
| Health data | **Never uploaded to third parties** | ✅ Data on your disk |

---

## 📋 Full Feature List

<details>
<summary>Click to expand all features</summary>

- **Multimodal Report Import** — upload photos of medical reports; AI extracts structured metrics
- **Person-Level Health Profile** — basic info / physiological metrics / diagnoses / medications / allergies / lifestyle / family history
- **AI Health Consultation** — intent routing + tool calling, grounded in your actual profile data
- **Metric Trend Visualization** — BP/glucose/heart rate/weight trends with abnormal markers and critical-value alerts
- **Personalized Checkup Recommendations** — 1+X+Y framework for customized checkup plans
- **Risk Self-Assessment** — 9 built-in scales (PHQ-9 / GAD-7 / diabetes / cardiovascular / insomnia / etc.)
- **Proactive Health Agent** — scheduled patrol engine, rule + AI dual-layer inference, auto-push reminders
- **Follow-up / Medication Reminders** — auto-generated todo tasks based on critical values and medications
- **Periodic Health Summaries** — auto weekly/monthly/yearly reports with trends and follow-up items
- **Report Semantic Search (RAG)** — archived reports auto-vectorized for semantic Q&A
- **Feishu / Lark Integration** — multiple bots, one per family member; WebSocket for text Q&A and image parsing
- **Mobile App** — Capacitor WebView, pairing code binding, secure public network access
- **Long-Term Conversation Memory** — each consultation rolls into compressed per-member memory
- **Age-Tiered Reference Ranges** — auto-matched to adult vs. child
- **Visit Preparation** — chief complaint-driven department recommendations, AI-generated checklists, PDF export

</details>

---

## 🤝 Contributing

Issues and PRs welcome! Please read the [Contributing Guide](CONTRIBUTING.md) first.

## 📖 Documentation

- [Deployment Guide](DEPLOYMENT.md) · [Developer Guide](DEVELOPMENT.md) · [Privacy Statement](PRIVACY.md)

## License

[MIT](LICENSE)
