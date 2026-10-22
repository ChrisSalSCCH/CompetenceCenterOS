import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { Pencil, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Avatar, EmptyState, ErrorBlock, ItemList, LoadingBlock, ModePill, PageHeader, Pill, ProgressBar, PriorityPill, Section, Stat, StatusPill } from '@/components/kit'
import { HistoryTimeline } from '@/components/HistoryTimeline'
import { CircleFormDialog, RoleFormDialog } from '@/components/StructureForms'
import { useSession } from '@/contexts/SessionContext'
import { fmtDate, fmtDateTime, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import type { CircleNode, GovMode, HistoryEntry, Item, RoleNode, Structure } from '@/lib/types'

interface CircleFull extends CircleNode {
  breadcrumb: { id: string; name: string }[]
  subcircles: CircleNode[]
  roles: RoleNode[]
  members: { user_id: string; name: string; avatar_color: string; roles: { id: string; name: string }[] }[]
  projects: { id: string; name: string; status: string; priority: string; due_date: string | null; owning_role_name: string | null }[]
  tasks: { id: string; title: string; status: string; priority: string; due_date: string | null; assignee_name: string | null }[]
  proposals: { id: string; title: string; status: string; workflow: string; created_at: string }[]
  meetings: { id: string; title: string; meeting_type: string; scheduled_at: string; status: string }[]
  history: HistoryEntry[]
  effective_mode: GovMode
  can_govern: boolean
}

interface Dashboard {
  stats: { roles: number; unfilled_roles: number; open_tasks: number; overdue_tasks: number; active_projects: number; open_tensions: number; open_proposals: number }
  objectives: { id: string; title: string; progress: number; circle_name: string; parent_id: string | null; key_results: { id: string; title: string; progress: number }[] }[]
  metrics: { id: string; name: string; unit: string; current_value: number; target_value: number; progress: number }[]
}

function Block({ title, items, empty }: Readonly<{ title: string; items: Item[]; empty: string }>) {
  return (
    <div>
      <div className="font-mono-label mb-2 text-muted-foreground">{title}</div>
      <ItemList items={items} empty={empty} />
    </div>
  )
}

export default function CircleDetail() {
  const { id } = useParams()
  const { t, lang } = useT()
  const navigate = useNavigate()
  const { isObserver } = useSession()
  const { data, isLoading, error } = useGet<CircleFull>(id ? `/circles/${id}` : null)
  const { data: dash } = useGet<Dashboard>(id ? `/circles/${id}/dashboard` : null)
  const { data: structure } = useGet<Structure>('/structure')
  const [circleDlg, setCircleDlg] = useState(false)
  const [roleDlg, setRoleDlg] = useState(false)
  const none = t('None defined')

  if (isLoading) return <LoadingBlock rows={6} />
  if (error || !data) return <ErrorBlock message={error?.message} />
  const circles = structure?.circles ?? []

  return (
    <>
      <PageHeader
        eyebrow={
          <span className="flex flex-wrap items-center gap-1">
            <Link to="/organization" className="hover:text-primary">{t('Organization')}</Link>
            {data.breadcrumb.slice(0, -1).map((b) => <span key={b.id}> / <Link to={`/organization/circles/${b.id}`} className="hover:text-primary">{b.name}</Link></span>)}
          </span>
        }
        title={data.name}
        subtitle={data.purpose}
        actions={
          <>
            <ModePill mode={data.effective_mode} />
            {!isObserver && <Button variant="outline" size="sm" onClick={() => setCircleDlg(true)}><Pencil className="mr-1 h-4 w-4" />{t('Edit')}</Button>}
            {!isObserver && <Button size="sm" onClick={() => setRoleDlg(true)}><Plus className="mr-1 h-4 w-4" />{t('New role')}</Button>}
          </>
        }
      />

      <Tabs defaultValue="overview" className="space-y-4">
        <TabsList className="h-auto flex-wrap">
          {['overview', 'roles', 'people', 'governance', 'work', 'meetings', 'history'].map((k) => (
            <TabsTrigger key={k} value={k}>{t({ overview: 'Overview', roles: 'Roles', people: 'People', governance: 'Governance', work: 'Work', meetings: 'Meetings', history: 'History' }[k] as string)}</TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="overview" className="space-y-4">
          {dash && (
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
              <Stat label={t('Roles')} value={dash.stats.roles} />
              <Stat label={t('Unfilled')} value={dash.stats.unfilled_roles} tone={dash.stats.unfilled_roles > 0 ? 'danger' : undefined} />
              <Stat label={t('Open tasks')} value={dash.stats.open_tasks} />
              <Stat label={t('Overdue')} value={dash.stats.overdue_tasks} tone={dash.stats.overdue_tasks > 0 ? 'danger' : undefined} />
              <Stat label={t('Projects')} value={dash.stats.active_projects} />
              <Stat label={t('Tensions')} value={dash.stats.open_tensions} />
              <Stat label={t('Proposals')} value={dash.stats.open_proposals} />
            </div>
          )}
          <div className="grid gap-4 lg:grid-cols-2">
            <Section title={t('About this circle')} index={1}>
              {data.description && <p className="mb-4 text-sm">{data.description}</p>}
              <div className="space-y-4">
                <Block title={t('Accountabilities')} items={data.accountabilities} empty={none} />
                <Block title={t('Domains')} items={data.domains} empty={none} />
                <Block title={t('Policies')} items={data.policies} empty={none} />
              </div>
            </Section>
            <div className="space-y-4">
              <Section title={t('Subcircles')} index={2}>
                {data.subcircles.length === 0 ? <EmptyState title={t('No subcircles')} /> : (
                  <div className="grid gap-2">
                    {data.subcircles.map((s) => (
                      <Link key={s.id} to={`/organization/circles/${s.id}`} className="paper-card interactive block p-3">
                        <div className="font-display text-base font-semibold">{s.name}</div>
                        <div className="line-clamp-2 text-xs text-muted-foreground">{s.purpose}</div>
                      </Link>
                    ))}
                  </div>
                )}
              </Section>
              <Section title={t('Goals & metrics')} index={3} action={<Link className="text-xs text-primary hover:underline" to="/goals">{t('Open')}</Link>}>
                {dash && dash.objectives.length === 0 && dash.metrics.length === 0 && <EmptyState title={t('No goals or KPIs yet')} />}
                <div className="space-y-3">
                  {dash?.objectives.slice(0, 3).map((o) => (
                    <div key={o.id}>
                      <div className="mb-1 text-sm font-medium">{o.title}</div>
                      <ProgressBar value={o.progress} tone="forest" />
                    </div>
                  ))}
                  {dash?.metrics.slice(0, 3).map((m) => (
                    <div key={m.id}>
                      <div className="mb-1 flex justify-between text-sm"><span>{m.name}</span><span className="font-mono text-xs text-muted-foreground">{m.current_value} / {m.target_value} {m.unit}</span></div>
                      <ProgressBar value={m.progress} tone="ochre" />
                    </div>
                  ))}
                </div>
              </Section>
            </div>
          </div>
        </TabsContent>

        <TabsContent value="roles">
          {data.roles.length === 0 ? <EmptyState title={t('No roles in this circle yet')} action={!isObserver ? <Button size="sm" onClick={() => setRoleDlg(true)}>{t('New role')}</Button> : undefined} /> : (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {data.roles.map((r, i) => (
                <Link key={r.id} to={`/organization/roles/${r.id}`} className="paper-card interactive reveal block p-4" style={{ ['--i' as string]: i }}>
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="font-display text-lg font-semibold leading-tight">{r.name}</h3>
                    {r.can_govern && <Pill tone="ink">{t('Governance')}</Pill>}
                  </div>
                  <p className="mt-1 line-clamp-3 text-sm text-muted-foreground">{r.purpose}</p>
                  <div className="mt-3 flex items-center gap-1">
                    {r.holders.length === 0 ? <Pill tone="ochre">{t('unfilled')}</Pill> : r.holders.map((h) => <Avatar key={h.assignment_id} name={h.name} color={h.avatar_color} size={26} />)}
                    <span className="ml-1 text-xs text-muted-foreground">{r.holders.map((h) => h.name).join(', ')}</span>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="people">
          <Section title={t('Members derived from role assignments')}>
            {data.members.length === 0 ? <EmptyState title={t('Nobody holds a role in this circle yet')} /> : (
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {data.members.map((m) => (
                  <Link key={m.user_id} to={`/people/${m.user_id}`} className="paper-card interactive flex items-center gap-3 p-3">
                    <Avatar name={m.name} color={m.avatar_color} size={38} />
                    <div>
                      <div className="text-sm font-medium">{m.name}</div>
                      <div className="text-xs text-muted-foreground">{m.roles.map((r) => r.name).join(' · ')}</div>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </Section>
        </TabsContent>

        <TabsContent value="governance" className="space-y-4">
          <Section title={t('Governance workflow')} action={<Button size="sm" onClick={() => navigate(`/governance/proposals/new?circle=${data.id}`)}><Plus className="mr-1 h-4 w-4" />{t('New proposal')}</Button>}>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <ModePill mode={data.effective_mode} />
              <span className="text-muted-foreground">{data.governance_mode ? t('Set on this circle') : t('Inherited from a parent circle or the organization default')}</span>
              {data.can_govern && <Pill tone="forest">{t('You hold governance authority here')}</Pill>}
            </div>
          </Section>
          <Section title={t('Proposals')}>
            {data.proposals.length === 0 ? <EmptyState title={t('No proposals for this circle')} /> : (
              <ul className="divide-y">
                {data.proposals.map((p) => (
                  <li key={p.id}>
                    <Link to={`/governance/proposals/${p.id}`} className="flex items-center justify-between gap-2 py-2.5 hover:text-primary">
                      <span className="text-sm font-medium">{p.title}</span>
                      <span className="flex items-center gap-2"><Pill>{p.workflow}</Pill><StatusPill status={p.status} /></span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Section>
        </TabsContent>

        <TabsContent value="work" className="space-y-4">
          <Section title={t('Current projects')} action={<Link className="text-xs text-primary hover:underline" to={`/work?circle=${data.id}&tab=projects`}>{t('Open')}</Link>}>
            {data.projects.length === 0 ? <EmptyState title={t('No active projects')} /> : (
              <ul className="divide-y">
                {data.projects.map((p) => (
                  <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
                    <div><div className="text-sm font-medium">{p.name}</div><div className="text-xs text-muted-foreground">{p.owning_role_name ?? '–'} · {t('due')} {fmtDate(p.due_date, lang)}</div></div>
                    <span className="flex gap-2"><PriorityPill priority={p.priority} /><StatusPill status={p.status} /></span>
                  </li>
                ))}
              </ul>
            )}
          </Section>
          <Section title={t('Open tasks')}>
            {data.tasks.length === 0 ? <EmptyState title={t('No open tasks')} /> : (
              <ul className="divide-y">
                {data.tasks.map((x) => (
                  <li key={x.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                    <div><div className="text-sm">{x.title}</div><div className="text-xs text-muted-foreground">{x.assignee_name ?? t('unassigned')} · {fmtDate(x.due_date, lang)}</div></div>
                    <StatusPill status={x.status} />
                  </li>
                ))}
              </ul>
            )}
          </Section>
        </TabsContent>

        <TabsContent value="meetings">
          <Section title={t('Meetings')} action={!isObserver ? <Button size="sm" onClick={() => navigate(`/meetings?new=${data.id}`)}><Plus className="mr-1 h-4 w-4" />{t('Schedule meeting')}</Button> : undefined}>
            {data.meetings.length === 0 ? <EmptyState title={t('No meetings yet')} /> : (
              <ul className="divide-y">
                {data.meetings.map((m) => (
                  <li key={m.id}>
                    <Link to={`/meetings/${m.id}`} className="flex items-center justify-between gap-2 py-2.5 hover:text-primary">
                      <span><span className="text-sm font-medium">{m.title}</span><span className="block text-xs text-muted-foreground">{fmtDateTime(m.scheduled_at, lang)} · {m.meeting_type}</span></span>
                      <StatusPill status={m.status} />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Section>
        </TabsContent>

        <TabsContent value="history">
          <Section title={t('Governance history')}>
            <HistoryTimeline entries={data.history} showEntity />
          </Section>
        </TabsContent>
      </Tabs>

      <CircleFormDialog open={circleDlg} onOpenChange={setCircleDlg} circles={circles} circle={circles.find((c) => c.id === data.id)} />
      <RoleFormDialog open={roleDlg} onOpenChange={setRoleDlg} circles={circles} circleId={data.id} />
    </>
  )
}
