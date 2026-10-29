import type { Tone } from '@/components/kit'
import type { CatalogKind, Category, Classification, Phase, Verification, KnowledgeSection, CrmRelationType, ActivityKind } from '@/lib/portfolio-types'

export const CATALOG_KINDS: { kind: CatalogKind; label: string }[] = [
  { kind: 'technology', label: 'Technologies' },
  { kind: 'industry', label: 'Industries' },
  { kind: 'research_area', label: 'Research areas' },
  { kind: 'competency', label: 'Competencies' },
  { kind: 'method', label: 'Methods' },
  { kind: 'application_domain', label: 'Application domains' },
  { kind: 'solution_type', label: 'Solution types' },
  { kind: 'reusable_component', label: 'Reusable components' },
]

export const KIND_SINGULAR: Record<CatalogKind, string> = {
  technology: 'Technology',
  industry: 'Industry',
  research_area: 'Research area',
  competency: 'Competency',
  method: 'Method',
  application_domain: 'Application domain',
  solution_type: 'Solution type',
  reusable_component: 'Reusable component',
}

export const CATEGORIES: Category[] = ['research', 'development', 'consulting', 'innovation', 'operations', 'other']
export const PHASES: Phase[] = ['idea', 'proposal', 'running', 'closing', 'completed', 'archived']
export const CLASSIFICATIONS: Classification[] = ['customer', 'internal']
export const PROJECT_STATUSES = ['planned', 'active', 'on_hold', 'done', 'cancelled'] as const
export const CRM_RELATIONS: CrmRelationType[] = ['customer', 'prospect', 'partner', 'research_partner', 'funder', 'supplier', 'competitor', 'other']
export const ACTIVITY_KINDS: ActivityKind[] = ['call', 'meeting', 'email', 'note', 'visit', 'other']

export const KNOWLEDGE_SECTIONS: { key: KnowledgeSection; label: string; hint: string; customerOnly?: boolean; aiOnly?: boolean }[] = [
  { key: 'business_context', label: 'Business context', hint: 'Why did the customer need this? What was the situation?', customerOnly: true },
  { key: 'solution', label: 'Solution', hint: 'What did we build or deliver, in a few sentences?' },
  { key: 'challenges', label: 'Challenges', hint: 'What was hard, and how was it solved?' },
  { key: 'results', label: 'Results', hint: 'What was achieved? Use facts that can be verified.' },
  { key: 'reuse', label: 'Reuse', hint: 'What could other projects take from this one?' },
  { key: 'architecture', label: 'Architecture', hint: 'Main building blocks and how they interact.' },
  { key: 'ai_usage', label: 'AI usage', hint: 'Which AI methods or models are used, and with which data?', aiOnly: true },
]

export const VERIFICATION_TONE: Record<Verification, Tone> = {
  unverified: 'neutral',
  verified: 'forest',
  approved: 'forest',
  ai_draft: 'ochre',
}

export const VERIFICATION_LABEL: Record<Verification, string> = {
  unverified: 'Unverified',
  verified: 'Verified',
  approved: 'Approved',
  ai_draft: 'AI draft',
}

export function phaseTone(phase: Phase): Tone {
  if (phase === 'running') return 'primary'
  if (phase === 'closing') return 'ochre'
  if (phase === 'completed') return 'forest'
  return 'neutral'
}

export function classificationTone(c: Classification): Tone {
  return c === 'customer' ? 'ink' : 'neutral'
}

/** Sections a project should maintain, depending on its classification and AI relevance. */
export function relevantSections(classification: Classification, aiRelevant: boolean) {
  return KNOWLEDGE_SECTIONS.filter((s) => (!s.customerOnly || classification === 'customer') && (!s.aiOnly || aiRelevant))
}

export function formatMoney(value: number | null | undefined, currency = 'EUR', lang = 'en'): string {
  if (value === null || value === undefined) return '–'
  return new Intl.NumberFormat(lang === 'de' ? 'de-AT' : 'en-GB', { style: 'currency', currency, maximumFractionDigits: 0 }).format(Number(value))
}

export function formatPct(value: number | null | undefined): string {
  return value === null || value === undefined ? '–' : `${value.toFixed(1)} %`
}

/** Comparison key matching the backend: lower-case letters, digits, '+' and '#' only. */
export function normalizeName(value: string): string {
  return value.toLowerCase().replaceAll(/[^a-z0-9+#]+/g, '')
}

/** The suggestion that equals the typed text (by name or alias), if any - then no "create" offer is made. */
export function exactSuggestion<T extends { name: string; matched_alias: string | null }>(items: T[], text: string): T | undefined {
  const key = normalizeName(text)
  if (!key) return undefined
  return items.find((i) => normalizeName(i.name) === key || (i.matched_alias !== null && normalizeName(i.matched_alias) === key))
}

/** True when a customer project would be saved without a customer organization. */
export function customerRuleViolated(classification: Classification, customerCount: number): boolean {
  return classification === 'customer' && customerCount < 1
}

export function fullName(c: { first_name: string; last_name: string }): string {
  return `${c.first_name} ${c.last_name}`.trim()
}

/** Days since an ISO date, or null when there is no date. */
export function daysSince(iso: string | null | undefined, now: Date = new Date()): number | null {
  if (!iso) return null
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return null
  return Math.floor((now.getTime() - then) / 86_400_000)
}
