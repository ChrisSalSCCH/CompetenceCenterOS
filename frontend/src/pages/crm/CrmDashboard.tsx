import { Link } from 'react-router'
import { ErrorBlock, LoadingBlock, PageHeader, Pill, Section, Stat } from '@/components/kit'
import { fmtDateTime, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import type { CrmDashboard as CrmDashboardData } from '@/lib/portfolio-types'

const PLANNED = [
  { to: '/crm/opportunities', label: 'Opportunities', hint: 'Pipeline with stages, values and forecast' },
  { to: '/crm/quotes', label: 'Quotes', hint: 'Quotes with line items, versions and approvals' },
  { to: '/crm/contracts', label: 'NDAs & Contracts', hint: 'NDAs and contracts with validity dates and reminders' },
]

export default function CrmDashboard() {
  const { t, lang } = useT()
  const { data, isLoading, error } = useGet<CrmDashboardData>('/crm/dashboard')
  if (isLoading) return <LoadingBlock rows={5} />
  if (error || !data) return <ErrorBlock message={error?.message} />

  return (
    <>
      <PageHeader title={t('CRM')} subtitle={t('Customer relationship overview')} />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label={t('Active customers')} value={data.active_customers} tone="primary" />
        <Stat label={t('Prospects')} value={data.prospects} />
        <Stat label={t('Partners')} value={data.partners} />
        <Stat label={t('Customer projects')} value={data.active_customer_projects} />
        <Stat label={t('Contacts')} value={data.contacts} />
        <Stat label={t('Open follow-ups')} value={data.open_follow_ups} hint={data.overdue_follow_ups > 0 ? `${data.overdue_follow_ups} ${t('Overdue')}` : undefined} tone={data.overdue_follow_ups > 0 ? 'danger' : undefined} />
        <Stat label={t('No contact for 90+ days')} value={data.customers_without_recent_activity} tone={data.customers_without_recent_activity > 0 ? 'danger' : undefined} />
        <Stat label={t('Customers without owner')} value={data.without_owner} />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Section title={t('Recent activities')} className="lg:col-span-2" index={1}>
          {data.recent_activities.length === 0 && <p className="text-sm italic text-muted-foreground">{t('No activities yet')}</p>}
          <ul className="divide-y">
            {data.recent_activities.map((a) => (
              <li key={a.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                <Pill>{t(a.kind)}</Pill>
                <span className="font-medium">{a.subject}</span>
                {a.crm_org_id && <Link to={`/crm/organizations/${a.crm_org_id}`} className="text-primary hover:underline">{a.org_name}</Link>}
                <span className="ml-auto text-xs text-muted-foreground">{fmtDateTime(a.occurred_at, lang)}</span>
              </li>
            ))}
          </ul>
        </Section>
        <div className="space-y-4">
          <Section title={t('Customers without owner')} index={2}>
            {data.customers_without_owner.length === 0 ? <p className="text-sm italic text-muted-foreground">–</p> : (
              <ul className="space-y-1">
                {data.customers_without_owner.map((c) => <li key={c.id}><Link to={`/crm/organizations/${c.id}`} className="text-sm hover:text-primary">{c.name}</Link></li>)}
              </ul>
            )}
          </Section>
          <Section title={t('Coming in a later phase')} index={3}>
            <ul className="space-y-2">
              {PLANNED.map((p) => (
                <li key={p.to}>
                  <Link to={p.to} className="flex items-center justify-between gap-2 rounded-lg border border-dashed p-2 text-sm hover:border-primary">
                    <span>{t(p.label)}</span><Pill tone="ochre">{t('Planned')}</Pill>
                  </Link>
                </li>
              ))}
            </ul>
          </Section>
        </div>
      </div>
    </>
  )
}
