import { useEffect, useState } from 'react'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ComboPicker } from '@/components/ComboPicker'
import { useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import { ACTIVITY_KINDS, fullName } from '@/lib/portfolio'
import type { ActivityKind, CrmOrgDetail } from '@/lib/portfolio-types'
import type { PersonRow } from '@/lib/types'

export function ActivityDialog({ org, open, onOpenChange }: Readonly<{ org: CrmOrgDetail; open: boolean; onOpenChange: (v: boolean) => void }>) {
  const { t } = useT()
  const act = useAct()
  const { data: people } = useGet<PersonRow[]>(open ? '/people' : null)
  const [kind, setKind] = useState<ActivityKind>('call')
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [contactId, setContactId] = useState<string[]>([])
  const [projectId, setProjectId] = useState<string[]>([])
  const [follow, setFollow] = useState(false)
  const [followTitle, setFollowTitle] = useState('')
  const [due, setDue] = useState('')
  const [assignee, setAssignee] = useState<string[]>([])

  useEffect(() => {
    if (open) {
      setKind('call')
      setSubject('')
      setBody('')
      setContactId([])
      setProjectId([])
      setFollow(false)
      setFollowTitle('')
      setDue('')
      setAssignee([])
    }
  }, [open])

  const canSave = subject.trim().length >= 2 && (!follow || followTitle.trim().length >= 2)

  const save = async () => {
    const res = await act('post', '/crm/activities', {
      crm_org_id: org.id, contact_id: contactId[0] ?? null, project_id: projectId[0] ?? null, kind, subject: subject.trim(), body,
      follow_up: follow ? { title: followTitle.trim(), due_date: due || null, assignee_id: assignee[0] ?? null } : null,
    })
    if (res) onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader><DialogTitle className="font-display text-xl">{t('Log activity')} · {org.name}</DialogTitle></DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-3 sm:grid-cols-[10rem_1fr]">
            <div className="grid gap-1.5">
              <Label>{t('Kind')}</Label>
              <Select value={kind} onValueChange={(v) => setKind(v as ActivityKind)}>
                <SelectTrigger aria-label={t('Kind')}><SelectValue /></SelectTrigger>
                <SelectContent>{ACTIVITY_KINDS.map((k) => <SelectItem key={k} value={k}>{t(k)}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5"><Label htmlFor="ac-subject">{t('Subject')} *</Label><Input id="ac-subject" value={subject} maxLength={200} onChange={(e) => setSubject(e.target.value)} autoFocus /></div>
          </div>
          <div className="grid gap-1.5"><Label htmlFor="ac-body">{t('Notes')}</Label><Textarea id="ac-body" rows={3} value={body} maxLength={10000} onChange={(e) => setBody(e.target.value)} /></div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="grid gap-1.5"><Label>{t('Contacts')}</Label><ComboPicker options={org.contacts.map((c) => ({ id: c.id, label: fullName(c), hint: c.contact_role }))} value={contactId} onChange={(v) => setContactId(v.slice(-1))} placeholder={t('Contacts')} /></div>
            <div className="grid gap-1.5"><Label>{t('Project')}</Label><ComboPicker options={org.projects.map((p) => ({ id: p.id, label: p.name }))} value={projectId} onChange={(v) => setProjectId(v.slice(-1))} placeholder={t('Project')} /></div>
          </div>
          <Label className="flex items-center gap-2"><Switch checked={follow} onCheckedChange={setFollow} />{t('Create follow-up task')}</Label>
          {follow && (
            <div className="grid gap-3 rounded-lg border bg-muted/30 p-3">
              <div className="grid gap-1.5"><Label htmlFor="ac-ft">{t('Follow-up title')} *</Label><Input id="ac-ft" value={followTitle} maxLength={200} onChange={(e) => setFollowTitle(e.target.value)} /></div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="grid gap-1.5"><Label htmlFor="ac-due">{t('Due date')}</Label><Input id="ac-due" type="date" value={due} onChange={(e) => setDue(e.target.value)} /></div>
                <div className="grid gap-1.5"><Label>{t('Assignee')}</Label><ComboPicker options={(people ?? []).map((p) => ({ id: p.id, label: p.name }))} value={assignee} onChange={(v) => setAssignee(v.slice(-1))} placeholder={t('Assignee')} /></div>
              </div>
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
