import { Link, useParams } from 'react-router'
import { Avatar, EmptyState, ErrorBlock, LoadingBlock, PageHeader, Pill, PriorityPill, Section, StatusPill } from '@/components/kit'
import { fmtDate, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'

interface PersonFull {
  id: string
  name: string
  email: string
  job_title: string | null
  skills: string[]
  availability: string | null
  avatar_color: string
  access_level: string
  roles: { role_id: string; role_name: string; purpose: string; circle_id: string; circle_name: string; focus: string | null }[]
  circles: { id: string; name: string; roles: string[] }[]
  tasks: { id: string; title: string; status: string; priority: string; due_date: string | null; is_overdue: boolean; project_name: string | null }[]
  projects: { id: string; name: string; status: string }[]
}

export default function PersonDetail() {
  const { id } = useParams()
  const { t, lang } = useT()
  const { data, isLoading, error } = useGet<PersonFull>(id ? `/people/${id}` : null)
  if (isLoading) return <LoadingBlock rows={5} />
  if (error || !data) return <ErrorBlock message={error?.message} />
  return (
    <>
      <PageHeader
        eyebrow={<Link to="/people" className="hover:text-primary">{t('People')}</Link>}
        title={
          <span className="flex items-center gap-4"><Avatar name={data.name} color={data.avatar_color} size={56} />{data.name}</span>
        }
        subtitle={`${data.job_title ?? ''} · ${data.email}`}
        actions={<>{data.availability && <Pill>{data.availability}</Pill>}{data.skills.map((s) => <Pill key={s} tone="forest">{s}</Pill>)}</>}
      />
      <div className="grid gap-4 lg:grid-cols-3">
        <Section title={t('Roles held')} index={1} className="lg:col-span-2">
          {data.roles.length === 0 ? <EmptyState title={t('No roles')} /> : (
            <div className="grid gap-3 md:grid-cols-2">
              {data.roles.map((r) => (
                <Link key={r.role_id} to={`/organization/roles/${r.role_id}`} className="paper-card interactive block p-3">
                  <div className="font-display text-base font-semibold">{r.role_name}</div>
                  <div className="text-xs text-muted-foreground">{r.circle_name}{r.focus ? ` · ${r.focus}` : ''}</div>
                  <p className="mt-1 line-clamp-2 text-sm">{r.purpose}</p>
                </Link>
              ))}
            </div>
          )}
        </Section>
        <Section title={t('Circles')} index={2}>
          <ul className="space-y-2">
            {data.circles.map((c) => (
              <li key={c.id}><Link to={`/organization/circles/${c.id}`} className="block text-sm hover:text-primary"><span className="font-medium">{c.name}</span><span className="block text-xs text-muted-foreground">{c.roles.join(' · ')}</span></Link></li>
            ))}
            {data.circles.length === 0 && <li className="text-sm text-muted-foreground">{t('Not a member of any circle')}</li>}
          </ul>
        </Section>
        <Section title={t('Open tasks')} index={3} className="lg:col-span-2">
          {data.tasks.length === 0 ? <EmptyState title={t('No open tasks')} /> : (
            <ul className="divide-y">
              {data.tasks.map((x) => (
                <li key={x.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <div><div className="text-sm">{x.title}</div><div className="text-xs text-muted-foreground">{x.project_name ?? '–'} · {fmtDate(x.due_date, lang)}</div></div>
                  <span className="flex items-center gap-2">{x.is_overdue && <Pill tone="danger">{t('overdue')}</Pill>}<PriorityPill priority={x.priority} /><StatusPill status={x.status} /></span>
                </li>
              ))}
            </ul>
          )}
        </Section>
        <Section title={t('Current projects')} index={4}>
          {data.projects.length === 0 ? <p className="text-sm text-muted-foreground">{t('No active projects')}</p> : (
            <ul className="space-y-2">{data.projects.map((p) => <li key={p.id} className="flex items-center justify-between text-sm"><span>{p.name}</span><StatusPill status={p.status} /></li>)}</ul>
          )}
        </Section>
      </div>
    </>
  )
}
