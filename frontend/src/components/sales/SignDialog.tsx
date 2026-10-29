import { useEffect, useState } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useAct } from '@/lib/hooks'
import { useT } from '@/lib/i18n'

/** Records a signature. Only holders of a signing role may do it; an administrator needs a note. */
export function SignDialog({ endpoint, title, open, onOpenChange }: Readonly<{ endpoint: string; title: string; open: boolean; onOpenChange: (v: boolean) => void }>) {
  const { t } = useT()
  const act = useAct()
  const [signedAt, setSignedAt] = useState('')
  const [name, setName] = useState('')
  const [note, setNote] = useState('')
  useEffect(() => {
    if (open) {
      setSignedAt(new Date().toISOString().slice(0, 10))
      setName('')
      setNote('')
    }
  }, [open])
  const save = async () => {
    const res = await act('post', endpoint, { signed_at: signedAt || null, signatory_name: name.trim() || null, override_note: note.trim() || null })
    if (res) onOpenChange(false)
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="font-display text-xl">{t('Record signature')}</DialogTitle>
          <DialogDescription>{title}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1.5"><Label htmlFor="sg-date">{t('Signed on')}</Label><Input id="sg-date" type="date" value={signedAt} onChange={(e) => setSignedAt(e.target.value)} /></div>
          <div className="grid gap-1.5"><Label htmlFor="sg-name">{t('Signatory')}</Label><Input id="sg-name" value={name} maxLength={160} onChange={(e) => setName(e.target.value)} /></div>
          <div className="grid gap-1.5">
            <Label htmlFor="sg-note">{t('Administrator note')}</Label>
            <Textarea id="sg-note" rows={2} value={note} maxLength={2000} onChange={(e) => setNote(e.target.value)} />
            <p className="text-xs text-muted-foreground">{t('Only needed if you do not hold a role that may sign. Only administrators can sign without such a role.')}</p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t('Cancel')}</Button>
          <Button onClick={save}>{t('Record signature')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
