import { useState } from 'react'
import { Link } from 'react-router'
import { Check, Minus } from 'lucide-react'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { CatalogPicker, type PickedEntry } from '@/components/CatalogPicker'
import { EmptyState, ErrorBlock, LoadingBlock, PageHeader, Pill, Section } from '@/components/kit'
import { fmtDate, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import type { CatalogEntry, ReferenceRow } from '@/lib/portfolio-types'

const ANY = 'any'

function Released({ ok, label }: Readonly<{ ok: boolean; label: string }>) {
  return (
    <span className={ok ? 'inline-flex items-center gap-1 text-[hsl(var(--forest))]' : 'inline-flex items-center gap-1 text-muted-foreground'}>
      {ok ? <Check className="h-3.5 w-3.5" aria-hidden /> : <Minus className="h-3.5 w-3.5" aria-hidden />}
      {label}
    </span>
  )
}

export default function References() {
  const { t, lang } = useT()
  const [tags, setTags] = useState<PickedEntry[]>([])
  const [industry, setIndustry] = useState(ANY)
  const query = tags.length ? `/portfolio/references?${tags.map((x) => `entry_ids=${x.id}`).join('&')}` : '/portfolio/references'
  const { data, isLoading, error } = useGet<ReferenceRow[]>(query, { industry_id: industry === ANY ? undefined : industry })
  const { data: industries } = useGet<CatalogEntry[]>('/catalog', { kind: 'industry' })

  return (
    <>
      <PageHeader title={t('References')} subtitle={t('Projects the customer released as references. Only released content is shown.')} />
      <Section className="mb-4">
        <div className="flex flex-wrap items-center gap-3">
          <Select value={industry} onValueChange={setIndustry}>
            <SelectTrigger className="w-56" aria-label={t('Industry')}><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value={ANY}>{t('Industry')}: {t('Any')}</SelectItem>
              {(industries ?? []).map((i) => <SelectItem key={i.id} value={i.id}>{i.name}</SelectItem>)}
            </SelectContent>
          </Select>
          <CatalogPicker value={tags} onChange={setTags} allowCreate={false} label={t('Technology')} />
        </div>
      </Section>
      {isLoading && <LoadingBlock />}
      {error && <ErrorBlock message={error.message} />}
      {data && data.length === 0 && <EmptyState title={t('No references match')} />}
      <div className="grid gap-4 md:grid-cols-2">
        {(data ?? []).map((r, i) => (
          <article key={r.project_id} className="paper-card reveal p-4" style={{ ['--i' as string]: i }}>
            <div className="mb-1 flex items-start justify-between gap-2">
              <h2 className="font-display text-lg font-semibold">
                {r.name_released ? <Link to={`/projects/${r.project_id}`} className="hover:text-primary">{r.title}</Link> : <span>{t('Confidential project')}{r.industry && ` (${r.industry})`}</span>}
              </h2>
              {r.industry && <Pill>{r.industry}</Pill>}
            </div>
            {!r.name_released && <Link to={`/projects/${r.project_id}`} className="text-xs text-primary hover:underline">{t('Project')}</Link>}
            {r.description && <p className="mt-2 text-sm">{r.description}</p>}
            <div className="mt-3 flex flex-wrap gap-1">{r.entries.map((e) => <Pill key={e.id} tone="primary">{e.name}</Pill>)}</div>
            <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs">
              <Released ok={r.name_released} label={t('Name released')} />
              <Released ok={r.logo_released} label={t('Logo released')} />
              <Released ok={r.images_released} label={t('Images released')} />
              <Released ok={r.results_released} label={t('Results released')} />
            </div>
            {r.approved_by_name && <p className="mt-2 text-xs text-muted-foreground">{t('Approved by')} {r.approved_by_name}{r.approved_at && ` · ${fmtDate(r.approved_at, lang)}`}</p>}
          </article>
        ))}
      </div>
    </>
  )
}
