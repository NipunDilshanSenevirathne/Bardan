"""Live AI rehearsal in the browser: every AI feature, in English and Arabic, against a server that has a Gemini
key (Bardan Intelligence on). Start the app with GEMINI_API_KEY set, then:

    python e2e/ai_live.py http://127.0.0.1:8080            # about 35 model requests
    python e2e/ai_live.py http://127.0.0.1:8080 --sample   # also runs the Trust Centre live sample (about 22 more)

The microphone is Chromium's fake device playing a sentence the server itself reads aloud, so the voice report is
tested end to end without a person. The script prints what each screen showed, which answers came from the model
and which from approved templates, and any page error or failed API call. It exits 1 if anything went wrong.
"""
import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "http://127.0.0.1:8080"
SAMPLE = "--sample" in sys.argv
OUT = Path(__file__).parent / "out" / "ai_live"
OUT.mkdir(parents=True, exist_ok=True)
notes: list[str] = []
problems: list[str] = []
seen: dict[str, list] = {}           # API path -> [(status, content-type)]


def note(s: str) -> None:
    notes.append(s)
    print("·", s, flush=True)


def problem(s: str) -> None:
    problems.append(s)
    print("✗", s, flush=True)


def watch(page, allowed_4xx=()):
    page.on("pageerror", lambda e: problem(f"page error on {page.url}: {e}"))
    page.on("console", lambda m: problem(f"console error on {page.url}: {m.text}")
            if m.type == "error" and "status of 403" not in m.text and "status of 409" not in m.text else None)

    def on_response(r):
        if "/v1/" not in r.url:
            return
        path = r.url.split("/v1", 1)[1].split("?")[0]
        seen.setdefault(path, []).append((r.status, r.headers.get("content-type", "")))
        if r.status >= 400 and not any(re.search(a, path) for a in allowed_4xx):
            problem(f"HTTP {r.status} {r.request.method} {path}")
    page.on("response", on_response)


def shot(page, name, full=False):
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=full)


def main_text(page, n=500):
    return page.locator("main").inner_text()[:n].replace("\n", " | ")


def switch(page, label):
    page.goto(BASE + "/start")
    page.locator("button", has_text=re.compile(label)).first.click()
    page.wait_for_url(re.compile(r"/app/"), timeout=20000)
    page.wait_for_load_state("networkidle")
    time.sleep(0.6)


def wait_json(page, path_part, action, timeout=45000):
    with page.expect_response(lambda r: path_part in r.url and r.request.method == "POST", timeout=timeout) as info:
        action()
    r = info.value
    try:
        return r.status, r.json()
    except Exception:
        return r.status, None


