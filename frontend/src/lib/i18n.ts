import { useCallback } from 'react'
import { DE } from '@/lib/i18n-de'
import { DE_COMMERCIAL } from '@/lib/i18n-de-commercial'
import { DE_PORTFOLIO } from '@/lib/i18n-de-portfolio'
import { DE_SALES } from '@/lib/i18n-de-sales'
import { usePrefs, type Lang } from '@/lib/prefs'

const DICTIONARY: Record<string, string> = { ...DE, ...DE_PORTFOLIO, ...DE_SALES, ...DE_COMMERCIAL }

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
