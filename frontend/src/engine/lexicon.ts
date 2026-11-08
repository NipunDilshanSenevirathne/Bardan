/*
 * Offline phrase matcher on the phone (English and Arabic, Gulf dialect, code-switching).
 *
 * A line-for-line port of backend/app/ai/intake.py offline_parse(), driven by the same lexicon file
 * (shared/lexicon.json). It lets a typed report open the emergency card at once with no network and no AI, and lets
 * a worker confirm and queue a typed report while offline. lexicon.test.ts holds it to the server's results.
 */
import lexicon from '../../../shared/lexicon.json'

export type Candidate = { intent: string; polarity: 'affirmed' | 'negated' | 'uncertain'; evidence_words: string[]; about: 'self' | 'other_person' }
export type Parse = { language: 'en' | 'ar' | 'mixed' | 'other'; transcript: string; candidates: Candidate[]; uncertain: boolean; method: 'offline_phrase_matcher' }
export type IntentInfo = { urgent: boolean; symptom?: string; icon: string; en: string; ar: string }

const LEX = lexicon as unknown as {
  neg_en: string[]; neg_ar: string[]; about_other: string[]; ar_prefixes: string[]
  phrases: [string, string[][]][]; cooccur: [string, string[], string[]][]; keywords: Record<string, string[]>
  dark: string[]; chest_pain: string[]; intents: Record<string, IntentInfo>
}
export const INTENTS: Record<string, IntentInfo> = LEX.intents
export const LEXICON_VERSION: string = (lexicon as any).version

const AR_DIACRITICS = /[ؐ-ًؚ-ٰٟۖ-ۭـ]/g
const STRIP = new Set(['.', ',', '!', '?', '؟', '،', ';', ':', '"', "'", '(', ')', '[', ']', '{', '}', '…', '-'])
const TOKEN = /[\p{L}\p{N}_ً-ٰٟ']+/gu
const NEG = new Set([...LEX.neg_en, ...LEX.neg_ar])
const ABOUT = new Set(LEX.about_other)

export function normToken(t: string): string {
  let s = t.normalize('NFKC').toLowerCase().replace(AR_DIACRITICS, '')
  s = s.replace(/[إأآٱ]/g, 'ا').replaceAll('ى', 'ي').replaceAll('ة', 'ه').replaceAll('ؤ', 'و').replaceAll('ئ', 'ي')
  let a = 0
  let b = s.length
  while (a < b && STRIP.has(s[a])) a++
  while (b > a && STRIP.has(s[b - 1])) b--
  return s.slice(a, b)
}

function tokenize(text: string): [string, string][] {
  return (text.match(TOKEN) ?? []).map((t) => [t, normToken(t)])
}

function stripArPrefix(n: string): string[] {
  const out = [n]
  for (const p of LEX.ar_prefixes) if (n.startsWith(p) && n.length - p.length >= 3) out.push(n.slice(p.length))
  return out
}
const hits = (n: string, set: Set<string>) => stripArPrefix(n).some((v) => set.has(v))
const normSet = (words: string[]) => new Set(words.map(normToken))
const KEYWORDS = Object.entries(LEX.keywords).map(([k, v]) => [k, normSet(v)] as const)
const COOCCUR = LEX.cooccur.map(([i, s, t]) => [i, normSet(s), normSet(t)] as const)
const DARK = normSet(LEX.dark)
const CHEST = normSet(LEX.chest_pain)

function language(text: string): Parse['language'] {
  let ar = 0
  let lat = 0
  for (const ch of text) {
    if (ch >= '؀' && ch <= 'ۿ') ar++
    else if (/^[A-Za-z]$/.test(ch)) lat++
  }
  if (ar && lat) return 'mixed'
  return ar ? 'ar' : lat ? 'en' : 'other'
}

export function offlineParse(text: string): Parse {
  const toks = tokenize(text)
  const norms = toks.map(([, n]) => n)
  const used = norms.map(() => false)
  const cands: Candidate[] = []
  const add = (intent: string, idxs: number[], polarity: Candidate['polarity'] = 'affirmed', about: Candidate['about'] = 'self') => {
    cands.push({ intent, polarity, evidence_words: idxs.map((i) => toks[i][0]), about })
    for (const i of idxs) used[i] = true
  }
  const about: Candidate['about'] = norms.some((n) => ABOUT.has(n)) ? 'other_person' : 'self'
  for (const [intent, phrases] of LEX.phrases) {
    for (const ph of phrases) {
      const L = ph.length
      for (let i = 0; i <= norms.length - L; i++) {
        let all = true
        for (let k = 0; k < L; k++) {
          const p = normToken(ph[k])
          if (!(norms[i + k] === p || stripArPrefix(norms[i + k]).includes(p))) { all = false; break }
        }
        if (all && !used.slice(i, i + L).some(Boolean)) add(intent, Array.from({ length: L }, (_, k) => i + k), 'affirmed', intent.startsWith('SYMPTOM') ? about : 'self')
      }
    }
  }
  for (const [intent, subj, state] of COOCCUR) {
    norms.forEach((n, i) => {
      if (used[i] || !hits(n, subj)) return
      for (let j = Math.max(0, i - 4); j < Math.min(norms.length, i + 5); j++) {
        if (j !== i && !used[j] && hits(norms[j], state)) { add(intent, [...new Set([i, j])].sort((x, y) => x - y)); break }
      }
    })
  }
  for (const [intent, wn] of KEYWORDS) {
    norms.forEach((n, i) => {
      if (used[i] || !hits(n, wn)) return
      let idxs = [i]
      const near = (set: Set<string>) => {
        const out: number[] = []
        for (let j = Math.max(0, i - 3); j < Math.min(norms.length, i + 4); j++) if (hits(norms[j], set)) out.push(j)
        return out
      }
      if (intent === 'SYMPTOM_MUSCLE_DARK_URINE') { const d = near(DARK); if (!d.length) return; idxs = [...idxs, ...d] }
      if (intent === 'SYMPTOM_CHEST_PAIN') { const d = near(CHEST); if (!d.length) return; idxs = [...idxs, ...d] }
      const neg: number[] = []
      for (let j = Math.max(0, i - 3); j < i; j++) if (NEG.has(norms[j])) neg.push(j)
      add(intent, [...new Set([...neg, ...idxs])].sort((x, y) => x - y), neg.length ? 'negated' : 'affirmed', about)
    })
  }
  const merged = new Map<string, Candidate>()
  let uncertain = false
  for (const c of cands) {
    const prev = merged.get(c.intent)
    if (prev && prev.polarity !== c.polarity) { prev.polarity = 'uncertain'; uncertain = true } else if (!prev) merged.set(c.intent, c)
  }
  const out = [...merged.values()]
  return { language: language(text), transcript: text, candidates: out, uncertain: uncertain || !out.length, method: 'offline_phrase_matcher' }
}

/** Urgent words found on the phone itself: the emergency card opens before any network call (T68). */
export function urgentNow(text: string): Candidate[] {
  return offlineParse(text).candidates.filter((c) => INTENTS[c.intent]?.urgent && c.polarity !== 'negated')
}
