import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { LoadingBlock } from '@/components/kit'
import { useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import { fmtMoney } from '@/lib/sales'
import type { CompareData, VersionSummary } from '@/lib/sales-types'

const TOTAL_LABEL: Record<string, string> = { price_total: 'Total price', cost_total: 'Cost', effort_days: 'Effort' }

export function NewProposalDialog({ opportunityId, defaultTitle, currency, open, onOpenChange }: Readonly<{
  opportunityId: string
  defaultTitle: string
  currency: string
  open: boolean
  onOpenChange: (v: boolean) => void
}>) {
  const { t } = useT()
  const act = useAct()
  const navigate = useNavigate()
  const [title, setTitle] = useState('')
  const [validUntil, setValidUntil] = useState('')
  useEffect(() => {
    if (open) {
      setTitle(defaultTitle)
      setValidUntil('')
    }
  }, [open, defaultTitle])
  const create = async () => {
    const res = await act<{ id: string }>('post', '/commercial/proposals', { opportunity_id: opportunityId, title: title.trim(), valid_until: validUntil || null, currency })
    if (!res) return
    onOpenChange(false)
    navigate(`/sales/proposals/${res.id}`)
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader><DialogTitle className="font-display text-xl">{t('New proposal')}</DialogTitle></DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1.5"><Label htmlFor="np-title">{t('Title')} *</Label><Input id="np-title" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} autoFocus /></div>
          <div className="grid gap-1.5"><Label htmlFor="np-valid">{t('Valid until')}</Label><Input id="np-valid" type="date" value={validUntil} onChange={(e) => setValidUntil(e.target.value)} /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t('Cancel')}</Button>
          <Button onClick={create} disabled={title.trim().length < 3}>{t('Create')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function CompareDialog({ proposalId, versions, open, onOpenChange }: Readonly<{ proposalId: string; versions: VersionSummary[]; open: boolean; onOpenChange: (v: boolean) => void }>) {
  const { t, lang } = useT()
  const [a, setA] = useState('')
  const [b, setB] = useState('')
  useEffect(() => {
    if (open && versions.length >= 2) {
      setA(versions[1].id)
      setB(versions[0].id)
    }
  }, [open, versions])
  const ready = a !== '' && b !== '' && a !== b
  const { data, isLoading } = useGet<CompareData>(open && ready ? `/commercial/proposals/${proposalId}/compare` : null, { a, b })
  const currency = versions[0]?.currency ?? 'EUR'
  const picker = (value: string, set: (v: string) => void, label: string) => (
    <Select value={value} onValueChange={set}>
      <SelectTrigger aria-label={label}><SelectValue placeholder={label} /></SelectTrigger>
      <SelectContent>{versions.map((v) => <SelectItem key={v.id} value={v.id}>v{v.version_no}{v.label ? ` · ${v.label}` : ''}</SelectItem>)}</SelectContent>
    </Select>
  )
  const list = (title: string, items: string[]) => items.length > 0 && <div><dt className="font-mono-label text-muted-foreground">{title}</dt><dd className="text-sm">{items.join(', ')}</dd></div>
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader><DialogTitle className="font-display text-xl">{t('Compare versions')}</DialogTitle></DialogHeader>
        <div className="grid gap-3 sm:grid-cols-2">{picker(a, setA, t('From version'))}{picker(b, setB, t('To version'))}</div>
        {isLoading && <LoadingBlock rows={2} />}
        {data && (
          <dl className="grid gap-3">
            {Object.entries(data.totals).map(([key, v]) => (
              <div key={key} className="flex items-baseline justify-between gap-3 border-b pb-1">
                <dt className="text-sm">{t(TOTAL_LABEL[key] ?? key)}</dt>
                <dd className="text-sm">{key === 'effort_days' ? `${v.from} → ${v.to}` : `${fmtMoney(v.from, currency, lang)} → ${fmtMoney(v.to, currency, lang)}`} <span className="text-xs text-muted-foreground">({v.delta > 0 ? '+' : ''}{key === 'effort_days' ? v.delta : fmtMoney(v.delta, currency, lang)})</span></dd>
              </div>
            ))}
            {list(t('Changed text fields'), data.changed_fields.map((f) => t(f.replaceAll('_', ' '))))}
            {list(t('Work packages added'), data.work_packages_added)}
            {list(t('Work packages removed'), data.work_packages_removed)}
            {list(t('Lines added'), data.lines_added)}
            {list(t('Lines removed'), data.lines_removed)}
          </dl>
        )}
      </DialogContent>
    </Dialog>
  )
}
