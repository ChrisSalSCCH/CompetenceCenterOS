import { useEffect, useState } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import type { Structure } from '@/lib/types'

const NONE = 'none'
const CONTEXTS = ['circle', 'role', 'project', 'responsibility', 'process']

export function TensionDialog({ open, onOpenChange, circleId }: Readonly<{ open: boolean; onOpenChange: (v: boolean) => void; circleId?: string }>) {
  const { t } = useT()
  const act = useAct()
  const { data } = useGet<Structure>(open ? '/structure' : null)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [context, setContext] = useState('circle')
  const [circle, setCircle] = useState(NONE)
  const [role, setRole] = useState(NONE)
  const [label, setLabel] = useState('')
  const [priority, setPriority] = useState('medium')

  useEffect(() => {
    if (open) {
      setTitle('')
      setDescription('')
      setContext('circle')
      setCircle(circleId ?? NONE)
      setRole(NONE)
      setLabel('')
      setPriority('medium')
    }
  }, [open, circleId])

  const roles = (data?.roles ?? []).filter((r) => circle === NONE || r.circle_id === circle)

  const save = async () => {
    const res = await act('post', '/tensions', {
      title: title.trim(),
      description,
      context_type: context,
      circle_id: circle === NONE ? null : circle,
      role_id: role === NONE ? null : role,
      context_label: label.trim() || null,
      priority,
    })
    if (res) onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="font-display text-xl">{t('Capture a tension')}</DialogTitle>
          <DialogDescription>{t('A tension is a gap between how things are and how they could be. Capture it now, process it later.')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="t-title">{t('Title')}</Label>
            <Input id="t-title" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} autoFocus />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="t-desc">{t('Description')}</Label>
            <Textarea id="t-desc" rows={3} value={description} maxLength={5000} onChange={(e) => setDescription(e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5">
              <Label>{t('Relates to')}</Label>
              <Select value={context} onValueChange={setContext}>
                <SelectTrigger aria-label={t('Relates to')}><SelectValue /></SelectTrigger>
                <SelectContent>{CONTEXTS.map((c) => <SelectItem key={c} value={c}>{t(c)}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label>{t('Priority')}</Label>
              <Select value={priority} onValueChange={setPriority}>
                <SelectTrigger aria-label={t('Priority')}><SelectValue /></SelectTrigger>
                <SelectContent>{['low', 'medium', 'high'].map((c) => <SelectItem key={c} value={c}>{t(c)}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5">
              <Label>{t('Circle')}</Label>
              <Select value={circle} onValueChange={(v) => { setCircle(v); setRole(NONE) }}>
                <SelectTrigger aria-label={t('Circle')}><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE}>–</SelectItem>
                  {(data?.circles ?? []).map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label>{t('Role')}</Label>
              <Select value={role} onValueChange={setRole}>
                <SelectTrigger aria-label={t('Role')}><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={NONE}>–</SelectItem>
                  {roles.map((r) => <SelectItem key={r.id} value={r.id}>{r.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>
          {(context === 'responsibility' || context === 'process' || context === 'project') && (
            <div className="grid gap-1.5">
              <Label htmlFor="t-label">{t('Which responsibility, process or project?')}</Label>
              <Input id="t-label" value={label} maxLength={300} onChange={(e) => setLabel(e.target.value)} />
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t('Cancel')}</Button>
          <Button onClick={save} disabled={title.trim().length < 3}>{t('Capture tension')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
