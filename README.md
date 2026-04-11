# PredictiveEng

> Predictive engineering intelligence that tells you where your codebase will break — before it does.

PredictiveEng is a multi-agent platform that analyzes public GitHub repositories and surfaces actionable insights about code health, security risks, developer burnout, cascade failure potential, and technical debt. It doesn't just report what's wrong — it predicts what's going to *cost you* if you ignore it.

---

## Why This Exists

Most code analysis tools dump a wall of metrics on you. Lines of code. Cyclomatic complexity numbers. Maybe a badge that says "B+". None of that tells an engineering lead (or a CEO) what actually matters:

- **Which file is going to cause an outage next month?**
- **How much will it cost us if we don't fix this now vs. 6 months from now?**
- **Is our team burning out?**

PredictiveEng answers those questions. It runs six specialized agents in parallel, combines their outputs into a unified health model, and generates an executive-grade AI brief that turns raw analysis into business decisions.

---

## Architecture

The system is built around a **multi-agent pipeline** where each agent is responsible for one domain of analysis. The orchestrator (`analyzer.py`) clones the repo, runs agents in parallel using thread pools, and assembles the final result.

```
┌──────────────────────────────────────────────────────────────────┐
│                         FastAPI Server                           │
│                        (main_FINAL.py)                           │
│                                                                  │
│  ┌─────────────┐    ┌─────────────────────────────────────────┐  │
│  │  REST API   │───▶│           Orchestrator                  │  │
│  │  Endpoints  │    │          (analyzer.py)                   │  │
│  └─────────────┘    │                                         │  │
│                     │   Stage 1 (parallel):                   │  │
│                     │     • Commit Analysis (PyDriller)        │  │
│                     │     • Code Quality (Radon CC + MI)       │  │
│                     │                                         │  │
│                     │   Stage 2 (parallel):                   │  │
│                     │     • Security Scanner                   │  │
│                     │     • Burnout Detector                   │  │
│                     │     • Cascade Analyzer                   │  │
│                     │     • Test Coverage                      │  │
│                     │                                         │  │
│                     │   Stage 3 (parallel):                   │  │
│                     │     • Dependency Risk                    │  │
│                     │     • Deployment Readiness               │  │
│                     │     • Technical Debt Calculator           │  │
│                     │                                         │  │
│                     │   Stage 4:                               │  │
│                     │     • AI Reporter (LLM executive brief)  │  │
│                     └─────────────────────────────────────────┘  │
│                                                                  │
│  ┌─────────────┐    ┌─────────────────────────────────────────┐  │
│  │  Chatbot    │───▶│  Contextual AI Assistant (LangChain)    │  │
│  │  /api/chat  │    │  + Code Fix Engine (/api/fix-code)      │  │
│  └─────────────┘    └─────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │          AES-256-GCM Encrypted API Layer                     ││
│  │        (session-based, all traffic encrypted)                 ││
│  └──────────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────┘
```

### The Agents

| Agent | File | What It Does |
|-------|------|-------------|
| **Commit Miner** | `analyzer.py` | Traverses git history with PyDriller. Identifies churn hotspots, bug-fix ratios, commit trends, and computes bus factor. |
| **Quality Analyzer** | `analyzer.py` | Runs Radon on every Python file to extract per-function cyclomatic complexity, maintainability index, and exact line numbers for problematic functions. |
| **Security Scanner** | `security_scanner.py` | Pattern-matches against 11 secret signatures (AWS keys, GitHub PATs, OpenAI keys, etc.) and 10 vulnerability patterns (eval injection, pickle deserialization, shell=True, etc.). |
| **Burnout Detector** | `burnout_detector.py` | Analyzes commit timestamps for after-hours work, weekend commits, and revert storms. Produces per-developer burnout scores. |
| **Cascade Analyzer** | `cascade_analyzer.py` | Builds a file-level import/dependency graph across Python, JS/TS, Go, Ruby, Java, and Rust. Runs BFS to compute blast radius — if file X breaks, what percentage of the codebase is affected? |
| **Debt Calculator** | `debt_calculator.py` | Translates complexity and maintainability metrics into dollar amounts using an hourly rate model, then projects compound growth (15% monthly) to show the cost of delay. |
| **Deploy Checker** | `deployment_readiness.py` | Runs 15 checks across infrastructure (Dockerfile, CI/CD), security (.gitignore, lock files), observability (logging, health checks), and hygiene (README, tests, LICENSE). |
| **AI Reporter** | `ai_reporter_FINAL.py` | Feeds all agent outputs into an LLM (Llama 3.3 70B via Groq) and generates a structured executive brief with risk levels, analogies, cost projections, and prioritized action items. |
| **AI Chatbot** | `chatbot.py` | Conversational assistant that can answer questions about analysis results with file/line precision, or operate in general mode without any analysis loaded. Also includes a code fix engine that generates refactored versions of complex functions. |

