/* Arabic renderings of fixed English labels that arrive from the server (scenario, forecast and report labels).
   Unknown strings are shown as sent. */
const AR: Record<string, string> = {
  'SYNTHETIC scenario. Fictional site and people. Replayed real weather (Abu Dhabi, 19 Aug 2025).':
    'سيناريو اصطناعي. موقع وأشخاص وهميون. طقس حقيقي مُعاد (أبوظبي، 19 أغسطس 2025).',
  'SIMULATION: synthetic site, replayed Abu Dhabi weather, emulated forecast error':
    'محاكاة: موقع اصطناعي وطقس أبوظبي المُعاد وخطأ توقع محاكى',
  "Forecast unavailable: the season's standard plan applies": 'التوقعات غير متاحة: تُطبق خطة الموسم القياسية',
  'Forecast service switched off for this sandbox (test T71).': 'خدمة التوقعات متوقفة في هذه البيئة (الاختبار T71).',
  'Live forecast for the site location. Weather data by Open-Meteo.com (CC BY 4.0).':
    'توقعات مباشرة لموقع العمل. بيانات الطقس من Open-Meteo.com (CC BY 4.0).',
  'Derived WBGT from the simulated zone instruments (replayed weather), up to the sandbox clock. Live values govern; forecasts can only add protection.':
    'WBGT مشتق من أجهزة المناطق المحاكاة (طقس مُعاد) حتى ساعة البيئة. القراءات المباشرة هي الحاكمة؛ التوقعات لا تضيف إلا حماية.',
  '90% interval = point +/- 1.645 sigma (sigma 0.5 C, +15% per lead day)': 'نطاق 90% = النقطة ± 1.645 سيغما (سيغما 0.5 درجة، +15% لكل يوم مهلة)',
  'band of the upper end of the 90% interval (Appendix G26)': 'نطاق الحد الأعلى لفاصل 90% (الملحق G26)',
  'SYNTHETIC; denominators shown; tiers reported separately': 'اصطناعي؛ المقامات معروضة؛ المستويات تُعرض منفصلة',
  'SIMULATION (synthetic history)': 'محاكاة (سجل اصطناعي)',
  'SIMULATION: synthetic Poisson series with injected changes; tests the detector, not a site':
    'محاكاة: سلاسل بواسون اصطناعية مع تغييرات محقونة؛ تختبر الكاشف لا الموقع',
  'Demonstration: paraphrased source, not official wording': 'للعرض: مصدر معاد صياغته وليس النص الرسمي',
  'Frozen typed test set (EN/AR). Recorded-speech and noise sets need consenting speakers (pilot).':
    'مجموعة اختبار نصية مجمّدة (إنجليزية/عربية). مجموعات الكلام المسجل والضوضاء تحتاج إلى متحدثين موافقين (مرحلة تجريبية).',
  'SIMULATION: 40-worker synthetic site on replayed days 12-19 Aug 2025 (emulated forecasts)':
    'محاكاة: موقع اصطناعي من 40 عاملاً في أيام مُعادة 12–19 أغسطس 2025 (توقعات محاكاة)',
  'Generated and frozen attacks, English and Arabic. Every failure becomes a regression test.':
    'هجمات مولّدة ومجمّدة بالإنجليزية والعربية. كل إخفاق يصبح اختبار انحدار.',
  'Backtest on derived WBGT from replayed 2025 weather; not site instruments': 'اختبار رجعي على WBGT مشتق من طقس 2025 المُعاد؛ ليس أجهزة موقع',
  "Backtest on derived WBGT from replayed 2025 weather (one season, four zones); not site instruments. Day-one evidence: a pilot recalibrates on the site's own readings.":
    'اختبار رجعي على WBGT مشتق من طقس 2025 المُعاد (موسم واحد، أربع مناطق)؛ ليس أجهزة موقع. دليل اليوم الأول: يعيد المشروع التجريبي المعايرة على قراءات الموقع نفسه.',
  'Author review; comprehension testing pending (protocol in docs/PILOT-KIT.md)': 'مراجعة المؤلف؛ اختبار الفهم معلّق (البروتوكول في docs/PILOT-KIT.md)',
  'Author review; native clinical review and teach-back testing pending (protocol in docs/PILOT-KIT.md)': 'مراجعة المؤلف؛ المراجعة السريرية من متحدثين أصليين واختبار إعادة الشرح معلّقان (البروتوكول في docs/PILOT-KIT.md)',
  "Draft -> Reviewed -> Released (§26.2). English and Arabic only in this prototype; nothing is 'released' before teach-back testing in the pilot.":
    'مسودة ← مُراجَع ← مُعتمد (§26.2). الإنجليزية والعربية فقط في هذا النموذج الأولي؛ لا يُعتمد أي شيء قبل اختبار إعادة الشرح في المشروع التجريبي.',
  'Scripted checks of the real code. They show what each workflow does, not how much faster people are. Timeliness comes only from observed drills.':
    'فحوص مكتوبة مسبقاً للشيفرة الفعلية. تُظهر ما يفعله كل أسلوب عمل، لا مدى سرعة الناس. الالتزام بالمواعيد يأتي فقط من التمارين المرصودة.',
  'Observed drill results: a handful of role-play drills, shown drill by drill. Not a site trial and not a health outcome.':
    'نتائج تمارين مرصودة: عدد قليل من تمارين تمثيل الأدوار، معروضة تمريناً تمريناً. ليست تجربة في موقع وليست نتيجة صحية.',
  'Demonstration excerpt (paraphrased); gold = a separate manual transcription of the same excerpt': 'مقتطف للعرض (معاد صياغته)؛ المرجع = نسخ يدوي منفصل للمقتطف نفسه',
  '15 gold and 15 forbidden questions (plan target: 100 and 30)': '15 سؤالاً مرجعياً و15 سؤالاً محظوراً (هدف الخطة: 100 و30)',
  'SYNTHETIC document': 'وثيقة اصطناعية',
  'Deterministic summary; numbers from the query result': 'ملخص حتمي؛ الأرقام من نتيجة الاستعلام',
  'AI-assisted; numbers from the query result': 'بمساعدة الذكاء الاصطناعي؛ الأرقام من نتيجة الاستعلام',
  "SIMULATION: replayed weather 12-18 Aug 2025, the supervisor's routine schedule each day":
    'محاكاة: طقس مُعاد 12–18 أغسطس 2025، وجدول المشرف المعتاد كل يوم',
}

export function L(s: string | null | undefined, lang: 'en' | 'ar'): string {
  if (!s) return ''
  return lang === 'ar' ? AR[s] ?? s : s
}
