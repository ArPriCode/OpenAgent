# ⚡ OS-Agent: Autonomous Open-Source Contribution Framework

> An intelligent, multi-repository open-source contributor and GSoC assistant powered by **Google Gemini** (Code Analysis & Bug Resolution), **Grok xAI** (Maintainer & Mentor Dialogue), and **PyGithub**.

---

## 🌟 Key Capabilities

- **Multi-Repository & GSoC Tracking**: Monitor multiple target repositories simultaneously (e.g., `sympy/sympy`, `scikit-learn/scikit-learn`, `zulip/zulip`, `pallets/flask`, `psf/requests`).
- **Precision Time Window Scheduling**: Configure strict working hours (e.g. `12:00` to `14:00`). Outside this window, the agent stays dormant and does not perform uninvited actions.
- **Continuous PR Review Watchdog**: Automatically polls your active Pull Requests. If a mentor or maintainer requests changes or leaves a comment, Gemini recalculates the code fix, updates the branch, pushes commits, and Grok posts a respectful, technical reply.
- **Gemini 2.0 / 1.5 Pro Bug Solver**: Indexes local codebase files, diagnoses the root cause, and generates multi-file diffs verified with local test suites and syntax compilers.
- **Grok Polite Community Communications**: Crafts authentic, humble issue claiming notes and structured PR descriptions adhering to open-source community standards.
- **🛡️ Human-in-the-Loop (HITL) Gate**: Inspect code diffs and Grok drafts in the Web Dashboard or terminal before commits are pushed or PRs are opened.
- **🧪 Safe Dry-Run Mode**: Test the entire discovery, solving, and PR pipeline locally without touching remote GitHub or burning tokens.

---

## 🏗️ Architecture & Internal Parts

```
OS-Agent Architecture:
├── TimeWindowScheduler  -> Enforces active hours (e.g., 12:00 - 14:00)
├── Multi-Repo Registry  -> Configures GSoC orgs, target labels, and priorities
├── IssueHunter          -> Scans repos for open, unassigned, beginner/GSoC issues
├── Codebase Context     -> Clones repos, extracts relevant files & AST symbols
├── GeminiSolver         -> High-capacity reasoning engine for code patches
├── GrokCommunicator     -> Polite mentor dialogue, PR summaries, review replies
├── PRReviewWatchdog     -> Listens for mentor review feedback and triggers auto-patches
├── GitManager           -> Local cloning, branch management, test execution & push
└── Web & CLI Dashboard  -> Real-time monitoring, time window control & HITL approval
```

---

## 🚀 Quick Start Guide

### 1. Setup Virtual Environment & Dependencies
```bash
# In the project root directory:
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment (`.env`)
Edit `.env` with your API keys and GitHub credentials:
```env
# GitHub Personal Access Token
GITHUB_TOKEN=ghp_your_token_here
GITHUB_USERNAME=your_username

# Google Gemini API
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.0-flash

# Grok / xAI API
GROK_API_KEY=your_grok_xai_key_here
GROK_MODEL=grok-2-latest
GROK_BASE_URL=https://api.x.ai/v1

# Contribution Window (24h format)
WORK_WINDOW_START=12:00
WORK_WINDOW_END=14:00
TIMEZONE=Asia/Kolkata

# Safety
DRY_RUN=true
REQUIRE_APPROVAL=true
```

---

## 🖥️ Usage Modes

### Mode 1: Interactive Web Dashboard (Recommended)
Launch the local web dashboard:
```bash
python main.py dashboard --port 8000
```
Open **`http://127.0.0.1:8000`** in your browser to:
- Adjust working hours (e.g. `12:00` to `14:00`) with live countdown
- Add / toggle target repositories (with 1-click GSoC preset buttons)
- View pending Human-in-the-Loop actions with side-by-side diffs
- Click `[✓ Approve & Push PR]` or `[✕ Reject]`
- Monitor real-time activity stream

### Mode 2: One-Off Contribution Run
```bash
# Run cycle (obeys time window)
python main.py run

# Force run cycle immediately (overrides time window)
python main.py run --force
```

### Mode 3: Continuous Daemon Loop
```bash
# Wakes up every minute, checks time window, and executes during active hours:
python main.py daemon
```

### Mode 4: System Status Check
```bash
python main.py status
```

---

## 🏛️ Managing Repositories (`config/repos.json`)

You can add repositories via the Web Dashboard or directly in `config/repos.json`:
```json
[
  {
    "repo": "sympy/sympy",
    "enabled": true,
    "labels": ["good first issue", "Easy to Fix", "gsoc"],
    "priority": 1,
    "notes": "SymPy Computer Algebra System"
  },
  {
    "repo": "scikit-learn/scikit-learn",
    "enabled": true,
    "labels": ["good first issue", "Easy"],
    "priority": 2,
    "notes": "Machine Learning in Python"
  }
]
```

---

## 🛡️ Best Practices & Community Etiquette

1. **Keep Human-in-the-Loop Enabled**: Always review generated diffs and PR descriptions before pushing to respect open-source maintainers' time.
2. **Rate Limits & Spam Prevention**: The agent limits new issue claims to 1-2 per active cycle.
3. **GSoC Organization Contribution**: Focus on repositories where you have read the contribution guidelines and setup instructions.
