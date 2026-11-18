# Browser rehearsals

Python Playwright scripts that click through the real app the way a judge would. Start the app first
(`make run`, which serves http://127.0.0.1:8080), then:

```bash
pip install playwright && python -m playwright install chromium   # once
python e2e/tour.py http://127.0.0.1:8080            # guided-tour steps 1-7, from a fresh sandbox (lab.py covers 8-9)
python e2e/offline_phone.py http://127.0.0.1:8080   # a phone loses its network: report, emergency, reload, reconnect
python e2e/ai_live.py http://127.0.0.1:8080         # with GEMINI_API_KEY set on the server: every AI feature, EN and AR
python e2e/drill.py http://127.0.0.1:8080 e2e/out/drill en   # a drill: facilitator console plus worker and supervisor phones
python e2e/lab.py http://127.0.0.1:8080             # Scenario Lab and shift simulator, then the worker-controlled wearable
python e2e/coach.py http://127.0.0.1:8080           # the step-by-step guided tour, all nine steps, as a judge clicks it
```

Each script prints what it saw and any page error or failed API call, and saves screenshots under `e2e/out/`.
`offline_phone.py` also checks that the emergency card covers the whole phone screen, and exits with an error if
it does not or if the page threw an error. `lab.py` exits with an error on any page error, failed call, invalid plan or
heart rate reaching the supervisor; when a change leaves no protected plan it applies the permitted option offered.
The only expected failed call is the guided tour's step 7, where the supervisor's attempt to open a clinical
record must be refused (HTTP 403) and recorded in the audit log.
