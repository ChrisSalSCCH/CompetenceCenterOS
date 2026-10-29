import { ExportMenu } from '@/components/management/ExportMenu'
import { EmptyState, ErrorBlock, LoadingBlock, PageHeader, Section, Stat } from '@/components/kit'
import { useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import { fmtMoneyMap } from '@/lib/sales'
import type { AnalyticsData, WinStats } from '@/lib/management-types'

function rate(s: WinStats): string {
  return s.win_rate === null ? '–' : `${s.win_rate}%`
}

export default function Analytics() {
  const { t, lang } = useT()
  const { data, isLoading, error } = useGet<AnalyticsData>('/management/analytics')

  if (isLoading) return <LoadingBlock />
  if (error || !data) return <ErrorBlock message={error?.message} />
  const hide = data.money_hidden

  return (
    <>
      <PageHeader
        eyebrow={t('Management')}
        title={t('Analytics')}
        subtitle={t('Win rates, customers, industries, technologies, lost reasons and margin.')}
        actions={<ExportMenu />}
      />
      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <Stat label={t('Cycle won (days)')} value={data.cycle_days.won ?? '–'} />
        <Stat label={t('Cycle lost (days)')} value={data.cycle_days.lost ?? '–'} />
        <Stat label={t('Proposals')} value={Object.values(data.proposals).reduce((a, b) => a + b, 0)} />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Section title={t('By category')}>
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs text-muted-foreground"><th>{t('Category')}</th><th className="text-right">{t('Won')}</th><th className="text-right">{t('Lost')}</th><th className="text-right">{t('Open')}</th><th className="text-right">{t('Win rate')}</th></tr></thead>
            <tbody>{data.by_category.map((c) => <tr key={c.category} className="border-t"><td className="py-1.5">{t(c.category)}</td><td className="text-right">{c.won}</td><td className="text-right">{c.lost}</td><td className="text-right">{c.open}</td><td className="text-right font-medium">{rate(c)}</td></tr>)}</tbody>
          </table>
        </Section>

        <Section title={t('Top customers')}>
          {data.customers.length === 0 ? <EmptyState title={t('Nothing to show')} /> : (
            <table className="w-full text-sm">
              <thead><tr className="text-left text-xs text-muted-foreground"><th>{t('Customer')}</th><th className="text-right">{t('Opportunities')}</th><th className="text-right">{t('Win rate')}</th><th className="text-right">{t('Won value')}</th></tr></thead>
              <tbody>{data.customers.map((c) => <tr key={c.crm_org_id} className="border-t"><td className="py-1.5">{c.name}</td><td className="text-right">{c.opportunities}</td><td className="text-right">{rate(c)}</td><td className="text-right">{hide ? '–' : fmtMoneyMap(c.won_value, lang)}</td></tr>)}</tbody>
            </table>
          )}
        </Section>

        <Section title={t('Industries')}>
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs text-muted-foreground"><th>{t('Industry')}</th><th className="text-right">{t('Projects')}</th><th className="text-right">{t('Opportunities')}</th></tr></thead>
            <tbody>{data.industries.map((i) => <tr key={i.industry} className="border-t"><td className="py-1.5">{i.industry}</td><td className="text-right">{i.projects}</td><td className="text-right">{i.opportunities}</td></tr>)}</tbody>
          </table>
        </Section>

        <Section title={t('Technologies')}>
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs text-muted-foreground"><th>{t('Technology')}</th><th className="text-right">{t('Projects')}</th><th className="text-right">{t('Opportunities')}</th></tr></thead>
            <tbody>{data.technologies.map((i) => <tr key={i.id} className="border-t"><td className="py-1.5">{i.name}</td><td className="text-right">{i.projects}</td><td className="text-right">{i.opportunities}</td></tr>)}</tbody>
          </table>
        </Section>

        <Section title={t('Lost reasons')}>
          {data.lost_reasons.length === 0 ? <EmptyState title={t('No lost opportunities with a reason')} /> : (
            <ul className="divide-y text-sm">{data.lost_reasons.map((r) => <li key={r.reason} className="flex justify-between py-1.5"><span>{r.reason}</span><span className="font-medium">{r.count}</span></li>)}</ul>
          )}
        </Section>

        {data.margin_by_category && (
          <Section title={t('Average margin by category')}>
            <ul className="divide-y text-sm">{data.margin_by_category.map((m) => <li key={m.category} className="flex justify-between py-1.5"><span>{t(m.category)}</span><span className="font-medium">{m.avg_margin_pct}% <span className="text-xs text-muted-foreground">({m.versions})</span></span></li>)}</ul>
          </Section>
        )}

        {data.contract_value_by_customer && (
          <Section title={t('Signed contract value by customer')}>
            <ul className="divide-y text-sm">{data.contract_value_by_customer.map((c) => <li key={`${c.customer}-${c.currency}`} className="flex justify-between py-1.5"><span>{c.customer}</span><span className="font-medium">{c.value.toLocaleString(lang)} {c.currency}</span></li>)}</ul>
          </Section>
        )}
      </div>
    </>
  )
}
