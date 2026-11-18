"""Rehearse guided-tour steps 1-7 from a fresh sandbox, as a judge would click it (Playwright, AI off); e2e/lab.py covers 8-9."""
import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else str(Path(__file__).parent / "out" / "tour"))
OUT.mkdir(parents=True, exist_ok=True)
notes: list[str] = []
problems: list[str] = []


def note(s):
    notes.append(s)
    print("·", s, flush=True)


def shot(page, name, full=False):
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=full)


def watch(page):
    page.on("pageerror", lambda e: problems.append(f"pageerror {page.url}: {e}"))
    page.on("console", lambda m: problems.append(f"console {page.url}: {m.text}") if m.type == "error" else None)
    page.on("response", lambda r: problems.append(f"HTTP {r.status} {r.request.method} {r.url}")
            if r.status >= 400 and "/v1/" in r.url else None)


def open_tour(page):
    page.locator("button:visible", has_text=re.compile("Guided tour|الجولة الإرشادية|جولة")).first.click()
    page.locator("[role=dialog]").wait_for()


def tour_go(page, n):
    open_tour(page)
    items = page.locator("[role=dialog] ol > li")
    items.nth(n - 1).locator("button", has_text=re.compile("^(Go|Take me there|اذهب|خذني)")).first.click()
    page.locator("[role=dialog]").wait_for(state="detached", timeout=30000)
    page.wait_for_load_state("networkidle")
    time.sleep(1.0)


def switch(page, persona_label):
    page.goto(BASE + "/start")
    page.locator("button", has_text=re.compile(persona_label)).first.click()
    page.wait_for_url(re.compile(r"/app/"), timeout=20000)
    page.wait_for_load_state("networkidle")
    time.sleep(0.8)


