import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'

type Theme = 'light' | 'dark'
const C = createContext<{ theme: Theme; toggle: () => void; set: (t: Theme) => void } | null>(null)

function initial(): Theme {
  return document.documentElement.classList.contains('dark') ? 'dark' : 'light'
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(initial)
  const set = useCallback((t: Theme) => {
    setTheme(t)
    document.documentElement.classList.toggle('dark', t === 'dark')
    try { localStorage.setItem('bardan.theme', t) } catch { /* ignore */ }
    const meta = document.querySelector('meta[name="theme-color"]')
    meta?.setAttribute('content', t === 'dark' ? '#060a14' : '#0B1324')
  }, [])
  const toggle = useCallback(() => set(theme === 'dark' ? 'light' : 'dark'), [theme, set])
  return <C.Provider value={{ theme, toggle, set }}>{children}</C.Provider>
}

export function useTheme() {
  const c = useContext(C)
  if (!c) throw new Error('ThemeProvider missing')
  return c
}
