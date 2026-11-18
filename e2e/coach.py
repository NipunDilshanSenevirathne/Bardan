"""Follow the step-by-step guided tour from start to finish, as a judge would (Playwright, AI off).

    python e2e/coach.py http://127.0.0.1:8080

Guided tour -> Start the guided tour, then all nine steps: every hint must ring its control (or say what to do
when there is nothing to ring), the judge does the clicking, and the tour ends with "Tour complete". Prints each
card as it appears; exits non-zero on any page error or failed API call other than the intended clinical denial.
"""
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else str(Path(__file__).parent / "out" / "coach"))
OUT.mkdir(parents=True, exist_ok=True)
problems: list[str] = []


def card(page):
    c = page.locator('[data-tour="coach-card"]')
    c.wait_for(timeout=15000)
    return c


def say(page, label, ring_expected=None):
    txt = card(page).inner_text().replace("\n", " | ")
    ring = page.locator("div.pointer-events-none.fixed").count()
    print(f"{label}: ring={ring} :: {txt[:170]}", flush=True)
    if ring_expected is not None and bool(ring) != ring_expected:
        problems.append(f"{label}: ring {'missing' if ring_expected else 'unexpected'}")
    return txt


def nxt(page, wait=1.0):
    card(page).locator('[data-tour="coach-next"]').click()
    time.sleep(wait)


def click(page, key, wait=1.4):
    page.locator(f'[data-tour="{key}"]').first.click()
    time.sleep(wait)


def shot(page, name):
    page.screenshot(path=str(OUT / f"{name}.jpg"), type="jpeg", quality=70)


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))
    page.on("response", lambda r: problems.append(f"HTTP {r.status} {r.url}")
            if r.status >= 400 and "/v1/" in r.url else None)

    page.goto(BASE + "/start")
    page.locator("button", has_text=re.compile("Joseph")).first.click()
    page.wait_for_url(re.compile(r"/app/site"), timeout=20000)
    page.wait_for_load_state("networkidle")
    time.sleep(1)
    page.locator("button:visible", has_text=re.compile("^Guided tour$")).first.click()
    time.sleep(0.8)
    page.locator('[data-tour="coach-start"]').click()
    time.sleep(2.5)

    # 1. Plan tomorrow (Joseph)
    say(page, "1.1", True)
    click(page, "plan-evaluate", 3)
    say(page, "1.2", True)
    click(page, "plan-optimise", 4)
    say(page, "1.3", True)
    shot(page, "1_certificate")
    nxt(page)
    say(page, "1.4", True)
    click(page, "plan-approve")
    say(page, "1.5", True)
    click(page, "plan-activate")
    say(page, "1 done", False)
    nxt(page, 2.5)

    # 2. Live values govern (Ravi)
    say(page, "2.1", True)
    nxt(page)
    say(page, "2.2", True)
    click(page, "worker-explain")
    say(page, "2 done", False)
    nxt(page, 2.5)

    # 3. Report in Arabic (Anwar)
    say(page, "3.1", True)
    shot(page, "3_arabic")
    click(page, "report-example", 3)
    say(page, "3.2", True)
    click(page, "report-confirm")
    say(page, "3 done", False)
    nxt(page, 2.5)

    # 4. Dispute a false completion (Joseph, then Ravi)
    say(page, "4.1", True)
    task = page.locator('[data-tour="task-WATER_RESTORE"]').first
    for label in ("^Accept$", "^Start$", "Report complete"):
        task.locator("button", has_text=re.compile(label)).first.click()
        time.sleep(1.2)
        task = page.locator('[data-tour="task-WATER_RESTORE"]').first
    nxt(page)
    say(page, "4.2", False)
    nxt(page, 2.5)
    say(page, "4.3", True)
    click(page, "worker-dispute")
    say(page, "4 done", False)
    nxt(page, 2.5)

    # 5. Watch the gate (Anwar)
    say(page, "5.1", True)
    page.locator("#askq").fill("Are my kidneys failing?")
    page.locator("#askq").press("Enter")
    time.sleep(3)
    nxt(page)
    say(page, "5.2", True)
    shot(page, "5_gate")
    nxt(page)
    say(page, "5 done", False)
    nxt(page, 2.5)

    # 6. Emergency with no network (Ravi)
    say(page, "6.1", False)
    nxt(page)
    say(page, "6.2", True)
    click(page, "shell-emergency", 0.5)
    page.locator("button", has_text=re.compile("Confused")).first.click()
    time.sleep(1)
    say(page, "6.3", False)
    shot(page, "6_emergency")
    for _ in range(3):
        dialog = page.locator("[role=dialog][aria-label=Emergency]")
        if not dialog.count():
            break
        close = dialog.locator("button", has_text=re.compile("^Close$"))
        (close.last if close.count() else dialog.locator("button[aria-label=Close]").first).click()
        time.sleep(0.6)
    nxt(page)
    say(page, "6 done", False)
    nxt(page, 2.5)

    # 7. Privacy you can test (Joseph): the refusal is the point
    say(page, "7.1", True)
    click(page, "privacy-try")
    say(page, "7 done", False)
    nxt(page, 3)

    # 8. Your own scenario (Joseph, Scenario Lab)
    say(page, "8.1", True)
    click(page, "lab-add-person", 1.5)
    say(page, "8.2", True)
    page.locator('input[type="range"]').first.focus()
    page.keyboard.press("ArrowRight")
    time.sleep(2.5)
    nxt(page)
    say(page, "8.3", True)
    shot(page, "8_break_planner")
    nxt(page)
    say(page, "8.4", True)
    click(page, "lab-step", 1.5)
    say(page, "8 done", False)
    nxt(page, 2.5)

    # 9. A wearable the worker controls (Ravi)
    say(page, "9.1", True)
    wear = page.locator('[data-tour="wear-card"]')
    wear.locator("button[role=switch]").nth(0).click()
    time.sleep(0.4)
    wear.locator("button[role=switch]").nth(1).click()
    time.sleep(1)
    nxt(page)
    say(page, "9.2", True)
    click(page, "wear-connect")
    say(page, "9.3", True)
    click(page, "wear-hard", 1.5)
    say(page, "9.4", False)
    nxt(page)
    end = say(page, "9 done", False)
    if "Tour complete" not in end:
        problems.append("the tour did not end with 'Tour complete'")
    shot(page, "9_done")
    nxt(page, 0.8)
    if page.locator('[data-tour="coach-card"]').count():
        problems.append("the tour card stayed open after Finish")
    browser.close()

problems = [x for x in problems if "/v1/clinical/patients/" not in x]   # step 7 is meant to be refused
print("\nproblems:", problems or "none")
sys.exit(1 if problems else 0)
