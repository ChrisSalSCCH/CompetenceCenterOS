import { useEffect, useState } from 'react'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { useT } from '@/lib/i18n'

/** Asks for the reason when an opportunity is lost. */
export function LostReasonDialog({ open, title, onOpenChange, onConfirm }: Readonly<{
  open: boolean
  title: string
  onOpenChange: (v: boolean) => void
  onConfirm: (reason: string) => void
}>) {
  const { t } = useT()
  const [reason, setReason] = useState('')
  useEffect(() => {
    if (open) setReason('')
  }, [open])
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="font-display text-xl">{t('Mark as lost')}</DialogTitle>
          <DialogDescription>{title}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-1.5">
          <Label htmlFor="lost-reason">{t('Reason')} *</Label>
          <Textarea id="lost-reason" rows={3} value={reason} maxLength={2000} onChange={(e) => setReason(e.target.value)} autoFocus />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t('Cancel')}</Button>
          <Button variant="destructive" disabled={reason.trim().length < 3} onClick={() => { onConfirm(reason.trim()); onOpenChange(false) }}>{t('Mark as lost')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
