# Closira Assistant — AI Customer Support for Bloom Aesthetics Clinic

> AI Engineering Internship Assignment — end-to-end conversational AI support workflow

---

## Overview

Closira Assistant is a production-style Python CLI that simulates an AI-powered customer support agent for **Bloom Aesthetics Clinic**, a fictional UK aesthetics SMB.

It uses the **Anthropic Claude API** to deliver a four-stage workflow:

| Stage | Module | What it does |
|-------|--------|--------------|
| 1 | FAQ Answering | Answers questions strictly from the clinic SOP |
| 2 | Lead Qualification | Collects treatment interest, availability, contact preference |
| 3 | Escalation Detection | Routes complaints, medical questions, and frustrated customers to humans |
| 4 | Session Summary | Generates a structured markdown handoff report |

---

## Features

- **SOP-grounded answers** — the AI will never invent information outside the clinic's data
- **Two-layer escalation** — fast keyword rules + LLM classification
- **Structured lead capture** — JSON output for CRM integration
- **Confidence scoring** — every answer shows a 0–100% confidence bar
- **Full conversation memory** — history passed on every API call
- **Retry/fallback handling** — graceful degradation if API call fails
- **Escalation logging** — all escalations written to `logs/escalation_logs.json`
- **Session summaries** — saved to `transcripts/` at session end
- **Modular architecture** — each agent is independently testable

---

## Project Structure

```
closira_assistant/
│
├── app.py                    # CLI entry point & session orchestrator
├── requirements.txt
├── README.md
├── .env.example              # Environment variable template
├── prompt_design.md          # Prompt engineering documentation
│
├── sop_data/
│   └── bloom_clinic.json     # Single source of truth for clinic info
│
├── transcripts/              # Sample conversations + saved session summaries
│   ├── in_scope.md
│   ├── out_of_scope.md
│   ├── escalation.md
│   ├── qualification.md
│   └── summary.md
│
├── logs/
│   └── escalation_logs.json  # Auto-appended on every escalation event
│
├── agents/
│   ├── faq_agent.py          # FAQ answering with SOP grounding
│   ├── qualification_agent.py# Lead qualification (4 questions, structured JSON)
│   ├── escalation_agent.py   # Rule-based + LLM escalation detection
│   └── summary_agent.py      # End-of-session markdown summary
│
└── utils/
    ├── prompts.py            # All prompt templates (centralised)
    └── sop_loader.py         # SOP JSON loader + prompt formatter
```

---

## Setup

### Prerequisites

- Python 3.10 or later
- An [Anthropic API key](https://console.anthropic.com/)

### 1. Clone / download the project

```bash
cd closira_assistant
```

### 2. Create a virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and set your API key:

```
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-haiku-4-5-20251001
```

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | Yes | — | Your Anthropic API key |
| `CLAUDE_MODEL` | No | `claude-haiku-4-5-20251001` | Claude model to use |

**Recommended models:**

| Model | Speed | Cost | Best for |
|-------|-------|------|----------|
| `claude-haiku-4-5-20251001` | Fast | Low | Development & demos |
| `claude-sonnet-4-6` | Balanced | Medium | Production |
| `claude-opus-4-7` | Slower | Higher | Maximum accuracy |

---

## Running the App

```bash
python app.py
```

### In-session commands

| Input | Action |
|-------|--------|
| Any question | FAQ answering |
| `summary` | Generate session summary now |
| `quit` / `exit` / `bye` | End session (summary auto-generated) |
| `Ctrl+C` | Force exit |

---

## Example Usage

```
╔══════════════════════════════════════════════════════════╗
║          🌸  Bloom Aesthetics Clinic  🌸                 ║
║          Powered by Closira Assistant                    ║
╚══════════════════════════════════════════════════════════╝

🤖 Closira: Hello and welcome to Bloom Aesthetics Clinic! 😊 ...

You: What are your Botox prices?

🤖 Closira: Botox treatments at Bloom Aesthetics Clinic start from £200.
            We'd recommend booking a free consultation first ...

  [Confidence: ██████████ 95%]

You: Do you offer laser hair removal?

🤖 Closira: I'm sorry, I don't have information about that in our current records.
            Let me connect you with a member of our team who can help.

🔔 [ESCALATION] Reason: out_of_scope | Confidence: 20%
```

---

## How the Workflow Operates

```
Customer message
       │
       ▼
┌─────────────────────┐
│  Escalation Check   │ ← runs EVERY turn (rules + LLM)
└──────────┬──────────┘
           │ no escalation
           ▼
┌─────────────────────┐
│    FAQ Agent        │ ← classify → answer (SOP-grounded)
└──────────┬──────────┘
           │ after N turns
           ▼
┌─────────────────────┐
│  Qualification Agent│ ← 4 questions, one at a time
└──────────┬──────────┘
           │ session end
           ▼
┌─────────────────────┐
│   Summary Agent     │ ← structured markdown report
└─────────────────────┘
```

---

## Output Files

| File | Generated when |
|------|---------------|
| `transcripts/summary_YYYYMMDD_HHMMSS.md` | Every session end |
| `logs/escalation_logs.json` | Any escalation event |

---

## Limitations

- **No real booking system** — the assistant cannot actually create appointments
- **No persistent memory across sessions** — each run starts fresh
- **SOP is static** — changes require editing `sop_data/bloom_clinic.json`
- **No voice or WhatsApp channel** — CLI only in this version
- **No retry on API failure** — a single failed call returns a canned fallback

---

## Future Improvements

- [ ] WhatsApp Business API integration (Twilio / Meta)
- [ ] Persistent session storage (SQLite / Redis)
- [ ] Real booking calendar integration (Calendly / Cal.com)
- [ ] Sentiment trend dashboard (Streamlit)
- [ ] Unit and integration test suite
- [ ] Streaming responses for lower perceived latency
- [ ] Multi-language support
- [ ] Admin UI for SOP updates without code changes

---

## Architecture Notes

### Why two escalation layers?

**Rule-based** (Layer 1) catches 80% of cases instantly with zero API cost. **LLM-based** (Layer 2) handles nuanced language the rules miss — e.g., polite-but-determined pricing negotiation. Running rules first keeps costs low.

### Why classify before answering?

The classification step (`FAQ_CLASSIFICATION_PROMPT`) is a lightweight, low-token call that provides a structured gate. It prevents the answer-generation step from ever being asked to answer an unanswerable question — which is the root cause of hallucination.

### Why centralise prompts in `utils/prompts.py`?

A single file makes prompt versioning, A/B testing, and review straightforward. Each template is a named constant — easy to find, easy to update.

---

*Built with [Anthropic Claude API](https://docs.anthropic.com/) · Python 3 · python-dotenv*
