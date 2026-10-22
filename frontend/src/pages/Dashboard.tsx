import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import { AlertTriangle, ArrowRight, CalendarDays, Plus, Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { EmptyState, ErrorBlock, LoadingBlock, PageHeader, Pill, PriorityPill, Section, Stat, StatusPill } from '@/components/kit'
import { TensionDialog } from '@/components/TensionDialog'
import { useSession } from '@/contexts/SessionContext'
import { fmtDate, fmtDateTime, useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import type { HeldRole, HistoryEntry } from '@/lib/types'

interface DashboardData {
  roles: (HeldRole & { purpose: string })[]
  tasks: { id: string; title: string; status: string; priority: string; due_date: string | null; is_overdue: boolean; project_name: string | null; role_name: string | null }[]
  meetings: { id: string; title: string; meeting_type: string; scheduled_at: string; status: string; circle_name: string }[]
  tensions: { id: string; title: string; priority: string; status: string; circle_name: string | null }[]
  proposals: { id: string; title: string; status: string; workflow: string; circle_name: string; action: 'decide' | 'finish_draft' | 'follow' }[]
  circle_updates: HistoryEntry[]
  counts: { open_tasks: number; overdue_tasks: number }
}

export default function Dashboard() {
  const { t, lang } = useT()
  const { session, isObserver } = useSession()
  const navigate = useNavigate()
  const act = useAct()
  const { data, isLoading, error } = useGet<DashboardData>('/dashboard')
  const [question, setQuestion] = useState('')
  const [tensionOpen, setTensionOpen] = useState(false)

  const ask = (e: FormEvent) => {
    e.preventDefault()
    if (question.trim().length > 1) navigate(`/assistant?q=${encodeURIComponent(question.trim())}`)
  }
  const firstName = session?.user.name.split(' ')[0]
  const hour = new Date().getHours()
  let greeting = t('Good evening')
  if (hour < 12) greeting = t('Good morning')
  else if (hour < 18) greeting = t('Good afternoon')

  return (
    <>
      <PageHeader eyebrow={new Date().toLocaleDateString(lang === 'de' ? 'de-AT' : 'en-GB', { weekday: 'long', day: 'numeric', month: 'long' })} title={`${greeting}, ${firstName}`} subtitle={t('What requires your attention today?')} />

      <form onSubmit={ask} className="reveal paper-card mb-6 flex items-center gap-3 p-2 pl-4" style={{ ['--i' as string]: 1 }}>
        <Sparkles className="h-5 w-5 shrink-0 text-primary" aria-hidden />
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          className="h-11 flex-1 bg-transparent text-base placeholder:text-muted-foreground focus:outline-none"
          placeholder={t('Ask anything about your organization...')}
          aria-label={t('Ask anything about your organization...')}
        />
        <Button type="submit" className="rounded-xl">{t('Ask')}<ArrowRight className="ml-1 h-4 w-4" /></Button>
      </form>

      {isLoading && <LoadingBlock rows={4} />}
      {error && <ErrorBlock message={error.message} />}
      {data && (
        <>
          <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label={t('My roles')} value={data.roles.length} />
            <Stat label={t('Open tasks')} value={data.counts.open_tasks} />
            <Stat label={t('Overdue')} value={data.counts.overdue_tasks} tone={data.counts.overdue_tasks > 0 ? 'danger' : undefined} />
            <Stat label={t('Needs my decision')} value={data.proposals.filter((p) => p.action === 'decide').length} tone="primary" />
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Section title={t('My tasks')} index={2} className="lg:col-span-2" action={<Link className="text-xs text-primary hover:underline" to="/work?scope=mine">{t('All tasks')}</Link>}>
              {data.tasks.length === 0 ? <EmptyState title={t('No open tasks')} hint={t('Enjoy the calm - or capture a tension.')} /> : (
                <ul className="divide-y">
                  {data.tasks.slice(0, 8).map((x) => (
                    <li key={x.id} className="flex items-center gap-3 py-2.5">
                      <Checkbox
                        aria-label={`${t('Mark done')}: ${x.title}`}
                        disabled={isObserver}
                        onCheckedChange={() => act('patch', `/tasks/${x.id}`, { status: 'done' })}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium">{x.title}</div>
                        <div className="truncate text-xs text-muted-foreground">{[x.project_name, x.role_name].filter(Boolean).join(' · ') || '–'}</div>
                      </div>
                      {x.is_overdue && <Pill tone="danger"><AlertTriangle className="h-3 w-3" />{t('overdue')}</Pill>}
                      <span className="hidden text-xs text-muted-foreground sm:block">{fmtDate(x.due_date, lang)}</span>
                      <PriorityPill priority={x.priority} />
                    </li>
                  ))}
                </ul>
              )}
            </Section>

            <Section title={t('Needs action: governance')} index={3}>
              {data.proposals.length === 0 ? <EmptyState title={t('Nothing waiting for you')} /> : (
                <ul className="space-y-2">
                  {data.proposals.map((p) => (
                    <li key={p.id}>
                      <Link to={`/governance/proposals/${p.id}`} className="paper-card interactive block p-3">
                        <div className="text-sm font-medium leading-snug">{p.title}</div>
                        <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                          {p.circle_name}
                          <StatusPill status={p.status} />
                          {p.action === 'decide' && <Pill tone="primary">{t('your decision')}</Pill>}
                          {p.action === 'finish_draft' && <Pill tone="ochre">{t('finish your draft')}</Pill>}
                        </div>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Section>

            <Section title={t('My roles')} index={4} action={<Link className="text-xs text-primary hover:underline" to="/my-roles">{t('Details')}</Link>}>
              {data.roles.length === 0 ? <EmptyState title={t('You do not hold a role yet')} /> : (
                <ul className="space-y-2">
                  {data.roles.map((r) => (
                    <li key={r.role_id}>
                      <Link to={`/organization/roles/${r.role_id}`} className="flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 hover:bg-muted">
                        <span><span className="block text-sm font-medium">{r.role_name}</span><span className="block text-xs text-muted-foreground">{r.circle_name}</span></span>
                        {r.can_govern && <Pill tone="ink">{t('Governance')}</Pill>}
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Section>

            <Section title={t('Upcoming meetings')} index={5}>
              {data.meetings.length === 0 ? <EmptyState title={t('No upcoming meetings')} /> : (
                <ul className="space-y-2">
                  {data.meetings.map((m) => (
                    <li key={m.id}>
                      <Link to={`/meetings/${m.id}`} className="flex items-start gap-3 rounded-lg px-2 py-1.5 hover:bg-muted">
                        <CalendarDays className="mt-0.5 h-4 w-4 text-primary" aria-hidden />
                        <span><span className="block text-sm font-medium">{m.title}</span><span className="block text-xs text-muted-foreground">{fmtDateTime(m.scheduled_at, lang)} · {m.circle_name}</span></span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Section>

            <Section title={t('My open tensions')} index={6} action={!isObserver ? <Button size="sm" variant="outline" onClick={() => setTensionOpen(true)}><Plus className="mr-1 h-4 w-4" />{t('Capture')}</Button> : undefined}>
              {data.tensions.length === 0 ? <EmptyState title={t('No open tensions')} hint={t('Noticing a gap? Capture it - it takes ten seconds.')} /> : (
                <ul className="space-y-2">
                  {data.tensions.map((x) => (
                    <li key={x.id} className="flex items-center justify-between gap-2 text-sm">
                      <span className="truncate">{x.title}</span><PriorityPill priority={x.priority} />
                    </li>
                  ))}
                  <li><Link to="/governance?tab=tensions" className="text-xs text-primary hover:underline">{t('Process tensions')}</Link></li>
                </ul>
              )}
            </Section>

            <Section title={t('Circle updates')} index={7} className="lg:col-span-3">
              {data.circle_updates.length === 0 ? <EmptyState title={t('No recent changes in your circles')} /> : (
                <ul className="grid gap-2 md:grid-cols-2">
                  {data.circle_updates.map((u) => (
                    <li key={u.id} className="rounded-lg border p-3 text-sm">
                      <div className="font-medium">{u.summary}</div>
                      <div className="text-xs text-muted-foreground">{fmtDate(u.created_at, lang)} · {u.actor_name}</div>
                    </li>
                  ))}
                </ul>
              )}
            </Section>
          </div>
        </>
      )}
      <TensionDialog open={tensionOpen} onOpenChange={setTensionOpen} />
    </>
  )
}