with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    watch(page)
    page.goto(BASE + "/")
    shot(page, "00_landing")
    page.goto(BASE + "/start")
    page.locator("button", has_text=re.compile("Joseph")).first.click()
    page.wait_for_url(re.compile(r"/app/site"), timeout=20000)

    # ---------------------------------------------------------------- step 1: plan tomorrow
    tour_go(page, 1)
    assert "/app/site/plan" in page.url, page.url
    page.locator("button", has_text=re.compile("Evaluate draft")).first.click()
    page.locator("text=/Rejected|Valid/").first.wait_for(timeout=60000)
    time.sleep(1)
    page.locator("button", has_text=re.compile("Optimise with Bardan")).first.click()
    page.locator("text=/Capacity-feasibility certificate/").first.wait_for(timeout=90000)
    time.sleep(1.5)
    shot(page, "01_plan_optimised", full=True)
    body = page.locator("main").inner_text()
    note(f"step 1: 05:30 in plan text: {'05:30' in body}; 'Approve plan' visible: {page.locator('button', has_text='Approve plan').count()}")
    if page.locator("button", has_text="Approve plan").count():
        page.locator("button", has_text="Approve plan").first.click()
        time.sleep(2)
        note(f"step 1: after approve -> Activate buttons: {page.locator('button', has_text=re.compile('^Activate$')).count()}")

    # ---------------------------------------------------------------- step 2: live values govern
    tour_go(page, 2)
    assert "/app/worker" in page.url, page.url
    time.sleep(1.5)
    shot(page, "02_ravi_harsh")
    note("step 2: worker card: " + page.locator("main").inner_text()[:300].replace("\n", " | "))

    # ---------------------------------------------------------------- step 3: report in Arabic
    tour_go(page, 3)
    assert "/app/worker/report" in page.url, page.url
    box = page.locator("#rtext")
    box.fill("ما فيني دوخة، بس الماي خلص")
    page.locator("button", has_text=re.compile("^تحقق$|^Check$")).first.click()
    page.locator("text=/سمعت|I heard/").first.wait_for(timeout=30000)
    time.sleep(0.8)
    shot(page, "03_anwar_heard")
    note("step 3: heard card: " + page.locator("main").inner_text()[:500].replace("\n", " | "))
    page.locator("button", has_text=re.compile("نعم، أرسل|Yes, send")).first.click()
    time.sleep(2)
    shot(page, "03_anwar_sent")
    note("step 3: after send: " + page.locator("main").inner_text()[:300].replace("\n", " | "))

    # ---------------------------------------------------------------- step 4: dispute a false completion
    tour_go(page, 4)
    assert "/app/site/tasks" in page.url, page.url
    time.sleep(1)
    card = page.locator("article, div[class*='overflow-hidden']").filter(has_text=re.compile("Restore water|إعادة")).first
    shot(page, "04a_joseph_tasks")
    for label in ("^Accept$|^قبول$", "^Start$|^بدء$"):
        btn = card.locator("button", has_text=re.compile(label))
        if btn.count():
            btn.first.click()
            time.sleep(1.2)
    card = page.locator("div[class*='overflow-hidden']").filter(has_text=re.compile("Restore water|إعادة")).first
    card.locator("button", has_text=re.compile("Report complete|أبلغ عن الإنجاز")).first.click()
    time.sleep(1.5)
    note("step 4: joseph reported complete (attestation)")
    switch(page, "Ravi")
    page.locator("button", has_text=re.compile("This didn.t happen|لم يحدث")).first.click()
    time.sleep(1.5)
    shot(page, "04b_ravi_disputed")
    switch(page, "Sara")
    page.goto(BASE + "/app/site/tasks")
    page.wait_for_load_state("networkidle")
    time.sleep(1)
    card = page.locator("div[class*='overflow-hidden']").filter(has_text=re.compile("Restore water|إعادة توفير الماء")).first
    shot(page, "04c_sara_tasks")
    card.locator("button", has_text=re.compile("^Accept$|^قبول$")).first.click()
    time.sleep(1.2)
    card = page.locator("div[class*='overflow-hidden']").filter(has_text=re.compile("Restore water|إعادة توفير الماء")).first
    sel = card.locator("select")
    opts = sel.first.locator("option").all_inner_texts() if sel.count() else []
    note(f"step 4: sara evidence options: {opts}")
    sel.first.select_option("independent_spot_check")
    card.locator("button", has_text=re.compile("Add evidence|أضف دليلاً")).first.click()
    time.sleep(1.2)
    card = page.locator("div[class*='overflow-hidden']").filter(has_text=re.compile("Restore water|إعادة توفير الماء")).first
    card.locator("input").filter(has_not=page.locator("[type=checkbox]")).last.fill("Checked the water point myself: refilled and cold")
    card.locator("button", has_text=re.compile("Resolve|حلّ")).first.click()
    time.sleep(1.5)
    card = page.locator("div[class*='overflow-hidden']").filter(has_text=re.compile("Restore water|إعادة توفير الماء")).first
    for label in ("^Start$|^بدء$", "Report complete|أبلغ عن الإنجاز", "^Verify$|^تحقّق$|^تحقق$"):
        btn = card.locator("button", has_text=re.compile(label))
        if btn.count():
            btn.first.click()
            time.sleep(1.3)
            card = page.locator("div[class*='overflow-hidden']").filter(has_text=re.compile("Restore water|إعادة توفير الماء")).first
    shot(page, "04d_sara_done", full=True)
    left = page.locator("div[class*='overflow-hidden']").filter(has_text=re.compile("Restore water|إعادة توفير الماء")).count()
    note(f"step 4: water task still in the open list: {left} (0 = verified and closed)")
    switch(page, "Ravi")
    time.sleep(1)
    shot(page, "04e_ravi_told")
    note("step 4: ravi sees: " + page.locator("main").inner_text()[:400].replace("\n", " | "))

    # ---------------------------------------------------------------- step 5: watch the gate
    tour_go(page, 5)
    assert "/app/worker/ask" in page.url, page.url
    page.locator("#askq").fill("Are my kidneys failing?")
    page.locator("#askq").press("Enter")
    time.sleep(4)
    shot(page, "05_ask_gate")
    note("step 5: ask: " + page.locator("main").inner_text()[:500].replace("\n", " | "))

    # ---------------------------------------------------------------- step 6: emergency with AI off
    tour_go(page, 6)
    open_tour(page)
    page.locator("[role=dialog] ol > li").nth(5).locator("button", has_text=re.compile("internet|offline|الإنترنت|دون اتصال")).first.click()
    time.sleep(1)
    page.locator("button", has_text=re.compile("Emergency|طوارئ")).first.click()
    time.sleep(1)
    page.locator("button", has_text=re.compile("Confused|ارتباك")).first.click()
    time.sleep(1.5)
    shot(page, "06_emergency_offline")
    note("step 6: card: " + page.locator("[role=dialog]").last.inner_text()[:700].replace("\n", " | "))
    dlg = page.locator("[role=dialog][aria-label=Emergency]")
    dlg.locator("button", has_text=re.compile("Call 998|اتصل بالرقم 998")).first.click()
    time.sleep(1)
    note("step 6: after Call 998: " + dlg.inner_text()[:900].replace("\n", " | ")[-420:])
    shot(page, "06b_emergency_dialler")
    for _ in range(3):
        if not page.locator("[role=dialog][aria-label=Emergency]").count():
            break
        btns = page.locator("[role=dialog][aria-label=Emergency] button", has_text=re.compile("^Close$|^إغلاق$"))
        (btns.last if btns.count() else page.locator("[role=dialog][aria-label=Emergency] button[aria-label=Close]").first).click()
        time.sleep(0.6)

    # ---------------------------------------------------------------- step 7: privacy
    tour_go(page, 7)
    time.sleep(1)
    page.locator("button", has_text=re.compile("Try to open a clinical record|حاول فتح سجل طبي")).first.click()
    time.sleep(1.5)
    shot(page, "07_privacy_denied")
    note("step 7: denied text present: " + str(page.locator("text=/Denied and recorded|مرفوض ومسجّل/").count()))
    switch(page, "Ravi")
    page.goto(BASE + "/app/worker/data")
    page.wait_for_load_state("networkidle")
    time.sleep(1)
    shot(page, "07b_ravi_privacy", full=True)
    note("step 7: ravi privacy: " + page.locator("main").inner_text()[:500].replace("\n", " | "))

    print("\nPROBLEMS:")
    for x in problems:
        print("  ", x)
    (OUT / "notes.json").write_text(json.dumps({"notes": notes, "problems": problems}, ensure_ascii=False, indent=1))
    b.close()
