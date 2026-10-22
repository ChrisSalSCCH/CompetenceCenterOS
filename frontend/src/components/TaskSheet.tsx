import { useEffect, useState } from 'react'
import { Plus, Trash2, ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { LoadingBlock } from '@/components/kit'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { fmtDateTime, useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import type { PersonRow, ProjectRow, Structure, TaskRow } from '@/lib/types'

const NONE = 'none'
const STATUSES = ['todo', 'doing', 'blocked', 'done']
const PRIORITIES = ['low', 'medium', 'high']

interface TaskFull extends TaskRow {
  comments: { id: string; body: string; created_at: string; author_name: string }[]
  activity: { id: string; action: string; detail: string | null; created_at: string; actor_name: string | null }[]
  attachments: { id: string; name: string; url: string }[]
  can_edit: boolean
}

function PickerSelect({ label, value, onChange, options, disabled }: Readonly<{ label: string; value: string; onChange: (v: string) => void; options: { id: string; name: string }[]; disabled?: boolean }>) {
  return (
    <div className="grid gap-1.5">
      <Label>{label}</Label>
      <Select value={value || NONE} onValueChange={(v) => onChange(v === NONE ? '' : v)} disabled={disabled}>
        <SelectTrigger aria-label={label}><SelectValue /></SelectTrigger>
        <SelectContent>
          <SelectItem value={NONE}>–</SelectItem>
          {options.map((o) => <SelectItem key={o.id} value={o.id}>{o.name}</SelectItem>)}
        </SelectContent>
      </Select>
    </div>
  )
}

export function TaskSheet({ taskId, onClose }: Readonly<{ taskId: string | null; onClose: () => void }>) {
  const { t, lang } = useT()
  const act = useAct()
  const open = taskId !== null
  const { data } = useGet<TaskFull>(taskId ? `/tasks/${taskId}` : null)
  const { data: people } = useGet<PersonRow[]>(open ? '/people' : null)
  const { data: structure } = useGet<Structure>(open ? '/structure' : null)
  const { data: projects } = useGet<ProjectRow[]>(open ? '/projects' : null)
  const [form, setForm] = useState({ title: '', description: '', status: 'todo', priority: 'medium', due_date: '', assignee_id: '', role_id: '', project_id: '' })
  const [comment, setComment] = useState('')
  const [docName, setDocName] = useState('')
  const [docUrl, setDocUrl] = useState('')

  useEffect(() => {
    if (data) {
      setForm({ title: data.title, description: data.description, status: data.status, priority: data.priority, due_date: data.due_date ?? '', assignee_id: data.assignee_id ?? '', role_id: data.role_id ?? '', project_id: data.project_id ?? '' })
    }
  }, [data])

  const save = async () => {
    const res = await act('patch', `/tasks/${taskId}`, {
      title: form.title.trim(), description: form.description, status: form.status, priority: form.priority,
      due_date: form.due_date || null, assignee_id: form.assignee_id || null, role_id: form.role_id || null, project_id: form.project_id || null,
    })
    if (res) onClose()
  }
  const addDoc = async () => {
    const res = await act('post', '/attachments', { entity_type: 'task', entity_id: taskId, name: docName.trim(), url: docUrl.trim() })
    if (res) { setDocName(''); setDocUrl('') }
  }
  const set = (k: keyof typeof form) => (v: string) => setForm((f) => ({ ...f, [k]: v }))
  const readOnly = data ? !data.can_edit : true

  return (
    <Sheet open={open} onOpenChange={(v) => !v && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
        <SheetHeader>
          <SheetTitle className="font-display text-2xl">{t('Task')}</SheetTitle>
          <SheetDescription>{t('Individual execution. Organizational accountability stays with the accountable role.')}</SheetDescription>
        </SheetHeader>
        {!data ? <LoadingBlock rows={4} /> : (
          <div className="mt-4 grid gap-4 px-4 pb-6">
            <div className="grid gap-1.5"><Label htmlFor="tk-title">{t('Title')}</Label><Input id="tk-title" value={form.title} maxLength={200} disabled={readOnly} onChange={(e) => set('title')(e.target.value)} /></div>
            <div className="grid gap-1.5"><Label htmlFor="tk-desc">{t('Description')}</Label><Textarea id="tk-desc" rows={3} value={form.description} disabled={readOnly} onChange={(e) => set('description')(e.target.value)} /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-1.5">
                <Label>{t('Status')}</Label>
                <Select value={form.status} onValueChange={set('status')} disabled={readOnly}>
                  <SelectTrigger aria-label={t('Status')}><SelectValue /></SelectTrigger>
                  <SelectContent>{STATUSES.map((s) => <SelectItem key={s} value={s}>{t(s)}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="grid gap-1.5">
                <Label>{t('Priority')}</Label>
                <Select value={form.priority} onValueChange={set('priority')} disabled={readOnly}>
                  <SelectTrigger aria-label={t('Priority')}><SelectValue /></SelectTrigger>
                  <SelectContent>{PRIORITIES.map((s) => <SelectItem key={s} value={s}>{t(s)}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <PickerSelect label={t('Responsible person')} value={form.assignee_id} onChange={set('assignee_id')} options={people ?? []} disabled={readOnly} />
              <div className="grid gap-1.5"><Label htmlFor="tk-due">{t('Due date')}</Label><Input id="tk-due" type="date" value={form.due_date} disabled={readOnly} onChange={(e) => set('due_date')(e.target.value)} /></div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <PickerSelect label={t('Accountable role')} value={form.role_id} onChange={set('role_id')} options={structure?.roles ?? []} disabled={readOnly} />
              <PickerSelect label={t('Project')} value={form.project_id} onChange={set('project_id')} options={projects ?? []} disabled={readOnly} />
            </div>
            {!readOnly && (
              <div className="flex justify-between">
                <ConfirmDialog trigger={<Button variant="ghost" className="text-destructive"><Trash2 className="mr-1 h-4 w-4" />{t('Delete')}</Button>} title={t('Delete this task?')} description={t('The task is removed from all boards.')} onConfirm={async () => { if (await act('delete', `/tasks/${taskId}`)) onClose() }} />
                <Button onClick={save}>{t('Save')}</Button>
              </div>
            )}
            {readOnly && <p className="rounded-lg bg-muted p-2 text-xs text-muted-foreground">{t('Only the assignee, the accountable role, the project team or governance roles can edit this task.')}</p>}

            <section>
              <h3 className="mb-2 font-display text-lg font-semibold">{t('Attachments')}</h3>
              <ul className="mb-2 space-y-1">{data.attachments.map((a) => <li key={a.id}><a href={a.url} target="_blank" rel="noreferrer noopener" className="flex items-center gap-1 text-sm text-primary hover:underline"><ExternalLink className="h-3.5 w-3.5" />{a.name}</a></li>)}</ul>
              {!readOnly && (
                <div className="flex flex-wrap gap-2">
                  <Input className="w-40" value={docName} onChange={(e) => setDocName(e.target.value)} placeholder={t('Name')} aria-label={t('Name')} />
                  <Input className="min-w-40 flex-1" value={docUrl} onChange={(e) => setDocUrl(e.target.value)} placeholder="https://" aria-label="URL" />
                  <Button variant="outline" onClick={addDoc} disabled={!docName.trim() || !docUrl.trim()}>{t('Add link')}</Button>
                </div>
              )}
              <p className="mt-1 text-xs text-muted-foreground">{t('File upload is planned; links are supported today.')}</p>
            </section>

            <section>
              <h3 className="mb-2 font-display text-lg font-semibold">{t('Comments')}</h3>
              <ul className="mb-3 space-y-2">
                {data.comments.map((c) => <li key={c.id} className="rounded-lg border p-2 text-sm"><span className="text-xs text-muted-foreground">{c.author_name} · {fmtDateTime(c.created_at, lang)}</span><p>{c.body}</p></li>)}
                {data.comments.length === 0 && <li className="text-sm text-muted-foreground">{t('No comments yet.')}</li>}
              </ul>
              <div className="flex gap-2">
                <Input value={comment} onChange={(e) => setComment(e.target.value)} placeholder={t('Write a comment')} aria-label={t('Write a comment')} onKeyDown={(e) => { if (e.key === 'Enter' && comment.trim()) { act('post', `/tasks/${taskId}/comments`, { body: comment }); setComment('') } }} />
                <Button variant="outline" disabled={!comment.trim()} onClick={async () => { if (await act('post', `/tasks/${taskId}/comments`, { body: comment })) setComment('') }}>{t('Post')}</Button>
              </div>
            </section>

            <section>
              <h3 className="mb-2 font-display text-lg font-semibold">{t('Activity')}</h3>
              <ul className="space-y-1 text-xs text-muted-foreground">
                {data.activity.map((a) => <li key={a.id}>{fmtDateTime(a.created_at, lang)} · {a.actor_name ?? '?'} · {a.action.replaceAll('_', ' ')}{a.detail ? `: ${a.detail}` : ''}</li>)}
              </ul>
            </section>
          </div>
        )}
      </SheetContent>
    </Sheet>
  )
}

export function NewTaskDialog({ open, onOpenChange, projectId, circleId }: Readonly<{ open: boolean; onOpenChange: (v: boolean) => void; projectId?: string; circleId?: string }>) {
  const { t } = useT()
  const act = useAct()
  const { data: people } = useGet<PersonRow[]>(open ? '/people' : null)
  const { data: structure } = useGet<Structure>(open ? '/structure' : null)
  const { data: projects } = useGet<ProjectRow[]>(open ? '/projects' : null)
  const [f, setF] = useState({ title: '', description: '', assignee_id: '', role_id: '', project_id: '', circle_id: '', due_date: '', priority: 'medium' })
  useEffect(() => {
    if (open) setF({ title: '', description: '', assignee_id: '', role_id: '', project_id: projectId ?? '', circle_id: circleId ?? '', due_date: '', priority: 'medium' })
  }, [open, projectId, circleId])
  const set = (k: keyof typeof f) => (v: string) => setF((s) => ({ ...s, [k]: v }))
  const save = async () => {
    const res = await act('post', '/tasks', {
      title: f.title.trim(), description: f.description, priority: f.priority, due_date: f.due_date || null,
      assignee_id: f.assignee_id || null, role_id: f.role_id || null, project_id: f.project_id || null, circle_id: f.project_id ? null : f.circle_id || null,
    })
    if (res) onOpenChange(false)
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="font-display text-xl">{t('New task')}</DialogTitle>
          <DialogDescription>{t('A person executes the task; the accountable role keeps organizational accountability.')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1.5"><Label htmlFor="nt-title">{t('Title')}</Label><Input id="nt-title" value={f.title} maxLength={200} onChange={(e) => set('title')(e.target.value)} autoFocus /></div>
          <div className="grid gap-1.5"><Label htmlFor="nt-desc">{t('Description')}</Label><Textarea id="nt-desc" rows={2} value={f.description} onChange={(e) => set('description')(e.target.value)} /></div>
          <div className="grid grid-cols-2 gap-3">
            <PickerSelect label={t('Responsible person')} value={f.assignee_id} onChange={set('assignee_id')} options={people ?? []} />
            <PickerSelect label={t('Accountable role')} value={f.role_id} onChange={set('role_id')} options={structure?.roles ?? []} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <PickerSelect label={t('Project')} value={f.project_id} onChange={set('project_id')} options={projects ?? []} />
            <PickerSelect label={t('Circle')} value={f.circle_id} onChange={set('circle_id')} options={structure?.circles ?? []} disabled={Boolean(f.project_id)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5"><Label htmlFor="nt-due">{t('Due date')}</Label><Input id="nt-due" type="date" value={f.due_date} onChange={(e) => set('due_date')(e.target.value)} /></div>
            <div className="grid gap-1.5">
              <Label>{t('Priority')}</Label>
              <Select value={f.priority} onValueChange={set('priority')}>
                <SelectTrigger aria-label={t('Priority')}><SelectValue /></SelectTrigger>
                <SelectContent>{PRIORITIES.map((s) => <SelectItem key={s} value={s}>{t(s)}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t('Cancel')}</Button>
          <Button onClick={save} disabled={f.title.trim().length < 2}><Plus className="mr-1 h-4 w-4" />{t('Create task')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
