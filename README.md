# PATCH

**PATCH (Protocol-Assisted Triage, Communication & Handoff)** will simulate
health episodes during a mission to Mars. It will use fictional data and model
delayed communication between the spacecraft and Earth. The repository is
currently a scaffold. The planned implementation uses Python 3.11, Streamlit,
SQLite, Pydantic, and pytest.

## Modules

| File | Planned responsibility |
| --- | --- |
| `app.py` | Streamlit entry point and user interface. |
| `contracts.py` | Shared contracts, data models, and validation. |
| `config_scenarios.py` | Scenario configuration and fictional data. |
| `core_hsm.py` | State machine and episode progression. |
| `space_link_db.py` | SQLite persistence and the message queue between the spacecraft and Earth. |
| `llm_anamnesis.py` | Optional language model integration for taking a medical history. |

See the [architecture document](docs/ARCHITECTURE.md) for the planned design.

## Planned scenarios

- **A — Interview during a communication delay.** The crew conducts a medical
  history interview while messages are in transit to Earth.
- **B — Simulated deterioration and delayed notification to Earth.** The
  simulated condition worsens, and Earth receives the update after the
  configured delay.

Both scenarios are planned for implementation.

## Git workflow

Changes move from a working branch to `dev`, then to `main`.

1. `dev` is the integration branch. Start each task on a new branch from the
   latest `dev`, for example `feat/hsm`, `fix/message-queue`, or `docs/scenarios`.
2. When the task is ready, push your branch and open a pull request with `dev`
   as the **base** and your working branch as the **compare** branch. Describe
   what changed and how you verified it.
3. When `dev` is ready for a release, open a pull request with `main` as the
   **base** and `dev` as the **compare** branch. `main` holds stable releases.
   Both `dev` and `main` receive changes through pull requests.

Use these commands to start and publish a working branch.

```bash
git switch dev
git pull --ff-only origin dev
git switch -c feat/my-task
# ... make and review your changes ...
git push -u origin feat/my-task
```

For this submission, the first pull request should use `dev` as the **base**
and the published working branch as the **compare** branch.
