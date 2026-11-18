"""Rehearse the Scenario Lab, the shift simulator and the worker-controlled wearable (Playwright, AI off).

1. As Joseph: open the Scenario Lab, check the plan is independently re-checked, change the weather and see
   it re-plan; play the shift in 30-minute steps; give Anwar (simulated watch, shares "needs a break") a
   harder day; make it hotter and cut the water; every step must stay valid.
2. As Ravi: turn on the optional wearable, choose to share "needs a break", connect the demo watch, simulate
   a hard hour and see the alert on Ravi's phone first.
3. As Joseph: the task says only "needs a break"; no number crosses.
Exits non-zero on any page error, failed API call or invalid plan.
"""
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else str(Path(__file__).parent / "out" / "lab"))
OUT.mkdir(parents=True, exist_ok=True)
problems: list[str] = []


def note(s):
    print("·", s, flush=True)


def watch(page):
    page.on("pageerror", lambda e: problems.append(f"pageerror {page.url}: {e}"))
    page.on("console", lambda m: problems.append(f"console {page.url}: {m.text}") if m.type == "error" else None)
    page.on("response", lambda r: problems.append(f"HTTP {r.status} {r.request.method} {r.url}")
            if r.status >= 400 and "/v1/" in r.url else None)


def sign_in(page, who, home):
    page.goto(BASE + "/start")
    page.locator("button", has_text=re.compile(who)).first.click()
    page.wait_for_url(re.compile(home), timeout=20000)
    page.wait_for_load_state("networkidle")


def wait_valid(page, timeout=30000):
    # The plan's own badge ("Re-checked independently: valid · N checks"), not the page subtitle.
    page.wait_for_selector("text=/Re-checked independently: valid/", timeout=timeout)
    if page.locator("text=/Re-check failed/").count():
        problems.append("plan shown as invalid")


with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    watch(page)

    sign_in(page, "Joseph", r"/app/site")
    page.goto(BASE + "/app/lab")
    wait_valid(page)
    note("Lab opened; the summer preset is planned and re-checked")
    page.screenshot(path=str(OUT / "01_lab.png"))

    slider = page.locator("input[type=range]").first
    slider.focus()
    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowRight")
    time.sleep(2.5)
    wait_valid(page)
    note("weather changed: re-planned")

    # Hotter still (46 °C): this day has no protected plan as entered. The Lab must say so and offer the
    # permitted option, never show a blank result; applying it gives a valid plan again.
    slider.focus()
    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowRight")
    time.sleep(2.5)                                   # let the re-plan land before judging what is shown
    card = page.locator("[data-testid=lab-noplan]")
    card.or_(page.locator("text=/Re-checked independently: valid/")).first.wait_for(timeout=30000)
    if card.count():
        note("46 °C: 'No protected plan' shown with its permitted options; applying the first")
        card.get_by_role("button", name=re.compile("Apply")).first.click()
        card.wait_for(state="detached", timeout=20000)
    wait_valid(page)
    note("46 °C: valid plan after the permitted remedy")

    page.locator("label", has_text="A harder day for").locator("select").select_option(label="Anwar")
    for _ in range(4):
        page.locator("button", has_text="+30 min").click()
        time.sleep(1.8)
        wait_valid(page)
    shared = page.locator("text=needs a break (own device, shared by choice)").count()
    note(f"after four steps Anwar's watch shared 'needs a break': {bool(shared)}")
    def resolve_if_needed(what):
        card = page.locator("[data-testid=lab-noplan]")
        if card.count():
            note(f"no protected plan after {what}: the day waits; applying the permitted remedy")
            card.get_by_role("button", name=re.compile("Apply")).first.click()
            card.wait_for(state="detached", timeout=20000)
            time.sleep(1.0)

    page.locator("button", has_text="Hotter than forecast").click()
    time.sleep(2.2)
    resolve_if_needed("the heat rose")
    wait_valid(page)
    page.locator("label", has_text="Water runs out").locator("select").select_option(label="Rebar tying")
    time.sleep(2.2)
    resolve_if_needed("the water outage")
    wait_valid(page)
    page.screenshot(path=str(OUT / "02_lab_shift.png"), full_page=True)
    note("hotter and water outage re-planned from the current time")

    sign_in(page, "Ravi", r"/app/worker")
    page.goto(BASE + "/app/worker/data")
    page.wait_for_selector("text=Wearable (optional)", timeout=20000)
    card = page.locator("text=Wearable (optional)").locator("xpath=ancestor::div[contains(@class,'card')]")
    card.locator("button[role=switch]").nth(0).click()
    time.sleep(0.3)
    card.locator("button[role=switch]").nth(1).click()
    time.sleep(1.2)
    page.locator("button", has_text="Connect the demo watch").click()
    time.sleep(1.5)
    page.locator("button", has_text="Simulate a hard hour").click()
    page.wait_for_selector("text=Your supervisor was told", timeout=20000)
    card.screenshot(path=str(OUT / "03_wearable_alert.png"))
    note("Ravi's watch alerted Ravi first and shared only 'needs a break'")

    sign_in(page, "Joseph", r"/app/site")
    page.goto(BASE + "/app/site/tasks")
    page.wait_for_selector("text=own wearable suggests a break", timeout=20000)
    text = page.locator("main").inner_text()
    if re.search(r"\b\d{2,3}\s*bpm\b", text):
        problems.append("a heart rate reached the supervisor")
    page.screenshot(path=str(OUT / "04_supervisor_task.png"))
    note("Joseph sees a 'check on a worker' task with no numbers")
    b.close()

print("\nproblems:", problems or "none")
sys.exit(1 if problems else 0)
