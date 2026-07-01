# Company Agents

Five Claude-powered agents, one per engineering role. Each runs as an interactive terminal session.

## Setup

```bash
pip install anthropic
export ANTHROPIC_API_KEY="sk-ant-..."
```

## Agents

| File | Role | What it does |
|------|------|--------------|
| `analyst.py` | Business Analyst | Requirements, user stories, gap analysis, data dictionaries |
| `tester.py` | QA / Tester | Test plans, test cases, bug reports, automation guidance |
| `solution_architect.py` | Solution Architect | System design, ADRs, tech stack trade-offs |
| `senior_fullstack.py` | Senior Fullstack Dev | Code review, implementation, FastAPI + React |
| `devops.py` | DevOps / SRE | CI/CD, Dockerfiles, incident runbooks, postmortems |

## Run any agent

```bash
# from repo root
python agents/analyst.py
python agents/tester.py
python agents/solution_architect.py
python agents/senior_fullstack.py
python agents/devops.py
```

## Session commands

| Command | Effect |
|---------|--------|
| `exit` | End session |
| `clear` | Reset conversation history (start fresh) |

## Tips

- Paste code snippets directly — agents can read and respond to large blocks.
- Each agent maintains conversation history within a session; type `clear` to reset context.
- Agents are opinionated and will push back — that's by design.
