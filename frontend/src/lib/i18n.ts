import { useCallback } from 'react'
import { DE } from '@/lib/i18n-de'
import { usePrefs, type Lang } from '@/lib/prefs'

/** Translate an English source string. Missing German entries fall back to English. */
export function translate(lang: Lang, text: string): string {
  if (lang === 'en') return text
  return DE[text] ?? text
}

export function useT(): { t: (text: string) => string; lang: Lang } {
  const { lang } = usePrefs()
  const t = useCallback((text: string) => translate(lang, text), [lang])
  return { t, lang }
}
