# Licences and credits

Bardan uses free and open-source software, public data and free photos only. The same list is served by
`GET /v1/reports/licences` and shown in the app (Trust Centre → Licences, and the Credits page).

## Software and data

| Component | Version | Licence | Used for |
|---|---|---|---|
| [FastAPI](https://github.com/fastapi/fastapi) | 0.151.0 | MIT | API framework |
| [Starlette](https://github.com/encode/starlette) | 1.9.0 | BSD-3-Clause | ASGI toolkit (via FastAPI) |
| [Pydantic](https://github.com/pydantic/pydantic) | 2.14.1 | MIT | Typed request and response schemas |
| [Uvicorn](https://github.com/encode/uvicorn) | 0.54.0 | BSD-3-Clause | ASGI server |
| [HTTPX](https://github.com/encode/httpx) | 0.28.1 | BSD-3-Clause | HTTP client (forecast provider, AI adapter) |
| [jsonschema](https://github.com/python-jsonschema/jsonschema) | 4.26.0 | MIT | Contract and AI-output schema checks |
| [NumPy](https://numpy.org) | 2.5.4 | BSD-3-Clause | Forecast model numerics |
| [Google OR-Tools (CP-SAT)](https://github.com/google/or-tools) | 9.15 | Apache-2.0 | Constraint solver for the shift planner |
| [thermofeel (ECMWF)](https://github.com/ecmwf/thermofeel) | 2.3.0 | Apache-2.0 | Liljegren WBGT calculation |
| [tzdata](https://github.com/python/tzdata) | 2026.5 | Apache-2.0 | Time-zone database fallback |
| [pytest](https://pytest.org) | 9.1.1 | MIT | Release tests |
| [React / React DOM](https://react.dev) | 19.3.1 | MIT | User interface |
| [React Router](https://reactrouter.com) | 7.18.4 | MIT | Routing |
| [TanStack Query](https://tanstack.com/query) | 5.104.5 | MIT | Data fetching and caching |
| [Recharts](https://recharts.org) | 3.10.1 | MIT | Charts |
| [Lucide icons](https://lucide.dev) | 1.60.0 | ISC | Icons |
| [Motion](https://motion.dev) | 14.4.0 | MIT | Animation (respects reduced motion) |
| [Tailwind CSS](https://tailwindcss.com) | 4.3.3 | MIT | Styling |
| [Vite](https://vite.dev) | 8.3.4 | MIT | Build tool |
| [vite-plugin-pwa / Workbox](https://vite-pwa-org.netlify.app) | 2.0.0 / 7.4.1 | MIT | Offline app shell |
| [node-qrcode](https://github.com/soldair/node-qrcode) | 1.5.4 | MIT | QR codes for share links |
| [clsx](https://github.com/lukeed/clsx) | 2.1.1 | MIT | Class names |
| [Plus Jakarta Sans (Fontsource)](https://github.com/tokotype/PlusJakartaSans) | 5.3.0 | OFL-1.1 | Latin typeface |
| [IBM Plex Sans Arabic (Fontsource)](https://github.com/IBM/plex) | 5.3.0 | OFL-1.1 | Arabic typeface |
| [TypeScript](https://www.typescriptlang.org) | 5.9.3 | Apache-2.0 | Type checking |
| [Vitest](https://vitest.dev) | 5.0.5 | MIT | Device-engine conformance tests |
| [NASA POWER hourly data](https://power.larc.nasa.gov) | 2025 season | Public data; attribution requested | Weather replay for the scenario and the forecast backtest |
| [Open-Meteo forecast API](https://open-meteo.com) | live | CC BY 4.0 | Live 72-hour forecast mode |
| [Unsplash photos](https://unsplash.com/license) | 9 photos | Unsplash Licence | Landing and persona photos (free, no watermarks) |

## Photos

All photos are from [Unsplash](https://unsplash.com/license) (free to use, no watermarks). They are used
unmodified apart from resizing and format conversion. Photographers:

| Photo | Photographer | Source |
|---|---|---|
| Seven construction workers on a slab | Scott Blake | [Unsplash](https://unsplash.com/photos/seven-construction-workers-standing-on-white-field-x-ghf9LjrVg) |
| People working on a building | Josue Isai Ramos Figueroa | [Unsplash](https://unsplash.com/photos/people-working-on-building-during-daytime-qvBYnMuNJ9A) |
| Silhouetted construction workers at sunset | Shivendu Shukla | [Unsplash](https://unsplash.com/photos/silhouetted-construction-workers-at-sunset-3yoTPuYR9ZY) |
| Burj Khalifa and highway in Dubai | David Rodrigo | [Unsplash](https://unsplash.com/photos/burj-khalifa-and-highway-in-dubai-Fr6zexbmjmc) |
| Construction worker inspects rebar | Toni Reed | [Unsplash](https://unsplash.com/photos/construction-worker-inspects-rebar-on-a-building-site-dSjrv4w1g1Q) |
| Two men working | Etienne Girardet | [Unsplash](https://unsplash.com/photos/two-men-working-sgYamIzhAhg) |
| Crane lifting a concrete panel | Elvir K | [Unsplash](https://unsplash.com/photos/gray-steel-frame-Xtyh5b5GGX4) |
| Low-angle view of a tower crane | James Sullivan | [Unsplash](https://unsplash.com/photos/low-angle-photography-of-gray-tower-crane-ESZRBtkQ_f8) |
| Construction worker on a building frame | Josh Olalde | [Unsplash](https://unsplash.com/photos/construction-worker-in-hard-hat-on-building-frame-X1P1_EDNnok) |

## Data notes

* **Weather replay:** hourly data for Abu Dhabi, summer 2025, from NASA POWER (public data; attribution
  requested). WBGT is derived with the Liljegren method (thermofeel, ECMWF). Values are labelled as derived,
  never as instrument readings.
* **Live forecast mode:** weather data by [Open-Meteo.com](https://open-meteo.com) under CC BY 4.0, shown
  with attribution wherever it is used.
* **Policy packs:** demonstration encodings of the Abu Dhabi heat code and the federal midday-break rule,
  with a paraphrased Sharjah excerpt for the compiler demo. They are not official wording and must be
  re-transcribed from the official documents and approved before any real use.
* **People, site, lab reports and history:** synthetic and fictional. Any resemblance to real people is
  coincidental.
* **Logo:** supplied by the author. **Interface:** original work for this project.

## Documentation and film tooling

These tools were used only to draw the documentation and make the film. None of them ships in the app, and the
images and video they produced are original work for this project.

| Tool | Licence | Used for |
|---|---|---|
| [Mermaid CLI](https://github.com/mermaid-js/mermaid-cli) | MIT | The technical diagrams in `docs/diagrams/src` |
| [Playwright](https://playwright.dev) with Chromium | Apache-2.0 | Browser rehearsals (`e2e/`), screenshots, and drawing the diagrams in `docs/diagrams/custom` |
| [imagequant](https://github.com/ImageOptim/libimagequant) (optional) | GPL-3.0 | Shrinking the diagram PNGs at build time; it is not part of the app |
| [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) (ONNX) | Apache-2.0 | The film's narration voice |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | MIT | Checking the film's captions against its soundtrack |
| [FFmpeg](https://ffmpeg.org) | LGPL-2.1+ / GPL (as built) | Encoding the film and the README animation |

The film's music and sound effects were generated in code for this project; no stock music or footage is used. The
screens shown in the README and the film are captured from the prototype itself, running on synthetic data.

## Methods and published values (Scenario Lab, break planner, optional wearable)

No code or text is copied from these; the equations and values are implemented from the published descriptions and
are listed for review in [RULE-REVIEW.md](RULE-REVIEW.md) (rows 16–21).

| Source | Used for |
|---|---|
| ISO 7243:2017, *Ergonomics of the thermal environment: assessment of heat stress using the WBGT index* | The one-hour WBGT reference values by metabolic rate |
| NIOSH, *Criteria for a Recommended Standard: Occupational Exposure to Heat and Hot Environments* (DHHS 2016-106) | REL and RAL (the same equations), acclimatization, hydration background |
| ACGIH TLV documentation for heat stress, as tabulated in the [OSHA Technical Manual, Section III, Chapter 4](https://obis.osha.gov/dts/osta/otm/otm_iii/otm_iii_4.html) | Work-rate classes, clothing adjustment factors, the screening table the tests compare against, physiological warning signs |
| Buller MJ et al. (2013), *Estimation of human core temperature from sequential heart rate observations*, Physiological Measurement 34:781–798; [US 2014/0180027 A1](https://patents.google.com/patent/US20140180027A1/en) | ECTemp parameters for the phone's body-heat estimate |
| AIHA Thermal Stress Working Group (2024), *Wearable physiological monitoring to assess heat strain* (white paper) | Accuracy limits, false alarms at 38 °C, consent and no-penalty safeguards |
| Morrissey MC et al. (2026), *Leveraging wearables to safeguard workers in a hotter climate*, Frontiers in Public Health 14:1867796 | No use for discipline, pay, task allocation, employment or immigration decisions |
| Hong Kong Labour Department, *Guidance Notes on Prevention of Heat Stroke at Work* (third edition, revised August 2026) | Hourly work–rest schedules by workload; extra rest for unacclimatised workers |
| Abu Dhabi Public Health Centre, *Safety in the Heat* (2026 campaign), and the MoHRE midday break (12:30–15:00, 15 June–15 September 2026) | Water guidance and the federal floor, already in the rule packs |
