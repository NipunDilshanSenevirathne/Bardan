"""End-to-end rehearsal of an observed drill: facilitator console + worker and supervisor phones (Playwright)."""
import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else str(Path(__file__).parent / "out" / "drill"))
OUT.mkdir(parents=True, exist_ok=True)
LANG = sys.argv[3] if len(sys.argv) > 3 else "en"
log = []


def shot(page, name, full=False):
    page.screenshot(path=str(OUT / f"{LANG}_{name}.png"), full_page=full)
    log.append(name)


def errors_of(page, bag):
    page.on("pageerror", lambda e: bag.append(f"pageerror: {e}"))
    page.on("console", lambda m: bag.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)


with sync_playwright() as p:
    b = p.chromium.launch()
    errs: list[str] = []
    fac = b.new_context(viewport={"width": 1280, "height": 900}, device_scale_factor=1)
    fac.add_init_script(f"try {{ localStorage.setItem('bardan.lang', '{LANG}') }} catch (e) {{}}")
    pg = fac.new_page()
    errors_of(pg, errs)
    pg.goto(BASE + "/start")
    pg.locator("button", has_text=re.compile("Guest reviewer|مُقيِّم ضيف|Guest")).first.click()
    pg.wait_for_url("**/app/trust", timeout=20000)
    pg.goto(BASE + "/app/drill")
    pg.locator("input[maxlength='80']").wait_for(timeout=20000)
    shot(pg, "01_setup", full=True)
    pg.fill("input[maxlength='80']", "Software rehearsal (no people)")
    # probes off for this rehearsal: the toggle is the only switch on the form
    pg.locator("[role=switch]").first.click()
    pg.locator("button", has_text=re.compile("Create the drill sandbox|أنشئ بيئة التمرين")).click()
    pg.locator("text=/Invite the team|ادعُ الفريق/").wait_for(timeout=20000)
    time.sleep(1.5)
    shot(pg, "02_console", full=True)
    sid = pg.evaluate("JSON.parse(localStorage.getItem('bardan.session.v1')).sandboxId")
    tok = pg.evaluate("(() => { const s = JSON.parse(localStorage.getItem('bardan.session.v1')); return s.tokens[s.persona] })()")

    def series():
        r = pg.request.get(BASE + "/v1/drills/series", headers={"Authorization": f"Bearer {tok}"})
        return r.json()

    phone = p.devices["iPhone 13"]
    wk = b.new_context(**phone)
    wk.add_init_script(f"try {{ localStorage.setItem('bardan.lang', '{LANG}') }} catch (e) {{}}")
    wp = wk.new_page()
    errors_of(wp, errs)
    wp.goto(f"{BASE}/start?join={sid}&as=ravi")
    wp.wait_for_url("**/app/worker", timeout=20000)
    sv = b.new_context(**phone)
    sv.add_init_script(f"try {{ localStorage.setItem('bardan.lang', '{LANG}') }} catch (e) {{}}")
    sp = sv.new_page()
    errors_of(sp, errs)
    sp.goto(f"{BASE}/start?join={sid}&as=joseph")
    sp.wait_for_url("**/app/site", timeout=20000)
    sp.goto(BASE + "/app/site/tasks")
    sp.locator("main").wait_for()
    assert wp.evaluate("JSON.parse(localStorage.getItem('bardan.session.v1')).sandboxId") == sid

    for n in range(2):
        s = series()
        nxt = next(d for d in s["drills"] if d["state"] == "planned")
        pg.locator("button", has_text=re.compile(r"Start drill|ابدأ التمرين")).click()
        pg.locator("text=/Since the failure started|منذ بدء العطل/").wait_for(timeout=10000)
        arm = nxt["arm"]
        log.append(f"drill {nxt['index']} arm={arm}")
        if arm == "current":
            wp.locator("#drill-cover-title").wait_for(timeout=15000)
            shot(wp, "03_worker_cover_current")
            for m in ("Reported to someone responsible|أُبلغ شخص مسؤول", "Fix started|بدأ الإصلاح",
                      "Reported as fixed|أُبلغ بأنه أُصلح", "Really back: I saw it|عادت فعلاً: رأيتها"):
                time.sleep(1.2)
                pg.locator("button", has_text=re.compile(m)).first.click()
                time.sleep(0.4)
            shot(pg, "04_running_current", full=True)
            pg.locator("textarea").fill("Rehearsal: no independent check in the usual way.")
            pg.locator("button", has_text=re.compile("End drill|أنهِ التمرين")).click()
            wp.locator("#drill-cover-title").wait_for(state="detached", timeout=20000)
        else:
            wp.locator("text=/Drill running: use Bardan|تمرين جارٍ: استخدم/").wait_for(timeout=15000)
            wp.goto(BASE + "/app/worker/report")
            wp.locator("button", has_text=re.compile("No drinking water|لا يوجد ماء للشرب")).first.click()
            time.sleep(1.5)
            shot(wp, "05_worker_reported")
            # supervisor: the new-task alert, then the task card
            sp.locator("[role=alert]", has_text=re.compile("New task|مهمة جديدة")).wait_for(timeout=20000)
            shot(sp, "06_supervisor_alert")
            sp.locator("[role=alert] button", has_text=re.compile("Open tasks|افتح المهام")).click()
            card = sp.locator("div.card, div[class*='overflow-hidden']").filter(has_text=re.compile("Restore water|إعادة توفير الماء")).filter(has_text=re.compile("Assigned|مُسندة|مسندة|assigned")).first
            card.locator("button", has_text=re.compile("^Accept$|^قبول$")).click()
            time.sleep(1.0)
            card = sp.locator("div[class*='overflow-hidden']").filter(has_text=re.compile("Restore water|إعادة توفير الماء")).first
            card.locator("button", has_text=re.compile("^Start$|^بدء$")).click()
            time.sleep(1.0)
            card.locator("select").select_option("water_point_check")
            card.locator("input[type=checkbox]").check()
            card.locator("button", has_text=re.compile("Report complete|أبلغ عن الإنجاز")).click()
            time.sleep(1.0)
            pg.locator("button", has_text=re.compile("Really back: I saw it|عادت فعلاً: رأيتها")).first.click()
            # worker confirms
            wp.goto(BASE + "/app/worker")
            wp.locator("button", has_text=re.compile("It is done|تم بالفعل")).first.click()
            time.sleep(2.5)
            shot(pg, "07_running_bardan", full=True)
            pg.locator("button", has_text=re.compile("End drill|أنهِ التمرين")).click()
        time.sleep(2.0)

    time.sleep(1.5)
    shot(pg, "08_results", full=True)
    s = series()
    out = {"sandbox": sid, "summary": s["summary"]["arms"],
           "drills": [{k: d[k] for k in ("index", "arm", "state", "outcome")} for d in s["drills"]]}
    # Trust Centre tab
    pg.goto(BASE + "/app/trust#drills")
    pg.locator("text=/What each workflow does|ما الذي يفعله كل أسلوب عمل/").wait_for(timeout=30000)
    time.sleep(1)
    shot(pg, "09_trust_drills", full=True)
    # export
    r = pg.request.get(BASE + "/v1/drills/export", headers={"Authorization": f"Bearer {tok}"})
    (OUT / f"{LANG}_export.json").write_text(r.text())
    print(json.dumps(out, indent=1, ensure_ascii=False))
    print("shots:", log)
    print("errors:", errs[:20])
    b.close()
