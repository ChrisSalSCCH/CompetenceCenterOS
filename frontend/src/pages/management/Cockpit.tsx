import { Link } from 'react-router'
import { AlertTriangle, ArrowRight } from 'lucide-react'
import { ExportMenu } from '@/components/management/ExportMenu'
import { EmptyState, ErrorBlock, LoadingBlock, PageHeader, Pill, Section, Stat, type Tone } from '@/components/kit'
import { fmtDate, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import { fmtMoneyMap, stageTone, STAGE_LABEL } from '@/lib/sales'
import type { Stage } from '@/lib/sales-types'
import type { CockpitData, QualityData } from '@/lib/management-types'
import { utilizationTone } from '@/lib/management'

const ATTENTION_LABEL: Record<string, string> = {
  overdue_actions: 'Overdue next actions',
  overdue_decisions: 'Overdue decisions',
  without_owner: 'Without owner',
  without_next_action: 'Without next action',
  stale: 'No activity for 30 days',
  authority_unclear: 'Decision authority unclear',
}

function Counts({ data, tone }: Readonly<{ data: Record<string, number>; tone?: Tone }>) {
  const { t } = useT()
  const entries = Object.entries(data)
  if (entries.length === 0) return <p className="text-sm italic text-muted-foreground">{t('Nothing to show')}</p>
  return (
    <div className="flex flex-wrap gap-2">
      {entries.map(([k, n]) => <Pill key={k} tone={tone}>{t(k.replaceAll('_', ' '))}: {n}</Pill>)}
    </div>
  )
}

export default function Cockpit() {
  const { t, lang } = useT()
  const { data, isLoading, error } = useGet<CockpitData>('/management/dashboard')
  const { data: quality } = useGet<QualityData>('/management/data-quality')

  if (isLoading) return <LoadingBlock />
  if (error || !data) return <ErrorBlock message={error?.message} />
  const hide = data.money_hidden
  const attention = Object.entries(data.attention).filter(([, b]) => b.count > 0)
  const cap = data.capacity

  return (
    <>
      <PageHeader
        eyebrow={t('Management')}
        title={t('Management cockpit')}
        subtitle={t('Pipeline, results, risks, contracts, projects and capacity in one view. Every figure is calculated from the stored records.')}
        actions={<ExportMenu />}
      />
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label={t('Open opportunities')} value={data.pipeline.open_count} />
        <Stat label={t('Weighted pipeline')} value={<span className="text-2xl">{hide ? '–' : fmtMoneyMap(data.pipeline.weighted, lang)}</span>} hint={t('Calculated: value x probability')} />
        <Stat label={t('Win rate')} value={data.results.win_rate === null ? '–' : `${data.results.win_rate}%`} hint={`${data.results.won} ${t('won')} / ${data.results.lost} ${t('lost')}`} />
        <Stat label={t('Average cycle (days)')} value={data.results.avg_cycle_days ?? '–'} hint={t('Won opportunities')} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Section title={t('Pipeline by stage')} index={1}>
          <ul className="divide-y">
            {data.pipeline.by_stage.map((s) => (
              <li key={s.stage} className="flex items-center justify-between gap-3 py-2 text-sm">
                <Pill tone={stageTone(s.stage as Stage)}>{t(STAGE_LABEL[s.stage as Stage] ?? s.stage)}</Pill>
                <span className="text-muted-foreground">{s.count}</span>
                <span className="ml-auto font-medium">{hide ? '–' : fmtMoneyMap(s.value, lang)}</span>
              </li>
            ))}
          </ul>
        </Section>

        <Section title={t('Needs attention')} index={2}>
          {attention.length === 0 && data.unfilled_decision_roles.length === 0 && <EmptyState title={t('Nothing needs attention')} />}
          <ul className="space-y-3">
            {attention.map(([key, bucket]) => (
              <li key={key}>
                <div className="flex items-center gap-2 text-sm font-medium">
                  <AlertTriangle className="h-4 w-4 text-[hsl(var(--ochre))]" aria-hidden />
                  {t(ATTENTION_LABEL[key] ?? key)} <Pill tone="ochre">{bucket.count}</Pill>
                </div>
                <ul className="ml-6 mt-1 space-y-0.5 text-xs">
                  {bucket.items.map((o) => (
                    <li key={o.id}><Link className="underline-offset-2 hover:underline" to={`/sales/opportunities/${o.id}`}>{o.number} {o.title}</Link> <span className="text-muted-foreground">{o.customer_name}</span></li>
                  ))}
                </ul>
              </li>
            ))}
            {data.unfilled_decision_roles.map((r) => (
              <li key={r.id} className="flex items-center gap-2 text-sm">
                <AlertTriangle className="h-4 w-4 text-destructive" aria-hidden />
                <span>{t('Deciding role without holder')}: <strong>{r.role_name}</strong> ({r.label})</span>
              </li>
            ))}
          </ul>
          {quality && quality.total > 0 && (
            <Link to="/management/data-quality" className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline">
              {quality.total} {t('data quality findings')} <ArrowRight className="h-3.5 w-3.5" aria-hidden />
            </Link>
          )}
        </Section>

        <Section title={t('Proposals')} index={3}>
          <Counts data={data.proposals.by_status} />
          {data.proposals.awaiting_approval.length > 0 && (
            <ul className="mt-3 space-y-1 text-sm">
              <li className="font-mono-label text-muted-foreground">{t('Awaiting approval')}</li>
              {data.proposals.awaiting_approval.map((p) => <li key={p.id}><Link className="hover:underline" to={`/sales/proposals/${p.id}`}>{p.number} {p.title}</Link></li>)}
            </ul>
          )}
        </Section>

        <Section title={t('Contracts and NDAs')} index={4}>
          <Counts data={data.contracts.by_state} />
          <p className="mt-2 text-sm">{t('Active contract value')}: <strong>{data.contracts.conditions_visible && !hide ? fmtMoneyMap(data.contracts.active_value, lang) : '–'}</strong></p>
          {!data.contracts.conditions_visible && <p className="text-xs text-muted-foreground">{t('Contract conditions need signing rights.')}</p>}
          {data.contracts.expiring.length > 0 && (
            <ul className="mt-2 space-y-1 text-sm">
              <li className="font-mono-label text-muted-foreground">{t('Expiring soon')}</li>
              {data.contracts.expiring.map((c) => <li key={c.id}><Link className="hover:underline" to={`/sales/contracts/${c.id}`}>{c.number} {c.title}</Link> <span className="text-muted-foreground">{fmtDate(c.valid_to, lang)}</span></li>)}
            </ul>
          )}
          <div className="mt-3"><div className="font-mono-label mb-1 text-muted-foreground">NDAs</div><Counts data={data.ndas} /></div>
        </Section>

        <Section title={t('Projects')} index={5}>
          <div className="mb-2 grid grid-cols-3 gap-2 text-center text-sm">
            <div><div className="font-display text-2xl">{data.projects.customer_active}</div><div className="text-xs text-muted-foreground">{t('Customer projects')}</div></div>
            <div><div className="font-display text-2xl">{data.projects.internal_active}</div><div className="text-xs text-muted-foreground">{t('Internal projects')}</div></div>
            <div><div className="font-display text-2xl">{data.projects.research}</div><div className="text-xs text-muted-foreground">{t('Research')}</div></div>
          </div>
          <Counts data={data.projects.by_phase} />
          {data.projects.finance && data.projects.finance.length > 0 && (
            <table className="mt-3 w-full text-sm">
              <thead><tr className="text-left text-xs text-muted-foreground"><th>{t('Currency')}</th><th className="text-right">{t('Budget')}</th><th className="text-right">{t('Costs to date')}</th></tr></thead>
              <tbody>{data.projects.finance.map((f) => <tr key={f.currency}><td>{f.currency}</td><td className="text-right">{f.budget.toLocaleString(lang)}</td><td className="text-right">{f.costs.toLocaleString(lang)}</td></tr>)}</tbody>
            </table>
          )}
        </Section>

        <Section title={t('Capacity')} index={6} action={<Link to="/projects" className="text-sm text-primary hover:underline">{t('Portfolio')}</Link>}>
          <div className="grid grid-cols-3 gap-2 text-center text-sm">
            <div><div className="font-display text-2xl">{cap.average_utilization === null ? '–' : `${cap.average_utilization}%`}</div><div className="text-xs text-muted-foreground">{t('Average utilization')}</div></div>
            <div><div className="font-display text-2xl">{cap.overloaded_people}</div><div className="text-xs text-muted-foreground">{t('Overloaded people')}</div></div>
            <div><div className="font-display text-2xl">{cap.people_without_capacity}</div><div className="text-xs text-muted-foreground">{t('Without capacity entry')}</div></div>
          </div>
          <div className="mt-3"><Pill tone={utilizationTone(cap.average_utilization)}>{cap.average_utilization === null ? t('No data') : `${cap.average_utilization}%`}</Pill></div>
        </Section>
      </div>
    </>
  )
}
