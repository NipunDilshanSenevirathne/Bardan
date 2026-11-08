import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { STRINGS, type Lang } from './strings'

type Ctx = { lang: Lang; dir: 'ltr' | 'rtl'; setLang: (l: Lang) => void; t: (k: string, v?: Record<string, string | number>) => string }
const I18n = createContext<Ctx | null>(null)

function readLang(): Lang {
  try {
    const l = localStorage.getItem('bardan.lang')
    if (l === 'ar' || l === 'en') return l
  } catch { /* storage blocked */ }
  return 'en'
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(readLang)
  const dir = lang === 'ar' ? 'rtl' : 'ltr'
  useEffect(() => {
    document.documentElement.lang = lang
    document.documentElement.dir = dir
  }, [lang, dir])
  const setLang = useCallback((l: Lang) => {
    setLangState(l)
    try { localStorage.setItem('bardan.lang', l) } catch { /* ignore */ }
  }, [])
  const t = useCallback((k: string, v?: Record<string, string | number>) => {
    let s = STRINGS[lang][k] ?? STRINGS.en[k] ?? k
    if (v) for (const [key, val] of Object.entries(v)) s = s.split(`{${key}}`).join(String(val))
    return s
  }, [lang])
  const value = useMemo(() => ({ lang, dir: dir as 'ltr' | 'rtl', setLang, t }), [lang, dir, setLang, t])
  return <I18n.Provider value={value}>{children}</I18n.Provider>
}

export function useI18n() {
  const c = useContext(I18n)
  if (!c) throw new Error('I18nProvider missing')
  return c
}

/** Pick the Arabic or English field of an object (e.g. name / name_ar). */
export function pick<T extends Record<string, any>>(obj: T | undefined | null, key: string, lang: Lang): string {
  if (!obj) return ''
  if (lang === 'ar' && obj[`${key}_ar`]) return obj[`${key}_ar`]
  return obj[key] ?? ''
}
