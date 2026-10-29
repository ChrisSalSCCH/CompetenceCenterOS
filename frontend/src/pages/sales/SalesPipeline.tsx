import { useMemo, useState, type DragEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import { AlarmClock, ArrowRightLeft, LayoutGrid, List, Plus, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Avatar, EmptyState, ErrorBlock, LoadingBlock, PageHeader, Pill, Section, Stat } from '@/components/kit'
import { OpportunityFormDialog } from '@/components/sales/OpportunityFormDialog'
import { LostReasonDialog } from '@/components/sales/StageDialog'
import { useSession } from '@/contexts/SessionContext'
import { fmtDate, useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import { CATEGORIES } from '@/lib/portfolio'
import { OPEN_STAGES, STAGES, STAGE_LABEL, bidTone, fmtMoney, fmtMoneyMap, groupByStage, riskTone, stageTone, weightedOpen } from '@/lib/sales'
import type { OppRow, PipelineData, Stage } from '@/lib/sales-types'
import { cn } from '@/lib/utils'

const ANY = 'any'
const MIME = 'text/x-opportunity'

interface Pending {
  id: string
  title: string
}

function Card({ opp, canMove, onMove, onOpen }: Readonly<{ opp: OppRow; canMove: boolean; onMove: (stage: Stage) => void; onOpen: () => void }>) {
  const { t, lang } = useT()
  const closed = opp.stage === 'won' || opp.stage === 'lost'
  const onDragStart = (e: DragEvent) => {
    e.dataTransfer.setData(MIME, opp.id)
    e.dataTransfer.effectAllowed = 'move'
  }
  return (
    <article
      draggable={canMove && !opp.project_id}
      onDragStart={onDragStart}
      className={cn('paper-card group relative cursor-pointer p-3 transition-shadow hover:shadow-md', opp.action_overdue && 'border-destructive/40')}
    >
      <div className="flex items-start justify-between gap-2">
        <button type="button" onClick={onOpen} className="min-w-0 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <div className="font-mono-label text-muted-foreground">{opp.number}</div>
          <div className="font-display text-base font-semibold leading-snug">{opp.title}</div>
          <div className="truncate text-xs text-muted-foreground">{opp.customer_name}</div>
        </button>
        {canMove && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" aria-label={`${t('Move')} ${opp.number}`}><ArrowRightLeft className="h-3.5 w-3.5" /></Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {STAGES.filter((s) => s !== opp.stage).map((s) => <DropdownMenuItem key={s} onSelect={() => onMove(s)}>{t(STAGE_LABEL[s])}</DropdownMenuItem>)}
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>
      <div className="mt-2 flex items-center justify-between gap-2">
        <span className="font-display text-lg font-semibold">{fmtMoney(opp.value_amount, opp.currency, lang)}</span>
        {!closed && <span className="text-xs text-muted-foreground" title={t('Probability')}>{opp.effective_probability}%</span>}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-1">
        {opp.bid_decision && opp.bid_decision !== 'pending' && <Pill tone={bidTone(opp.bid_decision)}>{t(opp.bid_decision.replaceAll('_', ' '))}</Pill>}
        {opp.risk === 'high' && <Pill tone={riskTone(opp.risk)}>{t('high risk')}</Pill>}
        {opp.project_id && <Pill tone="forest">{t('Project')}</Pill>}
        {opp.action_overdue && <Pill tone="danger"><AlarmClock className="h-3 w-3" aria-hidden />{t('Action overdue')}</Pill>}
        {!opp.action_overdue && opp.close_overdue && <Pill tone="danger">{t('Decision overdue')}</Pill>}
        <span className="ml-auto">{opp.owner_name && <Avatar name={opp.owner_name} size={22} />}</span>
      </div>
      {opp.next_action && !closed && <p className="mt-2 truncate text-[11px] text-muted-foreground" title={opp.next_action}>{opp.next_action}{opp.next_action_due && ` · ${fmtDate(opp.next_action_due, lang)}`}</p>}
    </article>
  )
}

export default function SalesPipeline() {
  const { t, lang } = useT()
  const navigate = useNavigate()
  const act = useAct()
  const { isObserver } = useSession()
  const [view, setView] = useState('board')
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState(ANY)
  const [overdueOnly, setOverdueOnly] = useState(false)
  const [creating, setCreating] = useState(false)
  const [lost, setLost] = useState<Pending | null>(null)
  const filters = { search: search.trim() || undefined, category: category === ANY ? undefined : category, overdue: overdueOnly || undefined }
  const { data: rows, isLoading, error } = useGet<OppRow[]>('/commercial/opportunities', filters)
  const { data: pipe } = useGet<PipelineData>('/commercial/pipeline')
  const grouped = useMemo(() => groupByStage(rows ?? []), [rows])
  const stageInfo = useMemo(() => new Map((pipe?.stages ?? []).map((s) => [s.stage, s])), [pipe])

  const move = async (id: string, stage: Stage, reason?: string) => {
    await act('post', `/commercial/opportunities/${id}/stage`, { stage, lost_reason: reason ?? null })
  }
  const requestMove = (opp: OppRow, stage: Stage) => {
    if (stage === opp.stage) return
    if (stage === 'lost') setLost({ id: opp.id, title: opp.title })
    else void move(opp.id, stage)
  }
  const onDrop = (e: DragEvent, stage: Stage) => {
    e.preventDefault()
    const id = e.dataTransfer.getData(MIME)
    const opp = (rows ?? []).find((r) => r.id === id)
    if (opp) requestMove(opp, stage)
  }
  const weighted = pipe ? weightedOpen(pipe.stages) : null

  return (
    <>
      <PageHeader
        title={t('Sales pipeline')}
        subtitle={t('Opportunities from first contact to a won project. Drag a card to another column to change its stage.')}
        actions={!isObserver && <Button onClick={() => setCreating(true)}><Plus className="mr-1 h-4 w-4" aria-hidden />{t('New opportunity')}</Button>}
      />
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label={t('Open opportunities')} value={pipe?.open_count ?? '–'} />
        <Stat label={t('Overdue')} value={pipe?.overdue_count ?? '–'} tone={pipe && pipe.overdue_count > 0 ? 'danger' : undefined} hint={t('Next action or decision date passed')} />
        <Stat label={t('Weighted pipeline')} value={<span className="text-2xl">{pipe?.money_hidden ? '–' : fmtMoneyMap(weighted, lang)}</span>} hint={t('Calculated: value x probability')} />
        <Stat label={t('Win rate')} value={pipe?.win_rate === null || pipe?.win_rate === undefined ? '–' : `${pipe.win_rate}%`} hint={t('Won / (won + lost)')} />
      </div>
      <Section className="mb-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative min-w-64 flex-1 md:max-w-md">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input className="pl-9" value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t('Search title, number, customer ...')} aria-label={t('Search')} />
          </div>
          <Select value={category} onValueChange={setCategory}>
            <SelectTrigger className="w-48" aria-label={t('Category')}><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value={ANY}>{t('Category')}: {t('Any')}</SelectItem>
              {CATEGORIES.map((c) => <SelectItem key={c} value={c}>{t(c)}</SelectItem>)}
            </SelectContent>
          </Select>
          <Button variant={overdueOnly ? 'default' : 'outline'} aria-pressed={overdueOnly} onClick={() => setOverdueOnly((v) => !v)}>{t('Overdue only')}</Button>
          <Tabs value={view} onValueChange={setView} className="ml-auto">
            <TabsList>
              <TabsTrigger value="board" aria-label={t('Board')}><LayoutGrid className="mr-1 h-4 w-4" aria-hidden />{t('Board')}</TabsTrigger>
              <TabsTrigger value="list" aria-label={t('List')}><List className="mr-1 h-4 w-4" aria-hidden />{t('List')}</TabsTrigger>
            </TabsList>
          </Tabs>
        </div>
      </Section>

      {isLoading && <LoadingBlock />}
      {error && <ErrorBlock message={error.message} />}

      {rows && view === 'board' && (
        <div className="flex gap-3 overflow-x-auto pb-4" role="list" aria-label={t('Pipeline board')}>
          {STAGES.map((stage) => {
            const info = stageInfo.get(stage)
            const cards = grouped[stage]
            return (
              <section
                key={stage}
                role="listitem"
                aria-label={t(STAGE_LABEL[stage])}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => onDrop(e, stage)}
                className={cn('flex w-72 shrink-0 flex-col rounded-xl border bg-muted/30 p-2', (stage === 'won' || stage === 'lost') && 'bg-muted/10')}
              >
                <header className="mb-2 flex items-center justify-between gap-2 px-1">
                  <div className="flex items-center gap-2">
                    <Pill tone={stageTone(stage)}>{t(STAGE_LABEL[stage])}</Pill>
                    <span className="text-xs text-muted-foreground">{cards.length}</span>
                  </div>
                  <span className="text-[11px] text-muted-foreground">{info?.value ? fmtMoneyMap(info.value, lang) : ''}</span>
                </header>
                <div className="flex flex-1 flex-col gap-2">
                  {cards.map((o) => <Card key={o.id} opp={o} canMove={!isObserver && !o.project_id} onMove={(s) => requestMove(o, s)} onOpen={() => navigate(`/sales/opportunities/${o.id}`)} />)}
                  {cards.length === 0 && <p className="rounded-lg border border-dashed p-4 text-center text-xs text-muted-foreground">{OPEN_STAGES.includes(stage) ? t('Drop a card here') : t('Nothing yet')}</p>}
                </div>
              </section>
            )
          })}
        </div>
      )}

      {rows && view === 'list' && (rows.length === 0 ? <EmptyState title={t('Nothing found.')} /> : (
        <Section className="overflow-x-auto p-0 md:p-0">
          <Table>
            <TableHeader>
              <TableRow><TableHead>{t('Opportunity')}</TableHead><TableHead>{t('Customer')}</TableHead><TableHead>{t('Stage')}</TableHead><TableHead className="text-right">{t('Value')}</TableHead><TableHead className="text-right">{t('Probability')}</TableHead><TableHead>{t('Decision')}</TableHead><TableHead>{t('Owner')}</TableHead><TableHead>{t('Next action')}</TableHead></TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((o) => (
                <TableRow key={o.id}>
                  <TableCell><Link to={`/sales/opportunities/${o.id}`} className="font-display text-base font-semibold hover:text-primary">{o.title}</Link><div className="font-mono-label text-muted-foreground">{o.number}</div></TableCell>
                  <TableCell className="text-sm">{o.customer_name}</TableCell>
                  <TableCell><Pill tone={stageTone(o.stage)}>{t(STAGE_LABEL[o.stage])}</Pill></TableCell>
                  <TableCell className="whitespace-nowrap text-right text-sm">{fmtMoney(o.value_amount, o.currency, lang)}</TableCell>
                  <TableCell className="text-right text-sm">{o.effective_probability}%</TableCell>
                  <TableCell className="text-sm">{fmtDate(o.expected_close, lang)}{o.close_overdue && <Pill tone="danger" className="ml-1">{t('overdue')}</Pill>}</TableCell>
                  <TableCell className="text-sm">{o.owner_name ?? '–'}</TableCell>
                  <TableCell className="max-w-56 truncate text-sm">{o.next_action ?? '–'}{o.action_overdue && <Pill tone="danger" className="ml-1">{t('overdue')}</Pill>}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Section>
      ))}

      <OpportunityFormDialog opp={null} open={creating} onOpenChange={setCreating} onSaved={(id) => navigate(`/sales/opportunities/${id}`)} />
      <LostReasonDialog open={lost !== null} title={lost?.title ?? ''} onOpenChange={(v) => !v && setLost(null)} onConfirm={(reason) => lost && move(lost.id, 'lost', reason)} />
    </>
  )
}
