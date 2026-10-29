import { useEffect, useState } from 'react'
import { Lock } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ComboPicker } from '@/components/ComboPicker'
import { Pill, ProgressBar, Section, Stat } from '@/components/kit'
import { fmtDate, useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import { formatMoney, formatPct } from '@/lib/portfolio'
import type { FinanceData, ProjectDetailData } from '@/lib/portfolio-types'
import type { PersonRow } from '@/lib/types'

const CYCLES: FinanceData['reporting_cycle'][] = ['none', 'monthly', 'quarterly', 'semiannual', 'yearly']

interface Form {
  budget_total: string
  budget_funding: string
  budget_own: string
  costs_to_date: string
  revenue_expected: string
  currency: string
  reporting_cycle: FinanceData['reporting_cycle']
  next_report_due: string
  last_report_at: string
  notes: string
}

const str = (n: number | null | undefined) => (n === null || n === undefined ? '' : String(n))
const num = (s: string) => (s.trim() === '' ? null : Number(s))

function toForm(d: FinanceData | null): Form {
  return {
    budget_total: str(d?.budget_total), budget_funding: str(d?.budget_funding), budget_own: str(d?.budget_own), costs_to_date: str(d?.costs_to_date),
    revenue_expected: str(d?.revenue_expected), currency: d?.currency ?? 'EUR', reporting_cycle: d?.reporting_cycle ?? 'none',
    next_report_due: d?.next_report_due ?? '', last_report_at: d?.last_report_at ?? '', notes: d?.notes ?? '',
  }
}

export function FinanceTab({ p }: Readonly<{ p: ProjectDetailData }>) {
  const { t, lang } = useT()
  const act = useAct()
  const f = p.finance
  const { data: people } = useGet<PersonRow[]>(f.can_edit ? '/people' : null)
  const [form, setForm] = useState<Form>(toForm(f.data))
  const [viewers, setViewers] = useState<string[]>(f.viewers.map((v) => v.user_id))
  const sig = JSON.stringify(f.data)
  const viewerSig = f.viewers.map((v) => v.user_id).join(',')
  useEffect(() => setForm(toForm(f.data)), [sig]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => setViewers(f.viewers.map((v) => v.user_id)), [viewerSig]) // eslint-disable-line react-hooks/exhaustive-deps
  const set = (k: keyof Form, v: string) => setForm((x) => ({ ...x, [k]: v }))

  if (f.restricted) {
    return (
      <Section>
        <div className="flex items-start gap-3" role="status">
          <Lock className="mt-0.5 h-5 w-5 text-muted-foreground" aria-hidden />
          <div>
            <p className="font-display text-lg font-semibold">{t('Finance data is restricted')}</p>
            <p className="text-sm text-muted-foreground">{t('Only administrators, the project manager and people they name can see finance data.')}</p>
          </div>
        </div>
      </Section>
    )
  }

  const fundingTooHigh = num(form.budget_funding) !== null && num(form.budget_total) !== null && (num(form.budget_funding) ?? 0) > (num(form.budget_total) ?? 0)
  const anyNegative = [form.budget_total, form.budget_funding, form.budget_own, form.costs_to_date, form.revenue_expected].some((v) => v !== '' && (Number.isNaN(Number(v)) || Number(v) < 0))
  const cur = f.data?.currency ?? 'EUR'
  const m = f.metrics

  const save = () => act('put', `/portfolio/${p.id}/finance`, {
    budget_total: num(form.budget_total), budget_funding: num(form.budget_funding), budget_own: num(form.budget_own), costs_to_date: num(form.costs_to_date),
    revenue_expected: num(form.revenue_expected), currency: form.currency.toUpperCase(), reporting_cycle: form.reporting_cycle,
    next_report_due: form.next_report_due || null, last_report_at: form.last_report_at || null, notes: form.notes,
  })

  const money = (k: keyof Form, label: string) => (
    <div className="grid gap-1.5">
      <Label htmlFor={`fin-${k}`}>{label}</Label>
      <Input id={`fin-${k}`} inputMode="decimal" value={form[k]} onChange={(e) => set(k, e.target.value)} aria-invalid={form[k] !== '' && (Number.isNaN(Number(form[k])) || Number(form[k]) < 0)} />
    </div>
  )

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label={t('Total budget')} value={formatMoney(f.data?.budget_total, cur, lang)} hint={t('Entered')} />
        <Stat label={t('Costs to date')} value={formatMoney(f.data?.costs_to_date, cur, lang)} hint={t('Entered')} />
        <Stat label={t('Remaining budget')} value={formatMoney(m?.budget_remaining, cur, lang)} hint={t('Calculated')} tone={m?.budget_remaining !== null && (m?.budget_remaining ?? 0) < 0 ? 'danger' : undefined} />
        <Stat label={t('Funding rate')} value={formatPct(m?.funding_rate)} hint={t('Calculated')} />
      </div>
      {m?.budget_used_pct !== null && m?.budget_used_pct !== undefined && (
        <Section title={t('Budget used')}>
          <ProgressBar value={m.budget_used_pct / 100} tone={m.budget_used_pct > 100 ? 'ochre' : 'primary'} />
          <p className="mt-1 text-xs text-muted-foreground">{t('Calculated')}</p>
        </Section>
      )}
      {m?.report_overdue && <Pill tone="danger">{t('Report overdue')}: {fmtDate(f.data?.next_report_due, lang)}</Pill>}

      <Section title={t('Finance & Reporting')}>
        {f.can_edit ? (
          <div className="grid gap-3">
            <div className="grid gap-3 sm:grid-cols-3">
              {money('budget_total', t('Total budget'))}
              {money('budget_funding', t('Funding'))}
              {money('budget_own', t('Own contribution'))}
              {money('costs_to_date', t('Costs to date'))}
              {money('revenue_expected', t('Expected revenue'))}
              <div className="grid gap-1.5"><Label htmlFor="fin-cur">{t('Currency')}</Label><Input id="fin-cur" value={form.currency} maxLength={3} onChange={(e) => set('currency', e.target.value.toUpperCase())} /></div>
            </div>
            {fundingTooHigh && <p className="text-xs text-destructive" role="alert">{t('Funding')} &gt; {t('Total budget')}</p>}
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="grid gap-1.5">
                <Label>{t('Reporting cycle')}</Label>
                <Select value={form.reporting_cycle} onValueChange={(v) => set('reporting_cycle', v)}>
                  <SelectTrigger aria-label={t('Reporting cycle')}><SelectValue /></SelectTrigger>
                  <SelectContent>{CYCLES.map((c) => <SelectItem key={c} value={c}>{t(c)}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="grid gap-1.5"><Label htmlFor="fin-next">{t('Next report due')}</Label><Input id="fin-next" type="date" value={form.next_report_due} onChange={(e) => set('next_report_due', e.target.value)} /></div>
              <div className="grid gap-1.5"><Label htmlFor="fin-last">{t('Last report')}</Label><Input id="fin-last" type="date" value={form.last_report_at} onChange={(e) => set('last_report_at', e.target.value)} /></div>
            </div>
            <div className="grid gap-1.5"><Label htmlFor="fin-notes">{t('Notes')}</Label><Textarea id="fin-notes" rows={2} maxLength={5000} value={form.notes} onChange={(e) => set('notes', e.target.value)} /></div>
            <div><Button onClick={save} disabled={fundingTooHigh || anyNegative || form.currency.length !== 3}>{t('Save')}</Button></div>
          </div>
        ) : (
          <dl className="grid gap-3 text-sm sm:grid-cols-3">
            <div><dt className="font-mono-label text-muted-foreground">{t('Funding')}</dt><dd>{formatMoney(f.data?.budget_funding, cur, lang)}</dd></div>
            <div><dt className="font-mono-label text-muted-foreground">{t('Own contribution')}</dt><dd>{formatMoney(f.data?.budget_own, cur, lang)}</dd></div>
            <div><dt className="font-mono-label text-muted-foreground">{t('Expected revenue')}</dt><dd>{formatMoney(f.data?.revenue_expected, cur, lang)}</dd></div>
            <div><dt className="font-mono-label text-muted-foreground">{t('Reporting cycle')}</dt><dd>{t(f.data?.reporting_cycle ?? 'none')}</dd></div>
            <div><dt className="font-mono-label text-muted-foreground">{t('Next report due')}</dt><dd>{fmtDate(f.data?.next_report_due, lang)}</dd></div>
          </dl>
        )}
      </Section>

      {f.can_edit && (
        <Section title={t('Who can see finance data')}>
          <p className="mb-2 text-xs text-muted-foreground">{t('Administrators and the project manager always can.')}</p>
          <ComboPicker multiple options={(people ?? []).map((x) => ({ id: x.id, label: x.name, hint: x.job_title }))} value={viewers} onChange={setViewers} placeholder={t('Add a person')} />
          <Button className="mt-2" size="sm" variant="outline" onClick={() => act('put', `/portfolio/${p.id}/finance-viewers`, { user_ids: viewers })}>{t('Save')}</Button>
        </Section>
      )}
    </div>
  )
}
