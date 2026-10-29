import { Link } from 'react-router'
import { ExportMenu } from '@/components/management/ExportMenu'
import { EmptyState, ErrorBlock, InfoNotice, LoadingBlock, PageHeader, Section } from '@/components/kit'
import { useSession } from '@/contexts/SessionContext'
import { useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import { fmtMoney } from '@/lib/sales'
import { monthLabel } from '@/lib/management'
import type { ForecastData } from '@/lib/management-types'

const CATEGORY_ORDER = ['secured', 'weighted', 'planned', 'hypothetical']

export default function Forecast() {
  const { t, lang } = useT()
  const { isObserver } = useSession()
  const { data, isLoading, error } = useGet<ForecastData>(isObserver ? null : '/management/forecast')

  if (isObserver) {
    return (
      <>
        <PageHeader title={t('Revenue forecast')} />
        <InfoNotice>{t('Read-only observers do not see monetary values.')}</InfoNotice>
      </>
    )
  }
  if (isLoading) return <LoadingBlock />
  if (error || !data) return <ErrorBlock message={error?.message} />
  const currencies = Object.entries(data.currencies)

  return (
    <>
      <PageHeader
        eyebrow={t('Management')}
        title={t('Revenue forecast')}
        subtitle={t('Secured, weighted, planned and hypothetical revenue per currency and month. Currencies are never converted or added.')}
        actions={<ExportMenu sets={['opportunities', 'contracts']} />}
      />
      {data.secured_hidden && <div className="mb-4"><InfoNotice>{t('Secured revenue comes from contract conditions and is hidden without signing rights.')}</InfoNotice></div>}
      {currencies.length === 0 && <EmptyState title={t('No forecast data yet')} hint={t('Add values and decision dates to opportunities.')} action={<Link className="text-sm text-primary hover:underline" to="/sales">{t('Open pipeline')}</Link>} />}
      <div className="space-y-4">
        {currencies.map(([cur, info]) => (
          <Section key={cur} title={cur}>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-sm">
                <thead>
                  <tr className="border-b text-left text-xs text-muted-foreground">
                    <th className="py-2">{t('Category')}</th>
                    {data.months.map((m) => <th key={m} className="py-2 text-right">{monthLabel(m, lang)}</th>)}
                    <th className="py-2 text-right">{t('Total')}</th>
                  </tr>
                </thead>
                <tbody>
                  {CATEGORY_ORDER.filter((c) => info.categories[c]).map((c) => (
                    <tr key={c} className="border-b last:border-0">
                      <th scope="row" className="py-2 text-left font-medium">{t(c)}</th>
                      {data.months.map((m) => <td key={m} className="py-2 text-right tabular-nums">{info.categories[c][m] ? fmtMoney(info.categories[c][m], cur, lang) : '–'}</td>)}
                      <td className="py-2 text-right font-semibold tabular-nums">{fmtMoney(info.totals[c] ?? 0, cur, lang)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>
        ))}
      </div>
      <Section title={t('Assumptions')} className="mt-4">
        <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
          {data.assumptions.map((a) => <li key={a}>{t(a)}</li>)}
        </ul>
        <p className="mt-2 text-xs text-muted-foreground">{data.sources.opportunities} {t('opportunities')}, {data.sources.milestones} {t('payment milestones')}</p>
      </Section>
    </>
  )
}
