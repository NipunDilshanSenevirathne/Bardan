/* Human wording for engine reason codes (EN/AR). Codes come from the deterministic policy engine. */
export function reasonText(code: string, lang: 'en' | 'ar', ctx: { value?: number | null } = {}): string {
  const en: Record<string, string> = {
    'emergency:urgent_symptom': 'Urgent symptoms: emergency steps first, no test needed.',
    'triage:concerning_symptom': 'You reported feeling unwell: stop, cool down and get checked.',
    'triage:possible_muscle_breakdown': 'Strong muscle pain or dark urine needs a clinician today.',
    'AE-FED-MIDDAY:window': 'Federal midday break: no outdoor work in the sun from 12:30 to 15:00.',
    'clinical:restriction': 'A clinician set a restriction label for you (the reason stays private).',
    'freshness:missing_or_stale': 'No current heat reading for your zone. This is not confirmed safe.',
    'resources:water_unavailable': 'Drinking water is not available in your zone.',
    'AE-AD-HEAT:unacclimatized': 'You are in your first days; the rules stop heat work in this band.',
    'policy:pack_integrity_failed': 'The heat rules failed their integrity check. Follow the site fallback plan; this is not confirmed safe.',
    'policy:pack_review_overdue': 'The heat rules are past their review date. Follow the site fallback plan; this is not confirmed safe.',
    'unknown:workload_or_ppe': 'The workload or protective clothing is not known, so the stricter site plan applies.',
    'conflict:sources_disagree': 'Two heat readings disagree. The stricter one applies until the safety lead checks them.',
  }
  const ar: Record<string, string> = {
    'emergency:urgent_symptom': 'أعراض عاجلة: خطوات الطوارئ أولاً ولا يلزم أي فحص.',
    'triage:concerning_symptom': 'أبلغت أنك تشعر بتوعك: توقف وتبرّد واطلب الفحص.',
    'triage:possible_muscle_breakdown': 'ألم العضلات الشديد أو البول الداكن يحتاج إلى طبيب اليوم.',
    'AE-FED-MIDDAY:window': 'استراحة منتصف النهار الاتحادية: لا عمل في الشمس من 12:30 حتى 15:00.',
    'clinical:restriction': 'وضعت الطبيبة قيداً على عملك (يبقى السبب خاصاً).',
    'freshness:missing_or_stale': 'لا توجد قراءة حرارة حالية لمنطقتك. هذا غير مؤكد أنه آمن.',
    'resources:water_unavailable': 'ماء الشرب غير متوفر في منطقتك.',
    'AE-AD-HEAT:unacclimatized': 'أنت في أيامك الأولى، والقواعد توقف العمل في الحر في هذا النطاق.',
    'policy:pack_integrity_failed': 'فشلت قواعد الحرارة في فحص السلامة. اتبع خطة الموقع البديلة؛ هذا غير مؤكد أنه آمن.',
    'policy:pack_review_overdue': 'تجاوزت قواعد الحرارة موعد مراجعتها. اتبع خطة الموقع البديلة؛ هذا غير مؤكد أنه آمن.',
    'unknown:workload_or_ppe': 'عبء العمل أو ملابس الحماية غير معروفة، لذلك تُطبق خطة الموقع الأشد.',
    'conflict:sources_disagree': 'قراءتا حرارة مختلفتان. تُطبق الأشد حتى يتحقق منهما مسؤول السلامة.',
  }
  const dict = lang === 'ar' ? ar : en
  if (dict[code]) return dict[code]
  const m = code.match(/^AE-AD-HEAT:(twl|wbgt_demo):(\w+)$/)
  if (m) {
    const bandEn: Record<string, string> = { unrestricted: 'unrestricted', acclimatization: 'acclimatization', buffer: 'buffer', withdrawal: 'withdrawal' }
    const bandAr: Record<string, string> = { unrestricted: 'غير المقيد', acclimatization: 'التأقلم', buffer: 'العازل', withdrawal: 'الانسحاب' }
    const v = ctx.value != null ? ` (${m[1] === 'twl' ? 'TWL' : 'WBGT'} ${ctx.value})` : ''
    return lang === 'ar'
      ? `قراءة منطقتك في نطاق ${bandAr[m[2]] ?? m[2]}${v} حسب قواعد أبوظبي.`
      : `Your zone reading is in the ${bandEn[m[2]] ?? m[2]} band${v} under Abu Dhabi’s heat code.`
  }
  return code
}
