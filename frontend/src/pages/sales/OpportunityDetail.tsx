import { useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { ArrowLeft, Pencil, Rocket, Trash2, Users } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Avatar, EmptyState, ErrorBlock, LoadingBlock, PageHeader, Pill, Section } from '@/components/kit'
import { BidPanel } from '@/components/sales/BidPanel'
import { ConvertDialog } from '@/components/sales/ConvertDialog'
import { OppActivities } from '@/components/sales/OppActivities'
import { OppLinksDialog } from '@/components/sales/OppLinksDialog'
import { OpportunityFormDialog } from '@/components/sales/OpportunityFormDialog'
import { ProcessChain } from '@/components/sales/ProcessChain'
import { LostReasonDialog } from '@/components/sales/StageDialog'
import { useSession } from '@/contexts/SessionContext'
import { fmtDate, fmtDateTime, useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import { PROPOSAL_TONE, STAGES, STAGE_LABEL, bidTone, fmtMoney, riskTone, stageTone } from '@/lib/sales'
import type { HistoryEvent, NdaCoverage, OppDetail, Stage } from '@/lib/sales-types'
import { DocumentsPanel } from '@/components/DocumentsPanel'
import { NewProposalDialog } from '@/components/sales/ProposalDialogs'
import { CoveragePill } from '@/pages/sales/NdaPages'

const TABS = ['overview', 'bid', 'proposals', 'agreements', 'activities', 'documents', 'history'] as const
type TabKey = (typeof TABS)[number]

function Fact({ label, children }: Readonly<{ label: string; children: ReactNode }>) {
  return (
    <div>
      <dt className="font-mono-label text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 text-sm">{children}</dd>
    </div>
  )
}

function Agreements({ o }: Readonly<{ o: OppDetail }>) {
  const { t, lang } = useT()
  const { data } = useGet<NdaCoverage>('/commercial/nda-coverage', { crm_org_id: o.crm_org_id, opportunity_id: o.id })
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Section title={t('NDAs')} action={data ? <CoveragePill coverage={data.state} /> : undefined}>
        {o.ndas.length === 0 && <p className="text-sm text-muted-foreground">{t('No NDA for this customer yet')}</p>}
        <ul className="divide-y">
          {o.ndas.map((n) => (
            <li key={n.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
              <Link to={`/sales/ndas/${n.id}`} className="flex-1 font-medium text-primary hover:underline">{n.number} · {n.title}</Link>
              <span className="text-xs text-muted-foreground">{fmtDate(n.valid_to, lang)}</span>
              <Pill>{t(n.status.replaceAll('_', ' '))}</Pill>
            </li>
          ))}
        </ul>
        <p className="mt-2 text-[11px] text-muted-foreground">{data?.notice ? t(data.notice) : ''}</p>
        <Button asChild variant="outline" size="sm" className="mt-2"><Link to="/sales/ndas">{t('Manage NDAs')}</Link></Button>
      </Section>
      <Section title={t('Contracts')}>
        {o.contracts.length === 0 && <p className="text-sm text-muted-foreground">{t('No contracts yet')}</p>}
        <ul className="divide-y">
          {o.contracts.map((c) => (
            <li key={c.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
              <Link to={`/sales/contracts/${c.id}`} className="flex-1 font-medium text-primary hover:underline">{c.number} · {c.title}</Link>
              <Pill>{t(c.status.replaceAll('_', ' '))}</Pill>
            </li>
          ))}
        </ul>
        <Button asChild variant="outline" size="sm" className="mt-2"><Link to="/sales/contracts">{t('Manage contracts')}</Link></Button>
      </Section>
    </div>
  )
}

function History({ id }: Readonly<{ id: string }>) {
  const { t, lang } = useT()
  const { data, isLoading } = useGet<HistoryEvent[]>(`/commercial/opportunities/${id}/history`)
  if (isLoading) return <LoadingBlock rows={3} />
  return (
    <Section title={t('History')}>
      {(data ?? []).length === 0 && <EmptyState title={t('No history yet')} />}
      <ul className="divide-y">
        {(data ?? []).map((e) => (
          <li key={e.id} className="flex flex-wrap items-baseline gap-x-3 py-2 text-sm">
            <span className="text-xs text-muted-foreground">{fmtDateTime(e.created_at, lang)}</span>
            <span className="flex-1">{e.summary}</span>
            <span className="text-xs text-muted-foreground">{e.actor_name}</span>
          </li>
        ))}
      </ul>
    </Section>
  )
}

export default function OpportunityDetail() {
  const { t, lang } = useT()
  const { id } = useParams()
  const navigate = useNavigate()
  const act = useAct()
  const { isAdmin, isObserver } = useSession()
  const [params, setParams] = useSearchParams()
  const { data: o, isLoading, error } = useGet<OppDetail>(id ? `/commercial/opportunities/${id}` : null)
  const [editing, setEditing] = useState(false)
  const [linking, setLinking] = useState(false)
  const [converting, setConverting] = useState(false)
  const [losing, setLosing] = useState(false)
  const [proposing, setProposing] = useState(false)
  const requested = params.get('tab')
  const tab: TabKey = TABS.find((x) => x === requested) ?? 'overview'

  if (isLoading) return <LoadingBlock rows={5} />
  if (error || !o) return <ErrorBlock message={error?.status === 404 ? t('Opportunity not found') : error?.message} />

  const closed = o.stage === 'won' || o.stage === 'lost'
  const move = (stage: Stage, reason?: string) => act('post', `/commercial/opportunities/${o.id}/stage`, { stage, lost_reason: reason ?? null })
  const onStage = (value: string) => {
    const stage = value as Stage
    if (stage === 'lost') setLosing(true)
    else void move(stage)
  }
  const remove = async () => {
    const ok = await act('delete', `/commercial/opportunities/${o.id}`)
    if (ok) navigate('/sales')
  }
  const canConvert = o.stage === 'won' && !o.project_id && o.can_edit

  return (
    <>
      <Link to="/sales" className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-primary"><ArrowLeft className="h-4 w-4" aria-hidden />{t('Back to pipeline')}</Link>
      <PageHeader
        eyebrow={o.number}
        title={o.title}
        subtitle={<Link to={`/crm/organizations/${o.crm_org_id}`} className="hover:text-primary">{o.customer_name}</Link>}
        actions={
          <>
            <Pill tone={stageTone(o.stage)}>{t(STAGE_LABEL[o.stage])}</Pill>
            {o.bid && o.bid.decision !== 'pending' && <Pill tone={bidTone(o.bid.decision)}>{t(o.bid.decision.replaceAll('_', ' '))}</Pill>}
            {o.can_edit && !o.project_id && (
              <Select value={o.stage} onValueChange={onStage}>
                <SelectTrigger className="w-44" aria-label={t('Stage')}><SelectValue /></SelectTrigger>
                <SelectContent>{STAGES.map((s) => <SelectItem key={s} value={s}>{t(STAGE_LABEL[s])}</SelectItem>)}</SelectContent>
              </Select>
            )}
            {canConvert && <Button onClick={() => setConverting(true)}><Rocket className="mr-1 h-4 w-4" aria-hidden />{t('Create project')}</Button>}
            {o.project_id && <Button asChild variant="outline"><Link to={`/projects/${o.project_id}`}>{t('Open project')}: {o.project_name}</Link></Button>}
            {o.can_edit && <Button variant="outline" size="icon" aria-label={t('Edit')} onClick={() => setEditing(true)}><Pencil className="h-4 w-4" /></Button>}
            {(isAdmin || (o.can_edit && !isObserver)) && !o.project_id && (
              <ConfirmDialog
                trigger={<Button variant="ghost" size="icon" aria-label={t('Delete opportunity')}><Trash2 className="h-4 w-4" /></Button>}
                title={t('Delete opportunity')} description={o.title} onConfirm={remove}
              />
            )}
          </>
        }
      />
      <ProcessChain opportunityId={o.id} />
      <Tabs value={tab} onValueChange={(v) => setParams({ tab: v }, { replace: true })} className="space-y-4">
        <TabsList className="h-auto flex-wrap justify-start">
          <TabsTrigger value="overview">{t('Overview')}</TabsTrigger>
          <TabsTrigger value="bid">{t('Bid / No-Bid')}</TabsTrigger>
          <TabsTrigger value="proposals">{t('Proposals')} ({o.proposals.length})</TabsTrigger>
          <TabsTrigger value="agreements">{t('NDAs & Contracts')}</TabsTrigger>
          <TabsTrigger value="activities">{t('Activities')}</TabsTrigger>
          <TabsTrigger value="documents">{t('Documents')}</TabsTrigger>
          <TabsTrigger value="history">{t('History')}</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <div className="grid gap-4 lg:grid-cols-[1fr_22rem]">
            <Section title={t('Facts')}>
              <dl className="grid gap-4 sm:grid-cols-3">
                <Fact label={t('Value')}>{fmtMoney(o.value_amount, o.currency, lang)}</Fact>
                <Fact label={t('Probability')}>{closed ? `${o.effective_probability}%` : `${o.effective_probability}% ${o.probability_manual ? `(${t('manual')})` : `(${t('stage default')})`}`}</Fact>
                <Fact label={t('Weighted value')}>{fmtMoney(o.weighted_value, o.currency, lang)} <span className="text-[11px] text-muted-foreground">{t('Calculated')}</span></Fact>
                <Fact label={t('Category')}>{t(o.category)}</Fact>
                <Fact label={t('Risk')}><Pill tone={riskTone(o.risk)}>{t(o.risk)}</Pill></Fact>
                <Fact label={t('Effort (days)')}>{o.effort_days ?? '–'}</Fact>
                <Fact label={t('Expected decision')}>{fmtDate(o.expected_close, lang)}{o.close_overdue && <Pill tone="danger" className="ml-1">{t('overdue')}</Pill>}</Fact>
                <Fact label={t('Start')}>{fmtDate(o.expected_start, lang)}</Fact>
                <Fact label={t('End')}>{fmtDate(o.expected_end, lang)}</Fact>
                <Fact label={t('Owner')}>{o.owner_name ?? '–'}</Fact>
                <Fact label={t('Circle')}>{o.circle_name ?? '–'}</Fact>
                <Fact label={t('Source')}>{o.source ?? '–'}</Fact>
                <Fact label={t('Next action')}>{o.next_action ?? '–'}{o.next_action_due && ` · ${fmtDate(o.next_action_due, lang)}`}{o.action_overdue && <Pill tone="danger" className="ml-1">{t('overdue')}</Pill>}</Fact>
              </dl>
              {o.description && <p className="mt-4 whitespace-pre-line text-sm text-muted-foreground">{o.description}</p>}
            </Section>
            <div className="space-y-4">
              <Section title={t('Team and roles')} action={o.can_edit ? <Button variant="ghost" size="sm" onClick={() => setLinking(true)}><Users className="mr-1 h-4 w-4" aria-hidden />{t('Edit')}</Button> : undefined}>
                {o.team.length === 0 && o.scoped_roles.length === 0 && <p className="text-sm text-muted-foreground">{t('No team assigned')}</p>}
                <ul className="space-y-1.5">
                  {o.team.map((m) => <li key={m.user_id} className="flex items-center gap-2 text-sm"><Avatar name={m.name} size={24} />{m.name}{m.team_role && <span className="text-xs text-muted-foreground">{m.team_role}</span>}</li>)}
                </ul>
                {o.scoped_roles.length > 0 && (
                  <>
                    <h3 className="font-mono-label mt-3 text-muted-foreground">{t('Responsible roles')}</h3>
                    <ul className="mt-1 space-y-1">
                      {o.scoped_roles.map((r) => <li key={r.scope_id} className="text-sm">{r.name} <span className="text-xs text-muted-foreground">{r.role_name}</span></li>)}
                    </ul>
                    <p className="mt-2 text-[11px] text-muted-foreground">{t('A responsibility for a customer gives context. It does not grant decision authority.')}</p>
                  </>
                )}
              </Section>
              <Section title={t('Customer contacts')}>
                {o.contacts.length === 0 && <p className="text-sm text-muted-foreground">{t('No contacts linked')}</p>}
                <ul className="space-y-1">{o.contacts.map((c) => <li key={c.id} className="text-sm">{c.first_name} {c.last_name}<span className="block text-xs text-muted-foreground">{[c.job_title, c.contact_role].filter(Boolean).join(' · ')}</span></li>)}</ul>
              </Section>
              <Section title={t('Technologies and references')}>
                <div className="flex flex-wrap gap-1.5">{o.entries.map((e) => <Pill key={e.id} tone="primary">{e.name}</Pill>)}</div>
                <ul className="mt-2 space-y-1">{o.references.map((r) => <li key={r.id} className="text-sm"><Link to={`/projects/${r.id}`} className="text-primary hover:underline">{r.name}</Link></li>)}</ul>
                {o.entries.length === 0 && o.references.length === 0 && <p className="text-sm text-muted-foreground">{t('Nothing linked yet')}</p>}
              </Section>
            </div>
          </div>
        </TabsContent>
        <TabsContent value="bid"><BidPanel opp={o} /></TabsContent>
        <TabsContent value="proposals">
          <Section title={t('Proposals')} action={o.can_edit && o.bid?.decision === 'bid' && !closed ? <Button size="sm" onClick={() => setProposing(true)}>{t('New proposal')}</Button> : undefined}>
            {o.proposals.length === 0 && <EmptyState title={t('No proposals yet')} hint={o.bid?.decision === 'bid' ? undefined : t('A Bid decision is required before a proposal can be created.')} />}
            <ul className="divide-y">
              {o.proposals.map((p) => (
                <li key={p.id} className="flex flex-wrap items-center gap-2 py-2.5 text-sm">
                  <Link to={`/sales/proposals/${p.id}`} className="flex-1 font-medium text-primary hover:underline">{p.number} · {p.title}</Link>
                  <span className="text-xs text-muted-foreground">v{p.version_no ?? 1} · {fmtMoney(p.price_total, p.currency ?? o.currency, lang)}</span>
                  <Pill tone={PROPOSAL_TONE[p.status]}>{t(p.status.replaceAll('_', ' '))}</Pill>
                </li>
              ))}
            </ul>
          </Section>
        </TabsContent>
        <TabsContent value="agreements"><Agreements o={o} /></TabsContent>
        <TabsContent value="documents"><DocumentsPanel entityType="opportunity" entityId={o.id} /></TabsContent>
        <TabsContent value="activities"><OppActivities opportunityId={o.id} activities={o.activities} canEdit={!isObserver} /></TabsContent>
        <TabsContent value="history"><History id={o.id} /></TabsContent>
      </Tabs>

      <OpportunityFormDialog opp={o} open={editing} onOpenChange={setEditing} />
      <OppLinksDialog opp={o} open={linking} onOpenChange={setLinking} />
      <ConvertDialog opp={o} open={converting} onOpenChange={setConverting} />
      <NewProposalDialog opportunityId={o.id} defaultTitle={`${o.title} - ${t('Proposal')}`} currency={o.currency} open={proposing} onOpenChange={setProposing} />
      <LostReasonDialog open={losing} title={o.title} onOpenChange={setLosing} onConfirm={(reason) => move('lost', reason)} />
    </>
  )
}
