"""Real network loss on a phone: airplane mode, reload, reconnect (Playwright, iPhone 13 emulation)."""
import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080"
OUT = Path(__file__).parent / "out" / "offline"
OUT.mkdir(parents=True, exist_ok=True)
log = []


def note(s):
    log.append(s)
    print("·", s, flush=True)


with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(**p.devices["iPhone 13"])
    page = ctx.new_page()
    errs = []
    problems = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.goto(BASE + "/start")
    page.locator("button", has_text=re.compile("Ravi")).first.click()
    page.wait_for_url(re.compile(r"/app/worker"), timeout=20000)
    ready = page.evaluate("navigator.serviceWorker ? navigator.serviceWorker.ready.then(() => true) : false")
    page.reload()
    page.wait_for_load_state("networkidle")
    controlled = page.evaluate("!!(navigator.serviceWorker && navigator.serviceWorker.controller)")
    note(f"service worker ready={ready} controls page={controlled}")
    session = page.evaluate("JSON.parse(localStorage.getItem('bardan.session.v1'))")
    sid = session["sandboxId"]

    # Airplane mode
    ctx.set_offline(True)
    page.goto(BASE + "/app/worker/report")      # offline: the service worker serves the app
    page.locator("#rtext").wait_for(timeout=15000)
    page.locator("#rtext").fill("water finished")
    page.locator("button", has_text=re.compile("^Check$")).first.click()
    time.sleep(1.5)
    page.screenshot(path=str(OUT / "01_offline_read_on_phone.png"))
    note("offline check: " + page.locator("main").inner_text()[:400].replace("\n", " | "))
    page.locator("button", has_text=re.compile("Yes, send")).first.click()
    time.sleep(1.0)
    outbox = page.evaluate("JSON.parse(localStorage.getItem('bardan.outbox.v1') || '[]').length")
    banner = page.locator("[role=status]").all_inner_texts()
    note(f"after send offline: outbox={outbox}; banner={banner}")
    page.screenshot(path=str(OUT / "02_offline_queued.png"))

    # Emergency while offline
    page.locator("button", has_text=re.compile("Emergency")).first.click()
    page.locator("button", has_text=re.compile("Confused")).first.click()
    time.sleep(1.0)
    dlg = page.locator("[role=dialog][aria-label=Emergency]")
    note("emergency offline: " + " | ".join(x for x in dlg.inner_text().split("\n") if x.strip())[-380:])
    top, bottom, vh = dlg.evaluate("e => { const r = e.getBoundingClientRect(); return [r.top, r.bottom, innerHeight] }")
    note(f"emergency card covers the whole screen: top={top} bottom={bottom} of {vh}")
    if top != 0 or abs(bottom - vh) > 0.5:
        problems.append(f"emergency card does not cover the screen (top={top}, bottom={bottom}, height={vh})")
    page.screenshot(path=str(OUT / "03_offline_emergency.png"))
    for _ in range(3):
        if not page.locator("[role=dialog][aria-label=Emergency]").count():
            break
        btns = page.locator("[role=dialog][aria-label=Emergency] button[aria-label=Close]")
        btns.first.click()
        time.sleep(0.5)

    # Reload while still offline: the app shell must come from the phone, and the queue must survive
    page.reload()
    page.wait_for_load_state("domcontentloaded")
    time.sleep(2)
    outbox2 = page.evaluate("JSON.parse(localStorage.getItem('bardan.outbox.v1') || '[]').length")
    title_ok = page.locator("header").count() > 0
    note(f"reload offline: app shell shown={title_ok}; outbox after reload={outbox2}")
    page.screenshot(path=str(OUT / "04_offline_reload.png"))

    # Reconnect: nothing pressed; the phone sends by itself
    ctx.set_offline(False)
    t0 = time.time()
    left = outbox2
    while time.time() - t0 < 25:
        time.sleep(1)
        left = page.evaluate("JSON.parse(localStorage.getItem('bardan.outbox.v1') || '[]').length")
        if left == 0:
            break
    note(f"reconnect: outbox emptied after {round(time.time() - t0, 1)} s (left={left})")
    page.screenshot(path=str(OUT / "05_reconnected.png"))

    # Server view: as the supervisor, is the water task there, and is the emergency received but not acknowledged?
    r = page.request.post(BASE + "/v1/sandbox/session", data={"persona": "joseph", "sandbox_id": sid})
    tok = r.json()["token"]
    tasks = page.request.get(BASE + "/v1/tasks", headers={"Authorization": f"Bearer {tok}"}).json()["tasks"]
    water = [t for t in tasks if t["action_code"] == "WATER_RESTORE"]
    ops = page.request.get(BASE + "/v1/sites/site_demo/operations", headers={"Authorization": f"Bearer {tok}"}).json()
    em = ops.get("emergencies", [])
    note(f"server: water tasks={len(water)} ({[t['source'] for t in water]}); emergencies={[(e.get('state'), bool(e.get('acknowledged'))) for e in em]}")

    # The worker's card now shows "received by the server" and, after the supervisor acknowledges, "seen"
    if em:
        eid = em[-1]["id"]
        a = page.request.post(BASE + f"/v1/emergency/{eid}/acknowledge", headers={"Authorization": f"Bearer {tok}"})
        note(f"supervisor acknowledges: HTTP {a.status}")
    page.locator("button", has_text=re.compile("Emergency")).first.click()
    time.sleep(4)
    dlg = page.locator("[role=dialog][aria-label=Emergency]")
    note("worker card after reconnect: " + " | ".join(x for x in dlg.inner_text().split("\n") if x.strip())[-420:])
    page.screenshot(path=str(OUT / "06_seen_by_team.png"))
    print("page errors:", errs[:5])
    print("problems:", problems or "none")
    (OUT / "log.json").write_text(json.dumps(log, indent=1, ensure_ascii=False))
    b.close()
sys.exit(1 if problems or errs else 0)
