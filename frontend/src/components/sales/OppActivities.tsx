import { useEffect, useState } from 'react'
import { Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { EmptyState, Pill, Section } from '@/components/kit'
import { fmtDate, fmtDateTime, useAct } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import type { OppActivity } from '@/lib/sales-types'

const KINDS = ['call', 'meeting', 'workshop', 'presentation', 'negotiation', 'email', 'visit', 'note', 'other'] as const

function LogDialog({ opportunityId, open, onOpenChange }: Readonly<{ opportunityId: string; open: boolean; onOpenChange: (v: boolean) => void }>) {
  const { t } = useT()
  const act = useAct()
  const [kind, setKind] = useState<string>('meeting')
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [follow, setFollow] = useState(false)
  const [followTitle, setFollowTitle] = useState('')
  const [due, setDue] = useState('')
  useEffect(() => {
    if (open) {
      setKind('meeting')
      setSubject('')
      setBody('')
      setFollow(false)
      setFollowTitle('')
      setDue('')
    }
  }, [open])
  const canSave = subject.trim().length >= 2 && (!follow || followTitle.trim().length >= 2)
  const save = async () => {
    const res = await act('post', '/crm/activities', {
      opportunity_id: opportunityId, kind, subject: subject.trim(), body,
      follow_up: follow ? { title: followTitle.trim(), due_date: due || null } : null,
    })
    if (res) onOpenChange(false)
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader><DialogTitle className="font-display text-xl">{t('Log activity')}</DialogTitle></DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-3 sm:grid-cols-[10rem_1fr]">
            <div className="grid gap-1.5">
              <Label>{t('Kind')}</Label>
              <Select value={kind} onValueChange={setKind}>
                <SelectTrigger aria-label={t('Kind')}><SelectValue /></SelectTrigger>
                <SelectContent>{KINDS.map((k) => <SelectItem key={k} value={k}>{t(k)}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5"><Label htmlFor="oa-subject">{t('Subject')} *</Label><Input id="oa-subject" value={subject} maxLength={200} onChange={(e) => setSubject(e.target.value)} autoFocus /></div>
          </div>
          <div className="grid gap-1.5"><Label htmlFor="oa-body">{t('Notes')}</Label><Textarea id="oa-body" rows={3} value={body} maxLength={10000} onChange={(e) => setBody(e.target.value)} /></div>
          <Label className="flex items-center gap-2 font-normal"><Switch checked={follow} onCheckedChange={setFollow} />{t('Create a follow-up task')}</Label>
          {follow && (
            <div className="grid gap-3 sm:grid-cols-[1fr_10rem]">
              <div className="grid gap-1.5"><Label htmlFor="oa-ft">{t('Task')} *</Label><Input id="oa-ft" value={followTitle} maxLength={200} onChange={(e) => setFollowTitle(e.target.value)} /></div>
              <div className="grid gap-1.5"><Label htmlFor="oa-due">{t('Due')}</Label><Input id="oa-due" type="date" value={due} onChange={(e) => setDue(e.target.value)} /></div>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t('Cancel')}</Button>
          <Button onClick={save} disabled={!canSave}>{t('Save')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function OppActivities({ opportunityId, activities, canEdit }: Readonly<{ opportunityId: string; activities: OppActivity[]; canEdit: boolean }>) {
  const { t, lang } = useT()
  const [open, setOpen] = useState(false)
  return (
    <Section title={t('Activities')} action={canEdit ? <Button size="sm" onClick={() => setOpen(true)}><Plus className="mr-1 h-4 w-4" aria-hidden />{t('Log activity')}</Button> : undefined}>
      {activities.length === 0 && <EmptyState title={t('No activities yet')} hint={t('Workshops, presentations and negotiations show up here.')} />}
      <ul className="divide-y">
        {activities.map((a) => (
          <li key={a.id} className="py-3">
            <div className="flex flex-wrap items-center gap-2">
              <Pill>{t(a.kind)}</Pill>
              <span className="font-medium">{a.subject}</span>
              <span className="ml-auto text-xs text-muted-foreground">{fmtDateTime(a.occurred_at, lang)}{a.author_name && ` · ${a.author_name}`}</span>
            </div>
            {a.body && <p className="mt-1 whitespace-pre-line text-sm text-muted-foreground">{a.body}</p>}
            {a.follow_up_task_id && (
              <p className="mt-1 text-xs">{t('Follow-up')}: <Pill tone={a.follow_up_status === 'done' ? 'forest' : 'ochre'}>{t(a.follow_up_status ?? 'todo')}</Pill>{a.follow_up_due && ` · ${fmtDate(a.follow_up_due, lang)}`}</p>
            )}
          </li>
        ))}
      </ul>
      <LogDialog opportunityId={opportunityId} open={open} onOpenChange={setOpen} />
    </Section>
  )
}
