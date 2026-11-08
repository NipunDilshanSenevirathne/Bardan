"""Model adapter for the prototype: Gemini API free tier (stateless generateContent).

Production plan (finalsystem.md §17) uses UAE-hosted open models. The prototype
uses the Gemini API free tier on SYNTHETIC data only. Model IDs, tiers, quotas
and fallbacks are an operational detail documented in docs/AI-MODELS.md; they
are never sent to the interface. The interface only ever sees "Bardan
Intelligence", the gate result and whether a reviewed template was used.

Design
  * discovery: ListModels once per process (cached), matched against families
  * a measured preference order per capability (fast text, audio, reasoning,
    bulk, embeddings, speech); other models of the same families come after it
  * thinking kept to the lowest level each model accepts, so a short JSON
    answer is not delayed or cut off by the model's own reasoning
  * client-side quotas: requests per minute and per day per model (free-tier
    limits from the author's AI Studio project), so we skip a model before Google
    has to refuse us; 429 responses honour RetryInfo, a zero quota parks the
    model until the daily reset, and a model the key cannot use (404) is never
    tried again in this process
  * dialects: JSON Schema output -> OpenAPI schema output -> plain JSON in text
    (Gemma models get no system instruction and no JSON mode)
  * an LRU cache of raw outputs keyed by the request, so repeated demo steps do
    not spend quota; the policy gate still runs on every use
  * hard timeouts; the caller always has a deterministic fallback
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

log = logging.getLogger("bardan.ai")
API = "https://generativelanguage.googleapis.com/v1beta"
ADAPTER_VERSION = "bardan-intelligence-adapter@1.3.0"
QUOTA_TZ = ZoneInfo("America/Los_Angeles")     # free-tier daily quotas reset at midnight Pacific time

# Free-tier limits from the author's AI Studio project (October 2026). RPM, RPD, TPM (None = not limited here).
FAMILY_LIMITS = {
    "flash-lite-3": (15, 500, None),
    "flash-lite-2.5": (10, 20, None),
    "flash": (5, 20, None),
    "gemma-4": (30, 14400, 16000),
    "tts": (3, 10, None),
    "embedding": (100, 1000, None),
}
# Preference order per capability, measured with the author's free-tier key on 21 October 2026. Median time for a
# two-line Arabic answer with JSON output: 3.5 Flash-Lite 1.1 s, 3.1 Flash-Lite 1.5 s, 3 Flash 1.5 s and 3.6 Flash
# 1.9 s (minimal thinking), Gemma 4 26B 2.3 s (minimal thinking). Speech: 2.3-4.0 s for one sentence.
# Models of a capability's families that are not listed here are tried after these, newest first.
PREFERRED = {
    "fast": ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemma-4-26b-a4b-it", "gemini-3-flash-preview",
             "gemini-3.6-flash"],
    "audio": ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3-flash-preview", "gemini-3.6-flash"],
    "reasoning": ["gemini-3-flash-preview", "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite",
                  "gemma-4-26b-a4b-it"],
    "bulk": ["gemma-4-26b-a4b-it", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"],
    "embedding": ["gemini-embedding-001", "gemini-embedding-2"],
    "tts": ["gemini-3.8-flash-lite-tts", "gemini-3.8-flash-tts", "gemini-2.5-flash-preview-tts",
            "gemini-3.1-flash-tts-preview"],
}
# Never selected. Far too slow for an interactive answer on the free tier (13-90 s for a two-line JSON answer, or
# no answer within 90 s): 3.8 Flash, 3.7 Flash, Gemma 4 31B. Aliases of a listed model: 3.5 Flash is served by
# 3.6 Flash, and the 3.1 Flash-Lite preview by 3.1 Flash-Lite.
SKIP = {"gemini-3.8-flash", "gemini-3.7-flash", "gemma-4-31b-it", "gemini-3.5-flash", "gemini-3.1-flash-lite-preview"}
DEFAULT_MODELS = {   # used only if ListModels is unavailable
    "flash-lite-3": ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"],
    "flash": ["gemini-3-flash-preview", "gemini-3.6-flash"],
    "gemma-4": ["gemma-4-26b-a4b-it"],
    "embedding": ["gemini-embedding-001", "gemini-embedding-2"],
    "tts": ["gemini-3.8-flash-lite-tts", "gemini-3.8-flash-tts", "gemini-2.5-flash-preview-tts"],
}
CAPABILITY_TIERS = {
    "fast": ["flash-lite-3", "gemma-4", "flash", "flash-lite-2.5"],
    "audio": ["flash-lite-3", "flash", "flash-lite-2.5"],
    "reasoning": ["flash", "flash-lite-3", "gemma-4", "flash-lite-2.5"],
    "bulk": ["gemma-4", "flash-lite-3"],
}
# Gemini 3 Flash and Gemma 4 think by default. On the free tier that cost 2-80 s and could use up the whole output
# budget before any JSON was written, so the adapter asks for the lowest level each model accepts.
THINKING_FAMILIES = {"flash", "gemma-4"}
THINKING_LEVELS = ["minimal", "low", None]
THINKING_HEADROOM = 1024           # extra output tokens when a model may still think
TIMEOUT_COOLDOWN_S = 180           # after a timeout the next request starts with another model
EXCLUDE = re.compile(r"(image|tts|live|audio|native|exp|computer|robotics|thinking|vision|embedding|aqa|learnlm)",
                     re.I)


def _family(name: str) -> str | None:
    n = name.split("/")[-1].lower()
    if "embedding" in n:
        return "embedding"
    if "tts" in n:
        return None if "pro" in n else "tts"
    if n.startswith("gemma-4"):
        return "gemma-4" if re.search(r"(26b|31b)", n) else None
    m = re.match(r"gemini-(\d+(?:\.\d+)?)-flash-lite", n)
    if m and EXCLUDE.search(n[m.end():]):
        return None
    if m:
        return "flash-lite-3" if float(m.group(1)) >= 3 else "flash-lite-2.5" if m.group(1) == "2.5" else None
    m = re.match(r"gemini-(\d+(?:\.\d+)?)-flash(?!-lite)", n)
    if m and not EXCLUDE.search(n.replace("flash", "")):
        return "flash" if float(m.group(1)) >= 2.5 else None
    return None


def _version_key(name: str) -> tuple:
    n = name.split("/")[-1].lower()
    m = re.search(r"-(\d+(?:\.\d+)?)(?=-|$)", n)
    v = float(m.group(1)) if m else 0.0
    preview = 1 if "preview" in n else 0
    return (-v, preview, n)


@dataclass
class ModelState:
    name: str
    family: str
    minute: deque = field(default_factory=deque)
    day: str = ""
    day_count: int = 0
    tokens_minute: deque = field(default_factory=deque)
    cooling_until: float = 0.0
    dialect: str | None = None        # "jsonschema" | "openapi" | "text"
    thinking: str | None = "unknown"  # the thinking level this model accepted ("minimal", "low", None)
    disabled: str | None = None       # set when the key can never use this model (404)
    failures: int = 0


class AIUnavailable(Exception):
    pass


class Embeddings(list):
    """Vectors in input order. ``model`` names the model that produced them: vectors from different embedding
    models live in different spaces and must never be compared with each other."""
    model: str = ""


def governance_check() -> None:
    """Data governance (T53): free-tier model services may use inputs to improve their products, so only the
    synthetic sandbox may ever reach them. A deployment that declares real data must use a paid, no-training
    tier under a data processing agreement; until then every AI call is refused and templates are used."""
    data_class = os.environ.get("BARDAN_DATA_CLASS", "synthetic")
    tier = os.environ.get("BARDAN_AI_TIER", "free")
    if data_class != "synthetic" and tier == "free":
        raise AIUnavailable("governance_blocked: real data may not be sent to a free-tier model")


class GeminiClient:
    def __init__(self, api_key: str | None = None, transport: httpx.BaseTransport | None = None) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("GEMINI_API_KEY", "")
        self.transport = transport        # tests plug in a scripted transport; None = the network
        self.models: dict[str, ModelState] = {}
        self.discovered = False
        self.discovery_error: str | None = None
        self.lock = threading.Lock()
        self.cache: OrderedDict[str, Any] = OrderedDict()
        self.cache_max = 512
        self.stats = {"calls": 0, "cache_hits": 0, "fallbacks": 0, "rate_limited": 0, "errors": 0,
                      "unavailable_models": 0}

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _http(self, timeout: float) -> httpx.Client:
        return httpx.Client(timeout=timeout, transport=self.transport)

    def _cache_get(self, key: str) -> Any:
        with self.lock:
            hit = self.cache.get(key)
            if hit is not None:
                self.cache.move_to_end(key)
                self.stats["cache_hits"] += 1
            return hit

    def _cache_put(self, key: str, value: Any) -> None:
        with self.lock:
            self.cache[key] = value
            self.cache.move_to_end(key)
            while len(self.cache) > self.cache_max:
                self.cache.popitem(last=False)

    # ------------------------------------------------------------ discovery
    def discover(self) -> None:
        if self.discovered or not self.configured:
            return
        names: list[str] = []
        try:
            with self._http(8.0) as c:
                token = None
                for _ in range(5):
                    params = {"pageSize": 1000, **({"pageToken": token} if token else {})}
                    r = c.get(f"{API}/models", params=params, headers={"x-goog-api-key": self.api_key})
                    r.raise_for_status()
                    data = r.json()
                    for m in data.get("models", []):
                        methods = m.get("supportedGenerationMethods", [])
                        if "generateContent" in methods or "embedContent" in methods:
                            names.append(m["name"].split("/")[-1])
                    token = data.get("nextPageToken")
                    if not token:
                        break
        except Exception as exc:  # fall back to documented defaults
            self.discovery_error = type(exc).__name__
            names = [n for ns in DEFAULT_MODELS.values() for n in ns]
        for n in names:
            fam = _family(n)
            if fam and n not in SKIP:
                self.models.setdefault(n, ModelState(n, fam))
        self.discovered = True
        log.info("AI models discovered: %s", sorted(self.models))

    def _candidates(self, tier: str) -> list[ModelState]:
        self.discover()
        out = [self.models[n] for n in PREFERRED.get(tier, []) if n in self.models]
        seen = {m.name for m in out}
        for fam in CAPABILITY_TIERS.get(tier, [tier]):
            out.extend(sorted((m for m in self.models.values() if m.family == fam and m.name not in seen),
                              key=lambda m: _version_key(m.name)))
        return [m for m in out if not m.disabled]

    # --------------------------------------------------------------- quotas
    def _admit(self, m: ModelState, est_tokens: int = 0) -> bool:
        rpm, rpd, tpm = FAMILY_LIMITS[m.family]
        now = time.time()
        today = datetime.now(QUOTA_TZ).strftime("%Y-%m-%d")
        with self.lock:
            if m.disabled or m.cooling_until > now:
                return False
            if m.day != today:
                m.day, m.day_count = today, 0
            while m.minute and now - m.minute[0] > 60:
                m.minute.popleft()
            while m.tokens_minute and now - m.tokens_minute[0][0] > 60:
                m.tokens_minute.popleft()
            if len(m.minute) >= rpm or m.day_count >= rpd:
                return False
            if tpm and sum(t for _, t in m.tokens_minute) + est_tokens > tpm:
                return False
            m.minute.append(now)
            m.day_count += 1
            if tpm:
                m.tokens_minute.append((now, est_tokens))
            return True

    def quota_report(self) -> list[dict[str, Any]]:
        """For docs and operators only. Never served to the interface."""
        self.discover()
        out = []
        for m in sorted(self.models.values(), key=lambda m: (m.family, _version_key(m.name))):
            rpm, rpd, tpm = FAMILY_LIMITS[m.family]
            out.append({"model": m.name, "family": m.family, "rpm": rpm, "rpd": rpd, "tpm": tpm,
                        "used_today": m.day_count, "cooling": m.cooling_until > time.time(), "dialect": m.dialect,
                        "thinking": m.thinking, "disabled": m.disabled})
        return out

    def _park(self, m: ModelState, exc: _RateLimited) -> None:
        self.stats["rate_limited"] += 1
        m.cooling_until = exc.until
        if exc.zero_quota or exc.per_day:
            m.day, m.day_count = datetime.now(QUOTA_TZ).strftime("%Y-%m-%d"), FAMILY_LIMITS[m.family][1]
            log.warning("AI model %s has no free quota left today; parked until the daily reset", m.name)

    def _disable(self, m: ModelState, reason: str) -> None:
        m.disabled = reason[:160]
        self.stats["unavailable_models"] += 1
        log.warning("AI model %s is not available to this key and will not be tried again: %s", m.name, reason)

    # ----------------------------------------------------------------- calls
    def generate_json(self, *, tier: str, system: str, user: str, schema: dict[str, Any],
                      inline: list[tuple[str, bytes]] | None = None, temperature: float = 0.2,
                      max_tokens: int = 900, timeout_s: float = 12.0, cache: bool = True) -> dict[str, Any]:
        """Return {"data": <parsed JSON>, "latency_ms", "tokens", "cached"}; raise AIUnavailable."""
        if not self.configured:
            raise AIUnavailable("not_configured")
        governance_check()
        key = _cache_key(tier, system, user, schema, inline)
        hit = self._cache_get(key) if cache else None
        if hit is not None:
            return {**hit, "cached": True}
        deadline = time.time() + timeout_s
        last_err = "no_model_available"
        est = (len(system) + len(user)) // 3 + max_tokens
        for m in self._candidates(tier):
            if time.time() > deadline - 1.0:
                last_err = "budget_exceeded"
                break
            if m.family == "gemma-4" and any(mime.startswith("audio/") for mime, _ in inline or []):
                continue                      # Gemma reads images here, but not audio
            if not self._admit(m, est):
                continue
            try:
                out = self._call(m, system, user, schema, inline, temperature, max_tokens,
                                 max(2.0, deadline - time.time()))
                self.stats["calls"] += 1
                m.failures = 0
                if cache:
                    self._cache_put(key, out)
                return {**out, "cached": False}
            except _RateLimited as rl:
                self._park(m, rl)
                last_err = "rate_limited"
            except _Gone as gone:
                self._disable(m, str(gone))
                last_err = "model_unavailable"
            except httpx.TimeoutException as exc:
                # A provider timeout ends the attempt at once: the approved template must follow within 2 s of the
                # timeout (§19 AI responsiveness, T51). No second model is tried now; the next request starts
                # with another model.
                self.stats["errors"] += 1
                m.failures += 1
                m.cooling_until = time.time() + TIMEOUT_COOLDOWN_S
                last_err = "timeout"
                log.warning("AI call timed out on %s: %s", m.name, type(exc).__name__)
                break
            except Exception as exc:
                self.stats["errors"] += 1
                m.failures += 1
                server_error = isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500
                if server_error or m.failures >= 3:
                    m.cooling_until = time.time() + (60 if server_error else 120)
                last_err = type(exc).__name__
                log.warning("AI call failed on %s: %s", m.name, str(exc)[:200])
        self.stats["fallbacks"] += 1
        raise AIUnavailable(last_err)

    def _call(self, m: ModelState, system, user, schema, inline, temperature, max_tokens, timeout_s):
        deadline = time.time() + timeout_s
        dialects = [m.dialect] if m.dialect else (["text"] if m.family == "gemma-4" else
                                                 ["jsonschema", "openapi", "text"])
        thinks = [m.thinking] if m.thinking != "unknown" else (
            list(THINKING_LEVELS) if m.family in THINKING_FAMILIES else [None])
        di = ti = 0
        err: Exception | None = None
        while di < len(dialects) and ti < len(thinks):
            remaining = deadline - time.time()
            if remaining <= 0.5:
                raise httpx.ReadTimeout("time budget used up")
            d, think = dialects[di], thinks[ti]
            body = self._body(m, d, system, user, schema, inline, temperature, max_tokens, think)
            t0 = time.perf_counter()
            with self._http(remaining) as c:
                r = c.post(f"{API}/models/{m.name}:generateContent", json=body,
                           headers={"x-goog-api-key": self.api_key})
            if r.status_code == 429:
                raise _RateLimited(r)
            if r.status_code == 404:
                raise _Gone(_error_message(r))
            if r.status_code == 400:
                msg = _error_message(r)
                if "thinking" in msg.lower() and ti + 1 < len(thinks):
                    ti += 1                   # this model does not accept that thinking level: try the next
                    continue
                err = RuntimeError(f"400 {msg[:200]}")
                di += 1                       # try the next output dialect
                continue
            r.raise_for_status()
            data = r.json()
            cand = (data.get("candidates") or [{}])[0]
            parsed = _parse_json(_text(data))
            if parsed is None:
                if cand.get("finishReason") == "MAX_TOKENS":
                    raise RuntimeError("output truncated before the JSON was complete")
                err = ValueError("model did not return JSON")
                di += 1
                continue
            m.dialect, m.thinking = d, think
            usage = data.get("usageMetadata", {})
            ms = int((time.perf_counter() - t0) * 1000)
            log.info("AI call ok: model=%s dialect=%s thinking=%s latency_ms=%d", m.name, d, think, ms)
            return {"data": parsed, "latency_ms": ms,
                    "tokens": {"in": usage.get("promptTokenCount"), "out": usage.get("candidatesTokenCount")},
                    "finish": cand.get("finishReason")}
        raise err or RuntimeError("no dialect worked")

    def _body(self, m, dialect, system, user, schema, inline, temperature, max_tokens, think=None):
        parts: list[dict[str, Any]] = []
        sys_text = system
        if dialect == "text":
            sys_text = (system + "\n\nReturn ONLY one JSON object, no prose, matching this JSON Schema:\n" +
                        json.dumps(schema, ensure_ascii=False))
        if m.family == "gemma-4":
            parts.append({"text": sys_text + "\n\n---\n\n" + user})
        else:
            parts.append({"text": user})
        for mime, blob in inline or []:
            parts.append({"inline_data": {"mime_type": mime, "data": base64.b64encode(blob).decode()}})
        headroom = THINKING_HEADROOM if m.family in THINKING_FAMILIES and think != "minimal" else 0
        cfg: dict[str, Any] = {"temperature": temperature, "maxOutputTokens": max_tokens + headroom}
        if think:
            cfg["thinkingConfig"] = {"thinkingLevel": think}
        if dialect == "jsonschema":
            cfg["responseMimeType"] = "application/json"
            cfg["responseJsonSchema"] = schema
        elif dialect == "openapi":
            cfg["responseMimeType"] = "application/json"
            cfg["responseSchema"] = _to_openapi(schema)
        body: dict[str, Any] = {"contents": [{"role": "user", "parts": parts}], "generationConfig": cfg}
        if m.family != "gemma-4":
            body["systemInstruction"] = {"parts": [{"text": sys_text}]}
        return body

    # ------------------------------------------------------------ embeddings
    def embed(self, texts: list[str], timeout_s: float = 8.0, task_types: list[str] | None = None,
              model: str | None = None) -> Embeddings:
        """Embed texts in one batch with ONE model (named on the result). ``model`` pins the model, for example to
        embed a question with the model that indexed the passages; if it cannot be used, AIUnavailable."""
        if not self.configured:
            raise AIUnavailable("not_configured")
        governance_check()
        if model:
            self.discover()
            cands = [self.models[model]] if model in self.models and not self.models[model].disabled else []
        else:
            cands = self._candidates("embedding")
        for m in cands:
            if not self._admit(m):
                continue
            reqs = []
            for i, t in enumerate(texts):
                q: dict[str, Any] = {"model": f"models/{m.name}", "content": {"parts": [{"text": t}]}}
                if task_types:
                    q["taskType"] = task_types[i]
                reqs.append(q)
            try:
                with self._http(timeout_s) as c:
                    r = c.post(f"{API}/models/{m.name}:batchEmbedContents", json={"requests": reqs},
                               headers={"x-goog-api-key": self.api_key})
                if r.status_code == 429:
                    self._park(m, _RateLimited(r))
                    continue
                if r.status_code == 404:
                    self._disable(m, _error_message(r))
                    continue
                r.raise_for_status()
                out = Embeddings(e["values"] for e in r.json()["embeddings"])
                out.model = m.name
                return out
            except Exception as exc:
                log.warning("embedding failed on %s: %s", m.name, str(exc)[:200])
        raise AIUnavailable("embedding_unavailable")

    # ------------------------------------------------------------------- TTS
    def speak(self, text: str, voice: str = "Kore", timeout_s: float = 15.0) -> bytes:
        """Return a WAV file of the text read aloud (24 kHz mono 16-bit from the current speech models)."""
        if not self.configured:
            raise AIUnavailable("not_configured")
        governance_check()
        key = "tts:" + hashlib.sha256((voice + text).encode()).hexdigest()
        hit = self._cache_get(key)
        if hit is not None:
            return hit
        for m in self._candidates("tts"):
            if not self._admit(m):
                continue
            body = {"contents": [{"parts": [{"text": text}]}],
                    "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {
                        "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
            try:
                with self._http(timeout_s) as c:
                    r = c.post(f"{API}/models/{m.name}:generateContent", json=body,
                               headers={"x-goog-api-key": self.api_key})
                if r.status_code == 429:
                    self._park(m, _RateLimited(r))
                    continue
                if r.status_code == 404:
                    self._disable(m, _error_message(r))
                    continue
                r.raise_for_status()
                part = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
                wav = _as_wav(base64.b64decode(part["data"]), part.get("mimeType", ""))
                self._cache_put(key, wav)
                return wav
            except Exception as exc:
                log.warning("tts failed on %s: %s", m.name, str(exc)[:200])
        raise AIUnavailable("tts_unavailable")


class _RateLimited(Exception):
    """A 429. A quota of zero, or a daily quota used up, parks the model until the daily reset; otherwise it cools
    down as RetryInfo asks. The daily case matters after a restart: this process's own day counts start again at
    zero, but Google's do not, and RetryInfo then asks for a retry within a minute that can only fail again."""

    def __init__(self, r: httpx.Response):
        super().__init__("rate limited")
        text = r.text
        self.zero_quota = bool(re.search(r"limit:\s*0\b", text) or re.search(r'"quotaValue":\s*"0"', text))
        self.per_day = _daily_quota_used_up(r)
        self.until = (_next_quota_reset() if self.zero_quota or self.per_day
                      else time.time() + _retry_seconds(r))


