import { useEffect, useState } from 'react'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { ComboPicker } from '@/components/ComboPicker'
import { useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import type { CrmOrgRow } from '@/lib/portfolio-types'

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/
const PHONE_RE = /^[0-9+()\-./ ]{3,40}$/

export function ContactFormDialog({ open, onOpenChange, presetOrgId }: Readonly<{ open: boolean; onOpenChange: (v: boolean) => void; presetOrgId?: string }>) {
  const { t } = useT()
  const act = useAct()
  const { data: orgs } = useGet<CrmOrgRow[]>(open ? '/crm/organizations' : null)
  const [first, setFirst] = useState('')
  const [last, setLast] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [title, setTitle] = useState('')
  const [role, setRole] = useState('')
  const [orgIds, setOrgIds] = useState<string[]>([])
  const [notes, setNotes] = useState('')

  useEffect(() => {
    if (open) {
      setFirst('')
      setLast('')
      setEmail('')
      setPhone('')
      setTitle('')
      setRole('')
      setNotes('')
      setOrgIds(presetOrgId ? [presetOrgId] : [])
    }
  }, [open, presetOrgId])

  const emailInvalid = email.trim() !== '' && !EMAIL_RE.test(email.trim())
  const phoneInvalid = phone.trim() !== '' && !PHONE_RE.test(phone.trim())
  const canSave = first.trim() !== '' && last.trim() !== '' && !emailInvalid && !phoneInvalid

  const save = async () => {
    const res = await act('post', '/crm/contacts', {
      first_name: first.trim(), last_name: last.trim(), email: email.trim() || null, phone: phone.trim() || null, job_title: title.trim() || null, notes,
      orgs: orgIds.map((id, i) => ({ crm_org_id: id, contact_role: role.trim() || null, is_primary: i === 0 })),
    })
    if (res) onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader><DialogTitle className="font-display text-xl">{t('New contact')}</DialogTitle></DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="grid gap-1.5"><Label htmlFor="ct-first">{t('First name')} *</Label><Input id="ct-first" value={first} maxLength={100} onChange={(e) => setFirst(e.target.value)} autoFocus /></div>
            <div className="grid gap-1.5"><Label htmlFor="ct-last">{t('Last name')} *</Label><Input id="ct-last" value={last} maxLength={100} onChange={(e) => setLast(e.target.value)} /></div>
            <div className="grid gap-1.5"><Label htmlFor="ct-mail">{t('Email')}</Label><Input id="ct-mail" type="email" value={email} maxLength={254} aria-invalid={emailInvalid} onChange={(e) => setEmail(e.target.value)} /></div>
            <div className="grid gap-1.5"><Label htmlFor="ct-phone">{t('Phone')}</Label><Input id="ct-phone" value={phone} maxLength={40} aria-invalid={phoneInvalid} onChange={(e) => setPhone(e.target.value)} /></div>
            <div className="grid gap-1.5"><Label htmlFor="ct-title">{t('Job title')}</Label><Input id="ct-title" value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} /></div>
            <div className="grid gap-1.5"><Label htmlFor="ct-role">{t('Contact role')}</Label><Input id="ct-role" value={role} maxLength={60} onChange={(e) => setRole(e.target.value)} /></div>
          </div>
          <div className="grid gap-1.5">
            <Label>{t('Organizations')}</Label>
            <ComboPicker multiple options={(orgs ?? []).map((o) => ({ id: o.id, label: o.name, hint: o.city }))} value={orgIds} onChange={setOrgIds} placeholder={t('Organizations')} />
            <p className="text-xs text-muted-foreground">{t('Primary contact')}: {orgs?.find((o) => o.id === orgIds[0])?.name ?? '–'}</p>
          </div>
          <div className="grid gap-1.5"><Label htmlFor="ct-notes">{t('Notes')}</Label><Textarea id="ct-notes" rows={2} value={notes} maxLength={5000} onChange={(e) => setNotes(e.target.value)} /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t('Cancel')}</Button>
          <Button onClick={save} disabled={!canSave}>{t('Create')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