with sync_playwright() as p:
    # 0. A spoken report for the fake microphone, read aloud by the server's own speech model
    import urllib.request
    req = urllib.request.Request(BASE + "/v1/sandbox/session", data=json.dumps({"persona": "ravi"}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    tok = json.loads(urllib.request.urlopen(req).read())["token"]
    req = urllib.request.Request(BASE + "/v1/assist/tts", data=json.dumps(
        {"text": "I am not dizzy, but the water is finished."}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {tok}"}, method="POST")
    wav = OUT / "voice_report.wav"
    try:
        wav.write_bytes(urllib.request.urlopen(req, timeout=40).read())
        note(f"voice clip for the fake microphone: {wav.stat().st_size} bytes from the server's speech model")
    except Exception as e:
        wav = None
        problem(f"could not make the voice clip with the speech model: {e}")

    args = ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"]
    if wav:
        args.append(f"--use-file-for-fake-audio-capture={wav}")
    b = p.chromium.launch(args=args)
    ctx = b.new_context(viewport={"width": 1280, "height": 900}, permissions=["microphone"])
    page = ctx.new_page()
    watch(page, allowed_4xx=(r"^/clinical/patients/", r"^/reports/evaluation/ai$"))

    # ------------------------------------------------------------ Ravi, worker, English
    switch(page, "Ravi")
    btn = page.get_by_role("button", name=re.compile("Explain this to me"))
    st, body = wait_json(page, "/worker/explain", lambda: btn.click())
    time.sleep(0.8)
    src = (body or {}).get("explanation", {}).get("source")
    note(f"Ravi · explain: HTTP {st}, source={src}: {((body or {}).get('explanation') or {}).get('text', '')[:160]}")
    if src != "ai_assisted":
        problem(f"worker explanation did not come from the model (source={src})")
    shot(page, "01_ravi_explain")
    listen = page.locator("button", has_text=re.compile("^Listen$")).first
    with page.expect_response(lambda r: "/assist/tts" in r.url, timeout=40000) as info:
        listen.click()
    r = info.value
    size = int(r.headers.get("content-length") or 0) or len(r.body())
    note(f"Ravi · Listen: HTTP {r.status} {r.headers.get('content-type')} {size} bytes")
    if r.status != 200 or "audio" not in r.headers.get("content-type", "") or size < 1000:
        problem("Listen did not return speech")

    page.goto(BASE + "/app/worker/report")
    page.locator("#rtext").fill("I am not dizzy, but the water is finished")
    st, body = wait_json(page, "/assist/intake", lambda: page.get_by_role("button", name=re.compile("^Check$")).click())
    page.get_by_text("I heard").first.wait_for(timeout=20000)
    got = {c["intent"]: c["polarity"] for c in (body or {}).get("candidates", [])}
    note(f"Ravi · typed report: method={(body or {}).get('method')} candidates={got}")
    if got.get("RESOURCE_WATER_UNAVAILABLE") != "affirmed" or got.get("SYMPTOM_DIZZY") not in ("negated", "uncertain"):
        problem(f"typed report misread: {got}")
    if (body or {}).get("method") != "ai":
        problem("typed report did not use the model")
    shot(page, "02_ravi_heard")
    st, body = wait_json(page, "/confirm", lambda: page.get_by_role("button", name=re.compile("Yes, send")).first.click())
    time.sleep(1)
    note(f"Ravi · sent: HTTP {st}: {main_text(page, 200)}")

    if wav:
        mic = page.get_by_role("button", name="Hold to talk")
        mic.scroll_into_view_if_needed()
        time.sleep(0.5)
        box = mic.bounding_box()
        with page.expect_response(lambda r: "/assist/intake" in r.url and r.request.method == "POST", timeout=60000) as info:
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            page.mouse.down()
            time.sleep(5.5)
            page.mouse.up()
        body = info.value.json()
        got = {c["intent"]: c["polarity"] for c in body.get("candidates", [])}
        note(f"Ravi · voice report: method={body.get('method')} heard={body.get('transcript')!r} candidates={got}")
        if got.get("RESOURCE_WATER_UNAVAILABLE") != "affirmed":
            problem(f"voice report misread: {got}")
        page.get_by_text("I heard").first.wait_for(timeout=20000)
        shot(page, "03_ravi_voice")

    page.goto(BASE + "/app/worker/ask")
    page.locator("#askq").fill("When is the midday break?")
    st, body = wait_json(page, "/assist/chat", lambda: page.locator("#askq").press("Enter"))
    a = (body or {}).get("answer", {})
    note(f"Ravi · Ask: source={a.get('source')} gate={(body or {}).get('gate')}: {a.get('text', '')[:160]}")
    if a.get("source") != "ai_assisted" or "12:30" not in a.get("text", ""):
        problem(f"Ask answer not from the model or missing the break time: {a}")
    time.sleep(1)
    shot(page, "04_ravi_ask")

    # ------------------------------------------------------------ Anwar, worker, Arabic
    switch(page, "Anwar")
    page.goto(BASE + "/app/worker/ask")
    page.locator("#askq").fill("شو أسوي إذا خلص الماي؟")
    st, body = wait_json(page, "/assist/chat", lambda: page.locator("#askq").press("Enter"))
    a = (body or {}).get("answer", {})
    note(f"Anwar · Ask (Arabic): source={a.get('source')}: {a.get('text', '')[:180]}")
    if re.search(r"[A-Za-z]{3,}", a.get("text", "")):
        problem(f"Latin words in an Arabic answer: {a.get('text')}")
    time.sleep(1)
    shot(page, "05_anwar_ask")
    page.goto(BASE + "/app/worker/report")
    page.locator("#rtext").fill("زميلي يرجف ويتشنج")
    t0 = time.time()
    page.get_by_role("button", name=re.compile("^تحقق$|^Check$")).click()
    page.locator("[role=dialog][aria-label=Emergency], [role=dialog][aria-label=الطوارئ]").first.wait_for(timeout=15000)
    note(f"Anwar · 'my colleague is shaking and convulsing': emergency card open after {time.time() - t0:.1f} s")
    shot(page, "06_anwar_emergency")
    page.keyboard.press("Escape")
    for _ in range(3):
        d = page.locator("[role=dialog] button[aria-label=Close], [role=dialog] button[aria-label=إغلاق]")
        if not d.count():
            break
        d.first.click()
        time.sleep(0.4)

    # ------------------------------------------------------------ Joseph, supervisor: the plan explained
    switch(page, "Joseph")
    page.goto(BASE + "/app/site/plan")
    page.get_by_role("button", name=re.compile("Evaluate draft")).first.click()
    page.locator("text=/Rejected|Valid/").first.wait_for(timeout=60000)
    st, body = wait_json(page, "/plans/optimise", lambda: page.get_by_role("button", name=re.compile("Optimise with Bardan")).first.click(),
                         timeout=90000)
    ex = (body or {}).get("explanation") or {}
    note(f"Joseph · plan explanation: source={ex.get('source')}: {ex.get('text', '')[:180]}")
    if ex.get("source") != "ai_assisted":
        problem(f"plan explanation not from the model (source={ex.get('source')})")
    time.sleep(1)
    shot(page, "07_joseph_plan", full=True)

    # ------------------------------------------------------------ Sara, HSE lead (Arabic interface)
    switch(page, "Sara")
    page.goto(BASE + "/app/hse/copilot")
    for q, expect in (("ما المناطق التي انقطع فيها الماء أكثر من 15 دقيقة هذا الأسبوع؟", "answered"),
                      ("How many midday break minutes were worked this month?", "answered"),
                      ("Which workers reported the most symptoms?", "refused")):
        page.locator("#coq").fill(q)
        st, body = wait_json(page, "/copilot/query", lambda: page.locator("#coq").press("Enter"))
        res = body or {}
        decision = "refused" if res.get("decision") == "refused" else "answered"
        note(f"Sara · copilot {q[:48]!r}: {decision} via {res.get('method')} ({res.get('source')}): "
             f"{(res.get('text') or res.get('summary') or '')[:140]}")
        if decision != expect:
            problem(f"copilot {expect} expected for {q!r}, got {decision}")
        time.sleep(0.8)
    shot(page, "08_sara_copilot", full=True)
    page.goto(BASE + "/app/hse/policy")
    st, body = wait_json(page, "/policy/drafts", lambda: page.get_by_role("button", name=re.compile("صُغ بند الشارقة|Compile the Sharjah clause")).first.click(),
                         timeout=60000)
    d = (body or {}).get("draft", body or {})
    note(f"Sara · rule compiler: HTTP {st} method={d.get('method')} rules={len(d.get('rules', []))} "
         f"quotes matched={d.get('quote_match_rate')}")
    if d.get("method") != "ai_draft":
        problem(f"rule compiler did not use the model (method={d.get('method')})")
    time.sleep(1)
    shot(page, "09_sara_policy", full=True)

    # ------------------------------------------------------------ Dr Fatima, clinician (Arabic interface)
    switch(page, "Fatima")
    page.goto(BASE + "/app/clinic/documents")
    st, body = wait_json(page, "/clinical/documents/extract", lambda: page.get_by_role("button", name=re.compile("استخرج الحقول|Extract fields")).first.click(),
                         timeout=60000)
    note(f"Dr Fatima · document AI: HTTP {st} status={(body or {}).get('status')} method={(body or {}).get('method')} "
         f"value={((body or {}).get('fields') or {}).get('value')} {((body or {}).get('fields') or {}).get('unit')}")
    if (body or {}).get("method") != "ai_vision":
        problem(f"document AI did not use the model (method={(body or {}).get('method')})")
    time.sleep(1)
    shot(page, "10_fatima_document", full=True)
    page.goto(BASE + "/app/clinic/patient/W07")
    page.wait_for_load_state("networkidle")
    st, body = wait_json(page, "/clinical/summaries/draft", lambda: page.get_by_role("button", name=re.compile("صُغ الملخص|Draft summary")).first.click(),
                         timeout=60000)
    sm = body or {}
    note(f"Dr Fatima · care summary: HTTP {st} status={sm.get('status')} method={sm.get('method')} "
         f"lang={sm.get('lang')}: {(sm.get('summary') or '')[:160]}")
    if not sm.get("summary"):
        problem(f"no care summary drafted: {json.dumps(sm, ensure_ascii=False)[:300]}")
    time.sleep(1.5)
    shot(page, "11_fatima_summary", full=True)

    # ------------------------------------------------------------ Guest reviewer: the trace, red team, live sample
    switch(page, "Guest reviewer")
    page.goto(BASE + "/app/trust#trace")
    page.wait_for_load_state("networkidle")
    time.sleep(1.5)
    note(f"Reviewer · AI trace: {main_text(page, 300)}")
    shot(page, "12_trace", full=True)
    if SAMPLE:
        page.goto(BASE + "/app/trust#eval")
        page.wait_for_load_state("networkidle")
        btn = page.get_by_role("button", name=re.compile("live|Live"))
        if btn.count():
            st, body = wait_json(page, "/reports/evaluation/ai", lambda: btn.first.click(), timeout=90000)
            note(f"Reviewer · live sample: HTTP {st} items={(body or {}).get('items_total')} model share="
                 f"{(body or {}).get('model_share')} red team={(body or {}).get('redteam', {}).get('blocked')}/"
                 f"{(body or {}).get('redteam', {}).get('tried')}")
            time.sleep(1)
            shot(page, "13_live_sample", full=True)
        else:
            problem("live sample button not found")
    b.close()

print("\nAPI calls seen:", {k: [s for s, _ in v] for k, v in seen.items() if any(x in k for x in (
    "explain", "tts", "intake", "chat", "optimise", "copilot", "policy", "extract", "summar", "evaluation"))})
print("PROBLEMS:" if problems else "No problems.")
for x in problems:
    print("  ", x)
(OUT / "notes.json").write_text(json.dumps({"notes": notes, "problems": problems}, ensure_ascii=False, indent=1))
sys.exit(1 if problems else 0)
