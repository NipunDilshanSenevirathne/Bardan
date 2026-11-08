/* Read aloud (finalsystem.md §7.5 "written in plain words and read aloud", journey §8.1 "the worker hears
   today's plan"). Bardan Intelligence speech when it is on and reachable; otherwise the phone's own voice.
   Nothing safety-critical depends on it: the emergency card never waits for speech. */
import { useEffect, useRef, useState } from 'react'
import { api, store } from './api'

const cache = new Map<string, string>()      // text -> object URL of generated speech (this tab only)
let current: HTMLAudioElement | null = null
let serverRestUntil = 0                      // after a refusal (quota used up), use the phone's voice for a while

function deviceVoice(text: string, lang: 'en' | 'ar', onEnd: () => void): boolean {
  const synth = typeof window !== 'undefined' ? window.speechSynthesis : undefined
  if (!synth || typeof SpeechSynthesisUtterance === 'undefined') return false
  const u = new SpeechSynthesisUtterance(text)
  u.lang = lang === 'ar' ? 'ar-AE' : 'en-GB'
  const voice = synth.getVoices().find((v) => v.lang.toLowerCase().startsWith(lang))
  if (voice) u.voice = voice
  u.onend = onEnd
  u.onerror = onEnd
  synth.cancel()
  synth.speak(u)
  return true
}

export function stopSpeaking() {
  try { current?.pause() } catch { /* ignore */ }
  current = null
  try { window.speechSynthesis?.cancel() } catch { /* ignore */ }
}

export function useSpeech() {
  const [speaking, setSpeaking] = useState(false)
  const [busy, setBusy] = useState(false)
  const [unavailable, setUnavailable] = useState(false)
  const alive = useRef(true)
  useEffect(() => { alive.current = true; return () => { alive.current = false; stopSpeaking() } }, [])
  const done = () => { if (alive.current) setSpeaking(false) }

  /** `server`: Bardan Intelligence speech is on for this sandbox (otherwise the phone's own voice is used). */
  async function speak(text: string, lang: 'en' | 'ar', server = true) {
    stopSpeaking()
    setUnavailable(false)
    // Created inside the tap, so browsers that need a gesture for sound still allow it after the download.
    const audio = new Audio()
    current = audio
    if (server && !store.get().offline && Date.now() > serverRestUntil) {
      try {
        let url = cache.get(text)
        if (!url) {
          setBusy(true)
          const blob = await api<Blob>('/assist/tts', { body: { text } })
          url = URL.createObjectURL(blob)
          cache.set(text, url)
        }
        if (current !== audio) return                // stopped while downloading
        audio.src = url
        audio.onended = done
        audio.onerror = done
        setSpeaking(true)
        await audio.play()
        return
      } catch (e: any) {
        // Speech off, quota used up, a network problem or a blocked autoplay: use the phone's own voice.
        if (e?.status) serverRestUntil = Date.now() + 5 * 60_000
      } finally {
        if (alive.current) setBusy(false)
      }
    }
    if (current !== audio) return
    if (deviceVoice(text, lang, done)) setSpeaking(true)
    else { setSpeaking(false); setUnavailable(true) }
  }

  return { speak, stop: () => { stopSpeaking(); setSpeaking(false); setBusy(false) }, speaking, busy, unavailable }
}
