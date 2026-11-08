# Contributing to Bardan

Thank you for helping. Bardan protects people working in dangerous heat, so a few rules matter more than speed. Please
read them before changing code.

## Set up

Python 3.12+ and Node 22+.

```bash
make setup      # .venv, server and web app dependencies
make dev-api    # API on :8080 with reload
make dev-web    # web app on :5173 with hot reload (second terminal)
make test       # type check, device engine (vitest) and server (pytest)
```

Browser rehearsals (the guided tour, a phone losing its network, a drill, every AI feature with a key) are in
[`e2e/`](e2e/README.md). The architecture is described in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## The rules a change must keep

1. **Emergency first.** Urgent words open the emergency card before any model, with no network. Nothing may slow or
   gate that path.
2. **AI proposes, engines decide, people approve.** A model may draft, explain or choose an approved message. It may
   not decide a protection state, relax a limit, verify a task, diagnose, give a kidney-risk figure, a dose or a
   fitness verdict, or rank a person. Every screen must work with AI off.
3. **No model names in the interface.** Model names, switching and quotas live in [docs/AI-MODELS.md](docs/AI-MODELS.md)
   only; a release test enforces it.
4. **Clinical separation and no retaliation signal.** Employer roles see no health data and never learn who disputed or
   reported.
5. **English and Arabic only, always both.** Every interface string is added in both languages, and Arabic screens are
   checked right to left. Do not add other languages.
6. **Synthetic data only.** Never commit real personal or health data, or any secret.
7. **Rules are data, and reviewed.** Heat-rule packs change through the compiler and two qualified approvals; a changed
   pack gets a new version and hash in `shared/packs/manifest.json`, and both engines must still pass the conformance
   suite.

## Tests

- A changed rule, route or screen comes with a release test in `backend/tests` or `frontend/src/engine`, named for the
  behaviour it holds, and linked to its acceptance case (`@pytest.mark.tcase("T..")`) where one applies.
- The device engine and the server engine must agree on `shared/conformance.json`.
- A finding from a live test becomes a regression test before the fix is merged.

## Style

- Python: `ruff check backend` (rules in `ruff.toml`); type hints on public functions.
- TypeScript: `npx tsc -b --noEmit` must be clean.
- Interface and documents: plain words, short sentences, and say what is simulated or not built.

## Diagrams

Diagrams live in [`docs/diagrams`](docs/diagrams/README.md): Mermaid sources in `src/`, hand-laid pages in `custom/`.
Use the Bardan palette (navy, blue, cyan, amber, red, violet for AI), English and Arabic only, and redraw with
`docs/diagrams/render.sh` and `python3 docs/diagrams/custom/build.py`.
