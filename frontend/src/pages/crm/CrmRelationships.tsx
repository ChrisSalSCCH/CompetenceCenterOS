import { Link } from 'react-router'
import { EmptyState, ErrorBlock, LoadingBlock, PageHeader, Pill, Section } from '@/components/kit'
import { useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import { daysSince } from '@/lib/portfolio'
import type { CrmOrgRow, RoleScope } from '@/lib/portfolio-types'

export default function CrmRelationships() {
  const { t } = useT()
  const { data, isLoading, error } = useGet<CrmOrgRow[]>('/crm/organizations', { relation: 'customer', status: 'active' })
  const { data: scopes } = useGet<RoleScope[]>('/crm/role-scopes')

  const rows = (data ?? [])
    .map((o) => ({ o, days: daysSince(o.last_activity_at) }))
    .sort((a, b) => (b.days ?? Number.MAX_SAFE_INTEGER) - (a.days ?? Number.MAX_SAFE_INTEGER))

  return (
    <>
      <PageHeader title={t('Customer Relationships')} subtitle={`${t('Customers needing attention')}. ${t('Sorted by time since last contact.')}`} />
      {isLoading && <LoadingBlock />}
      {error && <ErrorBlock message={error.message} />}
      {data && rows.length === 0 && <EmptyState title={t('Nothing found.')} />}
      <div className="grid gap-3 md:grid-cols-2">
        {rows.map(({ o, days }, i) => {
          const keyAccounts = (scopes ?? []).filter((s) => s.crm_org_id === o.id)
          const stale = days === null || days > 90
          return (
            <Link key={o.id} to={`/crm/organizations/${o.id}`} className="paper-card interactive reveal block p-4" style={{ ['--i' as string]: i }}>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="font-display text-lg font-semibold leading-tight">{o.name}</div>
                  <div className="text-xs text-muted-foreground">{o.industry ?? '–'} · {o.owner_name ?? t('Customers without owner')}</div>
                </div>
                <Pill tone={stale ? 'danger' : 'forest'}>{days === null ? t('No contact yet') : `${days} ${t('Days since last contact')}`}</Pill>
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <span>{o.project_count} {t('Projects')}</span>
                <span>{o.contact_count} {t('Contacts')}</span>
                {keyAccounts.length > 0 && <span>{t('Key accounts')}: {keyAccounts.map((k) => k.user_name).join(', ')}</span>}
              </div>
            </Link>
          )
        })}
      </div>
    </>
  )
}
