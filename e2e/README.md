# Browser rehearsals

Python Playwright scripts that click through the real app the way a judge would. Start the app first
(`make run`, which serves http://127.0.0.1:8080), then:

```bash
pip install playwright && python -m playwright install chromium   # once
python e2e/tour.py http://127.0.0.1:8080            # the seven guided-tour steps, from a fresh sandbox
python e2e/offline_phone.py http://127.0.0.1:8080   # a phone loses its network: report, emergency, reload, reconnect
python e2e/ai_live.py http://127.0.0.1:8080         # with GEMINI_API_KEY set on the server: every AI feature, EN and AR
python e2e/drill.py http://127.0.0.1:8080 e2e/out/drill en   # a drill: facilitator console plus worker and supervisor phones
```

Each script prints what it saw and any page error or failed API call, and saves screenshots under `e2e/out/`.
`offline_phone.py` also checks that the emergency card covers the whole phone screen, and exits with an error if
it does not or if the page threw an error.
The only expected failed call is the guided tour's step 7, where the supervisor's attempt to open a clinical
record must be refused (HTTP 403) and recorded in the audit log.
