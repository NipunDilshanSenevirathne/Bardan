"""Approved content: message templates, action labels and the knowledge registry.

English and Arabic only (prototype language scope). Templates follow
finalsystem.md Appendix E. Safety-critical messages are chosen by ID and filled
with typed slots; no model writes them (§16.5).

Release status (§26.2): both languages are "reviewed (prototype author review)".
Native-speaker clinical review and comprehension testing are required before
any real use; nothing here is a released clinical translation.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .policy import shared_dir

LANGS = ("en", "ar")
LANGUAGE_STATUS = {
    "en": {"name": "English", "status": "reviewed", "note": "Author review; comprehension testing pending (protocol in docs/PILOT-KIT.md)"},
    "ar": {"name": "العربية", "status": "reviewed", "dir": "rtl",
           "note": "Author review; native clinical review and teach-back testing pending (protocol in docs/PILOT-KIT.md)"},
}

TEMPLATES: dict[str, dict[str, str]] = {
    "msg.routine_plan": {
        "en": "Normal plan today. Drink water every hour from your own bottle and rest in the shade at your breaks.",
        "ar": "خطة عادية اليوم. اشرب الماء كل ساعة من زجاجتك الخاصة، واسترح في الظل أثناء فترات الراحة."},
    "msg.enhanced": {
        "en": "Extra protection now. Rest at {place} for {minutes} minutes every hour. If the rest place is full or closed, tell your supervisor.",
        "ar": "حماية إضافية الآن. استرح في {place} لمدة {minutes} دقيقة كل ساعة. إذا كان مكان الراحة ممتلئاً أو مغلقاً، أخبر مشرفك."},
    "msg.stop_task": {
        "en": "Stop this task now: {task}. Go to {place}. Your supervisor has the new plan.",
        "ar": "أوقف هذه المهمة الآن: {task}. اذهب إلى {place}. لدى مشرفك الخطة الجديدة."},
    "msg.assessment_unavailable": {
        "en": "We do not have current heat information for this area. Follow the site's fallback plan and ask the safety lead. This screen does not confirm conditions are safe.",
        "ar": "لا تتوفر لدينا معلومات حرارة حالية لهذه المنطقة. اتبع الخطة البديلة للموقع واسأل مسؤول السلامة. هذه الشاشة لا تؤكد أن الظروف آمنة."},
    "msg.required_break": {
        "en": "Your plan requires a break at {place} from {time}. If the place is unavailable, stop the task and ask for help.",
        "ar": "تتطلب خطتك استراحة في {place} من الساعة {time}. إذا لم يكن المكان متاحاً، أوقف المهمة واطلب المساعدة."},
    "msg.missing_resource": {
        "en": "The water point is empty. Stop the affected task and tell the safety lead. Work resumes when water is back.",
        "ar": "نقطة الماء فارغة. أوقف المهمة المتأثرة وأخبر مسؤول السلامة. يُستأنف العمل عند عودة الماء."},
    "msg.dispute_received": {
        "en": "You reported that this protection is still missing. The task stays open and has gone to {role}.",
        "ar": "أبلغت أن هذه الحماية ما زالت غير متوفرة. تبقى المهمة مفتوحة وأُحيلت إلى {role}."},
    "msg.dispute_resolved": {
        "en": "The HSE lead checked “{action}” in Zone {zone} at {time} and found it in place. If it is still "
              "missing, press “This didn’t happen” again: the task reopens.",
        "ar": "تحقّق مسؤول السلامة من «{action}» في المنطقة {zone} الساعة {time} ووجدها متوفرة. إذا كانت لا تزال "
              "غير متوفرة، اضغط «هذا لم يحدث» مرة أخرى: ستُعاد فتح المهمة."},
    "msg.new_worker_harsh": {
        "en": "{name}, the heat is too strong today for workers in their first days. Your supervisor will give you a shaded task. This is normal and keeps you safe.",
        "ar": "{name}، الحرارة اليوم شديدة جداً على العمال في أيامهم الأولى. سيعطيك مشرفك مهمة في الظل. هذا أمر طبيعي ويحافظ على سلامتك."},
    "msg.concerning_symptom": {
        "en": "Stop and move to a cool place. Ask your buddy or first aider for help. If you get confused, collapse or have chest or breathing problems, get emergency help.",
        "ar": "توقف وانتقل إلى مكان بارد. اطلب المساعدة من زميلك أو المسعف. إذا شعرت بالارتباك أو سقطت أو عانيت من مشكلة في الصدر أو التنفس، اطلب المساعدة الطارئة."},
    "msg.emergency": {
        "en": "Stop work. Call 998 or ask someone to call. Stay with the worker and start the site's cooling steps. Do not give drinks if they cannot swallow safely. Do not wait for any test.",
        "ar": "أوقف العمل. اتصل بالرقم 998 أو اطلب من أحد الاتصال. ابقَ مع العامل وابدأ خطوات التبريد في الموقع. لا تعطه أي شراب إذا لم يستطع البلع بأمان. لا تنتظر أي فحص."},
    "msg.muscle_dark_urine": {
        "en": "Strong muscle pain or very dark urine after work needs a clinician today. Stop work and go to the clinic now, or get emergency help if you feel very unwell.",
        "ar": "ألم العضلات الشديد أو البول الداكن جداً بعد العمل يحتاج إلى طبيب اليوم. أوقف العمل واذهب إلى العيادة الآن، أو اطلب المساعدة الطارئة إذا شعرت بتوعك شديد."},
    "msg.result_needs_clinician": {
        "en": "This result needs a clinician to review it. It is not a diagnosis. Your appointment is {date}. Only you and your care team can see it.",
        "ar": "تحتاج هذه النتيجة إلى مراجعة الطبيب. وهي ليست تشخيصاً. موعدك {date}. لا يراها سواك وفريق رعايتك."},
    "msg.result_unverified": {
        "en": "This result could not be verified. It does not show that your kidneys are normal. Follow the care team's instructions.",
        "ar": "تعذّر التحقق من هذه النتيجة. وهي لا تُظهر أن كليتيك سليمتان. اتبع تعليمات فريق الرعاية."},
    "msg.hydration_retest": {
        "en": "Please rest and drink water. The nurse will test again at {time}.",
        "ar": "يُرجى الراحة وشرب الماء. ستعيد الممرضة الفحص الساعة {time}."},
    "msg.restriction_label": {
        "en": "{name}: shaded light duty until {time}. No other action needed.",
        "ar": "{name}: عمل خفيف في الظل حتى {time}. لا يلزم أي إجراء آخر."},
    "msg.clinic_absence": {
        "en": "{name}: clinic visit {time_range}.",
        "ar": "{name}: زيارة للعيادة {time_range}."},
    "msg.at_clinic": {
        "en": "{name}: at clinic; return time pending.",
        "ar": "{name}: في العيادة؛ وقت العودة لم يُحدد بعد."},
    "msg.task_to_supervisor": {
        "en": "Zone {zone}: {action}. Please accept within {minutes} minutes and add evidence when done.",
        "ar": "المنطقة {zone}: {action}. يُرجى القبول خلال {minutes} دقيقة وإضافة الدليل عند الانتهاء."},
    "msg.task_now": {
        "en": "Zone {zone}: {action}. Act now and add evidence when done.",
        "ar": "المنطقة {zone}: {action}. تصرّف الآن وأضف الدليل عند الانتهاء."},
    "msg.escalation": {
        "en": "Zone {zone}: {action} is overdue or disputed. It is now with you. Please act or reassign.",
        "ar": "المنطقة {zone}: {action} متأخرة أو معترض عليها. أصبحت الآن لديك. يُرجى التصرف أو إعادة الإسناد."},
    "msg.ac_broken_ack": {
        "en": "Thank you. A housing task was created. Your name is not shared.",
        "ar": "شكراً لك. أُنشئت مهمة للسكن. لا تتم مشاركة اسمك."},
    "msg.sharing_withdrawn": {
        "en": "Optional sharing has stopped on this phone. Other services update when they receive the change. Some clinical records must be kept by law.",
        "ar": "توقفت المشاركة الاختيارية على هذا الهاتف. تُحدَّث الخدمات الأخرى عند استلام التغيير. يجب الاحتفاظ ببعض السجلات الطبية بحكم القانون."},
    "msg.diagnosis_request": {
        "en": "This app cannot diagnose kidney disease or clear you for work. It can show verified results and connect you with the care team.",
        "ar": "لا يستطيع هذا التطبيق تشخيص أمراض الكلى أو منحك إذناً بالعمل. يمكنه عرض النتائج المؤكدة وربطك بفريق الرعاية."},
    "msg.emergency_disclosure": {
        "en": "In an emergency, first aiders and the site team are told where you are and when it happened, so they can reach you. Your health details stay private.",
        "ar": "في حالة الطوارئ يُبلَّغ المسعفون وفريق الموقع بمكانك ووقت الحادث حتى يصلوا إليك. تبقى تفاصيلك الصحية خاصة."},
    "msg.escalation_pending": {
        "en": "The safety lead could not be reached yet. The escalation is waiting to send. Keep the protection in place at Zone {zone} and call if it is urgent.",
        "ar": "تعذّر الوصول إلى مسؤول السلامة حتى الآن. التصعيد بانتظار الإرسال. حافظ على الحماية في المنطقة {zone} واتصل إذا كان الأمر عاجلاً."},
    "msg.fluid_plan": {
        "en": "You have an individual fluid plan from your clinician. Follow that plan for how much to drink, not general advice. If you are unsure, ask the clinic.",
        "ar": "لديك خطة سوائل فردية من طبيبك. اتبع تلك الخطة في كمية الشرب، وليس النصائح العامة. إذا لم تكن متأكداً، اسأل العيادة."},
    "msg.routine_plan_fluid": {
        "en": "Normal plan today. Follow your individual fluid plan and rest in the shade at your breaks.",
        "ar": "الخطة عادية اليوم. اتبع خطة السوائل الفردية الخاصة بك واسترح في الظل أثناء الاستراحات."},
    "msg.safe_fallback_fluid": {
        "en": "I can't give a detailed answer right now. Rest in the shade, follow your individual fluid plan, and tell your supervisor if you feel unwell. If you feel very sick, call 998.",
        "ar": "لا أستطيع تقديم إجابة مفصلة الآن. استرح في الظل واتبع خطة السوائل الفردية، وأخبر مشرفك إذا شعرت بتوعك. إذا شعرت بمرض شديد، اتصل بالرقم 998."},
    "msg.ask_not_covered": {
        "en": "Bardan has no approved answer to that yet. Ask your supervisor or the clinic. If you feel unwell, stop, rest in the shade and tell someone. In an emergency call 998.",
        "ar": "لا توجد لدى بَرْدًا إجابة معتمدة عن هذا السؤال بعد. اسأل مشرفك أو العيادة. إذا شعرت بتوعك فتوقف واسترح في الظل وأخبر أحداً. في حالة الطوارئ اتصل بالرقم 998."},
    "msg.safe_fallback": {
        "en": "I can't give a detailed answer right now. Rest in the shade, drink water, and tell your supervisor if you feel unwell. If you feel very sick, call 998.",
        "ar": "لا أستطيع تقديم إجابة مفصلة الآن. استرح في الظل واشرب الماء، وأخبر مشرفك إذا شعرت بتوعك. إذا شعرت بمرض شديد، اتصل بالرقم 998."},
    "msg.consent_summary": {
        "en": "Your protection does not depend on sharing anything. Your employer never sees your health results. You can change optional sharing at any time.",
        "ar": "حمايتك لا تعتمد على مشاركة أي شيء. صاحب العمل لا يرى نتائجك الصحية أبداً. يمكنك تغيير المشاركة الاختيارية في أي وقت."},
    "msg.medicine_info": {
        "en": "I can't give medicine doses. Some pain medicines can affect the kidneys and how the body copes with heat. Please ask the pharmacist or the clinic before taking them.",
        "ar": "لا أستطيع إعطاء جرعات الأدوية. بعض مسكنات الألم قد تؤثر على الكليتين وعلى تحمّل الجسم للحرارة. يُرجى سؤال الصيدلي أو العيادة قبل تناولها."},
    "msg.not_understood": {
        "en": "I did not understand. Please choose:",
        "ar": "لم أفهم. يُرجى الاختيار:"},
    "msg.water_task_created": {
        "en": "Thank you. A task to restore water at Zone {zone} was created. Heat work stops until water is back.",
        "ar": "شكراً لك. أُنشئت مهمة لإعادة الماء في المنطقة {zone}. يتوقف العمل في الحر حتى يعود الماء."},
    "msg.report_received": {
        "en": "Thank you. A task was created for Zone {zone}. If you feel unwell, stop and ask for help.",
        "ar": "شكراً لك. أُنشئت مهمة للمنطقة {zone}. إذا شعرت بتوعك، توقف واطلب المساعدة."},
    "msg.forecast_unavailable": {
        "en": "Forecast unavailable. The season's standard plan applies. Nothing is relaxed.",
        "ar": "التوقعات غير متاحة. تُطبق خطة الموسم القياسية. لا يتم تخفيف أي إجراء."},
    "msg.tomorrow_start": {
        "en": "Tomorrow ({date}): start {start} at {place}. Your breaks: {breaks}.",
        "ar": "غداً ({date}): ابدأ الساعة {start} في {place}. استراحاتك: {breaks}."},
    "msg.tomorrow_new_worker": {
        "en": "Tomorrow ({date}): induction and daily review {induction}, then {task} {heat}. Shaded task after that. Your buddy works with you.",
        "ar": "غداً ({date}): التعريف والمراجعة اليومية {induction}، ثم {task} {heat}. بعد ذلك مهمة في الظل. يعمل زميلك معك."},
    "msg.midday_break": {
        "en": "Midday break: outdoor work in the sun stops from 12:30 to 15:00. Rest at {place}.",
        "ar": "استراحة منتصف النهار: يتوقف العمل في الشمس من 12:30 حتى 15:00. استرح في {place}."},
    "msg.fasting_info": {
        "en": "If you fast, your reminders can change. Emergency advice never changes. If you are in the kidney care pathway, you can talk privately with your clinician before a fast.",
        "ar": "إذا كنت صائماً، يمكن تغيير مواعيد التذكير. نصائح الطوارئ لا تتغير أبداً. إذا كنت ضمن مسار رعاية الكلى، يمكنك التحدث بشكل خاص مع طبيبك قبل الصيام."},
}

ACTION_LABELS: dict[str, dict[str, str]] = {
    "STANDARD_CONTROLS": {"en": "Normal plan: water every hour, shade at breaks", "ar": "خطة عادية: ماء كل ساعة وظل أثناء الراحة"},
    "EXTRA_BREAKS": {"en": "Extra shaded breaks every hour", "ar": "استراحات إضافية في الظل كل ساعة"},
    "ASSURED_FLUIDS": {"en": "Water and electrolytes at the work area", "ar": "ماء وأملاح قرب مكان العمل"},
    "SHADE_AND_VENTILATION": {"en": "Shade and ventilation at the work area", "ar": "ظل وتهوية في مكان العمل"},
    "NO_LONE_WORK": {"en": "No working alone: stay with your buddy", "ar": "لا عمل منفرداً: ابقَ مع زميلك"},
    "ESSENTIAL_WORK_ONLY": {"en": "Essential work only, with authorisation", "ar": "العمل الضروري فقط وبتصريح"},
    "UNACCLIMATIZED_STOP_HEAT_WORK": {"en": "New or returning workers: stop heat work", "ar": "العمال الجدد أو العائدون: أوقفوا العمل في الحر"},
    "LIMIT_EXPOSURE": {"en": "Limit heat time to your schedule", "ar": "حدّد وقتك في الحر حسب جدولك"},
    "FOLLOW_FALLBACK_PLAN": {"en": "Follow the site's fallback plan", "ar": "اتبع الخطة البديلة للموقع"},
    "STOP_OUTDOOR_WORK": {"en": "Stop outdoor work in the sun", "ar": "أوقف العمل في الخارج تحت الشمس"},
    "MOVE_TO_SHADE": {"en": "Move to shade or a cooled area", "ar": "انتقل إلى الظل أو مكان مكيف"},
    "REASSIGN_SHADED_LIGHT": {"en": "Shaded light duty", "ar": "عمل خفيف في الظل"},
    "RESTORE_WATER": {"en": "Restore drinking water", "ar": "إعادة توفير ماء الشرب"},
    "STOP_AFFECTED_WORK": {"en": "Stop the affected work", "ar": "أوقف العمل المتأثر"},
    "STOP_ACTIVITY": {"en": "Stop the activity now", "ar": "أوقف النشاط الآن"},
    "FIRST_AIDER_CHECK": {"en": "Buddy or first aider checks on you", "ar": "يتفقدك زميلك أو المسعف"},
    "URGENT_CLINICAL_ASSESSMENT": {"en": "Urgent clinic assessment today", "ar": "تقييم عاجل في العيادة اليوم"},
    "RESOLVE_SOURCE_CONFLICT": {"en": "Two heat readings disagree: the safety lead checks them; the stricter one applies",
                                "ar": "قراءتا حرارة مختلفتان: يتحقق مسؤول السلامة منهما، وتُطبق الأشد"},
    "EMERGENCY_CARD": {"en": "Open the emergency card", "ar": "افتح بطاقة الطوارئ"},
    "CALL_998": {"en": "Call 998", "ar": "اتصل بالرقم 998"},
    "START_COOLING": {"en": "Start cooling now", "ar": "ابدأ التبريد الآن"},
    "BUDDY_STAY": {"en": "Buddy stays with the worker", "ar": "يبقى الزميل مع العامل"},
}

TASK_LABELS: dict[str, dict[str, str]] = {
    "WATER_RESTORE": {"en": "Restore water", "ar": "إعادة توفير الماء"},
    "SHADE_EXTEND": {"en": "Open or extend shaded rest", "ar": "فتح أو توسيع مكان الراحة المظلل"},
    "CHECK_WORKER": {"en": "Check on a worker", "ar": "تفقد عامل"},
    "ENHANCED_SCHEDULE": {"en": "Apply the enhanced work-rest schedule", "ar": "تطبيق جدول العمل والراحة المعزز"},
    "STOP_AFFECTED_WORK": {"en": "Stop the affected work", "ar": "إيقاف العمل المتأثر"},
    "NEW_WORKER_REVIEW": {"en": "New-worker daily review", "ar": "المراجعة اليومية للعامل الجديد"},
    "AC_FIX": {"en": "Fix accommodation air conditioning", "ar": "إصلاح تكييف السكن"},
    "TRAINING_DUE": {"en": "Heat-safety training due", "ar": "تدريب السلامة من الحرارة مستحق"},
    "MOVE_TO_SHADED_TASK": {"en": "Move a worker to a shaded task", "ar": "نقل عامل إلى مهمة في الظل"},
    "COOLING_FIX": {"en": "Repair cooling equipment", "ar": "إصلاح معدات التبريد"},
    "BREAK_ACCESS": {"en": "Make sure breaks can be taken", "ar": "التأكد من إمكانية أخذ الاستراحات"},
    "CLINIC_TRANSPORT": {"en": "Arrange clinic transport", "ar": "ترتيب النقل إلى العيادة"},
    "HSE_REVIEW": {"en": "HSE review of a recurring gap", "ar": "مراجعة السلامة لفجوة متكررة"},
}

STATE_LABELS = {
    "routine": {"en": "Normal plan", "ar": "خطة عادية"},
    "enhanced": {"en": "Extra breaks", "ar": "استراحات إضافية"},
    "stop": {"en": "Stop this task", "ar": "أوقف هذه المهمة"},
    "emergency": {"en": "Get help now", "ar": "اطلب المساعدة الآن"},
    "unavailable": {"en": "Not confirmed safe", "ar": "غير مؤكد أنه آمن"},
}

BAND_LABELS = {
    "unrestricted": {"en": "Unrestricted", "ar": "غير مقيد"},
    "acclimatization": {"en": "Acclimatization", "ar": "التأقلم"},
    "buffer": {"en": "Buffer", "ar": "المنطقة العازلة"},
    "withdrawal": {"en": "Withdrawal", "ar": "الانسحاب"},
    "unavailable": {"en": "Unavailable", "ar": "غير متاح"},
}

# Closed intent set for Speak (§14.1). Urgent intents open the emergency card at once.
# Closed intent set for Speak, with labels and urgency. Kept in shared/lexicon.json with the offline phrase lexicon,
# so the phone and the server read the same list.
with open(shared_dir() / "lexicon.json", encoding="utf-8") as _f:
    INTENTS: dict[str, dict[str, Any]] = json.load(_f)["intents"]

# Approved knowledge registry for retrieval (§16.3 step 3). Filtered by approval,
# jurisdiction and effective date before any model sees it (tests T46, T47).
KNOWLEDGE: list[dict[str, Any]] = [
    {"id": "K-HYD-1", "status": "approved", "jurisdiction": ["AE-AD", "general"], "effective": "2024-07-15",
     "source": "ADOSH-SF Safety in the Heat V4.0 §5.2 (4-6 L a day); NIOSH (cup every 15-20 min, hourly upper limit)",
     "tags": ["water", "hydration", "drink", "ماء", "شرب"],
     "en": "Drink water before you start work and at frequent intervals during the day, from your own bottle. In the Gulf summer that is about 4 to 6 litres over the day. In very hot work a cup every 15 to 20 minutes helps. Do not drink more than about 1.4 litres in an hour. If your doctor gave you a fluid limit, follow your own care plan.",
     "ar": "اشرب الماء قبل بدء العمل وعلى فترات متقاربة خلال اليوم، من زجاجتك الخاصة. في صيف الخليج يعادل ذلك نحو 4 إلى 6 لترات خلال اليوم. في العمل شديد الحرارة يساعد شرب كوب كل 15 إلى 20 دقيقة. لا تشرب أكثر من 1.4 لتر تقريباً في الساعة. إذا حدد لك طبيبك كمية سوائل، فاتبع خطة رعايتك."},
    {"id": "K-MID-1", "status": "approved", "jurisdiction": ["AE", "AE-AD", "general"], "effective": "2025-06-15",
     "source": "MoHRE midday break notice (demonstration pack)", "tags": ["midday", "break", "استراحة", "الظهر"],
     "en": "From 15 June to 15 September, outdoor work in direct sun stops from 12:30 to 15:00 in the UAE. Shaded rest, drinking water and first aid must be available.",
     "ar": "من 15 يونيو إلى 15 سبتمبر يتوقف العمل في الخارج تحت أشعة الشمس المباشرة من 12:30 حتى 15:00 في الإمارات. ويجب توفير مكان راحة مظلل وماء للشرب وإسعافات أولية."},
    {"id": "K-SIGN-1", "status": "approved", "jurisdiction": ["general"], "effective": "2024-01-01",
     "source": "Bardan reviewed content (heat illness signs)", "tags": ["symptoms", "dizzy", "headache", "أعراض", "دوخة"],
     "en": "Warning signs of heat illness are headache, dizziness, nausea, cramps and unusual weakness. Stop, move to a cool place and tell your buddy or first aider.",
     "ar": "علامات الإنذار للإجهاد الحراري هي الصداع والدوخة والغثيان والتشنجات والضعف غير المعتاد. توقف وانتقل إلى مكان بارد وأخبر زميلك أو المسعف."},
    {"id": "K-EMG-1", "status": "approved", "jurisdiction": ["general"], "effective": "2024-01-01",
     "source": "Bardan reviewed emergency content", "tags": ["emergency", "confused", "collapse", "طوارئ", "إغماء"],
     "en": "Confusion, slurred speech, collapse, a seizure, chest pain or difficulty breathing are emergencies. Call 998, stay with the person and start cooling. Do not wait for any test.",
     "ar": "الارتباك وتلعثم الكلام والسقوط والنوبة وألم الصدر وصعوبة التنفس حالات طارئة. اتصل بالرقم 998 وابقَ مع الشخص وابدأ التبريد. لا تنتظر أي فحص."},
    {"id": "K-KID-1", "status": "approved", "jurisdiction": ["general"], "effective": "2024-03-01",
     "source": "KDIGO 2024 (background); Bardan claims policy", "tags": ["kidney", "result", "test", "كلى", "نتيجة"],
     "en": "A kidney test result must be reviewed by a clinician. One abnormal result is not a diagnosis; tests are repeated to confirm. Only you and your care team can see your results.",
     "ar": "يجب أن يراجع الطبيب نتيجة فحص الكلى. النتيجة غير الطبيعية مرة واحدة ليست تشخيصاً، وتُعاد الفحوص للتأكيد. لا يرى نتائجك سواك وفريق رعايتك."},
    {"id": "K-ACC-1", "status": "approved", "jurisdiction": ["AE-AD"], "effective": "2016-07-01",
     "source": "OSHAD-SF Technical Guideline Safety in the Heat V3.0", "tags": ["new", "first days", "acclimatization", "جديد", "تأقلم"],
     "en": "In your first days your time in the heat grows step by step over five days: 20, 40, 60, 80 and then 100 percent. A buddy works with you and your supervisor reviews your day.",
     "ar": "في أيامك الأولى يزداد وقتك في الحر تدريجياً على مدى خمسة أيام: 20 ثم 40 ثم 60 ثم 80 ثم 100 بالمئة. يعمل معك زميل ويراجع مشرفك يومك."},
    {"id": "K-MED-1", "status": "approved", "jurisdiction": ["general"], "effective": "2024-01-01",
     "source": "Bardan reviewed content (medicines and heat)", "tags": ["medicine", "painkiller", "ibuprofen", "دواء", "مسكن"],
     "en": "Some pain medicines, for example ibuprofen-type medicines, can affect the kidneys and how the body copes with heat. Ask the pharmacist or the clinic. This app does not give doses.",
     "ar": "بعض مسكنات الألم، مثل أدوية الإيبوبروفين، قد تؤثر على الكليتين وعلى تحمّل الجسم للحرارة. اسأل الصيدلي أو العيادة. هذا التطبيق لا يعطي جرعات."},
    {"id": "K-DATA-1", "status": "approved", "jurisdiction": ["general"], "effective": "2024-01-01",
     "source": "Bardan worker data promises", "tags": ["data", "privacy", "employer", "بيانات", "خصوصية"],
     "en": "Your employer never sees your health results. Your protection does not depend on sharing anything, and you can change optional sharing at any time.",
     "ar": "صاحب العمل لا يرى نتائجك الصحية أبداً. حمايتك لا تعتمد على مشاركة أي شيء، ويمكنك تغيير المشاركة الاختيارية في أي وقت."},
    {"id": "K-URINE-1", "status": "approved", "jurisdiction": ["general"], "effective": "2024-01-01",
     "source": "Bardan reviewed content (safe triage)", "tags": ["urine", "muscle", "dark", "بول", "عضلات"],
     "en": "Strong muscle pain or weakness, very dark urine or much less urine after hard work needs a clinician the same day. No test is needed first.",
     "ar": "ألم العضلات الشديد أو الضعف أو البول الداكن جداً أو قلة البول بعد العمل الشاق يحتاج إلى طبيب في اليوم نفسه. لا يلزم أي فحص قبل ذلك."},
    {"id": "K-REST-1", "status": "approved", "jurisdiction": ["AE-AD", "general"], "effective": "2024-07-15",
     "source": "ADOSH-SF CoP 11.0 V4.0", "tags": ["rest", "shade", "break", "راحة", "ظل"],
     "en": "Rest in shade or a cooled area at your breaks. If the rest area is full or closed, tell your supervisor or report it in the app.",
     "ar": "استرح في الظل أو في مكان مكيف أثناء استراحاتك. إذا كان مكان الراحة ممتلئاً أو مغلقاً، أخبر مشرفك أو أبلغ عن ذلك في التطبيق."},
    {"id": "K-WGAP-1", "status": "approved", "jurisdiction": ["AE-AD", "general"], "effective": "2024-07-15",
     "source": "ADOSH-SF CoP 11.0 V4.0 (cool drinking water at the work area)",
     "tags": ["water", "empty", "finished", "cooler", "ماء", "ماي", "خلص", "فارغ"],
     "en": "If the water point is empty or the water is not cool, report it in the app or tell your supervisor. A task is created to bring water back, and work in the heat in your zone stops until it is back.",
     "ar": "إذا كانت نقطة الماء فارغة أو كان الماء غير بارد، أبلغ عن ذلك في التطبيق أو أخبر مشرفك. تُنشأ مهمة لإعادة الماء، ويتوقف العمل في الحر في منطقتك حتى يعود."},
    {"id": "K-SLEEP-1", "status": "approved", "jurisdiction": ["AE", "general"], "effective": "2024-01-01",
     "source": "UAE labour accommodation rules (background)", "tags": ["room", "sleep", "ac", "غرفة", "نوم", "مكيف"],
     "en": "Worker accommodation must be air-conditioned. If your room AC is broken, report it. A housing task is created and your name is not shared.",
     "ar": "يجب أن يكون سكن العمال مكيفاً. إذا كان مكيف غرفتك معطلاً، أبلغ عن ذلك. تُنشأ مهمة للسكن ولا تتم مشاركة اسمك."},
    {"id": "K-FAST-1", "status": "approved", "jurisdiction": ["general"], "effective": "2024-01-01",
     "source": "Bardan reviewed content (fasting preference)", "tags": ["fasting", "ramadan", "صيام", "رمضان"],
     "en": "If you fast, your reminders can change. Emergency advice never changes. Workers in the kidney care pathway can talk privately with their clinician before a fast.",
     "ar": "إذا كنت صائماً يمكن تغيير مواعيد التذكير. نصائح الطوارئ لا تتغير أبداً. يمكن للعمال في مسار رعاية الكلى التحدث بشكل خاص مع الطبيب قبل الصيام."},
    {"id": "K-DISP-1", "status": "approved", "jurisdiction": ["general"], "effective": "2024-01-01",
     "source": "Bardan worker promises", "tags": ["dispute", "didn't happen", "اعتراض", "لم يحدث"],
     "en": "If a protection did not happen, press 'This didn't happen'. The task stays open and goes to the safety lead. Reporting never affects your pay.",
     "ar": "إذا لم تحدث الحماية، اضغط 'هذا لم يحدث'. تبقى المهمة مفتوحة وتُحال إلى مسؤول السلامة. الإبلاغ لا يؤثر على أجرك أبداً."},
    # Deliberately unusable entries, kept to test the filters.
    {"id": "K-BLOG-9", "status": "unapproved", "jurisdiction": ["general"], "effective": "2023-01-01",
     "source": "Unreviewed blog post", "tags": ["water", "electrolyte", "ماء"],
     "en": "Drink five litres of electrolyte drink every hour to stay safe in the heat.",
     "ar": "اشرب خمسة لترات من مشروب الأملاح كل ساعة لتبقى آمناً في الحر."},
    {"id": "K-SHJ-2", "status": "draft", "jurisdiction": ["AE-SH"], "effective": "2024-07-01",
     "source": "AE-SHJ-HEAT draft pack (not approved)", "tags": ["water", "sharjah", "ماء"],
     "en": "In the high-risk zone, 1.5 litres of water per hour.",
     "ar": "في منطقة الخطر العالي، 1.5 لتر من الماء في الساعة."},
]


def render(template_id: str, lang: str, **slots: Any) -> str:
    t = TEMPLATES[template_id][lang if lang in LANGS else "en"]
    try:
        return t.format(**slots)
    except KeyError:
        return re.sub(r"\{[a-z_0-9]+\}", "…", t)


def approved_passages(jurisdiction: str = "AE-AD", on_date: str = "2025-08-19") -> list[dict[str, Any]]:
    out = []
    for k in KNOWLEDGE:
        if k["status"] != "approved":
            continue
        if not ({jurisdiction, "general"} & set(k["jurisdiction"])) and not (
                jurisdiction.startswith("AE") and "AE" in k["jurisdiction"]):
            continue
        if k["effective"] > on_date:
            continue
        out.append(k)
    return out


def render_notification(n: dict[str, Any], lang: str) -> str:
    """Render a queued notification with localised task names (never raw action codes)."""
    slots = dict((n.get("slots_by_lang") or {}).get(lang) or n.get("slots") or {})
    if "action" in slots:
        slots["action"] = label(TASK_LABELS, str(slots["action"]), lang)
    if slots.get("zone") in (None, "-", ""):
        slots["zone"] = "—"
    template = n["template"]
    if template == "msg.task_to_supervisor" and int(slots.get("minutes") or 0) == 0:
        template = "msg.task_now"
    return render(template, lang, **slots)


def label(table: dict[str, dict[str, str]], key: str, lang: str) -> str:
    row = table.get(key)
    if not row:
        return key
    return row.get(lang) or row["en"]


# Worker-facing wording for engine reason codes, the same sentences the app's "Why" list shows
# (frontend/src/lib/reasons.ts). Used to give the explanation model plain facts instead of codes.
REASON_TEXT = {
    "emergency:urgent_symptom": {"en": "Urgent symptoms: emergency steps first, no test needed.",
                                 "ar": "أعراض عاجلة: خطوات الطوارئ أولاً ولا يلزم أي فحص."},
    "triage:concerning_symptom": {"en": "You reported feeling unwell: stop, cool down and get checked.",
                                  "ar": "أبلغت أنك تشعر بتوعك: توقف وتبرّد واطلب الفحص."},
    "triage:possible_muscle_breakdown": {"en": "Strong muscle pain or dark urine needs a clinician today.",
                                         "ar": "ألم العضلات الشديد أو البول الداكن يحتاج إلى طبيب اليوم."},
    "AE-FED-MIDDAY:window": {"en": "Federal midday break: no outdoor work in the sun from 12:30 to 15:00.",
                             "ar": "استراحة منتصف النهار الاتحادية: لا عمل في الشمس من 12:30 حتى 15:00."},
    "clinical:restriction": {"en": "A clinician set a restriction label for you (the reason stays private).",
                             "ar": "وضعت الطبيبة قيداً على عملك (يبقى السبب خاصاً)."},
    "freshness:missing_or_stale": {"en": "No current heat reading for your zone. This is not confirmed safe.",
                                   "ar": "لا توجد قراءة حرارة حالية لمنطقتك. هذا غير مؤكد أنه آمن."},
    "resources:water_unavailable": {"en": "Drinking water is not available in your zone.",
                                    "ar": "ماء الشرب غير متوفر في منطقتك."},
    "AE-AD-HEAT:unacclimatized": {"en": "You are in your first days; the rules stop heat work in this band.",
                                  "ar": "أنت في أيامك الأولى، والقواعد توقف العمل في الحر في هذا النطاق."},
    "policy:pack_integrity_failed": {"en": "The heat rules failed their integrity check. Follow the site fallback "
                                           "plan; this is not confirmed safe.",
                                     "ar": "فشلت قواعد الحرارة في فحص السلامة. اتبع خطة الموقع البديلة؛ هذا غير مؤكد "
                                           "أنه آمن."},
    "policy:pack_review_overdue": {"en": "The heat rules are past their review date. Follow the site fallback plan; "
                                         "this is not confirmed safe.",
                                   "ar": "تجاوزت قواعد الحرارة موعد مراجعتها. اتبع خطة الموقع البديلة؛ هذا غير مؤكد "
                                         "أنه آمن."},
    "unknown:workload_or_ppe": {"en": "The workload or protective clothing is not known, so the stricter site plan "
                                      "applies.",
                                "ar": "عبء العمل أو ملابس الحماية غير معروفة، لذلك تُطبق خطة الموقع الأشد."},
    "conflict:sources_disagree": {"en": "Two heat readings disagree. The stricter one applies until the safety lead "
                                        "checks them.",
                                  "ar": "قراءتا حرارة مختلفتان. تُطبق الأشد حتى يتحقق منهما مسؤول السلامة."},
}
_BAND_WORDS = {"unrestricted": ("unrestricted", "غير المقيد"), "acclimatization": ("acclimatization", "التأقلم"),
               "buffer": ("buffer", "العازل"), "withdrawal": ("withdrawal", "الانسحاب")}


def reason_text(code: str, lang: str, value: float | None = None) -> str:
    """The worker-facing sentence for a reason code (English or Arabic); the code itself if none is known."""
    row = REASON_TEXT.get(code)
    if row:
        return row.get(lang) or row["en"]
    m = re.match(r"^AE-AD-HEAT:(twl|wbgt_demo):(\w+)$", code)
    if m:
        en, ar = _BAND_WORDS.get(m.group(2), (m.group(2), m.group(2)))
        v = f" ({'TWL' if m.group(1) == 'twl' else 'WBGT'} {value:g})" if value is not None else ""
        return (f"قراءة منطقتك في نطاق {ar}{v} حسب قواعد أبوظبي." if lang == "ar"
                else f"Your zone reading is in the {en} band{v} under Abu Dhabi’s heat code.")
    return code