class _Gone(Exception):
    """A 404: the model is listed but this key cannot use it (for example 'no longer available to new users')."""


def _next_quota_reset() -> float:
    now = datetime.now(QUOTA_TZ)
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return nxt.timestamp()


def _error_message(r: httpx.Response) -> str:
    try:
        return str(r.json().get("error", {}).get("message", ""))
    except Exception:
        return r.text[:300]


def _daily_quota_used_up(r: httpx.Response) -> bool:
    """True when the 429 names a per-day quota (QuotaFailure quotaId such as
    GenerateRequestsPerDayPerProjectPerModel-FreeTier)."""
    try:
        for d in r.json().get("error", {}).get("details", []):
            if d.get("@type", "").endswith("QuotaFailure"):
                for v in d.get("violations", []):
                    if "perday" in str(v.get("quotaId", "")).lower():
                        return True
    except Exception:
        pass
    return False


def _retry_seconds(r: httpx.Response) -> float:
    try:
        for d in r.json().get("error", {}).get("details", []):
            if d.get("@type", "").endswith("RetryInfo"):
                return float(str(d.get("retryDelay", "30s")).rstrip("s")) + 1
    except Exception:
        pass
    return 30.0


def _text(data: dict[str, Any]) -> str:
    cands = data.get("candidates") or []
    if not cands:
        return ""
    parts = (cands[0].get("content") or {}).get("parts") or []
    return "".join(p.get("text", "") for p in parts if not p.get("thought"))


