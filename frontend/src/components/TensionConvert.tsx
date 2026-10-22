import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import type { PersonRow, Structure } from '@/lib/types'

export type ConvertTarget = 'task' | 'project' | 'proposal' | 'decision' | 'resolution'

export interface ConvertableTension {
  id: string
  title: string
  description: string
  circle_id: string | null
}

const HELP: Record<ConvertTarget, string> = {
  task: 'A single next action for one person.',
  project: 'An outcome that needs several steps and an owning role.',
  proposal: 'A change to roles, domains, policies or circles - goes through governance.',
  decision: 'Record a decision that resolves the tension.',
  resolution: 'Document how the tension was resolved without further work.',
}

export function TensionConvertDialog({ tension, target, onClose, meetingId }: Readonly<{ tension: ConvertableTension | null; target: ConvertTarget; onClose: () => void; meetingId?: string }>) {
  const { t } = useT()
  const act = useAct()
  const navigate = useNavigate()
  const open = tension !== null
  const { data: structure } = useGet<Structure>(open ? '/structure' : null)
  const { data: people } = useGet<PersonRow[]>(open && target === 'task' ? '/people' : null)
  const [title, setTitle] = useState('')
  const [note, setNote] = useState('')
  const [assignee, setAssignee] = useState('')
  const [due, setDue] = useState('')
  const [circle, setCircle] = useState('')
  const [role, setRole] = useState('')

  useEffect(() => {
    if (tension) {
      setTitle(tension.title)
      setNote('')
      setAssignee('')
      setDue('')
      setCircle(tension.circle_id ?? '')
      setRole('')
    }
  }, [tension])

  if (!tension) return null
  const roles = (structure?.roles ?? []).filter((r) => !circle || r.circle_id === circle)

  const save = async () => {
    const res = await act<{ outcome_ref_id: string }>('post', `/tensions/${tension.id}/convert`, {
      to: target,
      title: title.trim() || undefined,
      note: note.trim() || undefined,
      assignee_id: assignee || undefined,
      role_id: role || undefined,
      circle_id: circle || undefined,
      due_date: due || undefined,
      meeting_id: meetingId,
    })
    if (!res) return
    onClose()
    if (target === 'proposal') {
      toast.success(t('Draft proposal created - add the proposed modifications.'))
      navigate(`/governance/proposals/new?edit=${res.outcome_ref_id}`)
    } else {
      toast.success(t('Tension processed.'))
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="font-display text-xl">{t(`Create ${target}`)}</DialogTitle>
          <DialogDescription>{t(HELP[target])}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          {target !== 'resolution' && (
            <div className="grid gap-1.5"><Label htmlFor="cv-title">{t('Title')}</Label><Input id="cv-title" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} /></div>
          )}
          <div className="grid gap-1.5">
            <Label htmlFor="cv-note">{target === 'resolution' ? t('How was it resolved?') : t('Notes')}</Label>
            <Textarea id="cv-note" rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
          </div>
          {target === 'task' && (
            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-1.5">
                <Label>{t('Assignee')}</Label>
                <Select value={assignee} onValueChange={setAssignee}>
                  <SelectTrigger aria-label={t('Assignee')}><SelectValue placeholder={t('Me')} /></SelectTrigger>
                  <SelectContent>{(people ?? []).map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="grid gap-1.5"><Label htmlFor="cv-due">{t('Due date')}</Label><Input id="cv-due" type="date" value={due} onChange={(e) => setDue(e.target.value)} /></div>
            </div>
          )}
          {(target === 'project' || target === 'proposal') && (
            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-1.5">
                <Label>{t('Circle')}</Label>
                <Select value={circle} onValueChange={(v) => { setCircle(v); setRole('') }}>
                  <SelectTrigger aria-label={t('Circle')}><SelectValue placeholder={t('Choose a circle.')} /></SelectTrigger>
                  <SelectContent>{(structure?.circles ?? []).map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              {target === 'project' && (
                <div className="grid gap-1.5">
                  <Label>{t('Owning role')}</Label>
                  <Select value={role} onValueChange={setRole}>
                    <SelectTrigger aria-label={t('Owning role')}><SelectValue placeholder={t('Choose a role')} /></SelectTrigger>
                    <SelectContent>{roles.map((r) => <SelectItem key={r.id} value={r.id}>{r.name}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
              )}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{t('Cancel')}</Button>
          <Button onClick={save} disabled={target === 'resolution' ? !note.trim() : !title.trim() || ((target === 'project' || target === 'proposal') && !circle)}>{t('Confirm')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
