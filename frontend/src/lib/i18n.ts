import { useCallback } from 'react'
import { DE } from '@/lib/i18n-de'
import { DE_PORTFOLIO } from '@/lib/i18n-de-portfolio'
import { usePrefs, type Lang } from '@/lib/prefs'

const DICTIONARY: Record<string, string> = { ...DE, ...DE_PORTFOLIO }

/** Translate an English source string. Missing German entries fall back to English. */
export function translate(lang: Lang, text: string): string {
  if (lang === 'en') return text
  return DICTIONARY[text] ?? text
}

export function useT(): { t: (text: string) => string; lang: Lang } {
  const { lang } = usePrefs()
  const t = useCallback((text: string) => translate(lang, text), [lang])
  return { t, lang }
}