def _parse_json(text: str) -> Any:
    if not text:
        return None
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", t, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None


def _to_openapi(schema: dict[str, Any]) -> dict[str, Any]:
    """Convert a small JSON Schema to the OpenAPI subset (uppercase types, no additionalProperties)."""
    if not isinstance(schema, dict):
        return schema
    out: dict[str, Any] = {}
    for k, v in schema.items():
        if k in ("additionalProperties", "$schema", "title", "minLength", "maxLength", "pattern", "minimum",
                 "maximum"):
            continue
        if k == "type":
            out["type"] = (v[0] if isinstance(v, list) else v).upper()
        elif k == "properties":
            out["properties"] = {pk: _to_openapi(pv) for pk, pv in v.items()}
        elif k == "items":
            out["items"] = _to_openapi(v)
        else:
            out[k] = v
    return out


def _cache_key(tier, system, user, schema, inline) -> str:
    h = hashlib.sha256()
    for p in (tier, system, user, json.dumps(schema, sort_keys=True)):
        h.update(p.encode())
    for mime, blob in inline or []:
        h.update(mime.encode())
        h.update(hashlib.sha256(blob).digest())
    return h.hexdigest()


def _as_wav(audio: bytes, mime: str) -> bytes:
    """Speech models return either a finished WAV file or raw 16-bit PCM ('audio/L16; rate=24000')."""
    if audio[:4] == b"RIFF":
        return audio
    m = re.search(r"rate=(\d+)", mime or "")
    return _pcm_to_wav(audio, int(m.group(1)) if m else 24000)


def _pcm_to_wav(pcm: bytes, rate: int = 24000) -> bytes:
    import struct
    header = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate,
                                                                                     rate * 2, 2, 16)
    return header + b"data" + struct.pack("<I", len(pcm)) + pcm


CLIENT = GeminiClient()
