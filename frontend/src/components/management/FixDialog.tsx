import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import type { FixAction, QualityIssue } from '@/lib/management-types'
import type { PersonRow } from '@/lib/types'

const PERSON_ACTIONS: FixAction[] = ['set_owner', 'set_manager']

function needsPerson(action: string | undefined): boolean {
  return PERSON_ACTIONS.includes(action as FixAction)
}

export function FixDialog({ issue, onClose }: Readonly<{ issue: QualityIssue | null; onClose: () => void }>) {
  const { t } = useT()
  const act = useAct()
  const action = issue?.fix?.action
  const { data: people } = useGet<PersonRow[]>(needsPerson(action) ? '/people' : null)
  const [userId, setUserId] = useState('')
  const [text, setText] = useState('')
  const [day, setDay] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setUserId('')
    setText('')
    setDay('')
  }, [issue?.id])

  if (!issue?.fix) return null

  const valid = (needsPerson(action) && userId !== '') || (action === 'set_next_action' && text.trim() !== '') || (action === 'set_close_date' && day !== '')

  const submit = async () => {
    setBusy(true)
    const res = await act('post', '/management/data-quality/fix', {
      action,
      entity_id: issue.entity_id,
      user_id: userId || null,
      text: text.trim() || null,
      day: day || null,
    })
    setBusy(false)
    if (res) onClose()
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('Fix finding')}</DialogTitle>
          <DialogDescription>{issue.label} – {t(issue.message)}</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          {needsPerson(action) && (
            <div className="space-y-1.5">
              <Label htmlFor="fix-person">{action === 'set_manager' ? t('Project manager') : t('Owner')}</Label>
              <Select value={userId} onValueChange={setUserId}>
                <SelectTrigger id="fix-person"><SelectValue placeholder={t('Choose a person')} /></SelectTrigger>
                <SelectContent>{(people ?? []).map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          )}
          {action === 'set_next_action' && (
            <>
              <div className="space-y-1.5">
                <Label htmlFor="fix-text">{t('Next action')}</Label>
                <Input id="fix-text" maxLength={300} value={text} onChange={(e) => setText(e.target.value)} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="fix-due">{t('Due')}</Label>
                <Input id="fix-due" type="date" value={day} onChange={(e) => setDay(e.target.value)} />
              </div>
            </>
          )}
          {action === 'set_close_date' && (
            <div className="space-y-1.5">
              <Label htmlFor="fix-day">{t('Expected decision')}</Label>
              <Input id="fix-day" type="date" value={day} onChange={(e) => setDay(e.target.value)} />
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{t('Cancel')}</Button>
          <Button disabled={!valid || busy} onClick={() => void submit()}>{t('Save')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
