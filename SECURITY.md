# Security policy

Bardan is a competition prototype that runs on **synthetic data only**. It still treats security and privacy as
features, and reports are welcome.

## Reporting a problem

Please report privately, through GitHub's **Report a vulnerability** button on this repository's **Security** tab
(private vulnerability reporting). Do not open a public issue for a security problem.

A useful report says what you found, how to reproduce it (persona, scene, steps or a request), and what it lets someone
do. You will get an acknowledgement, and a fix or an explanation, as soon as possible.

**Please do not** test against anyone else's data, use real personal or health information, run load or denial-of-service
tests against a hosted demo, or try social engineering. Each judge sandbox is private and resets after an hour; the
emergency dialler is a mock and never contacts emergency services.

## What is in scope

The most valuable findings are anything that breaks one of Bardan's promises:

- an employer role (supervisor, HSE lead or reviewer) reading clinical data, or anything beyond a visit window or a
  duty label;
- a supervisor learning who disputed a task or reported a missing protection;
- a task verified without its required evidence tier, or a dispute closed without a fresh, independent check;
- a model's output reaching a person without passing the Guardian, or a model name reaching the interface;
- a withdrawn consent being restored, or a small group being singled out from aggregates;
- the hash-chained audit log being changed without detection;
- one judge's sandbox affecting another's.

## How the prototype protects itself

- Signed, expiring capability tokens per persona; every route checks a role capability on the server.
- Employer roles hold no clinical permission; the clinical vault has its own key; refused attempts are audited and shown
  to the worker.
- A hash-chained, append-only audit log, checked by `GET /v1/audit/verify`.
- Rate limits, RFC 9457 problem details without stack traces, and idempotency keys for offline retries.
- No personal identifiers in any AI prompt; real data on a free AI tier is refused.
- The container runs as a non-root user; secrets live in Secret Manager, never in the repository.

## Secrets

No API key, token or password belongs in this repository, its issues, screenshots or logs. If you find one, report it
privately and it will be revoked.
