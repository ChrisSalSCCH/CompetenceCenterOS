import { useEffect, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ComboPicker } from '@/components/ComboPicker'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState, InfoNotice, LoadingBlock, PageHeader, Pill, Section } from '@/components/kit'
import { useSession } from '@/contexts/SessionContext'
import { fmtDate, useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import { CATEGORIES } from '@/lib/portfolio'
import { OPEN_STAGES, STAGE_LABEL, fmtMoney } from '@/lib/sales'
import type { CalcUnit, DecisionRule, RateRow, Stage } from '@/lib/sales-types'

const ANY = 'any'
const TYPES: DecisionRule['decision_type'][] = ['bid', 'proposal_approval', 'contract_signature', 'nda_signature']
const TYPE_LABEL: Record<string, string> = { bid: 'Bid / No-Bid', proposal_approval: 'Proposal approval', contract_signature: 'Contract signature', nda_signature: 'NDA signature' }
const UNITS: CalcUnit[] = ['day', 'hour', 'piece', 'flat']

interface StageConfig {
  probabilities: Record<Stage, number>
  defaults: Record<Stage, number>
}

interface Structure {
  roles: { id: string; name: string; circle_id: string }[]
  circles: { id: string; name: string }[]
}

function Probabilities({ canEdit }: Readonly<{ canEdit: boolean }>) {
  const { t } = useT()
  const act = useAct()
  const { data } = useGet<StageConfig>('/commercial/stage-config')
  const [values, setValues] = useState<Record<string, string>>({})
  useEffect(() => {
    if (data) setValues(Object.fromEntries(OPEN_STAGES.map((s) => [s, String(data.probabilities[s])])))
  }, [data])
  const invalid = OPEN_STAGES.some((s) => {
    const n = Number(values[s])
    return values[s] === '' || !Number.isInteger(n) || n < 0 || n > 100
  })
  const save = () => act('put', '/commercial/stage-config', { probabilities: Object.fromEntries(OPEN_STAGES.map((s) => [s, Number(values[s])])) })
  return (
    <Section title={t('Probability per stage')}>
      <p className="mb-3 text-xs text-muted-foreground">{t('Used for the weighted pipeline unless an opportunity has its own probability. Won is always 100%, lost 0%.')}</p>
      <div className="grid gap-3 sm:grid-cols-5">
        {OPEN_STAGES.map((s) => (
          <div key={s} className="grid gap-1.5">
            <Label htmlFor={`prob-${s}`}>{t(STAGE_LABEL[s])}</Label>
            <Input id={`prob-${s}`} inputMode="numeric" value={values[s] ?? ''} disabled={!canEdit} aria-invalid={values[s] === '' || Number(values[s]) > 100} onChange={(e) => setValues((v) => ({ ...v, [s]: e.target.value }))} />
          </div>
        ))}
      </div>
      {canEdit && <Button className="mt-3" onClick={save} disabled={invalid}>{t('Save')}</Button>}
    </Section>
  )
}

function RuleDialog({ open, onOpenChange }: Readonly<{ open: boolean; onOpenChange: (v: boolean) => void }>) {
  const { t } = useT()
  const act = useAct()
  const { data: structure } = useGet<Structure>(open ? '/structure' : null)
  const [type, setType] = useState<string>('bid')
  const [label, setLabel] = useState('')
  const [role, setRole] = useState<string[]>([])
  const [category, setCategory] = useState(ANY)
  const [risk, setRisk] = useState(ANY)
  const [min, setMin] = useState('')
  const [max, setMax] = useState('')
  const [step, setStep] = useState('1')
  useEffect(() => {
    if (open) {
      setType('bid')
      setLabel('')
      setRole([])
      setCategory(ANY)
      setRisk(ANY)
      setMin('')
      setMax('')
      setStep('1')
    }
  }, [open])
  const lo = min.trim() === '' ? null : Number(min)
  const hi = max.trim() === '' ? null : Number(max)
  const rangeInvalid = (lo !== null && (Number.isNaN(lo) || lo < 0)) || (hi !== null && (Number.isNaN(hi) || hi < 0)) || (lo !== null && hi !== null && hi < lo)
  const stepNum = Number(step)
  const stepInvalid = !Number.isInteger(stepNum) || stepNum < 1 || stepNum > 20
  const save = async () => {
    const res = await act('post', '/commercial/decision-rules', {
      decision_type: type, label: label.trim(), role_id: role[0], category: category === ANY ? null : category, risk: risk === ANY ? null : risk, min_value: lo, max_value: hi, step_order: stepNum,
    })
    if (res) onOpenChange(false)
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader><DialogTitle className="font-display text-xl">{t('New decision rule')}</DialogTitle></DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1.5">
            <Label>{t('Decision')}</Label>
            <Select value={type} onValueChange={setType}>
              <SelectTrigger aria-label={t('Decision')}><SelectValue /></SelectTrigger>
              <SelectContent>{TYPES.map((x) => <SelectItem key={x} value={x}>{t(TYPE_LABEL[x])}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="grid gap-1.5"><Label htmlFor="dr-label">{t('Label')} *</Label><Input id="dr-label" value={label} maxLength={120} onChange={(e) => setLabel(e.target.value)} /></div>
          <div className="grid gap-1.5"><Label>{t('Role that decides')} *</Label><ComboPicker options={(structure?.roles ?? []).map((r) => ({ id: r.id, label: r.name, hint: structure?.circles.find((c) => c.id === r.circle_id)?.name }))} value={role} onChange={(v) => setRole(v.slice(-1))} placeholder={t('Choose role')} /></div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="grid gap-1.5">
              <Label>{t('Category')}</Label>
              <Select value={category} onValueChange={setCategory}>
                <SelectTrigger aria-label={t('Category')}><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value={ANY}>{t('Any')}</SelectItem>{CATEGORIES.map((c) => <SelectItem key={c} value={c}>{t(c)}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label>{t('Risk')}</Label>
              <Select value={risk} onValueChange={setRisk}>
                <SelectTrigger aria-label={t('Risk')}><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value={ANY}>{t('Any')}</SelectItem>{['low', 'medium', 'high'].map((r) => <SelectItem key={r} value={r}>{t(r)}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="grid gap-1.5"><Label htmlFor="dr-min">{t('Value from')}</Label><Input id="dr-min" inputMode="decimal" value={min} aria-invalid={rangeInvalid} onChange={(e) => setMin(e.target.value)} /></div>
            <div className="grid gap-1.5"><Label htmlFor="dr-max">{t('Value up to')}</Label><Input id="dr-max" inputMode="decimal" value={max} aria-invalid={rangeInvalid} onChange={(e) => setMax(e.target.value)} /></div>
            <div className="grid gap-1.5"><Label htmlFor="dr-step">{t('Step')}</Label><Input id="dr-step" inputMode="numeric" value={step} aria-invalid={stepInvalid} onChange={(e) => setStep(e.target.value)} /></div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t('Cancel')}</Button>
          <Button onClick={save} disabled={label.trim().length < 2 || role.length === 0 || rangeInvalid || stepInvalid}>{t('Create')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Rules({ canEdit }: Readonly<{ canEdit: boolean }>) {
  const { t, lang } = useT()
  const act = useAct()
  const { data, isLoading } = useGet<DecisionRule[]>('/commercial/decision-rules')
  const [adding, setAdding] = useState(false)
  return (
    <Section title={t('Decision rules')} action={canEdit ? <Button size="sm" onClick={() => setAdding(true)}><Plus className="mr-1 h-4 w-4" aria-hidden />{t('New rule')}</Button> : undefined}>
      <div className="mb-3"><InfoNotice>{t('Authority comes from the role a person holds, never from a job title. Without a matching rule, only an administrator can decide - with a recorded note.')}</InfoNotice></div>
      {isLoading && <LoadingBlock rows={2} />}
      {data && data.length === 0 && <EmptyState title={t('No decision rules yet')} hint={t('Until rules exist, every decision is marked as needing clarification.')} />}
      {data && data.length > 0 && (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader><TableRow><TableHead>{t('Decision')}</TableHead><TableHead>{t('Label')}</TableHead><TableHead>{t('Role')}</TableHead><TableHead>{t('Applies to')}</TableHead><TableHead>{t('Step')}</TableHead><TableHead /></TableRow></TableHeader>
            <TableBody>
              {data.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="text-sm">{t(TYPE_LABEL[r.decision_type])}</TableCell>
                  <TableCell className="text-sm">{r.label}</TableCell>
                  <TableCell className="text-sm">{r.role_name} <Pill tone={r.holders > 0 ? 'forest' : 'danger'}>{r.holders > 0 ? r.holders : t('unfilled')}</Pill></TableCell>
                  <TableCell className="text-xs text-muted-foreground">{[r.category && t(r.category), r.risk && `${t('Risk')}: ${t(r.risk)}`, r.min_value !== null && `≥ ${fmtMoney(r.min_value, 'EUR', lang)}`, r.max_value !== null && `≤ ${fmtMoney(r.max_value, 'EUR', lang)}`].filter(Boolean).join(' · ') || t('Everything')}</TableCell>
                  <TableCell className="text-sm">{r.step_order}</TableCell>
                  <TableCell>{canEdit && <ConfirmDialog trigger={<Button variant="ghost" size="icon" aria-label={t('Remove')}><Trash2 className="h-4 w-4" /></Button>} title={t('Remove')} description={r.label} onConfirm={() => act('delete', `/commercial/decision-rules/${r.id}`)} />}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      <RuleDialog open={adding} onOpenChange={setAdding} />
    </Section>
  )
}

function RateDialog({ open, onOpenChange }: Readonly<{ open: boolean; onOpenChange: (v: boolean) => void }>) {
  const { t } = useT()
  const act = useAct()
  const [name, setName] = useState('')
  const [role, setRole] = useState('')
  const [unit, setUnit] = useState<string>('day')
  const [cost, setCost] = useState('0')
  const [sell, setSell] = useState('0')
  const [currency, setCurrency] = useState('EUR')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  useEffect(() => {
    if (open) {
      setName('')
      setRole('')
      setUnit('day')
      setCost('0')
      setSell('0')
      setCurrency('EUR')
      setFrom(new Date().toISOString().slice(0, 10))
      setTo('')
    }
  }, [open])
  const bad = (s: string) => s.trim() === '' || Number.isNaN(Number(s)) || Number(s) < 0
  const datesInvalid = from !== '' && to !== '' && to < from
  const save = async () => {
    const res = await act('post', '/commercial/rates', { name: name.trim(), role_label: role.trim(), unit, cost_rate: Number(cost), sell_rate: Number(sell), currency, valid_from: from || null, valid_to: to || null })
    if (res) onOpenChange(false)
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader><DialogTitle className="font-display text-xl">{t('New price list entry')}</DialogTitle></DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="grid gap-1.5"><Label htmlFor="rt-name">{t('Name')} *</Label><Input id="rt-name" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} /></div>
            <div className="grid gap-1.5"><Label htmlFor="rt-role">{t('Role label')} *</Label><Input id="rt-role" value={role} maxLength={120} onChange={(e) => setRole(e.target.value)} /></div>
          </div>
          <div className="grid gap-3 sm:grid-cols-4">
            <div className="grid gap-1.5">
              <Label>{t('Unit')}</Label>
              <Select value={unit} onValueChange={setUnit}>
                <SelectTrigger aria-label={t('Unit')}><SelectValue /></SelectTrigger>
                <SelectContent>{UNITS.map((u) => <SelectItem key={u} value={u}>{t(u)}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5"><Label htmlFor="rt-cost">{t('Cost rate')}</Label><Input id="rt-cost" inputMode="decimal" value={cost} aria-invalid={bad(cost)} onChange={(e) => setCost(e.target.value)} /></div>
            <div className="grid gap-1.5"><Label htmlFor="rt-sell">{t('Sell rate')}</Label><Input id="rt-sell" inputMode="decimal" value={sell} aria-invalid={bad(sell)} onChange={(e) => setSell(e.target.value)} /></div>
            <div className="grid gap-1.5"><Label htmlFor="rt-cur">{t('Currency')}</Label><Input id="rt-cur" value={currency} maxLength={3} onChange={(e) => setCurrency(e.target.value.toUpperCase())} /></div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="grid gap-1.5"><Label htmlFor="rt-from">{t('Valid from')}</Label><Input id="rt-from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></div>
            <div className="grid gap-1.5"><Label htmlFor="rt-to">{t('Valid until')}</Label><Input id="rt-to" type="date" value={to} aria-invalid={datesInvalid} onChange={(e) => setTo(e.target.value)} /></div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t('Cancel')}</Button>
          <Button onClick={save} disabled={name.trim().length < 2 || role.trim().length < 2 || bad(cost) || bad(sell) || datesInvalid || currency.length !== 3}>{t('Create')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Rates({ canEdit }: Readonly<{ canEdit: boolean }>) {
  const { t, lang } = useT()
  const act = useAct()
  const { data, isLoading } = useGet<RateRow[]>('/commercial/rates')
  const [adding, setAdding] = useState(false)
  return (
    <Section title={t('Price list')} action={canEdit ? <Button size="sm" onClick={() => setAdding(true)}><Plus className="mr-1 h-4 w-4" aria-hidden />{t('New entry')}</Button> : undefined}>
      {isLoading && <LoadingBlock rows={2} />}
      {data && data.length === 0 && <EmptyState title={t('No price list entries yet')} hint={t('Entries have a validity period; a proposal only accepts entries that are valid today.')} />}
      {data && data.length > 0 && (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader><TableRow><TableHead>{t('Name')}</TableHead><TableHead>{t('Role label')}</TableHead><TableHead>{t('Unit')}</TableHead><TableHead className="text-right">{t('Cost rate')}</TableHead><TableHead className="text-right">{t('Sell rate')}</TableHead><TableHead>{t('Valid')}</TableHead><TableHead /></TableRow></TableHeader>
            <TableBody>
              {data.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="text-sm">{r.name}</TableCell>
                  <TableCell className="text-sm">{r.role_label}</TableCell>
                  <TableCell className="text-sm">{t(r.unit)}</TableCell>
                  <TableCell className="text-right text-sm">{fmtMoney(r.cost_rate, r.currency, lang)}</TableCell>
                  <TableCell className="text-right text-sm">{fmtMoney(r.sell_rate, r.currency, lang)}</TableCell>
                  <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{fmtDate(r.valid_from, lang)} – {r.valid_to ? fmtDate(r.valid_to, lang) : t('open')}</TableCell>
                  <TableCell>{canEdit && <ConfirmDialog trigger={<Button variant="ghost" size="icon" aria-label={t('Remove')}><Trash2 className="h-4 w-4" /></Button>} title={t('Remove')} description={r.name} onConfirm={() => act('delete', `/commercial/rates/${r.id}`)} />}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      <RateDialog open={adding} onOpenChange={setAdding} />
    </Section>
  )
}

export default function SalesSettings() {
  const { t } = useT()
  const { isAdmin, isObserver } = useSession()
  return (
    <>
      <PageHeader title={t('Sales settings')} subtitle={isAdmin ? t('Probabilities, who may decide what, and the price list.') : t('Read-only: only administrators change these settings.')} />
      <div className="space-y-4">
        <Probabilities canEdit={isAdmin} />
        <Rules canEdit={isAdmin} />
        {!isObserver && <Rates canEdit={isAdmin} />}
      </div>
    </>
  )
}
