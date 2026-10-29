import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, ShieldCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ErrorBlock, LoadingBlock, Pill, Section } from '@/components/kit'
import { fmtDateTime, useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import { BID_CRITERIA, bidScore, bidTone } from '@/lib/sales'
import type { BidInfo, OppDetail } from '@/lib/sales-types'
import { cn } from '@/lib/utils'

interface Row {
  rating: number
  weight: number
  comment: string
}

const EMPTY: Row = { rating: 0, weight: 3, comment: '' }
const LEVELS = [1, 2, 3, 4, 5]

function rowsFrom(info: BidInfo | undefined): Record<string, Row> {
  const out: Record<string, Row> = {}
  for (const c of BID_CRITERIA) out[c.key] = { ...EMPTY }
  for (const s of info?.scores ?? []) out[s.criterion] = { rating: s.rating, weight: s.weight, comment: s.comment ?? '' }
  return out
}

export function BidPanel({ opp }: Readonly<{ opp: OppDetail }>) {
  const { t, lang } = useT()
  const act = useAct()
  const { data, isLoading, error } = useGet<BidInfo>(`/commercial/opportunities/${opp.id}/bid`)
  const [rows, setRows] = useState<Record<string, Row>>(rowsFrom(undefined))
  const [rationale, setRationale] = useState('')
  const [conditions, setConditions] = useState('')
  const [overrideNote, setOverrideNote] = useState('')

  useEffect(() => {
    setRows(rowsFrom(data))
    setRationale(data?.assessment?.rationale ?? '')
    setConditions(data?.assessment?.conditions ?? '')
    setOverrideNote('')
  }, [data])

  const score = useMemo(() => bidScore(Object.values(rows)), [rows])
  if (isLoading) return <LoadingBlock rows={4} />
  if (error || !data) return <ErrorBlock message={error?.message} />

  const decision = data.assessment?.decision ?? 'pending'
  const final = decision === 'bid' || decision === 'no_bid'
  const needsOverride = !data.authority.authorized
  const canTakeDecision = data.can_decide && (!needsOverride || data.authority.can_override)
  const closed = opp.stage === 'won' || opp.stage === 'lost'

  const setRow = (key: string, patch: Partial<Row>) => setRows((r) => ({ ...r, [key]: { ...r[key], ...patch } }))

  const saveScores = () =>
    act('put', `/commercial/opportunities/${opp.id}/bid/scores`, {
      scores: Object.entries(rows).filter(([, r]) => r.rating > 0).map(([criterion, r]) => ({ criterion, rating: r.rating, weight: r.weight, comment: r.comment.trim() || null })),
      rationale, conditions,
    })

  const decide = (choice: 'bid' | 'no_bid' | 'clarify') =>
    act('post', `/commercial/opportunities/${opp.id}/bid/decision`, { decision: choice, rationale, conditions, override_note: needsOverride && overrideNote.trim() ? overrideNote.trim() : null })

  const needsNote = needsOverride && overrideNote.trim().length < 3
  const decideDisabled = !canTakeDecision || closed || rationale.trim().length < 3 || needsNote

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_22rem]">
      <Section title={t('Assessment')} action={<span className="text-xs text-muted-foreground">{t('Calculated')}</span>}>
        <p className="mb-3 text-xs text-muted-foreground">{t('The score is guidance only. It never decides anything by itself.')}</p>
        <div className="space-y-3">
          {BID_CRITERIA.map((c) => {
            const row = rows[c.key]
            return (
              <div key={c.key} className="rounded-lg border p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="text-sm font-medium">{t(c.label)}</div>
                    <div className="text-[11px] text-muted-foreground">{t(c.hint)}</div>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="flex gap-1" role="group" aria-label={`${t(c.label)}: ${t('Rating')}`}>
                      {LEVELS.map((n) => (
                        <button
                          key={n}
                          type="button"
                          disabled={!data.can_edit}
                          aria-pressed={row.rating === n}
                          onClick={() => setRow(c.key, { rating: row.rating === n ? 0 : n })}
                          className={cn('h-8 w-8 rounded-md border text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60', row.rating === n ? 'border-primary bg-primary text-primary-foreground' : 'hover:bg-muted')}
                        >
                          {n}
                        </button>
                      ))}
                    </div>
                    <Select value={String(row.weight)} onValueChange={(v) => setRow(c.key, { weight: Number(v) })} disabled={!data.can_edit}>
                      <SelectTrigger className="h-8 w-24" aria-label={`${t(c.label)}: ${t('Weight')}`}><SelectValue /></SelectTrigger>
                      <SelectContent>{LEVELS.map((n) => <SelectItem key={n} value={String(n)}>{t('Weight')} {n}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                </div>
                <Input className="mt-2 h-8" value={row.comment} maxLength={1000} disabled={!data.can_edit} placeholder={t('Comment or evidence')} aria-label={`${t(c.label)}: ${t('Comment')}`} onChange={(e) => setRow(c.key, { comment: e.target.value })} />
              </div>
            )
          })}
        </div>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <div className="font-display text-2xl font-semibold">{score === null ? '–' : `${score} / 100`}</div>
          {data.can_edit && <Button variant="outline" onClick={saveScores}>{t('Save assessment')}</Button>}
        </div>
      </Section>

      <div className="space-y-4">
        <Section title={t('Who may decide')}>
          {data.authority.rules.length === 0 && (
            <p className="flex items-start gap-2 text-sm"><AlertTriangle className="mt-0.5 h-4 w-4 text-[hsl(var(--ochre))]" aria-hidden />{t('Clarification required: no decision rule applies. Only an administrator can decide, with a note.')}</p>
          )}
          <ul className="space-y-1.5 text-sm">
            {data.authority.rules.map((r) => (
              <li key={r.id} className="flex items-center justify-between gap-2">
                <span>{r.role_name}<span className="block text-[11px] text-muted-foreground">{r.label}</span></span>
                <Pill tone={r.holders > 0 ? 'forest' : 'danger'}>{r.holders > 0 ? `${r.holders} ${t('holders')}` : t('unfilled')}</Pill>
              </li>
            ))}
          </ul>
          {data.authority.rules.length > 0 && data.authority.unclear && <p className="mt-2 text-xs text-destructive">{t('The responsible role is not filled. Clarification required.')}</p>}
          {data.authority.authorized && <p className="mt-2 flex items-center gap-1.5 text-xs text-[hsl(var(--forest))]"><ShieldCheck className="h-4 w-4" aria-hidden />{t('You hold a deciding role.')}</p>}
        </Section>

        <Section title={t('Decision')} action={<Pill tone={bidTone(decision)}>{t(decision.replaceAll('_', ' '))}</Pill>}>
          {data.assessment?.decided_at && (
            <p className="mb-2 text-xs text-muted-foreground">{data.assessment.decided_by_name} · {fmtDateTime(data.assessment.decided_at, lang)}{data.assessment.admin_override && ` · ${t('administrator override')}`}</p>
          )}
          {data.assessment?.admin_override && data.assessment.override_note && <p className="mb-2 rounded-md border border-dashed p-2 text-xs">{data.assessment.override_note}</p>}
          <div className="grid gap-3">
            <div className="grid gap-1.5"><Label htmlFor="bid-rationale">{t('Rationale')} *</Label><Textarea id="bid-rationale" rows={3} value={rationale} maxLength={10000} disabled={closed} onChange={(e) => setRationale(e.target.value)} /></div>
            <div className="grid gap-1.5"><Label htmlFor="bid-conditions">{t('Conditions')}</Label><Textarea id="bid-conditions" rows={2} value={conditions} maxLength={5000} disabled={closed} onChange={(e) => setConditions(e.target.value)} /></div>
            {needsOverride && data.authority.can_override && (
              <div className="grid gap-1.5"><Label htmlFor="bid-override">{t('Administrator note')} *</Label><Textarea id="bid-override" rows={2} value={overrideNote} maxLength={2000} onChange={(e) => setOverrideNote(e.target.value)} /></div>
            )}
            {needsOverride && !data.authority.can_override && !closed && <p className="text-xs text-muted-foreground">{t('Only the holders of the roles above can decide.')}</p>}
            <div className="flex flex-wrap gap-2">
              <Button disabled={decideDisabled} onClick={() => decide('bid')}>{t('Bid')}</Button>
              <Button variant="destructive" disabled={decideDisabled} onClick={() => decide('no_bid')}>{t('No-Bid')}</Button>
              {data.can_edit && <Button variant="outline" disabled={closed || (final && decideDisabled)} onClick={() => decide('clarify')}>{t('Needs clarification')}</Button>}
            </div>
          </div>
        </Section>
      </div>
    </div>
  )
}
