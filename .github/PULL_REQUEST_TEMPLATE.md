## What changes, and why

<!-- One or two sentences. Link the issue if there is one. -->

## Checklist

- [ ] `make test` passes (device engine and server), and `npx tsc -b --noEmit` is clean.
- [ ] A changed rule, route or screen has a release test, linked to its acceptance case where one applies.
- [ ] Every new interface string exists in **English and Arabic**, and Arabic screens were checked right to left.
- [ ] No model name, model switching or quota appears anywhere in the interface (documentation only).
- [ ] AI still only proposes: engines decide and a named person approves, and the screen works with AI off.
- [ ] Employer roles still see no health data and no sign of who disputed or reported.
- [ ] Synthetic data only; no secrets, keys or personal data in code, tests, screenshots or logs.
- [ ] Documents and diagrams that describe this behaviour are updated (`docs/`, `docs/diagrams`).
