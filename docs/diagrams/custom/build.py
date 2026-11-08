"""Render the hand-laid diagrams in this folder to PNG with the Chromium that Playwright installs.

    python3 docs/diagrams/custom/build.py            # every page
    python3 docs/diagrams/custom/build.py hero ai-integration

Each <name>.html here becomes docs/diagrams/<name>.png (twice the layout size, transparent corners). A page can
set data-scale on its .canvas (for example 1.5 for screenshot collages) and data-format="jpeg".

Icons are Lucide (ISC licence, the same set the app uses). They are copied into the page at build time from
frontend/node_modules, so run `make setup` first. Write <i data-icon="droplet"></i> in a page to place one.

After rendering, the script reports any element that spills outside its canvas, so a long label is caught here
rather than in the README. If the `imagequant` package is installed (pip install imagequant), each PNG is reduced to
a 256-colour palette (the pngquant method), which keeps it sharp at about a third of the size.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

try:
    import imagequant
    from PIL import Image
except ImportError:  # optional: without it the PNGs are simply larger
    imagequant = None

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ICONS = ROOT / "frontend" / "node_modules" / "lucide-react" / "dist" / "esm" / "icons"
OUT = HERE.parent

_cache: dict[str, str] = {}


def icon_svg(name: str, extra_class: str = "") -> str:
    if name not in _cache:
        src = (ICONS / f"{name}.mjs").read_text(encoding="utf-8")
        alias = re.search(r"export \{ default \} from '\./([\w-]+)\.mjs'", src)
        if alias and "node:" not in src:          # an old name kept as an alias of the new one
            src = (ICONS / f"{alias.group(1)}.mjs").read_text(encoding="utf-8")
        body = src[src.index("node:"):src.index("};")]
        parts = []
        for tag, attrs in re.findall(r'\[\s*"(\w+)",\s*\{([^}]*)\}\s*\]', body):
            kv = [(k, v) for k, v in re.findall(r'(\w+):\s*"([^"]*)"', attrs) if k != "key"]
            parts.append(f"<{tag} " + " ".join(f'{k}="{v}"' for k, v in kv) + "/>")
        _cache[name] = "".join(parts)
    cls = ("ic " + extra_class).strip()
    return (f'<svg class="{cls}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
            f'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
            f'aria-hidden="true">{_cache[name]}</svg>')


def inline_icons(html: str) -> str:
    def sub(m: re.Match) -> str:
        return icon_svg(m.group(1), m.group(3) or "")
    return re.sub(r'<i data-icon="([\w-]+)"( class="([^"]*)")?\s*></i>', sub, html)


SPILL_JS = """() => {
  const c = document.querySelector('.canvas').getBoundingClientRect();
  const bad = [];
  for (const el of document.querySelectorAll('.canvas *')) {
    if (el.closest('svg') && el.tagName.toLowerCase() !== 'svg') continue;
    if (el.closest('.bleed')) continue;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    if (r.right > c.right + 0.5 || r.bottom > c.bottom + 0.5 || r.left < c.left - 0.5) {
      bad.push(el.tagName + '.' + (el.className.baseVal ?? el.className) + ' ' + (el.textContent || '').trim().slice(0, 40));
    }
    if (el.matches('.fit') && (el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1)) {
      bad.push('overflow: ' + (el.textContent || '').trim().slice(0, 60));
    }
  }
  return bad.slice(0, 12);
}"""


def render(names: list[str]) -> None:
    pages = sorted(p for p in HERE.glob("*.html") if not p.name.startswith("_"))
    if names:
        pages = [p for p in pages if p.stem in names]
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for page_file in pages:
            html = inline_icons(page_file.read_text(encoding="utf-8"))
            tmp = HERE / f"_build_{page_file.name}"
            tmp.write_text(html, encoding="utf-8")
            try:
                probe = browser.new_page(viewport={"width": 1800, "height": 1200})
                probe.goto(tmp.as_uri())
                scale = float(probe.evaluate("document.querySelector('.canvas').dataset.scale || 2"))
                fmt = probe.evaluate("document.querySelector('.canvas').dataset.format || 'png'")
                probe.close()
                page = browser.new_page(viewport={"width": 1800, "height": 1200}, device_scale_factor=scale)
                page.goto(tmp.as_uri())
                page.evaluate("document.fonts.ready")
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(150)
                spill = page.evaluate(SPILL_JS)
                out = OUT / f"{page_file.stem}.{'jpg' if fmt == 'jpeg' else 'png'}"
                el = page.locator(".canvas")
                if fmt == "jpeg":
                    el.screenshot(path=str(out), type="jpeg", quality=88)
                else:
                    el.screenshot(path=str(out), omit_background=True)
                    if imagequant is not None:
                        q = imagequant.quantize_pil_image(Image.open(out).convert("RGBA"), dithering_level=1.0,
                                                          max_colors=256, min_quality=70, max_quality=95)
                        q.save(out, optimize=True)
                box = el.bounding_box()
                print(f"{out.relative_to(ROOT)}  {round(box['width'])}x{round(box['height'])} @{scale}x  "
                      f"{out.stat().st_size // 1024} KB" + (f"  SPILL: {spill}" if spill else ""))
                page.close()
            finally:
                tmp.unlink(missing_ok=True)
        browser.close()


if __name__ == "__main__":
    render(sys.argv[1:])
