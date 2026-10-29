import { useEffect, useState } from 'react'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ComboPicker } from '@/components/ComboPicker'
import { useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import { CATEGORIES } from '@/lib/portfolio'
import type { CrmOrgRow } from '@/lib/portfolio-types'
import type { OppDetail, Risk } from '@/lib/sales-types'
import type { PersonRow } from '@/lib/types'

const RISKS: Risk[] = ['low', 'medium', 'high']
const NONE = 'none'
const CURRENCY_RE = /^[A-Z]{3}$/

interface Circles {
  circles: { id: string; name: string }[]
}

interface FormState {
  title: string
  description: string
  customer: string[]
  circle: string
  category: string
  risk: Risk
  source: string
  value: string
  currency: string
  probability: string
  effort: string
  close: string
  start: string
  end: string
  owner: string[]
  nextAction: string
  nextDue: string
}

function initialCustomer(opp: OppDetail | null, customerId?: string): string[] {
  if (opp) return [opp.crm_org_id]
  return customerId ? [customerId] : []
}

function initial(opp: OppDetail | null, customerId?: string): FormState {
  return {
    title: opp?.title ?? '',
    description: opp?.description ?? '',
    customer: initialCustomer(opp, customerId),
    circle: opp?.circle_id ?? NONE,
    category: opp?.category ?? 'other',
    risk: opp?.risk ?? 'medium',
    source: opp?.source ?? '',
    value: opp?.value_amount === null || opp?.value_amount === undefined ? '' : String(opp.value_amount),
    currency: opp?.currency ?? 'EUR',
    probability: opp?.probability_manual && opp.probability !== null ? String(opp.probability) : '',
    effort: opp?.effort_days === null || opp?.effort_days === undefined ? '' : String(opp.effort_days),
    close: opp?.expected_close ?? '',
    start: opp?.expected_start ?? '',
    end: opp?.expected_end ?? '',
    owner: opp?.owner_user_id ? [opp.owner_user_id] : [],
    nextAction: opp?.next_action ?? '',
    nextDue: opp?.next_action_due ?? '',
  }
}

export function OpportunityFormDialog({ opp, open, onOpenChange, customerId, onSaved }: Readonly<{
  opp: OppDetail | null
  open: boolean
  onOpenChange: (v: boolean) => void
  customerId?: string
  onSaved?: (id: string) => void
}>) {
  const { t } = useT()
  const act = useAct()
  const { data: orgs } = useGet<CrmOrgRow[]>(open ? '/crm/organizations' : null)
  const { data: people } = useGet<PersonRow[]>(open ? '/people' : null)
  const { data: structure } = useGet<Circles>(open ? '/structure' : null)
  const [f, setF] = useState<FormState>(initial(opp, customerId))
  useEffect(() => {
    if (open) setF(initial(opp, customerId))
  }, [open, opp, customerId])
  const patch = (p: Partial<FormState>) => setF((x) => ({ ...x, ...p }))

  const valueNum = f.value.trim() === '' ? null : Number(f.value)
  const probNum = f.probability.trim() === '' ? null : Number(f.probability)
  const effortNum = f.effort.trim() === '' ? null : Number(f.effort)
  const valueInvalid = valueNum !== null && (Number.isNaN(valueNum) || valueNum < 0)
  const probInvalid = probNum !== null && (!Number.isInteger(probNum) || probNum < 0 || probNum > 100)
  const effortInvalid = effortNum !== null && (Number.isNaN(effortNum) || effortNum < 0)
  const datesInvalid = f.start !== '' && f.end !== '' && f.end < f.start
  const canSave = f.title.trim().length >= 3 && f.customer.length === 1 && CURRENCY_RE.test(f.currency) && !valueInvalid && !probInvalid && !effortInvalid && !datesInvalid

  const save = async () => {
    const body = {
      title: f.title.trim(), description: f.description, crm_org_id: f.customer[0], circle_id: f.circle === NONE ? null : f.circle, category: f.category, risk: f.risk,
      source: f.source.trim() || null, value_amount: valueNum, currency: f.currency, probability: probNum, effort_days: effortNum, expected_close: f.close || null,
      expected_start: f.start || null, expected_end: f.end || null, owner_user_id: f.owner[0] ?? null, next_action: f.nextAction.trim() || null, next_action_due: f.nextDue || null,
    }
    const res = opp ? await act('patch', `/commercial/opportunities/${opp.id}`, body) : await act<{ id: string }>('post', '/commercial/opportunities', body)
    if (!res) return
    onOpenChange(false)
    if (!opp && onSaved) onSaved((res as { id: string }).id)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader><DialogTitle className="font-display text-xl">{opp ? t('Edit opportunity') : t('New opportunity')}</DialogTitle></DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1.5"><Label htmlFor="op-title">{t('Title')} *</Label><Input id="op-title" value={f.title} maxLength={200} onChange={(e) => patch({ title: e.target.value })} autoFocus /></div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="grid gap-1.5">
              <Label>{t('Customer')} *</Label>
              <ComboPicker options={(orgs ?? []).map((o) => ({ id: o.id, label: o.name, hint: o.city }))} value={f.customer} onChange={(v) => patch({ customer: v.slice(-1) })} placeholder={t('Choose customer')} />
            </div>
            <div className="grid gap-1.5">
              <Label>{t('Owner')}</Label>
              <ComboPicker options={(people ?? []).map((p) => ({ id: p.id, label: p.name, hint: p.job_title }))} value={f.owner} onChange={(v) => patch({ owner: v.slice(-1) })} placeholder={t('Owner')} />
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="grid gap-1.5">
              <Label>{t('Category')}</Label>
              <Select value={f.category} onValueChange={(v) => patch({ category: v })}>
                <SelectTrigger aria-label={t('Category')}><SelectValue /></SelectTrigger>
                <SelectContent>{CATEGORIES.map((c) => <SelectItem key={c} value={c}>{t(c)}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label>{t('Risk')}</Label>
              <Select value={f.risk} onValueChange={(v) => patch({ risk: v as Risk })}>
                <SelectTrigger aria-label={t('Risk')}><SelectValue /></SelectTrigger>
                <SelectContent>{RISKS.map((r) => <SelectItem key={r} value={r}>{t(r)}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label>{t('Circle')}</Label>
              <Select value={f.circle} onValueChange={(v) => patch({ circle: v })}>
                <SelectTrigger aria-label={t('Circle')}><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value={NONE}>–</SelectItem>{(structure?.circles ?? []).map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-4">
            <div className="grid gap-1.5 sm:col-span-2"><Label htmlFor="op-value">{t('Expected value')}</Label><Input id="op-value" inputMode="decimal" value={f.value} aria-invalid={valueInvalid} onChange={(e) => patch({ value: e.target.value })} /></div>
            <div className="grid gap-1.5"><Label htmlFor="op-cur">{t('Currency')}</Label><Input id="op-cur" value={f.currency} maxLength={3} aria-invalid={!CURRENCY_RE.test(f.currency)} onChange={(e) => patch({ currency: e.target.value.toUpperCase() })} /></div>
            <div className="grid gap-1.5"><Label htmlFor="op-prob">{t('Probability %')}</Label><Input id="op-prob" inputMode="numeric" value={f.probability} placeholder={t('Stage default')} aria-invalid={probInvalid} onChange={(e) => patch({ probability: e.target.value })} /></div>
          </div>
          <div className="grid gap-3 sm:grid-cols-4">
            <div className="grid gap-1.5"><Label htmlFor="op-effort">{t('Effort (days)')}</Label><Input id="op-effort" inputMode="decimal" value={f.effort} aria-invalid={effortInvalid} onChange={(e) => patch({ effort: e.target.value })} /></div>
            <div className="grid gap-1.5"><Label htmlFor="op-close">{t('Expected decision')}</Label><Input id="op-close" type="date" value={f.close} onChange={(e) => patch({ close: e.target.value })} /></div>
            <div className="grid gap-1.5"><Label htmlFor="op-start">{t('Start')}</Label><Input id="op-start" type="date" value={f.start} onChange={(e) => patch({ start: e.target.value })} /></div>
            <div className="grid gap-1.5"><Label htmlFor="op-end">{t('End')}</Label><Input id="op-end" type="date" value={f.end} aria-invalid={datesInvalid} onChange={(e) => patch({ end: e.target.value })} /></div>
          </div>
          <div className="grid gap-3 sm:grid-cols-[1fr_10rem_10rem]">
            <div className="grid gap-1.5"><Label htmlFor="op-next">{t('Next action')}</Label><Input id="op-next" value={f.nextAction} maxLength={300} onChange={(e) => patch({ nextAction: e.target.value })} /></div>
            <div className="grid gap-1.5"><Label htmlFor="op-due">{t('Due')}</Label><Input id="op-due" type="date" value={f.nextDue} onChange={(e) => patch({ nextDue: e.target.value })} /></div>
            <div className="grid gap-1.5"><Label htmlFor="op-source">{t('Source')}</Label><Input id="op-source" value={f.source} maxLength={40} onChange={(e) => patch({ source: e.target.value })} /></div>
          </div>
          <div className="grid gap-1.5"><Label htmlFor="op-desc">{t('Description')}</Label><Textarea id="op-desc" rows={3} value={f.description} maxLength={10000} onChange={(e) => patch({ description: e.target.value })} /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t('Cancel')}</Button>
          <Button onClick={save} disabled={!canSave}>{t('Save')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
