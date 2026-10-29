import { Link } from 'react-router'
import { Check, Circle, CircleDot, XCircle } from 'lucide-react'
import { Section } from '@/components/kit'
import { fmtDate, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import { CHAIN_LABEL } from '@/lib/sales'
import type { ChainData, ChainRef } from '@/lib/sales-types'
import { cn } from '@/lib/utils'

const STEP_ICON = { done: Check, current: CircleDot, pending: Circle } as const

function refPath(ref: ChainRef): string | null {
  if (ref.type === 'proposal') return `/sales/proposals/${ref.id}`
  if (ref.type === 'contract') return `/sales/contracts/${ref.id}`
  if (ref.type === 'project') return `/projects/${ref.id}`
  return null
}

export function ProcessChain({ opportunityId }: Readonly<{ opportunityId: string }>) {
  const { t, lang } = useT()
  const { data } = useGet<ChainData>(`/commercial/opportunities/${opportunityId}/chain`)
  if (!data) return null
  return (
    <Section className="mb-4">
      <ol className="grid gap-3 sm:grid-cols-4 lg:grid-cols-7" aria-label={t('Process')}>
        {data.steps.map((s) => {
          const Icon = STEP_ICON[s.status]
          return (
            <li key={s.key} className="min-w-0">
              <div className="flex items-center gap-2">
                <span className={cn('flex h-6 w-6 shrink-0 items-center justify-center rounded-full border', s.status === 'done' && 'border-[hsl(var(--forest))] bg-[hsl(var(--forest)/0.12)] text-[hsl(var(--forest))]', s.status === 'current' && 'border-primary bg-primary/10 text-primary', s.status === 'pending' && 'text-muted-foreground')}>
                  <Icon className="h-3.5 w-3.5" aria-hidden />
                </span>
                <span className={cn('truncate text-sm font-medium', s.status === 'pending' && 'text-muted-foreground')}>{t(CHAIN_LABEL[s.key] ?? s.key)}</span>
                <span className="sr-only">{t(s.status)}</span>
              </div>
              <div className="ml-8 mt-0.5 space-y-0.5 text-xs text-muted-foreground">
                {s.at && <div>{fmtDate(s.at, lang)}</div>}
                {s.refs.map((r) => {
                  const to = refPath(r)
                  return to ? <Link key={r.id} to={to} className="block truncate text-primary hover:underline">{r.label}</Link> : <span key={r.id} className="block truncate">{t(r.label.replaceAll('_', ' '))}</span>
                })}
              </div>
            </li>
          )
        })}
      </ol>
      {data.lost && (
        <p className="mt-3 flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-2 text-sm">
          <XCircle className="mt-0.5 h-4 w-4 text-destructive" aria-hidden />
          <span><span className="font-medium">{t('Lost')}:</span> {data.lost_reason}</span>
        </p>
      )}
    </Section>
  )
}