---

## Key Features

- **No GitHub token required** — works entirely with public API endpoints and HTTPS cloning
- **Function-level precision** — doesn't just say "this file is complex", it tells you `calculate_scores() at line 147 has CC=23, break it into 4 helpers`
- **Cost projections** — technical debt is expressed in USD with compound growth curves, not abstract grades
- **Cascade failure mapping** — import graph analysis shows blast radius percentages for every file
- **Developer burnout signals** — after-hours commit percentages, weekend work rates, revert storm detection
- **Encrypted API traffic** — AES-256-GCM session encryption so nothing sensitive shows up in browser DevTools
- **AI chatbot** — ask questions about your analysis in natural language, get answers with exact file/line references
- **One-click code fixes** — select a complex function, get a fully refactored version with explanation

---

## Getting Started

### Prerequisites

- Python 3.10+
- Git (accessible from PATH)
- A [Groq API key](https://console.groq.com/) (free tier works fine)

### Setup

```bash
# Clone the repo
git clone https://github.com/GALAXYAI01/SunHacks.git
cd SunHacks

# Create virtual environment
python -m venv venv
source venv/bin/activate        # Linux/Mac
# venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements_FINAL.txt

# Configure environment
cp .env.example .env            # or create .env manually
```

Add your API key to `.env`:

```
GROQ_API_KEY=your_groq_api_key_here
```

Optionally, you can also set a GitHub token to increase API rate limits (not required):

```
GITHUB_TOKEN=your_github_pat_here
```

### Run

```bash
python main.py
```

The server starts on `http://localhost:8000`. Open it in your browser to access the dashboard.

**API docs** are auto-generated at `http://localhost:8000/docs`.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/analyze` | Start analysis for a single repo |
| `POST` | `/api/analyze/portfolio` | Analyze up to 8 repos at once |
| `GET` | `/api/jobs/{id}` | Poll job status and progress |
| `GET` | `/api/jobs/{id}/health` | Health scores + AI summary |
| `GET` | `/api/jobs/{id}/components` | Per-file component risk predictions |
| `GET` | `/api/jobs/{id}/cascade` | Cascade failure blast radius data |
| `GET` | `/api/jobs/{id}/security` | Security findings + dependency risk |
| `GET` | `/api/jobs/{id}/burnout` | Developer burnout analysis |
| `GET` | `/api/jobs/{id}/debt` | Technical debt with cost projections |
| `GET` | `/api/jobs/{id}/deployment` | Deployment readiness checklist |
| `GET` | `/api/jobs/{id}/ceo-brief` | Full AI-generated executive brief |
| `POST` | `/api/chat` | AI chatbot (works with or without analysis) |
| `POST` | `/api/fix-code` | Generate refactored code for a function |
| `POST` | `/api/handshake` | Initialize encrypted session |

---

## How the Health Score Works

The overall score is a weighted composite:

```
Overall = Quality(45%) + Stability(35%) + Activity(20%)
```

- **Quality** — derived from average cyclomatic complexity across all files, penalized by the proportion of high-risk files
- **Stability** — inverse of bug-fix ratio in commit history (more bug-fix commits = lower stability)
- **Activity** — recent commit frequency over the last 4 weeks

Each component file gets an individual **failure probability** calculated from:
- Cyclomatic complexity (35% weight)
- Maintainability index (25% weight)
- File churn from commits (25% weight)
- Bug-related changes (15% weight)

---

## Tech Stack

- **Backend**: FastAPI + Uvicorn
- **Analysis**: GitPython, PyDriller, Radon
- **AI/LLM**: LangChain + Groq (Llama 3.3 70B) — falls back to Anthropic if configured
- **Security**: AES-256-GCM via Python `cryptography` library
- **Frontend**: Single-page HTML/CSS/JS dashboard

---

## Project Structure

```
├── main.py                    # Entry point (uvicorn launcher)
├── main_FINAL.py              # FastAPI app, routes, encryption middleware
├── analyzer.py                # Core orchestrator + commit/quality analysis
├── security_scanner.py        # Secret + vulnerability pattern scanner
├── burnout_detector.py        # Commit-time burnout signal detection
├── cascade_analyzer.py        # Import graph + blast radius computation
├── debt_calculator.py         # Technical debt quantification + projections
├── deployment_readiness.py    # 15-check deployment readiness audit
├── ai_reporter_FINAL.py       # LLM-powered executive brief generator
├── chatbot.py                 # AI assistant + code fix engine
├── index.html                 # Dashboard frontend
├── login.html                 # Login page
├── requirements_FINAL.txt     # Python dependencies
├── .env                       # API keys (not committed)
└── .gitignore
```

---

## Built For

**SunHacks 2026** — Arizona State University

---

## License

This project is provided as-is for educational and hackathon purposes.
