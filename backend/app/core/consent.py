"""Purpose-specific consent events (finalsystem.md §20.4, §23.2-§23.3, B.6; tests T38-T42).

Append-only. A withdrawal always wins: a stale grant created earlier on an
offline device can never bring access back. Legally necessary safety processing
is not consent-based and is never shown as a reversible preference.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

PURPOSES: dict[str, dict[str, Any]] = {
    "safety_operations": {
        "basis": "legal_duty", "withdrawable": False,
        "en": "Site heat protection (required by the employer's legal duty)",
        "ar": "الحماية من الحرارة في الموقع (التزام قانوني على صاحب العمل)",
        "explain_en": "Needed to protect you at work. It never includes health results.",
        "explain_ar": "مطلوبة لحمايتك في العمل. ولا تشمل أبداً نتائجك الصحية."},
    "clinical_care": {
        "basis": "consent", "withdrawable": True,
        "en": "Voluntary kidney follow-up with the clinic", "ar": "متابعة الكلى الطوعية مع العيادة",
        "explain_en": "Your clinic sees your results. Your employer never does. Some records must be kept by law.",
        "explain_ar": "ترى العيادة نتائجك ولا يراها صاحب العمل أبداً. يجب الاحتفاظ ببعض السجلات بحكم القانون."},
    "share_checkins_with_clinic": {
        "basis": "consent", "withdrawable": True,
        "en": "Share my private check-ins with the site nurse", "ar": "مشاركة فحوصاتي الخاصة مع ممرضة الموقع",
        "explain_en": "Optional. Helps the nurse follow up. You can stop at any time.",
        "explain_ar": "اختياري. يساعد الممرضة في المتابعة. يمكنك الإيقاف في أي وقت."},
    "passport_sharing": {
        "basis": "consent", "withdrawable": True,
        "en": "Share my care summary by link with a doctor I choose", "ar": "مشاركة ملخص رعايتي عبر رابط مع طبيب أختاره",
        "explain_en": "Optional. Links expire. Downloaded copies cannot be recalled.",
        "explain_ar": "اختياري. تنتهي صلاحية الروابط. لا يمكن استرجاع النسخ التي تم تنزيلها."},
    "research": {
        "basis": "consent", "withdrawable": True,
        "en": "Use my data in approved research", "ar": "استخدام بياناتي في بحث معتمد",
        "explain_en": "Optional and off by default. Never needed for protection.",
        "explain_ar": "اختياري وغير مفعل افتراضياً. لا يلزم أبداً للحماية."},
    "reminders_whatsapp": {
        "basis": "consent", "withdrawable": True,
        "en": "Reminders by WhatsApp", "ar": "تذكيرات عبر واتساب",
        "explain_en": "Optional communications.", "explain_ar": "اتصالات اختيارية."},
}


class ConsentStore:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def seed(self) -> None:
        base = "2025-08-17T09:00:00+04:00"
        for wid, purposes in {
            "W01": ["share_checkins_with_clinic", "reminders_whatsapp"],
            "W07": ["clinical_care", "share_checkins_with_clinic", "passport_sharing"],
            "W36": ["clinical_care"],
        }.items():
            for p in purposes:
                self.events.append({"worker_ref": wid, "purpose": p, "action": "grant", "at": base,
                                    "recorded_at": base, "device": "kiosk-onboarding", "notice_version": "notice-1.0",
                                    "source": "independent onboarding", "seq": len(self.events) + 1,
                                    "server_stamped": True})

    def record(self, *, worker_ref: str, purpose: str, action: str, at: str, device: str = "phone",
               recorded_at: str | None = None, server_stamped: bool = False) -> dict[str, Any]:
        if purpose not in PURPOSES:
            raise ValueError("unknown purpose")
        if not PURPOSES[purpose]["withdrawable"]:
            raise PermissionError("This processing is a legal duty, not a preference, so it cannot be switched off "
                                  "here. It never includes health results.")
        if action not in ("grant", "withdraw"):
            raise ValueError("action must be grant or withdraw")
        ev = {"worker_ref": worker_ref, "purpose": purpose, "action": action, "at": at,
              "recorded_at": recorded_at or at, "device": device, "notice_version": "notice-1.0",
              "seq": len(self.events) + 1, "server_stamped": server_stamped}
        self.events.append(ev)
        return ev

    @staticmethod
    def _later(g: dict[str, Any], w: dict[str, Any]) -> bool:
        """Is grant g later than withdrawal w? Event times are compared as instants (offsets respected).
        On an exact tie the withdrawal wins, unless both were stamped by the server online, where the order
        of arrival is known."""
        tg, tw = datetime.fromisoformat(g["at"]), datetime.fromisoformat(w["at"])
        if tg != tw:
            return tg > tw
        return bool(g.get("server_stamped") and w.get("server_stamped") and g.get("seq", 0) > w.get("seq", 0))

    def status(self, worker_ref: str, purpose: str) -> dict[str, Any]:
        """Withdrawal wins: a grant counts only if it is later than every withdrawal, so a stale grant from an
        offline device can never bring access back (T38). Grants with untrusted device times are rejected at
        sync (T55)."""
        if not PURPOSES[purpose]["withdrawable"]:
            return {"purpose": purpose, "active": True, "basis": "legal_duty"}
        evs = [e for e in self.events if e["worker_ref"] == worker_ref and e["purpose"] == purpose]
        withdrawals = [e for e in evs if e["action"] == "withdraw"]
        grants = [e for e in evs if e["action"] == "grant"]
        if not grants:
            return {"purpose": purpose, "active": False, "since": None}
        valid = [g for g in grants if all(self._later(g, w) for w in withdrawals)]
        last_w = max((e["at"] for e in withdrawals), key=datetime.fromisoformat, default=None)
        active = bool(valid)
        since = max((g["at"] for g in valid), key=datetime.fromisoformat, default=last_w)
        return {"purpose": purpose, "active": active, "since": since,
                "withdrawn_at": last_w if not active else None}

    def summary(self, worker_ref: str) -> list[dict[str, Any]]:
        out = []
        for p, meta in PURPOSES.items():
            st = self.status(worker_ref, p)
            out.append({**st, "label_en": meta["en"], "label_ar": meta["ar"], "explain_en": meta["explain_en"],
                        "explain_ar": meta["explain_ar"], "withdrawable": meta["withdrawable"],
                        "basis": meta["basis"]})
        return out

    def history(self, worker_ref: str) -> list[dict[str, Any]]:
        return [e for e in self.events if e["worker_ref"] == worker_ref]
