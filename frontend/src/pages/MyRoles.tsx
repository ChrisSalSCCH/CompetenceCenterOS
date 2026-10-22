import { Link } from 'react-router'
import { EmptyState, ErrorBlock, ItemList, LoadingBlock, PageHeader, Pill, Section, StatusPill } from '@/components/kit'
import { fmtDate, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import type { Item } from '@/lib/types'

interface MyRole {
  id: string
  name: string
  purpose: string
  circle_id: string
  circle_name: string
  can_govern: boolean
  focus: string | null
  accountabilities: Item[]
  domains: Item[]
  authorities: Item[]
  co_holders: string[]
  tasks: { id: string; title: string; status: string; due_date: string | null; is_overdue: boolean }[]
  projects: { id: string; name: string; status: string }[]
  metrics: { id: string; name: string; unit: string; target_value: number; current_value: number }[]
}

export default function MyRoles() {
  const { t, lang } = useT()
  const { data, isLoading, error } = useGet<MyRole[]>('/my-roles')
  return (
    <>
      <PageHeader title={t('My Roles')} subtitle={t('Everything you are accountable for, in one place.')} />
      {isLoading && <LoadingBlock rows={3} />}
      {error && <ErrorBlock message={error.message} />}
      {data && data.length === 0 && <EmptyState title={t('You do not hold a role yet')} hint={t('A governance role holder or an administrator can assign roles to you.')} />}
      <div className="space-y-5">
        {data?.map((r, i) => (
          <Section key={r.id} index={i} title={<Link to={`/organization/roles/${r.id}`} className="hover:text-primary">{r.name}</Link>} action={<span className="flex items-center gap-2">{r.can_govern && <Pill tone="ink">{t('Governance')}</Pill>}<Link to={`/organization/circles/${r.circle_id}`} className="text-xs text-muted-foreground hover:text-primary">{r.circle_name}</Link></span>}>
            <p className="mb-4 font-display text-lg leading-snug">{r.purpose}</p>
            {r.focus && <p className="mb-3 text-xs text-muted-foreground">{t('Your focus')}: {r.focus}</p>}
            {r.co_holders.length > 0 && <p className="mb-3 text-xs text-muted-foreground">{t('Shared with')}: {r.co_holders.join(', ')}</p>}
            <div className="grid gap-5 md:grid-cols-3">
              <div><div className="font-mono-label mb-2 text-muted-foreground">{t('Accountabilities')}</div><ItemList items={r.accountabilities} empty={t('None defined')} /></div>
              <div><div className="font-mono-label mb-2 text-muted-foreground">{t('Domains')}</div><ItemList items={r.domains} empty={t('None defined')} /></div>
              <div><div className="font-mono-label mb-2 text-muted-foreground">{t('Decision authorities')}</div><ItemList items={r.authorities} empty={t('None defined')} /></div>
            </div>
            {(r.tasks.length > 0 || r.projects.length > 0 || r.metrics.length > 0) && (
              <div className="mt-5 grid gap-4 border-t pt-4 md:grid-cols-3">
                <div>
                  <div className="font-mono-label mb-2 text-muted-foreground">{t('Open tasks')}</div>
                  <ul className="space-y-1 text-sm">{r.tasks.map((x) => <li key={x.id} className="flex justify-between gap-2"><span className="truncate">{x.title}</span><span className={x.is_overdue ? 'text-destructive' : 'text-muted-foreground'}>{fmtDate(x.due_date, lang)}</span></li>)}</ul>
                </div>
                <div>
                  <div className="font-mono-label mb-2 text-muted-foreground">{t('Projects')}</div>
                  <ul className="space-y-1 text-sm">{r.projects.map((p) => <li key={p.id} className="flex justify-between gap-2"><span>{p.name}</span><StatusPill status={p.status} /></li>)}</ul>
                </div>
                <div>
                  <div className="font-mono-label mb-2 text-muted-foreground">{t('KPIs')}</div>
                  <ul className="space-y-1 text-sm">{r.metrics.map((m) => <li key={m.id} className="flex justify-between gap-2"><span>{m.name}</span><span className="font-mono text-xs">{m.current_value}/{m.target_value} {m.unit}</span></li>)}</ul>
                </div>
              </div>
            )}
          </Section>
        ))}
      </div>
    </>
  )
}
