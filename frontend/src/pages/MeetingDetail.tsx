import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { ArrowLeft, ArrowRight, Check, Flag, Play, Plus, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Checkbox } from '@/components/ui/checkbox'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ErrorBlock, LoadingBlock, PageHeader, Pill, ProgressBar, Section, StatusPill, Avatar } from '@/components/kit'
import { TensionConvertDialog, type ConvertTarget } from '@/components/TensionConvert'
import { useSession } from '@/contexts/SessionContext'
import { fmtDate, fmtDateTime, useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'

interface AgendaItem {
  id: string
  position: number
  title: string
  kind: string
  notes: string
  outcome: string
  status: 'pending' | 'done'
  tension_id: string | null
  tension_title: string | null
  tension_description: string | null
  tension_creator: string | null
  tension_priority: string | null
  project_name: string | null
}

interface MeetingFull {
  id: string
  title: string
  meeting_type: string
  scheduled_at: string
  duration_min: number
  status: string
  circle_id: string
  circle_name: string
  facilitator_name: string | null
  current_step: number
  checkin_notes: string
  notes: string
  participants: { user_id: string; name: string; attended: boolean; avatar_color: string }[]
  agenda: AgendaItem[]
  decisions: { id: string; title: string; rationale: string; decided_by_name: string | null }[]
  tasks: { id: string; title: string; status: string; due_date: string | null; assignee_name: string | null }[]
  proposals: { id: string; title: string; status: string }[]
  metrics: { id: string; name: string; unit: string; target_value: number; current_value: number; direction: string }[]
  projects: { id: string; name: string; status: string; due_date: string | null }[]
  open_tensions: { id: string; title: string; priority: string }[]
  can_run: boolean
}

function stepClass(current: boolean, done: boolean): string {
  if (current) return 'border-primary bg-primary text-primary-foreground'
  return done ? 'border-[hsl(var(--forest)/0.4)] bg-[hsl(var(--forest)/0.1)]' : 'hover:bg-muted'
}

function QuickTask({ meetingId, circleId }: Readonly<{ meetingId: string; circleId: string }>) {
  const { t } = useT()
  const act = useAct()
  const [title, setTitle] = useState('')
  const { data: people } = useGet<{ id: string; name: string }[]>('/people')
  const [who, setWho] = useState('')
  const add = async () => {
    const res = await act('post', '/tasks', { title: title.trim(), meeting_id: meetingId, circle_id: circleId, assignee_id: who || undefined })
    if (res) setTitle('')
  }
  return (
    <div className="flex flex-wrap gap-2">
      <Input className="min-w-48 flex-1" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} placeholder={t('New follow-up task')} aria-label={t('New follow-up task')} onKeyDown={(e) => { if (e.key === 'Enter' && title.trim().length > 1) add() }} />
      <Select value={who} onValueChange={setWho}>
        <SelectTrigger className="w-44" aria-label={t('Assignee')}><SelectValue placeholder={t('Assignee')} /></SelectTrigger>
        <SelectContent>{(people ?? []).map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}</SelectContent>
      </Select>
      <Button onClick={add} disabled={title.trim().length < 2}><Plus className="mr-1 h-4 w-4" />{t('Add task')}</Button>
    </div>
  )
}

function QuickDecision({ meetingId }: Readonly<{ meetingId: string }>) {
  const { t } = useT()
  const act = useAct()
  const [title, setTitle] = useState('')
  const add = async () => {
    const res = await act('post', `/meetings/${meetingId}/decisions`, { title: title.trim() })
    if (res) setTitle('')
  }
  return (
    <div className="flex gap-2">
      <Input value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} placeholder={t('Record a decision')} aria-label={t('Record a decision')} onKeyDown={(e) => { if (e.key === 'Enter' && title.trim().length > 2) add() }} />
      <Button variant="outline" onClick={add} disabled={title.trim().length < 3}>{t('Record')}</Button>
    </div>
  )
}

