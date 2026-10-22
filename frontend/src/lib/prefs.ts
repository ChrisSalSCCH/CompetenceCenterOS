import { useEffect, useState } from 'react'

export type Lang = 'en' | 'de'
export type Theme = 'light' | 'dark'

const bus = new EventTarget()
const LANG_KEY = 'circleos.lang'
const THEME_KEY = 'circleos.theme'

function readLang(): Lang {
  const saved = localStorage.getItem(LANG_KEY)
  if (saved === 'de' || saved === 'en') return saved
  return navigator.language.toLowerCase().startsWith('de') ? 'de' : 'en'
}

function readTheme(): Theme {
  return localStorage.getItem(THEME_KEY) === 'dark' ? 'dark' : 'light'
}

let lang: Lang = readLang()
let theme: Theme = readTheme()

function applyTheme(): void {
  document.documentElement.classList.toggle('dark', theme === 'dark')
  document.documentElement.lang = lang
}
applyTheme()

export function setLang(next: Lang): void {
  lang = next
  localStorage.setItem(LANG_KEY, next)
  applyTheme()
  bus.dispatchEvent(new Event('change'))
}

export function setTheme(next: Theme): void {
  theme = next
  localStorage.setItem(THEME_KEY, next)
  applyTheme()
  bus.dispatchEvent(new Event('change'))
}

export function getLang(): Lang {
  return lang
}

export function usePrefs(): { lang: Lang; theme: Theme } {
  const [state, setState] = useState({ lang, theme })
  useEffect(() => {
    const handler = () => setState({ lang, theme })
    bus.addEventListener('change', handler)
    return () => bus.removeEventListener('change', handler)
  }, [])
  return state
}
