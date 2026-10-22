import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { ChevronDown, ListChecks, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { EmptyState, ErrorBlock, LoadingBlock, ModePill, PageHeader, Pill, PriorityPill, Section, StatusPill } from '@/components/kit'
import { HistoryTimeline } from '@/components/HistoryTimeline'
import { TensionDialog } from '@/components/TensionDialog'
import { TensionConvertDialog, type ConvertTarget, type ConvertableTension } from '@/components/TensionConvert'
import { useSession } from '@/contexts/SessionContext'
import { fmtDate, useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import type { HistoryEntry, ProposalRow, Structure, TensionRow } from '@/lib/types'

interface DecisionRow {
  id: string
  title: string
  outcome: string
  rationale: string
  created_at: string
  circle_name: string | null
  decided_by_name: string | null
  proposal_id: string | null
  meeting_id: string | null
}

function ProposalsTab() {
  const { t, lang } = useT()
  const { isObserver } = useSession()
  const navigate = useNavigate()
  const [scope, setScope] = useState('open')
  const { data, isLoading, error } = useGet<ProposalRow[]>('/proposals', { status: scope === 'all' || scope === 'mine' ? undefined : scope, mine: scope === 'mine' })
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Select value={scope} onValueChange={setScope}>
          <SelectTrigger className="w-52" aria-label={t('Filter proposals')}><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="open">{t('Open proposals')}</SelectItem>
            <SelectItem value="accepted">{t('Accepted')}</SelectItem>
            <SelectItem value="rejected">{t('Rejected')}</SelectItem>
            <SelectItem value="mine">{t('Initiated by me')}</SelectItem>
            <SelectItem value="all">{t('All')}</SelectItem>
          </SelectContent>
        </Select>
        {!isObserver && <Button onClick={() => navigate('/governance/proposals/new')}><Plus className="mr-1 h-4 w-4" />{t('New proposal')}</Button>}
      </div>
      {isLoading && <LoadingBlock />}
      {error && <ErrorBlock message={error.message} />}
      {data && data.length === 0 && <EmptyState title={t('No proposals here')} hint={t('Use a tension or the assistant to draft one.')} />}
      <div className="grid gap-3">
        {data?.map((p, i) => (
          <Link key={p.id} to={`/governance/proposals/${p.id}`} className="paper-card interactive reveal flex flex-wrap items-center justify-between gap-3 p-4" style={{ ['--i' as string]: i }}>
            <div className="min-w-0">
              <div className="font-display text-lg font-semibold leading-tight">{p.title}</div>
              <div className="text-xs text-muted-foreground">{p.circle_name} · {t('by')} {p.initiator_name} · {fmtDate(p.created_at, lang)}</div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {p.ai_generated && <Pill tone="ochre">{t('AI draft')}</Pill>}
              {p.open_objections > 0 && <Pill tone="danger">{p.open_objections} {t('objection(s)')}</Pill>}
              <ModePill mode={p.workflow} />
              <StatusPill status={p.status} />
            </div>
          </Link>
        ))}
      </div>
    </div>
  )
}

function TensionsTab() {
  const { t } = useT()
  const { isObserver, canGovern } = useSession()
  const act = useAct()
  const [scope, setScope] = useState<'mine' | 'circle' | 'all'>('mine')
  const [circle, setCircle] = useState('')
  const [dialog, setDialog] = useState(false)
  const [convert, setConvert] = useState<{ tension: ConvertableTension; target: ConvertTarget } | null>(null)
  const { data: structure } = useGet<Structure>('/structure')
  const selectedCircle = circle || structure?.circles.find((c) => !c.parent_id)?.id || ''
  const { data, isLoading, error } = useGet<TensionRow[]>('/tensions', { scope, circle_id: scope === 'circle' ? selectedCircle : undefined })
  const targets: ConvertTarget[] = ['task', 'project', 'proposal', 'decision', 'resolution']
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Tabs value={scope} onValueChange={(v) => setScope(v as typeof scope)}>
            <TabsList>
              <TabsTrigger value="mine">{t('My inbox')}</TabsTrigger>
              <TabsTrigger value="circle">{t('Circle backlog')}</TabsTrigger>
              <TabsTrigger value="all">{t('All')}</TabsTrigger>
            </TabsList>
          </Tabs>
          {scope === 'circle' && (
            <Select value={selectedCircle} onValueChange={setCircle}>
              <SelectTrigger className="w-56" aria-label={t('Circle')}><SelectValue /></SelectTrigger>
              <SelectContent>{(structure?.circles ?? []).map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent>
            </Select>
          )}
        </div>
        {!isObserver && <Button onClick={() => setDialog(true)}><Plus className="mr-1 h-4 w-4" />{t('Capture tension')}</Button>}
      </div>
      {isLoading && <LoadingBlock />}
      {error && <ErrorBlock message={error.message} />}
      {data && data.length === 0 && <EmptyState title={t('No tensions here')} hint={t('Tensions are normal - they are the fuel for improving the organization.')} />}
      <div className="grid gap-3">
        {data?.map((x, i) => {
          const active = x.status === 'open' || x.status === 'processing'
          const mayProcess = !isObserver && active
          return (
            <div key={x.id} className="paper-card reveal p-4" style={{ ['--i' as string]: i }}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-display text-lg font-semibold leading-tight">{x.title}</div>
                  {x.description && <p className="mt-1 text-sm text-muted-foreground">{x.description}</p>}
                  <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                    <span>{x.creator_name}</span>
                    {x.circle_name && <Pill>{x.circle_name}</Pill>}
                    {x.role_name && <Pill>{x.role_name}</Pill>}
                    <Pill>{t(x.context_type)}{x.context_label ? `: ${x.context_label}` : ''}</Pill>
                    {x.outcome_type && <Pill tone="forest">→ {t(x.outcome_type)}</Pill>}
                  </div>
                  {x.resolution_note && <p className="mt-2 text-sm italic">“{x.resolution_note}”</p>}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <PriorityPill priority={x.priority} />
                  <StatusPill status={x.status} />
                  {mayProcess && (
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button size="sm"><ListChecks className="mr-1 h-4 w-4" />{t('Process')}<ChevronDown className="ml-1 h-3 w-3" /></Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        {targets.map((tg) => (
                          <DropdownMenuItem key={tg} onSelect={() => setConvert({ tension: { id: x.id, title: x.title, description: x.description, circle_id: x.circle_id }, target: tg })}>
                            {t(`Create ${tg}`)}
                          </DropdownMenuItem>
                        ))}
                        <DropdownMenuItem onSelect={() => act('patch', `/tensions/${x.id}`, { status: 'dropped' })}>{t('Drop tension')}</DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  )}
                </div>
              </div>
              {x.circle_id && canGovern(x.circle_id) && active && <p className="mt-2 text-[11px] text-muted-foreground">{t('You may process this tension in this circle.')}</p>}
            </div>
          )
        })}
      </div>
      <TensionDialog open={dialog} onOpenChange={setDialog} />
      <TensionConvertDialog tension={convert?.tension ?? null} target={convert?.target ?? 'task'} onClose={() => setConvert(null)} />
    </div>
  )
}

function DecisionsTab() {
  const { t, lang } = useT()
  const { data, isLoading } = useGet<DecisionRow[]>('/governance/decisions')
  return (
    <Section title={t('Decision records')}>
      {isLoading && <LoadingBlock rows={3} />}
      {data && data.length === 0 && <EmptyState title={t('No decisions recorded yet')} />}
      <ul className="divide-y">
        {data?.map((d) => (
          <li key={d.id} className="py-3">
            <div className="flex flex-wrap items-center gap-2">
              {d.proposal_id ? <Link className="text-sm font-medium hover:text-primary" to={`/governance/proposals/${d.proposal_id}`}>{d.title}</Link> : <span className="text-sm font-medium">{d.title}</span>}
              <StatusPill status={d.outcome} />
            </div>
            <div className="text-xs text-muted-foreground">{fmtDate(d.created_at, lang)} · {d.circle_name} · {d.decided_by_name}</div>
            {d.rationale && <p className="mt-1 text-sm">{d.rationale}</p>}
          </li>
        ))}
      </ul>
    </Section>
  )
}

function HistoryTab() {
  const { t } = useT()
  const { data, isLoading } = useGet<HistoryEntry[]>('/governance/history', { limit: 80 })
  return (
    <Section title={t('Organization change history')}>
      <p className="mb-4 text-sm text-muted-foreground">{t('Every structural change with who proposed it, who decided, when and why. Use the date selector on the Organization page to view the structure at any past date.')}</p>
      {isLoading ? <LoadingBlock rows={3} /> : <HistoryTimeline entries={data ?? []} showEntity />}
    </Section>
  )
}

export default function Governance() {
  const { t } = useT()
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') ?? 'proposals'
  return (
    <>
      <PageHeader title={t('Governance')} subtitle={t('Transparent, structured and auditable changes to roles and circles.')} />
      <Tabs value={tab} onValueChange={(v) => setParams({ tab: v })} className="space-y-4">
        <TabsList>
          <TabsTrigger value="proposals">{t('Proposals')}</TabsTrigger>
          <TabsTrigger value="tensions">{t('Tensions')}</TabsTrigger>
          <TabsTrigger value="decisions">{t('Decisions')}</TabsTrigger>
          <TabsTrigger value="history">{t('History')}</TabsTrigger>
        </TabsList>
        <TabsContent value="proposals"><ProposalsTab /></TabsContent>
        <TabsContent value="tensions"><TensionsTab /></TabsContent>
        <TabsContent value="decisions"><DecisionsTab /></TabsContent>
        <TabsContent value="history"><HistoryTab /></TabsContent>
      </Tabs>
    </>
  )
}