function NotesField({ item }: Readonly<{ item: AgendaItem }>) {
  const { t } = useT()
  const act = useAct()
  const [notes, setNotes] = useState(item.notes)
  const [outcome, setOutcome] = useState(item.outcome)
  useEffect(() => { setNotes(item.notes); setOutcome(item.outcome) }, [item.id, item.notes, item.outcome])
  const save = () => {
    if (notes !== item.notes || outcome !== item.outcome) act('patch', `/agenda/${item.id}`, { notes, outcome })
  }
  return (
    <div className="grid gap-3">
      <Textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} onBlur={save} placeholder={t('Notes')} aria-label={t('Notes')} />
      <Textarea rows={2} value={outcome} onChange={(e) => setOutcome(e.target.value)} onBlur={save} placeholder={t('Outcome')} aria-label={t('Outcome')} />
    </div>
  )
}

function FacilitatorMode({ m, onExit }: Readonly<{ m: MeetingFull; onExit: () => void }>) {
  const { t } = useT()
  const act = useAct()
  const [convert, setConvert] = useState<ConvertTarget | null>(null)
  const step = Math.min(m.current_step, Math.max(m.agenda.length - 1, 0))
  const item = m.agenda[step]
  const go = (n: number) => act('post', `/meetings/${m.id}/step`, { step: Math.max(0, Math.min(m.agenda.length - 1, n)) })
  const finish = async () => {
    const res = await act('post', `/meetings/${m.id}/finish`)
    if (res) onExit()
  }
  if (!item) return null
  const isLast = step === m.agenda.length - 1

  return (
    <div className="fixed inset-0 z-40 flex flex-col overflow-y-auto bg-background" role="dialog" aria-label={t('Facilitator mode')}>
      <div className="flex items-center gap-3 border-b bg-sidebar px-4 py-3 text-sidebar-foreground md:px-8">
        <span className="font-display text-lg font-semibold">{m.title}</span>
        <Pill tone="ochre">{t('Facilitator mode')}</Pill>
        <Button variant="ghost" size="sm" className="ml-auto text-sidebar-foreground hover:bg-sidebar-accent" onClick={onExit}><X className="mr-1 h-4 w-4" />{t('Leave focus view')}</Button>
      </div>
      <div className="mx-auto w-full max-w-4xl flex-1 px-4 py-6 md:px-8">
        <ol className="mb-6 flex flex-wrap gap-1.5" aria-label={t('Agenda')}>
          {m.agenda.map((a, i) => (
            <li key={a.id}>
              <button type="button" onClick={() => go(i)} className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${stepClass(i === step, a.status === 'done')}`}>
                {i + 1}. {a.kind === 'tension' && a.tension_id ? a.title.slice(0, 22) : a.title}
              </button>
            </li>
          ))}
        </ol>
        <ProgressBar value={(step + 1) / m.agenda.length} tone="forest" />

        <div key={item.id} className="pop-in mt-6">
          <div className="font-mono-label text-primary">{t('Step')} {step + 1} / {m.agenda.length} · {t(item.kind)}</div>
          <h2 className="mt-1 font-display text-4xl font-semibold leading-tight">{item.title}</h2>

          <div className="mt-6 space-y-5">
            {item.kind === 'checkin' && <p className="text-muted-foreground">{t('Each participant shares in one sentence how they arrive. No discussion.')}</p>}
            {item.kind === 'checklist' && <p className="text-muted-foreground">{t('Review the recurring checklist items: done or not done, no discussion.')}</p>}
            {item.kind === 'metrics' && (
              <div className="grid gap-2">
                {m.metrics.length === 0 && <p className="text-muted-foreground">{t('No KPIs defined for this circle.')}</p>}
                {m.metrics.map((x) => (
                  <div key={x.id} className="paper-card p-3">
                    <div className="flex justify-between text-sm"><span className="font-medium">{x.name}</span><span className="font-mono">{x.current_value} / {x.target_value} {x.unit}</span></div>
                  </div>
                ))}
              </div>
            )}
            {item.kind === 'projects' && (
              <div className="grid gap-2">
                {m.projects.length === 0 && <p className="text-muted-foreground">{t('No active projects.')}</p>}
                {m.projects.map((p) => (
                  <div key={p.id} className="paper-card flex items-center justify-between p-3 text-sm"><span className="font-medium">{p.name}</span><span className="flex items-center gap-2 text-xs text-muted-foreground">{fmtDate(p.due_date)} <StatusPill status={p.status} /></span></div>
                ))}
              </div>
            )}
            {item.kind === 'tension' && (
              <div className="paper-card p-4">
                {item.tension_id ? (
                  <>
                    <p className="text-sm text-muted-foreground">{item.tension_creator}</p>
                    <p className="mt-1">{item.tension_description || t('No description.')}</p>
                    <div className="mt-4 flex flex-wrap gap-2">
                      {(['task', 'project', 'proposal', 'decision', 'resolution'] as ConvertTarget[]).map((tg) => <Button key={tg} size="sm" variant="outline" onClick={() => setConvert(tg)}>{t(`Create ${tg}`)}</Button>)}
                    </div>
                  </>
                ) : <p className="text-muted-foreground">{t('Process the circle\'s tensions one by one. Add tensions to the agenda before or during the meeting.')}</p>}
              </div>
            )}
            {item.kind === 'closing' && <p className="text-muted-foreground">{t('Closing round: each participant shares a final reflection on the meeting.')}</p>}

            <NotesField item={item} />

            <div className="grid gap-3 rounded-xl border p-4">
              <div className="font-mono-label text-muted-foreground">{t('Capture outcomes')}</div>
              <QuickTask meetingId={m.id} circleId={m.circle_id} />
              <QuickDecision meetingId={m.id} />
              <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                <span>{m.tasks.length} {t('tasks')}</span><span>{m.decisions.length} {t('decisions')}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div className="sticky bottom-0 flex items-center justify-between gap-2 border-t bg-background/95 px-4 py-3 backdrop-blur md:px-8">
        <Button variant="outline" onClick={() => go(step - 1)} disabled={step === 0}><ArrowLeft className="mr-1 h-4 w-4" />{t('Back')}</Button>
        <Button variant="ghost" onClick={async () => { await act('patch', `/agenda/${item.id}`, { status: item.status === 'done' ? 'pending' : 'done' }) }}><Check className="mr-1 h-4 w-4" />{item.status === 'done' ? t('Reopen step') : t('Mark step done')}</Button>
        {isLast ? <Button onClick={finish}><Flag className="mr-1 h-4 w-4" />{t('Finish meeting')}</Button> : <Button onClick={async () => { await act('patch', `/agenda/${item.id}`, { status: 'done' }); await go(step + 1) }}>{t('Next')}<ArrowRight className="ml-1 h-4 w-4" /></Button>}
      </div>
      <TensionConvertDialog tension={convert && item.tension_id ? { id: item.tension_id, title: item.title, description: item.tension_description ?? '', circle_id: m.circle_id } : null} target={convert ?? 'task'} onClose={() => setConvert(null)} meetingId={m.id} />
    </div>
  )
}

export default function MeetingDetail() {
  const { id } = useParams()
  const { t, lang } = useT()
  const act = useAct()
  const { isObserver } = useSession()
  const { data, isLoading, error } = useGet<MeetingFull>(id ? `/meetings/${id}` : null)
  const [focus, setFocus] = useState(false)
  const [newItem, setNewItem] = useState('')
  if (isLoading) return <LoadingBlock rows={5} />
  if (error || !data) return <ErrorBlock message={error?.message} />
  const live = data.status === 'in_progress'
  const editable = data.status !== 'completed' && data.status !== 'cancelled' && !isObserver

  const start = async () => {
    const res = await act('post', `/meetings/${data.id}/start`)
    if (res) setFocus(true)
  }
  const addTension = (tid: string) => act('post', `/meetings/${data.id}/agenda`, { title: 'Tension', kind: 'tension', tension_id: tid })
  const addItem = async () => {
    const res = await act('post', `/meetings/${data.id}/agenda`, { title: newItem.trim(), kind: 'custom' })
    if (res) setNewItem('')
  }

  return (
    <>
      {focus && live && <FacilitatorMode m={data} onExit={() => setFocus(false)} />}
      <PageHeader
        eyebrow={<Link to="/meetings" className="hover:text-primary">{t('Meetings')}</Link>}
        title={data.title}
        subtitle={`${fmtDateTime(data.scheduled_at, lang)} · ${data.duration_min} min · ${data.circle_name} · ${t('Facilitator')}: ${data.facilitator_name ?? '–'}`}
        actions={
          <>
            <Pill>{t(data.meeting_type)}</Pill>
            <StatusPill status={data.status} />
            {data.can_run && data.status === 'scheduled' && <Button onClick={start}><Play className="mr-1 h-4 w-4" />{t('Start meeting')}</Button>}
            {data.can_run && live && <Button onClick={() => setFocus(true)}><Play className="mr-1 h-4 w-4" />{t('Open facilitator mode')}</Button>}
          </>
        }
      />
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Section title={t('Agenda')} index={1}>
            <ol className="space-y-3">
              {data.agenda.map((a, i) => (
                <li key={a.id} className="rounded-xl border p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex items-center gap-2 text-sm font-medium">
                      <span className="font-mono text-xs text-muted-foreground">{i + 1}</span>{a.title}
                      <Pill>{t(a.kind)}</Pill>{a.tension_priority && <Pill tone="ochre">{t(a.tension_priority)}</Pill>}
                    </span>
                    <span className="flex items-center gap-1">
                      <StatusPill status={a.status === 'done' ? 'done' : 'todo'} />
                      {editable && <Button variant="ghost" size="icon" className="h-7 w-7" aria-label={t('Remove')} onClick={() => act('delete', `/agenda/${a.id}`)}><X className="h-4 w-4" /></Button>}
                    </span>
                  </div>
                  {(a.notes || a.outcome) && (
                    <div className="mt-2 space-y-1 text-sm">
                      {a.notes && <p>{a.notes}</p>}
                      {a.outcome && <p className="text-[hsl(var(--forest))]">→ {a.outcome}</p>}
                    </div>
                  )}
                </li>
              ))}
            </ol>
            {editable && (
              <div className="mt-4 space-y-3 border-t pt-4">
                <div className="flex gap-2">
                  <Input value={newItem} maxLength={200} onChange={(e) => setNewItem(e.target.value)} placeholder={t('Add an agenda item')} aria-label={t('Add an agenda item')} />
                  <Button variant="outline" onClick={addItem} disabled={!newItem.trim()}><Plus className="mr-1 h-4 w-4" />{t('Add')}</Button>
                </div>
                {data.open_tensions.length > 0 && (
                  <div>
                    <div className="font-mono-label mb-1 text-muted-foreground">{t('Open tensions of this circle')}</div>
                    <div className="flex flex-wrap gap-2">
                      {data.open_tensions.map((x) => <Button key={x.id} size="sm" variant="secondary" onClick={() => addTension(x.id)}><Plus className="mr-1 h-3.5 w-3.5" />{x.title}</Button>)}
                    </div>
                  </div>
                )}
              </div>
            )}
          </Section>

          <Section title={t('Outcomes')} index={2}>
            <div className="grid gap-5 md:grid-cols-2">
              <div>
                <div className="font-mono-label mb-2 text-muted-foreground">{t('Decisions')}</div>
                {data.decisions.length === 0 && <p className="text-sm text-muted-foreground">{t('No decisions recorded.')}</p>}
                <ul className="space-y-2">{data.decisions.map((d) => <li key={d.id} className="text-sm"><span className="font-medium">{d.title}</span>{d.rationale && <span className="block text-xs text-muted-foreground">{d.rationale}</span>}</li>)}</ul>
                {editable && <div className="mt-3"><QuickDecision meetingId={data.id} /></div>}
              </div>
              <div>
                <div className="font-mono-label mb-2 text-muted-foreground">{t('Follow-up tasks')}</div>
                {data.tasks.length === 0 && <p className="text-sm text-muted-foreground">{t('No tasks created.')}</p>}
                <ul className="space-y-2">{data.tasks.map((x) => <li key={x.id} className="flex items-center justify-between gap-2 text-sm"><span>{x.title}<span className="block text-xs text-muted-foreground">{x.assignee_name ?? t('unassigned')} · {fmtDate(x.due_date, lang)}</span></span><StatusPill status={x.status} /></li>)}</ul>
              </div>
            </div>
            {data.proposals.length > 0 && (
              <div className="mt-5">
                <div className="font-mono-label mb-2 text-muted-foreground">{t('Governance proposals from this meeting')}</div>
                <ul className="space-y-1">{data.proposals.map((p) => <li key={p.id}><Link className="text-sm text-primary hover:underline" to={`/governance/proposals/${p.id}`}>{p.title}</Link> <StatusPill status={p.status} /></li>)}</ul>
              </div>
            )}
            {editable && <div className="mt-5 border-t pt-4"><QuickTask meetingId={data.id} circleId={data.circle_id} /></div>}
          </Section>

          <Section title={t('Meeting notes')} index={3}>
            <MeetingNotes id={data.id} notes={data.notes} disabled={isObserver} />
          </Section>
        </div>

        <div className="space-y-4">
          <Section title={t('Participants')} index={1}>
            <ul className="space-y-2">
              {data.participants.map((p) => (
                <li key={p.user_id} className="flex items-center gap-2">
                  <Avatar name={p.name} color={p.avatar_color} size={26} />
                  <span className="flex-1 text-sm">{p.name}</span>
                  {data.can_run && data.status !== 'cancelled' && <label className="flex items-center gap-1 text-xs text-muted-foreground"><Checkbox checked={p.attended} onCheckedChange={(v) => act('post', `/meetings/${data.id}/attendance`, { user_id: p.user_id, attended: Boolean(v) })} aria-label={`${t('Attended')}: ${p.name}`} />{t('present')}</label>}
                </li>
              ))}
            </ul>
          </Section>
          <Section title={t('Prepared context')} index={2}>
            <div className="space-y-3 text-sm">
              <div><div className="font-mono-label mb-1 text-muted-foreground">{t('KPIs')}</div>{data.metrics.length === 0 ? <p className="text-muted-foreground">–</p> : data.metrics.map((x) => <div key={x.id} className="flex justify-between"><span>{x.name}</span><span className="font-mono text-xs">{x.current_value}/{x.target_value}</span></div>)}</div>
              <div><div className="font-mono-label mb-1 text-muted-foreground">{t('Projects')}</div>{data.projects.length === 0 ? <p className="text-muted-foreground">–</p> : data.projects.map((x) => <div key={x.id} className="flex justify-between"><span>{x.name}</span><StatusPill status={x.status} /></div>)}</div>
            </div>
          </Section>
          {data.can_run && data.status === 'scheduled' && !isObserver && (
            <Button variant="ghost" className="text-destructive" onClick={() => act('patch', `/meetings/${data.id}`, { status: 'cancelled' })}>{t('Cancel meeting')}</Button>
          )}
        </div>
      </div>
    </>
  )
}

function MeetingNotes({ id, notes, disabled }: Readonly<{ id: string; notes: string; disabled: boolean }>) {
  const { t } = useT()
  const act = useAct()
  const [value, setValue] = useState(notes)
  useEffect(() => setValue(notes), [notes])
  return (
    <div className="grid gap-2">
      <Textarea rows={5} value={value} disabled={disabled} onChange={(e) => setValue(e.target.value)} aria-label={t('Meeting notes')} placeholder={t('Capture notes, agreements and open questions...')} />
      {!disabled && <Button className="w-fit" size="sm" variant="outline" disabled={value === notes} onClick={() => act('patch', `/meetings/${id}`, { notes: value })}>{t('Save notes')}</Button>}
    </div>
  )
}
