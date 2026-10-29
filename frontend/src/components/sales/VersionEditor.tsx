import { useEffect, useMemo, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { Pill, Section } from '@/components/kit'
import { useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import { calcTotals, fmtMoney } from '@/lib/sales'
import type { CalcUnit, LineKind, RateRow, VersionData } from '@/lib/sales-types'

const KINDS: LineKind[] = ['labor', 'material', 'travel', 'external', 'other']
const UNITS: CalcUnit[] = ['day', 'hour', 'piece', 'flat']
const NO_RATE = 'none'
const CURRENCY_RE = /^[A-Z]{3}$/

interface WpDraft { key: string; code: string; title: string; description: string; milestone_title: string; milestone_due: string; start_date: string; end_date: string }
interface LineDraft {
  key: string
  line_kind: LineKind
  description: string
  role_label: string
  rate_entry_id: string
  quantity: string
  unit: CalcUnit
  unit_cost: string
  unit_price: string
  currency: string
  wp: string
}

let counter = 0
const nextKey = (): string => `k${++counter}`
const num = (s: string): number => (s.trim() === '' || Number.isNaN(Number(s)) ? 0 : Number(s))

function wpsFrom(v: VersionData): WpDraft[] {
  return v.work_packages.map((w) => ({
    key: w.id, code: w.code, title: w.title, description: w.description, milestone_title: w.milestone_title ?? '', milestone_due: w.milestone_due ?? '',
    start_date: w.start_date ?? '', end_date: w.end_date ?? '',
  }))
}

function linesFrom(v: VersionData): LineDraft[] {
  return v.lines.map((l) => ({
    key: l.id, line_kind: l.line_kind, description: l.description, role_label: l.role_label ?? '', rate_entry_id: l.rate_entry_id ?? '',
    quantity: String(l.quantity), unit: l.unit, unit_cost: l.unit_cost === null ? '0' : String(l.unit_cost), unit_price: l.unit_price === null ? '0' : String(l.unit_price),
    currency: l.currency, wp: l.work_package_id ? String(v.work_packages.findIndex((w) => w.id === l.work_package_id)) : '',
  }))
}

export function VersionEditor({ version, readOnly, onSaved, registerSave }: Readonly<{
  version: VersionData
  readOnly: boolean
  onSaved: () => void
  registerSave?: (save: (() => Promise<boolean>) | null) => void
}>) {
  const { t, lang } = useT()
  const act = useAct()
  const today = new Date().toISOString().slice(0, 10)
  const { data: rates } = useGet<RateRow[]>(readOnly ? null : '/commercial/rates', { valid_on: today })
  const [head, setHead] = useState({ label: '', summary: '', scope_text: '', assumptions: '', exclusions: '', terms: '', currency: 'EUR', fx_rate: '', fx_note: '' })
  const [wps, setWps] = useState<WpDraft[]>([])
  const [lines, setLines] = useState<LineDraft[]>([])

  useEffect(() => {
    setHead({
      label: version.label ?? '', summary: version.summary, scope_text: version.scope_text, assumptions: version.assumptions, exclusions: version.exclusions,
      terms: version.terms, currency: version.currency, fx_rate: version.fx_rate === null ? '' : String(version.fx_rate), fx_note: version.fx_note ?? '',
    })
    setWps(wpsFrom(version))
    setLines(linesFrom(version))
  }, [version])

  const fx = head.fx_rate.trim() === '' ? null : Number(head.fx_rate)
  const foreign = lines.some((l) => l.currency !== head.currency)
  const fxInvalid = foreign && (fx === null || Number.isNaN(fx) || fx <= 0 || head.fx_note.trim() === '')
  const currencyInvalid = !CURRENCY_RE.test(head.currency)
  const totals = useMemo(
    () => calcTotals(lines.map((l) => ({ line_kind: l.line_kind, quantity: num(l.quantity), unit: l.unit, unit_cost: num(l.unit_cost), unit_price: num(l.unit_price), currency: l.currency })), head.currency, fx),
    [lines, head.currency, fx],
  )
  const invalidLine = lines.some((l) => l.description.trim() === '' || num(l.quantity) < 0 || !CURRENCY_RE.test(l.currency))
  const invalidWp = wps.some((w) => w.title.trim() === '')
  const valid = !fxInvalid && !currencyInvalid && !invalidLine && !invalidWp

  const save = async (): Promise<boolean> => {
    if (!valid) return false
    const res = await act('put', `/commercial/proposals/${version.proposal_id}/versions/${version.id}`, {
      label: head.label || null, summary: head.summary, scope_text: head.scope_text, assumptions: head.assumptions, exclusions: head.exclusions, terms: head.terms,
      currency: head.currency, fx_rate: foreign ? fx : null, fx_note: foreign ? head.fx_note.trim() : null,
      work_packages: wps.map((w) => ({
        code: w.code, title: w.title.trim(), description: w.description, milestone_title: w.milestone_title.trim() || null, milestone_due: w.milestone_due || null,
        start_date: w.start_date || null, end_date: w.end_date || null,
      })),
      lines: lines.map((l) => ({
        line_kind: l.line_kind, description: l.description.trim(), role_label: l.role_label.trim() || null, rate_entry_id: l.rate_entry_id || null, quantity: num(l.quantity), unit: l.unit,
        unit_cost: num(l.unit_cost), unit_price: num(l.unit_price), currency: l.currency, wp_index: l.wp === '' ? null : Number(l.wp),
      })),
    })
    if (res) onSaved()
    return Boolean(res)
  }

  useEffect(() => {
    registerSave?.(readOnly ? null : save)
    return () => registerSave?.(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [readOnly, head, wps, lines])

  const setLine = (key: string, patch: Partial<LineDraft>) => setLines((ls) => ls.map((l) => (l.key === key ? { ...l, ...patch } : l)))
  const setWp = (key: string, patch: Partial<WpDraft>) => setWps((ws) => ws.map((w) => (w.key === key ? { ...w, ...patch } : w)))
  const pickRate = (key: string, rateId: string) => {
    if (rateId === NO_RATE) {
      setLine(key, { rate_entry_id: '' })
      return
    }
    const r = (rates ?? []).find((x) => x.id === rateId)
    if (r) setLine(key, { rate_entry_id: r.id, role_label: r.role_label, unit: r.unit, unit_cost: String(r.cost_rate), unit_price: String(r.sell_rate), currency: r.currency })
  }
  const textField = (id: string, label: string, key: 'summary' | 'scope_text' | 'assumptions' | 'exclusions' | 'terms', rows = 3) => (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{t(label)}</Label>
      <Textarea id={id} rows={rows} value={head[key]} maxLength={20000} disabled={readOnly} onChange={(e) => setHead((h) => ({ ...h, [key]: e.target.value }))} />
    </div>
  )

  return (
    <div className="space-y-4">
      <Section title={t('Content')}>
        <div className="grid gap-3">
          <div className="grid gap-3 sm:grid-cols-[1fr_8rem]">
            <div className="grid gap-1.5"><Label htmlFor="ve-label">{t('Label')}</Label><Input id="ve-label" value={head.label} maxLength={120} disabled={readOnly} onChange={(e) => setHead((h) => ({ ...h, label: e.target.value }))} /></div>
            <div className="grid gap-1.5"><Label htmlFor="ve-cur">{t('Currency')}</Label><Input id="ve-cur" value={head.currency} maxLength={3} disabled={readOnly} aria-invalid={currencyInvalid} onChange={(e) => setHead((h) => ({ ...h, currency: e.target.value.toUpperCase() }))} /></div>
          </div>
          {textField('ve-summary', 'Summary', 'summary')}
          {textField('ve-scope', 'Scope of work', 'scope_text', 5)}
          <div className="grid gap-3 md:grid-cols-2">
            {textField('ve-assume', 'Assumptions', 'assumptions')}
            {textField('ve-excl', 'Exclusions', 'exclusions')}
          </div>
          {textField('ve-terms', 'Commercial terms', 'terms')}
        </div>
      </Section>

      <Section title={t('Work packages and milestones')} action={readOnly ? undefined : <Button size="sm" variant="outline" onClick={() => setWps((w) => [...w, { key: nextKey(), code: `WP${w.length + 1}`, title: '', description: '', milestone_title: '', milestone_due: '', start_date: '', end_date: '' }])}><Plus className="mr-1 h-4 w-4" aria-hidden />{t('Add work package')}</Button>}>
        {wps.length === 0 && <p className="text-sm text-muted-foreground">{t('No work packages yet')}</p>}
        <div className="space-y-2">
          {wps.map((w, i) => (
            <div key={w.key} className="grid gap-2 rounded-lg border p-3 md:grid-cols-[5rem_1fr_1fr_9rem_auto]">
              <Input value={w.code} maxLength={20} disabled={readOnly} aria-label={t('Code')} onChange={(e) => setWp(w.key, { code: e.target.value })} />
              <Input value={w.title} maxLength={200} disabled={readOnly} placeholder={`${t('Title')} *`} aria-label={t('Title')} aria-invalid={w.title.trim() === ''} onChange={(e) => setWp(w.key, { title: e.target.value })} />
              <Input value={w.milestone_title} maxLength={200} disabled={readOnly} placeholder={t('Milestone')} aria-label={t('Milestone')} onChange={(e) => setWp(w.key, { milestone_title: e.target.value })} />
              <Input type="date" value={w.milestone_due} disabled={readOnly} aria-label={t('Milestone due')} onChange={(e) => setWp(w.key, { milestone_due: e.target.value })} />
              {!readOnly && <Button variant="ghost" size="icon" aria-label={`${t('Remove')} ${i + 1}`} onClick={() => { setWps((ws) => ws.filter((x) => x.key !== w.key)); setLines((ls) => ls.map((l) => (l.wp === String(i) ? { ...l, wp: '' } : l))) }}><Trash2 className="h-4 w-4" /></Button>}
            </div>
          ))}
        </div>
      </Section>

      <Section title={t('Calculation')} action={readOnly ? <span className="text-xs text-muted-foreground">{t('Locked versions cannot be edited')}</span> : <Button size="sm" variant="outline" onClick={() => setLines((l) => [...l, { key: nextKey(), line_kind: 'labor', description: '', role_label: '', rate_entry_id: '', quantity: '1', unit: 'day', unit_cost: '0', unit_price: '0', currency: head.currency, wp: '' }])}><Plus className="mr-1 h-4 w-4" aria-hidden />{t('Add line')}</Button>}>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[56rem] text-sm">
            <thead className="text-left text-xs text-muted-foreground">
              <tr><th className="p-1">{t('Description')}</th><th className="p-1">{t('Type')}</th><th className="p-1">{t('Price list')}</th><th className="p-1">{t('Work package')}</th><th className="p-1">{t('Qty')}</th><th className="p-1">{t('Unit')}</th>{version.can_see_cost && <th className="p-1">{t('Unit cost')}</th>}<th className="p-1">{t('Unit price')}</th><th className="p-1">{t('Curr.')}</th><th className="p-1 text-right">{t('Total')}</th><th /></tr>
            </thead>
            <tbody>
              {lines.map((l) => (
                <tr key={l.key} className="border-t align-top">
                  <td className="p-1"><Input value={l.description} maxLength={300} disabled={readOnly} aria-label={t('Description')} aria-invalid={l.description.trim() === ''} onChange={(e) => setLine(l.key, { description: e.target.value })} /></td>
                  <td className="p-1">
                    <Select value={l.line_kind} onValueChange={(v) => setLine(l.key, { line_kind: v as LineKind })} disabled={readOnly}>
                      <SelectTrigger className="w-28" aria-label={t('Type')}><SelectValue /></SelectTrigger>
                      <SelectContent>{KINDS.map((k) => <SelectItem key={k} value={k}>{t(k)}</SelectItem>)}</SelectContent>
                    </Select>
                  </td>
                  <td className="p-1">
                    <Select value={l.rate_entry_id || NO_RATE} onValueChange={(v) => pickRate(l.key, v)} disabled={readOnly}>
                      <SelectTrigger className="w-36" aria-label={t('Price list')}><SelectValue /></SelectTrigger>
                      <SelectContent><SelectItem value={NO_RATE}>–</SelectItem>{(rates ?? []).map((r) => <SelectItem key={r.id} value={r.id}>{r.name}</SelectItem>)}</SelectContent>
                    </Select>
                  </td>
                  <td className="p-1">
                    <Select value={l.wp === '' ? NO_RATE : l.wp} onValueChange={(v) => setLine(l.key, { wp: v === NO_RATE ? '' : v })} disabled={readOnly}>
                      <SelectTrigger className="w-28" aria-label={t('Work package')}><SelectValue /></SelectTrigger>
                      <SelectContent><SelectItem value={NO_RATE}>–</SelectItem>{wps.map((w, i) => <SelectItem key={w.key} value={String(i)}>{w.code || w.title || i + 1}</SelectItem>)}</SelectContent>
                    </Select>
                  </td>
                  <td className="p-1"><Input className="w-20" inputMode="decimal" value={l.quantity} disabled={readOnly} aria-label={t('Qty')} onChange={(e) => setLine(l.key, { quantity: e.target.value })} /></td>
                  <td className="p-1">
                    <Select value={l.unit} onValueChange={(v) => setLine(l.key, { unit: v as CalcUnit })} disabled={readOnly}>
                      <SelectTrigger className="w-24" aria-label={t('Unit')}><SelectValue /></SelectTrigger>
                      <SelectContent>{UNITS.map((u) => <SelectItem key={u} value={u}>{t(u)}</SelectItem>)}</SelectContent>
                    </Select>
                  </td>
                  {version.can_see_cost && <td className="p-1"><Input className="w-24" inputMode="decimal" value={l.unit_cost} disabled={readOnly} aria-label={t('Unit cost')} onChange={(e) => setLine(l.key, { unit_cost: e.target.value })} /></td>}
                  <td className="p-1"><Input className="w-24" inputMode="decimal" value={l.unit_price} disabled={readOnly} aria-label={t('Unit price')} onChange={(e) => setLine(l.key, { unit_price: e.target.value })} /></td>
                  <td className="p-1"><Input className="w-16" value={l.currency} maxLength={3} disabled={readOnly} aria-label={t('Currency')} aria-invalid={!CURRENCY_RE.test(l.currency)} onChange={(e) => setLine(l.key, { currency: e.target.value.toUpperCase() })} /></td>
                  <td className="whitespace-nowrap p-1 text-right">{fmtMoney(num(l.quantity) * num(l.unit_price), l.currency, lang)}</td>
                  <td className="p-1">{!readOnly && <Button variant="ghost" size="icon" aria-label={t('Remove')} onClick={() => setLines((ls) => ls.filter((x) => x.key !== l.key))}><Trash2 className="h-4 w-4" /></Button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {foreign && (
          <div className="mt-3 grid gap-3 rounded-lg border border-dashed p-3 sm:grid-cols-[10rem_1fr]">
            <div className="grid gap-1.5"><Label htmlFor="ve-fx">{t('Exchange rate')} *</Label><Input id="ve-fx" inputMode="decimal" value={head.fx_rate} disabled={readOnly} aria-invalid={fxInvalid} onChange={(e) => setHead((h) => ({ ...h, fx_rate: e.target.value }))} /></div>
            <div className="grid gap-1.5"><Label htmlFor="ve-fxn">{t('Source of the rate')} *</Label><Input id="ve-fxn" value={head.fx_note} maxLength={300} disabled={readOnly} aria-invalid={fxInvalid} onChange={(e) => setHead((h) => ({ ...h, fx_note: e.target.value }))} /></div>
            <p className="text-xs text-muted-foreground sm:col-span-2">{t('1 unit of a foreign currency equals this many units of the version currency. The source is documented with the version.')}</p>
          </div>
        )}
        <dl className="mt-4 flex flex-wrap items-end justify-end gap-x-8 gap-y-2 text-right">
          <div><dt className="font-mono-label text-muted-foreground">{t('Effort')}</dt><dd className="font-display text-xl">{totals.effort} {t('days')}</dd></div>
          {version.can_see_cost && <div><dt className="font-mono-label text-muted-foreground">{t('Cost')}</dt><dd className="font-display text-xl">{fmtMoney(totals.cost, head.currency, lang)}</dd></div>}
          {version.can_see_cost && <div><dt className="font-mono-label text-muted-foreground">{t('Margin')}</dt><dd className="font-display text-xl">{totals.marginPct === null ? '–' : `${totals.marginPct}%`}</dd></div>}
          <div><dt className="font-mono-label text-muted-foreground">{t('Total price')} <Pill className="ml-1">{t('Calculated')}</Pill></dt><dd className="font-display text-3xl font-semibold">{fmtMoney(totals.price, head.currency, lang)}</dd></div>
        </dl>
      </Section>
    </div>
  )
}
