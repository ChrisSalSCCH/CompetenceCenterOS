import api from '@/lib/api'

export const EXPORT_SETS = ['opportunities', 'proposals', 'contracts', 'ndas', 'customers', 'projects', 'data_quality'] as const
export type ExportSet = (typeof EXPORT_SETS)[number]
export type ExportFormat = 'csv' | 'xlsx'

export const EXPORT_LABEL: Record<ExportSet, string> = {
  opportunities: 'Opportunities',
  proposals: 'Proposals',
  contracts: 'Contracts',
  ndas: 'NDAs',
  customers: 'Customers',
  projects: 'Projects',
  data_quality: 'Data quality findings',
}

/** Download an export through the authenticated client, then hand the blob to the browser. */
export async function downloadExport(dataset: ExportSet, format: ExportFormat): Promise<void> {
  const res = await api.get<Blob>(`/management/export/${dataset}`, { params: { format }, responseType: 'blob' })
  const url = URL.createObjectURL(res.data)
  const link = document.createElement('a')
  link.href = url
  link.download = `${dataset}.${format}`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

/** "2026-03" -> "Mar 2026"; any other key (e.g. "undated") is returned unchanged. */
export function monthLabel(key: string, lang: string): string {
  const m = /^(\d{4})-(\d{2})$/.exec(key)
  if (!m) return key
  return new Date(Number(m[1]), Number(m[2]) - 1, 1).toLocaleDateString(lang === 'de' ? 'de-AT' : 'en-GB', { month: 'short', year: 'numeric' })
}

export function sumValues(values: Record<string, number> | undefined): number {
  return Object.values(values ?? {}).reduce((a, b) => a + b, 0)
}

export function utilizationTone(pct: number | null): 'neutral' | 'forest' | 'ochre' | 'danger' {
  if (pct === null) return 'neutral'
  if (pct > 100) return 'danger'
  if (pct > 85) return 'ochre'
  return 'forest'
}
