import { useMemo, useState, type DragEvent } from 'react'
import { useSearchParams } from 'react-router'
import { AlertTriangle, CalendarClock, Plus, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { Checkbox } from '@/components/ui/checkbox'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Avatar, EmptyState, ErrorBlock, LoadingBlock, PageHeader, Pill, PriorityPill, ProgressBar, StatusPill } from '@/components/kit'
import { NewTaskDialog, TaskSheet } from '@/components/TaskSheet'
import { useSession } from '@/contexts/SessionContext'
import { fmtDate, useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import type { PersonRow, ProjectRow, Structure, TaskRow, TaskStatus } from '@/lib/types'
import { cn } from '@/lib/utils'

const COLUMNS: TaskStatus[] = ['todo', 'doing', 'blocked', 'done']
const ALL = 'all'

function TaskCard({ task, onOpen, onDragStart }: Readonly<{ task: TaskRow; onOpen: () => void; onDragStart: (e: DragEvent) => void }>) {
  const { t, lang } = useT()
  return (
    <div
      draggable
      onDragStart={onDragStart}
      onClick={onOpen}
      onKeyDown={(e) => { if (e.key === 'Enter') onOpen() }}
      tabIndex={0}
      role="button"
      aria-label={task.title}
      className={cn('paper-card cursor-grab p-3 text-left active:cursor-grabbing focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring', task.is_overdue && 'border-destructive/50 bg-destructive/5')}
    >
      <div className="text-sm font-medium leading-snug">{task.title}</div>
      <div className="mt-1 truncate text-xs text-muted-foreground">{[task.project_name, task.role_name].filter(Boolean).join(' · ')}</div>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <PriorityPill priority={task.priority} />
        {task.due_date && (
          <Pill tone={task.is_overdue ? 'danger' : 'neutral'}>{task.is_overdue ? <AlertTriangle className="h-3 w-3" /> : <CalendarClock className="h-3 w-3" />}{fmtDate(task.due_date, lang)}</Pill>
        )}
        {task.assignee_name && <span className="ml-auto" title={task.assignee_name}><Avatar name={task.assignee_name} size={22} /></span>}
        {!task.assignee_name && <span className="ml-auto text-[11px] text-muted-foreground">{t('unassigned')}</span>}
      </div>
    </div>
  )
}

function ProjectSheet({ id, onClose }: Readonly<{ id: string | null; onClose: () => void }>) {
  const { t, lang } = useT()
  const act = useAct()
  const { isObserver } = useSession()
  const { data } = useGet<ProjectRow & { tasks: TaskRow[]; milestones: { id: string; title: string; due_date: string | null; done: boolean }[]; can_manage: boolean }>(id ? `/projects/${id}` : null)
  const [ms, setMs] = useState('')
  const [taskOpen, setTaskOpen] = useState(false)
  const [taskId, setTaskId] = useState<string | null>(null)
  return (
    <Sheet open={id !== null} onOpenChange={(v) => !v && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
        <SheetHeader>
          <SheetTitle className="font-display text-2xl">{data?.name ?? t('Project')}</SheetTitle>
          <SheetDescription>{data?.description}</SheetDescription>
        </SheetHeader>
        {!data ? <LoadingBlock rows={3} /> : (
          <div className="mt-2 grid gap-4 px-4 pb-6">
            <div className="flex flex-wrap gap-2"><StatusPill status={data.status} /><PriorityPill priority={data.priority} /><Pill>{data.circle_name}</Pill></div>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div><div className="font-mono-label text-muted-foreground">{t('Accountable role')}</div>{data.owning_role_name ?? '–'}</div>
              <div><div className="font-mono-label text-muted-foreground">{t('Due')}</div>{fmtDate(data.due_date, lang)}</div>
              <div className="col-span-2"><div className="font-mono-label text-muted-foreground">{t('Responsible people')}</div>{data.people.map((p) => p.name).join(', ') || '–'}</div>
            </div>
            {data.can_manage && (
              <div className="grid gap-1.5">
                <Label>{t('Status')}</Label>
                <Select value={data.status} onValueChange={(v) => act('patch', `/projects/${data.id}`, { status: v })}>
                  <SelectTrigger aria-label={t('Status')}><SelectValue /></SelectTrigger>
                  <SelectContent>{['planned', 'active', 'on_hold', 'done', 'cancelled'].map((s) => <SelectItem key={s} value={s}>{t(s.replaceAll('_', ' '))}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            )}
            <section>
              <h3 className="mb-2 font-display text-lg font-semibold">{t('Milestones')}</h3>
              <ul className="space-y-1.5">
                {data.milestones.map((m) => (
                  <li key={m.id} className="flex items-center gap-2 text-sm">
                    <Checkbox checked={m.done} disabled={!data.can_manage} onCheckedChange={(v) => act('patch', `/milestones/${m.id}`, { done: Boolean(v) })} aria-label={m.title} />
                    <span className={m.done ? 'line-through text-muted-foreground' : ''}>{m.title}</span>
                    <span className="ml-auto text-xs text-muted-foreground">{fmtDate(m.due_date, lang)}</span>
                  </li>
                ))}
                {data.milestones.length === 0 && <li className="text-sm text-muted-foreground">{t('No milestones yet.')}</li>}
              </ul>
              {data.can_manage && (
                <div className="mt-2 flex gap-2">
                  <Input value={ms} onChange={(e) => setMs(e.target.value)} placeholder={t('New milestone')} aria-label={t('New milestone')} />
                  <Button variant="outline" disabled={!ms.trim()} onClick={async () => { if (await act('post', `/projects/${data.id}/milestones`, { title: ms.trim() })) setMs('') }}>{t('Add')}</Button>
                </div>
              )}
            </section>
            <section>
              <div className="mb-2 flex items-center justify-between">
                <h3 className="font-display text-lg font-semibold">{t('Tasks')}</h3>
                {!isObserver && <Button size="sm" variant="outline" onClick={() => setTaskOpen(true)}><Plus className="mr-1 h-4 w-4" />{t('New task')}</Button>}
              </div>
              <ul className="divide-y">
                {data.tasks.map((x) => (
                  <li key={x.id}>
                    <button type="button" onClick={() => setTaskId(x.id)} className="flex w-full items-center justify-between gap-2 py-2 text-left text-sm hover:text-primary">
                      <span>{x.title}<span className="block text-xs text-muted-foreground">{x.assignee_name ?? t('unassigned')}</span></span>
                      <span className="flex items-center gap-1">{x.is_overdue && <Pill tone="danger">{t('overdue')}</Pill>}<StatusPill status={x.status} /></span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          </div>
        )}
        <NewTaskDialog open={taskOpen} onOpenChange={setTaskOpen} projectId={id ?? undefined} />
        <TaskSheet taskId={taskId} onClose={() => setTaskId(null)} />
      </SheetContent>
    </Sheet>
  )
}

function NewProjectDialog({ open, onOpenChange }: Readonly<{ open: boolean; onOpenChange: (v: boolean) => void }>) {
  const { t } = useT()
  const act = useAct()
  const { data: structure } = useGet<Structure>(open ? '/structure' : null)
  const { data: people } = useGet<PersonRow[]>(open ? '/people' : null)
  const [f, setF] = useState({ name: '', description: '', circle_id: '', owning_role_id: '', due_date: '', priority: 'medium', person_ids: [] as string[] })
  const roles = (structure?.roles ?? []).filter((r) => r.circle_id === f.circle_id)
  const save = async () => {
    const res = await act('post', '/projects', { ...f, due_date: f.due_date || null, owning_role_id: f.owning_role_id || null, status: 'planned' })
    if (res) {
      onOpenChange(false)
      setF({ name: '', description: '', circle_id: '', owning_role_id: '', due_date: '', priority: 'medium', person_ids: [] })
    }
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="font-display text-xl">{t('New project')}</DialogTitle>
          <DialogDescription>{t('Projects are owned by a role; people carry out the tasks.')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1.5"><Label htmlFor="np-name">{t('Name')}</Label><Input id="np-name" value={f.name} maxLength={200} onChange={(e) => setF({ ...f, name: e.target.value })} /></div>
          <div className="grid gap-1.5"><Label htmlFor="np-desc">{t('Description')}</Label><Textarea id="np-desc" rows={2} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></div>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5">
              <Label>{t('Circle')}</Label>
              <Select value={f.circle_id} onValueChange={(v) => setF({ ...f, circle_id: v, owning_role_id: '' })}>
                <SelectTrigger aria-label={t('Circle')}><SelectValue placeholder={t('Choose a circle.')} /></SelectTrigger>
                <SelectContent>{(structure?.circles ?? []).map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label>{t('Owning role')}</Label>
              <Select value={f.owning_role_id} onValueChange={(v) => setF({ ...f, owning_role_id: v })} disabled={!f.circle_id}>
                <SelectTrigger aria-label={t('Owning role')}><SelectValue placeholder={t('Choose a role')} /></SelectTrigger>
                <SelectContent>{roles.map((r) => <SelectItem key={r.id} value={r.id}>{r.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5"><Label htmlFor="np-due">{t('Due date')}</Label><Input id="np-due" type="date" value={f.due_date} onChange={(e) => setF({ ...f, due_date: e.target.value })} /></div>
            <div className="grid gap-1.5">
              <Label>{t('Priority')}</Label>
              <Select value={f.priority} onValueChange={(v) => setF({ ...f, priority: v })}>
                <SelectTrigger aria-label={t('Priority')}><SelectValue /></SelectTrigger>
                <SelectContent>{['low', 'medium', 'high'].map((s) => <SelectItem key={s} value={s}>{t(s)}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </div>
          <fieldset className="grid max-h-40 gap-1.5 overflow-y-auto rounded-lg border p-3">
            <legend className="px-1 text-xs text-muted-foreground">{t('Responsible people')}</legend>
            {(people ?? []).map((p) => (
              <label key={p.id} className="flex items-center gap-2 text-sm">
                <Checkbox checked={f.person_ids.includes(p.id)} onCheckedChange={(v) => setF({ ...f, person_ids: v ? [...f.person_ids, p.id] : f.person_ids.filter((x) => x !== p.id) })} />{p.name}
              </label>
            ))}
          </fieldset>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t('Cancel')}</Button>
          <Button onClick={save} disabled={f.name.trim().length < 3 || !f.circle_id}>{t('Create project')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default function Work() {
  const { t, lang } = useT()
  const act = useAct()
  const { isObserver } = useSession()
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') ?? 'board'
  const [scope, setScope] = useState<'mine' | 'all'>(params.get('scope') === 'mine' ? 'mine' : 'all')
  const [circle, setCircle] = useState(params.get('circle') ?? ALL)
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState<'due' | 'priority' | 'created'>('due')
  const [overdue, setOverdue] = useState(false)
  const [moved, setMoved] = useState<Record<string, TaskStatus>>({})
  const [openTask, setOpenTask] = useState<string | null>(params.get('task'))
  const [openProject, setOpenProject] = useState<string | null>(params.get('project'))
  const [taskDlg, setTaskDlg] = useState(false)
  const [projDlg, setProjDlg] = useState(false)
  const [dragOver, setDragOver] = useState<TaskStatus | null>(null)

  const { data: structure } = useGet<Structure>('/structure')
  const { data: tasks, isLoading, error } = useGet<TaskRow[]>('/tasks', { scope, circle_id: circle === ALL ? undefined : circle, search, sort, overdue })
  const { data: projects } = useGet<ProjectRow[]>('/projects', { circle_id: circle === ALL ? undefined : circle })

  const rows = useMemo(() => (tasks ?? []).map((x) => ({ ...x, status: moved[x.id] ?? x.status })), [tasks, moved])
  const overdueCount = rows.filter((r) => r.is_overdue).length

  const drop = async (e: DragEvent, status: TaskStatus) => {
    e.preventDefault()
    setDragOver(null)
    const id = e.dataTransfer.getData('text/plain')
    const task = rows.find((r) => r.id === id)
    if (!task || task.status === status) return
    setMoved((m) => ({ ...m, [id]: status }))
    await act('patch', `/tasks/${id}`, { status })
    setMoved((m) => {
      const next = { ...m }
      delete next[id]
      return next
    })
  }

  return (
    <>
      <PageHeader
        title={t('Projects & Tasks')}
        subtitle={t('Projects belong to a role (accountability); tasks are carried out by people (execution).')}
        actions={!isObserver ? (
          <>
            <Button variant="outline" onClick={() => setProjDlg(true)}><Plus className="mr-1 h-4 w-4" />{t('New project')}</Button>
            <Button onClick={() => setTaskDlg(true)}><Plus className="mr-1 h-4 w-4" />{t('New task')}</Button>
          </>
        ) : undefined}
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Tabs value={scope} onValueChange={(v) => setScope(v as 'mine' | 'all')}>
          <TabsList><TabsTrigger value="mine">{t('My tasks')}</TabsTrigger><TabsTrigger value="all">{t('Circle tasks')}</TabsTrigger></TabsList>
        </Tabs>
        <Select value={circle} onValueChange={setCircle}>
          <SelectTrigger className="w-52" aria-label={t('Circle')}><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{t('All circles')}</SelectItem>
            {(structure?.circles ?? []).map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
          </SelectContent>
        </Select>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input className="w-52 pl-9" value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t('Search tasks')} aria-label={t('Search tasks')} />
        </div>
        <Select value={sort} onValueChange={(v) => setSort(v as typeof sort)}>
          <SelectTrigger className="w-40" aria-label={t('Sort')}><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="due">{t('Due date')}</SelectItem>
            <SelectItem value="priority">{t('Priority')}</SelectItem>
            <SelectItem value="created">{t('Newest')}</SelectItem>
          </SelectContent>
        </Select>
        <label className="flex items-center gap-2 text-sm"><Switch checked={overdue} onCheckedChange={setOverdue} />{t('Overdue only')}{overdueCount > 0 && <Pill tone="danger">{overdueCount}</Pill>}</label>
      </div>

      <Tabs value={tab} onValueChange={(v) => setParams((p) => { const n = new URLSearchParams(p); n.set('tab', v); return n })}>
        <TabsList className="mb-4">
          <TabsTrigger value="board">{t('Board')}</TabsTrigger>
          <TabsTrigger value="list">{t('List')}</TabsTrigger>
          <TabsTrigger value="projects">{t('Projects')}</TabsTrigger>
        </TabsList>

        {isLoading && <LoadingBlock />}
        {error && <ErrorBlock message={error.message} />}

        <TabsContent value="board">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {COLUMNS.map((col) => {
              const items = rows.filter((r) => r.status === col)
              return (
                <section
                  key={col}
                  aria-label={t(col)}
                  onDragOver={(e) => { e.preventDefault(); setDragOver(col) }}
                  onDragLeave={() => setDragOver(null)}
                  onDrop={(e) => drop(e, col)}
                  className={cn('min-h-40 rounded-2xl border bg-muted/40 p-2 transition-colors', dragOver === col && 'border-primary bg-primary/5')}
                >
                  <div className="mb-2 flex items-center justify-between px-1"><StatusPill status={col} /><span className="font-mono text-xs text-muted-foreground">{items.length}</span></div>
                  <div className="space-y-2">
                    {items.map((x) => <TaskCard key={x.id} task={x} onOpen={() => setOpenTask(x.id)} onDragStart={(e) => e.dataTransfer.setData('text/plain', x.id)} />)}
                    {items.length === 0 && <p className="px-2 py-6 text-center text-xs text-muted-foreground">{t('Drop tasks here')}</p>}
                  </div>
                </section>
              )
            })}
          </div>
        </TabsContent>

        <TabsContent value="list">
          {rows.length === 0 ? <EmptyState title={t('No tasks match the filters')} /> : (
            <div className="paper-card overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="border-b text-left text-xs text-muted-foreground">{['Task', 'Status', 'Priority', 'Due', 'Responsible', 'Accountable role', 'Project'].map((h) => <th key={h} className="px-3 py-2 font-medium">{t(h)}</th>)}</tr></thead>
                <tbody>
                  {rows.map((x) => (
                    <tr key={x.id} className={cn('cursor-pointer border-b last:border-0 hover:bg-muted/50', x.is_overdue && 'bg-destructive/5')} onClick={() => setOpenTask(x.id)}>
                      <td className="px-3 py-2 font-medium"><button type="button" className="text-left hover:text-primary" onClick={() => setOpenTask(x.id)}>{x.title}</button></td>
                      <td className="px-3 py-2"><StatusPill status={x.status} /></td>
                      <td className="px-3 py-2"><PriorityPill priority={x.priority} /></td>
                      <td className={cn('px-3 py-2', x.is_overdue && 'font-medium text-destructive')}>{fmtDate(x.due_date, lang)}</td>
                      <td className="px-3 py-2">{x.assignee_name ?? '–'}</td>
                      <td className="px-3 py-2">{x.role_name ?? '–'}</td>
                      <td className="px-3 py-2">{x.project_name ?? '–'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </TabsContent>

        <TabsContent value="projects">
          {(projects ?? []).length === 0 ? <EmptyState title={t('No projects')} /> : (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {projects?.map((p, i) => (
                <button key={p.id} type="button" onClick={() => setOpenProject(p.id)} className="paper-card interactive reveal p-4 text-left" style={{ ['--i' as string]: i }}>
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="font-display text-lg font-semibold leading-tight">{p.name}</h3>
                    <StatusPill status={p.status} />
                  </div>
                  <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{p.description}</p>
                  <div className="mt-3"><ProgressBar value={p.task_count ? p.tasks_done / p.task_count : 0} tone="forest" /></div>
                  <div className="mt-3 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                    <PriorityPill priority={p.priority} /><Pill>{p.circle_name}</Pill>
                    {p.owning_role_name && <Pill tone="forest">{p.owning_role_name}</Pill>}
                    <span>{t('due')} {fmtDate(p.due_date, lang)}</span>
                    <span>{p.milestones_done}/{p.milestone_count} {t('milestones')}</span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>

      <TaskSheet taskId={openTask} onClose={() => setOpenTask(null)} />
      <ProjectSheet id={openProject} onClose={() => setOpenProject(null)} />
      <NewTaskDialog open={taskDlg} onOpenChange={setTaskDlg} circleId={circle === ALL ? undefined : circle} />
      <NewProjectDialog open={projDlg} onOpenChange={setProjDlg} />
    </>
  )
}
