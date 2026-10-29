import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { ArrowLeft, BellRing, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ComboPicker } from '@/components/ComboPicker'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { DocumentsPanel } from '@/components/DocumentsPanel'
import { EmptyState, ErrorBlock, InfoNotice, LoadingBlock, PageHeader, Pill, Section } from '@/components/kit'
import { SignDialog } from '@/components/sales/SignDialog'
import { useSession } from '@/contexts/SessionContext'
import { fmtDate, useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import type { CrmOrgRow, PortfolioRow } from '@/lib/portfolio-types'
import { CONTRACT_TONE, fmtMoney } from '@/lib/sales'
import type { ContractDetailData, ContractRow, ReminderItem } from '@/lib/sales-types'

const KINDS = ['framework', 'project', 'service', 'license', 'research', 'other'] as const
const CURRENCY_RE = /^[A-Z]{3}$/

function StatePill({ state }: Readonly<{ state: ContractRow['state'] }>) {
  const { t } = useT()
  return <Pill tone={CONTRACT_TONE[state]}>{t(state.replaceAll('_', ' '))}</Pill>
}

function ContractFormDialog({ open, onOpenChange }: Readonly<{ open: boolean; onOpenChange: (v: boolean) => void }>) {
  const { t } = useT()
  const act = useAct()
  const { data: orgs } = useGet<CrmOrgRow[]>(open ? '/crm/organizations' : null)
  const { data: contracts } = useGet<ContractRow[]>(open ? '/commercial/contracts' : null, { kind: 'framework' })
  const { data: projects } = useGet<PortfolioRow[]>(open ? '/portfolio' : null)
  const [customer, setCustomer] = useState<string[]>([])
  const [title, setTitle] = useState('')
  const [kind, setKind] = useState<string>('project')
  const [parent, setParent] = useState<string[]>([])
  const [value, setValue] = useState('')
  const [currency, setCurrency] = useState('EUR')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [notice, setNotice] = useState('')
  const [projectIds, setProjectIds] = useState<string[]>([])
  useEffect(() => {
    if (open) {
      setCustomer([])
      setTitle('')
      setKind('project')
      setParent([])
      setValue('')
      setCurrency('EUR')
      setFrom('')
      setTo('')
      setNotice('')
      setProjectIds([])
    }
  }, [open])
  const amount = value.trim() === '' ? null : Number(value)
  const valueInvalid = amount !== null && (Number.isNaN(amount) || amount < 0)
  const datesInvalid = from !== '' && to !== '' && to < from
  const canSave = customer.length === 1 && title.trim().length >= 3 && !valueInvalid && !datesInvalid && CURRENCY_RE.test(currency)
  const save = async () => {
    const res = await act('post', '/commercial/contracts', {
      crm_org_id: customer[0], title: title.trim(), contract_kind: kind, parent_contract_id: parent[0] ?? null, value_amount: amount, currency,
      valid_from: from || null, valid_to: to || null, notice_period_days: notice.trim() === '' ? null : Number(notice), project_ids: projectIds,
    })
    if (res) onOpenChange(false)
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader><DialogTitle className="font-display text-xl">{t('New contract')}</DialogTitle></DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1.5"><Label>{t('Customer')} *</Label><ComboPicker options={(orgs ?? []).map((o) => ({ id: o.id, label: o.name, hint: o.city }))} value={customer} onChange={(v) => setCustomer(v.slice(-1))} placeholder={t('Choose customer')} /></div>
          <div className="grid gap-1.5"><Label htmlFor="ct-title">{t('Title')} *</Label><Input id="ct-title" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} /></div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="grid gap-1.5">
              <Label>{t('Kind')}</Label>
              <Select value={kind} onValueChange={setKind}>
                <SelectTrigger aria-label={t('Kind')}><SelectValue /></SelectTrigger>
                <SelectContent>{KINDS.map((k) => <SelectItem key={k} value={k}>{t(k)}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label>{t('Framework agreement')}</Label>
              <ComboPicker options={(contracts ?? []).filter((c) => customer.length === 0 || c.crm_org_id === customer[0]).map((c) => ({ id: c.id, label: c.title, hint: c.number }))} value={parent} onChange={(v) => setParent(v.slice(-1))} placeholder={t('None')} />
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-[1fr_6rem_1fr_1fr]">
            <div className="grid gap-1.5"><Label htmlFor="ct-value">{t('Value')}</Label><Input id="ct-value" inputMode="decimal" value={value} aria-invalid={valueInvalid} onChange={(e) => setValue(e.target.value)} /></div>
            <div className="grid gap-1.5"><Label htmlFor="ct-cur">{t('Currency')}</Label><Input id="ct-cur" value={currency} maxLength={3} onChange={(e) => setCurrency(e.target.value.toUpperCase())} /></div>
            <div className="grid gap-1.5"><Label htmlFor="ct-from">{t('Valid from')}</Label><Input id="ct-from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></div>
            <div className="grid gap-1.5"><Label htmlFor="ct-to">{t('Valid until')}</Label><Input id="ct-to" type="date" value={to} aria-invalid={datesInvalid} onChange={(e) => setTo(e.target.value)} /></div>
          </div>
          <div className="grid gap-1.5"><Label htmlFor="ct-notice">{t('Notice period (days)')}</Label><Input id="ct-notice" inputMode="numeric" value={notice} onChange={(e) => setNotice(e.target.value)} /></div>
          <div className="grid gap-1.5"><Label>{t('Projects covered')}</Label><ComboPicker multiple options={(projects ?? []).map((p) => ({ id: p.id, label: p.name, hint: p.project_no }))} value={projectIds} onChange={setProjectIds} placeholder={t('Choose projects')} /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t('Cancel')}</Button>
          <Button onClick={save} disabled={!canSave}>{t('Create')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Reminders() {
  const { t, lang } = useT()
  const act = useAct()
  const { data } = useGet<ReminderItem[]>('/commercial/reminders')
  useEffect(() => {
    void act('post', '/commercial/reminders/run')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  if (!data || data.length === 0) return null
  return (
    <Section title={t('Reminders')} className="mb-4" action={<BellRing className="h-4 w-4 text-muted-foreground" aria-hidden />}>
      <ul className="divide-y">
        {data.map((r) => (
          <li key={`${r.entity_id}-${r.kind}`} className="flex flex-wrap items-center gap-2 py-1.5 text-sm">
            <Pill tone={r.kind === 'overdue' ? 'danger' : 'ochre'}>{t(r.kind.replaceAll('_', ' '))}</Pill>
            <Link to={r.link} className="font-medium hover:text-primary">{r.number} · {r.title}</Link>
            <span className="ml-auto text-xs text-muted-foreground">{fmtDate(r.due_date, lang)}</span>
          </li>
        ))}
      </ul>
    </Section>
  )
}

export function ContractList() {
  const { t, lang } = useT()
  const { isObserver } = useSession()
  const [creating, setCreating] = useState(false)
  const { data, isLoading, error } = useGet<ContractRow[]>('/commercial/contracts')
  return (
    <>
      <PageHeader title={t('Contracts')} subtitle={t('Framework agreements, call-offs and project contracts.')} actions={!isObserver && <Button onClick={() => setCreating(true)}><Plus className="mr-1 h-4 w-4" aria-hidden />{t('New contract')}</Button>} />
      <Reminders />
      {isLoading && <LoadingBlock />}
      {error && <ErrorBlock message={error.message} />}
      {data && data.length === 0 && <EmptyState title={t('No contracts yet')} />}
      {data && data.length > 0 && (
        <Section className="overflow-x-auto p-0 md:p-0">
          <Table>
            <TableHeader><TableRow><TableHead>{t('Contract')}</TableHead><TableHead>{t('Customer')}</TableHead><TableHead>{t('Kind')}</TableHead><TableHead>{t('Status')}</TableHead><TableHead className="text-right">{t('Value')}</TableHead><TableHead>{t('Valid until')}</TableHead><TableHead>{t('Projects')}</TableHead></TableRow></TableHeader>
            <TableBody>
              {data.map((c) => (
                <TableRow key={c.id}>
                  <TableCell><Link to={`/sales/contracts/${c.id}`} className="font-display text-base font-semibold hover:text-primary">{c.title}</Link><div className="font-mono-label text-muted-foreground">{c.number}</div></TableCell>
                  <TableCell className="text-sm">{c.customer_name}</TableCell>
                  <TableCell className="text-sm">{t(c.contract_kind)}</TableCell>
                  <TableCell><StatePill state={c.state} /></TableCell>
                  <TableCell className="whitespace-nowrap text-right text-sm">{c.terms_visible ? fmtMoney(c.value_amount, c.currency, lang) : t('restricted')}</TableCell>
                  <TableCell className="text-sm">{fmtDate(c.valid_to, lang)}</TableCell>
                  <TableCell className="text-sm">{c.project_count}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Section>
      )}
      <ContractFormDialog open={creating} onOpenChange={setCreating} />
    </>
  )
}

function MilestoneDialog({ contractId, currency, open, onOpenChange }: Readonly<{ contractId: string; currency: string; open: boolean; onOpenChange: (v: boolean) => void }>) {
  const { t } = useT()
  const act = useAct()
  const [title, setTitle] = useState('')
  const [due, setDue] = useState('')
  const [amount, setAmount] = useState('')
  useEffect(() => {
    if (open) {
      setTitle('')
      setDue('')
      setAmount('')
    }
  }, [open])
  const value = amount.trim() === '' ? null : Number(amount)
  const invalid = value !== null && (Number.isNaN(value) || value < 0)
  const save = async () => {
    const res = await act('post', `/commercial/contracts/${contractId}/milestones`, { title: title.trim(), due_date: due || null, amount: value, currency })
    if (res) onOpenChange(false)
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader><DialogTitle className="font-display text-xl">{t('Payment milestone')}</DialogTitle></DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1.5"><Label htmlFor="ms-title">{t('Title')} *</Label><Input id="ms-title" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} /></div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="grid gap-1.5"><Label htmlFor="ms-due">{t('Due')}</Label><Input id="ms-due" type="date" value={due} onChange={(e) => setDue(e.target.value)} /></div>
            <div className="grid gap-1.5"><Label htmlFor="ms-amount">{t('Amount')} ({currency})</Label><Input id="ms-amount" inputMode="decimal" value={amount} aria-invalid={invalid} onChange={(e) => setAmount(e.target.value)} /></div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t('Cancel')}</Button>
          <Button onClick={save} disabled={title.trim().length < 2 || invalid}>{t('Save')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function AmendmentDialog({ contractId, open, onOpenChange }: Readonly<{ contractId: string; open: boolean; onOpenChange: (v: boolean) => void }>) {
  const { t } = useT()
  const act = useAct()
  const [title, setTitle] = useState('')
  const [delta, setDelta] = useState('')
  const [until, setUntil] = useState('')
  const [signed, setSigned] = useState(false)
  useEffect(() => {
    if (open) {
      setTitle('')
      setDelta('')
      setUntil('')
      setSigned(false)
    }
  }, [open])
  const value = delta.trim() === '' ? null : Number(delta)
  const invalid = value !== null && Number.isNaN(value)
  const save = async () => {
    const res = await act('post', `/commercial/contracts/${contractId}/amendments`, { title: title.trim(), value_delta: value, new_valid_to: until || null, signed })
    if (res) onOpenChange(false)
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader><DialogTitle className="font-display text-xl">{t('Amendment')}</DialogTitle></DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1.5"><Label htmlFor="am-title">{t('Title')} *</Label><Input id="am-title" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} /></div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="grid gap-1.5"><Label htmlFor="am-delta">{t('Change of value')}</Label><Input id="am-delta" inputMode="decimal" value={delta} aria-invalid={invalid} onChange={(e) => setDelta(e.target.value)} /></div>
            <div className="grid gap-1.5"><Label htmlFor="am-until">{t('New end date')}</Label><Input id="am-until" type="date" value={until} onChange={(e) => setUntil(e.target.value)} /></div>
          </div>
          <Label className="flex items-center gap-2 font-normal"><Switch checked={signed} onCheckedChange={setSigned} />{t('Signed - apply value and term now')}</Label>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t('Cancel')}</Button>
          <Button onClick={save} disabled={title.trim().length < 2 || invalid}>{t('Save')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function ContractDetail() {
  const { t, lang } = useT()
  const { id } = useParams()
  const act = useAct()
  const [signing, setSigning] = useState(false)
  const [milestone, setMilestone] = useState(false)
  const [amending, setAmending] = useState(false)
  const { data: c, isLoading, error } = useGet<ContractDetailData>(id ? `/commercial/contracts/${id}` : null)
  if (isLoading) return <LoadingBlock rows={4} />
  if (error || !c) return <ErrorBlock message={error?.status === 404 ? t('Contract not found') : error?.message} />
  const open = c.status === 'draft' || c.status === 'in_review'
  return (
    <>
      <Link to="/sales/contracts" className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-primary"><ArrowLeft className="h-4 w-4" aria-hidden />{t('Back to contracts')}</Link>
      <PageHeader
        eyebrow={c.number}
        title={c.title}
        subtitle={<Link to={`/crm/organizations/${c.customer.id}`} className="hover:text-primary">{c.customer.name}</Link>}
        actions={
          <>
            <StatePill state={c.state} />
            {c.can_edit && open && <Button onClick={() => setSigning(true)}>{t('Record signature')}</Button>}
            {c.can_edit && c.status === 'signed' && <ConfirmDialog trigger={<Button variant="outline">{t('Terminate')}</Button>} title={t('Terminate')} description={c.title} onConfirm={() => act('post', `/commercial/contracts/${c.id}/terminate`)} />}
          </>
        }
      />
      {!c.terms_visible && <div className="mb-4"><InfoNotice>{t('The conditions of this contract are only visible to its owner, the opportunity team and signing roles.')}</InfoNotice></div>}
      <div className="grid gap-4 lg:grid-cols-2">
        <Section title={t('Terms')}>
          <dl className="grid gap-3 text-sm sm:grid-cols-2">
            <div><dt className="font-mono-label text-muted-foreground">{t('Kind')}</dt><dd>{t(c.contract_kind)}</dd></div>
            <div><dt className="font-mono-label text-muted-foreground">{t('Value')}</dt><dd>{c.terms_visible ? fmtMoney(c.value_amount, c.currency, lang) : t('restricted')}</dd></div>
            <div><dt className="font-mono-label text-muted-foreground">{t('Valid from')}</dt><dd>{fmtDate(c.valid_from, lang)}</dd></div>
            <div><dt className="font-mono-label text-muted-foreground">{t('Valid until')}</dt><dd>{fmtDate(c.valid_to, lang)}</dd></div>
            <div><dt className="font-mono-label text-muted-foreground">{t('Notice period (days)')}</dt><dd>{c.notice_period_days ?? '–'}{c.auto_renew && ` · ${t('renews automatically')}`}</dd></div>
            <div><dt className="font-mono-label text-muted-foreground">{t('Signed on')}</dt><dd>{fmtDate(c.signed_at, lang)}{c.signed_by_name && ` · ${c.signed_by_name}`}</dd></div>
            <div><dt className="font-mono-label text-muted-foreground">{t('Owner')}</dt><dd>{c.owner_name ?? '–'}</dd></div>
            {c.parent && <div><dt className="font-mono-label text-muted-foreground">{t('Framework agreement')}</dt><dd><Link to={`/sales/contracts/${c.parent.id}`} className="text-primary hover:underline">{c.parent.number} · {c.parent.title}</Link></dd></div>}
            {c.opportunity && <div><dt className="font-mono-label text-muted-foreground">{t('Opportunity')}</dt><dd><Link to={`/sales/opportunities/${c.opportunity.id}`} className="text-primary hover:underline">{c.opportunity.number}</Link></dd></div>}
          </dl>
          {c.notes && <p className="mt-3 whitespace-pre-line text-sm text-muted-foreground">{c.notes}</p>}
        </Section>
        <Section title={t('Projects covered')}>
          {c.projects.length === 0 && <p className="text-sm text-muted-foreground">{t('No projects linked')}</p>}
          <ul className="space-y-1 text-sm">{c.projects.map((p) => <li key={p.id}><Link to={`/projects/${p.id}`} className="text-primary hover:underline">{p.name}</Link> <span className="text-xs text-muted-foreground">{t(p.phase)}</span></li>)}</ul>
          {c.children.length > 0 && (
            <>
              <h3 className="font-mono-label mt-3 text-muted-foreground">{t('Call-offs')}</h3>
              <ul className="mt-1 space-y-1 text-sm">{c.children.map((k) => <li key={k.id}><Link to={`/sales/contracts/${k.id}`} className="text-primary hover:underline">{k.number} · {k.title}</Link></li>)}</ul>
            </>
          )}
        </Section>
        <Section title={t('Payment milestones')} action={c.can_edit ? <Button size="sm" variant="outline" onClick={() => setMilestone(true)}><Plus className="mr-1 h-4 w-4" aria-hidden />{t('Add')}</Button> : undefined}>
          {c.milestones.length === 0 && <p className="text-sm text-muted-foreground">{t('No milestones yet')}</p>}
          <ul className="divide-y">
            {c.milestones.map((m) => (
              <li key={m.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                <span className="flex-1">{m.title}<span className="block text-xs text-muted-foreground">{fmtDate(m.due_date, lang)}</span></span>
                <span>{c.terms_visible ? fmtMoney(m.amount, m.currency, lang) : '–'}</span>
                {c.can_edit ? (
                  <Select value={m.status} onValueChange={(v) => act('patch', `/commercial/contracts/${c.id}/milestones/${m.id}`, { status: v })}>
                    <SelectTrigger className="h-8 w-28" aria-label={t('Status')}><SelectValue /></SelectTrigger>
                    <SelectContent>{['planned', 'invoiced', 'paid'].map((s) => <SelectItem key={s} value={s}>{t(s)}</SelectItem>)}</SelectContent>
                  </Select>
                ) : <Pill>{t(m.status)}</Pill>}
              </li>
            ))}
          </ul>
        </Section>
        <Section title={t('Amendments')} action={c.can_edit ? <Button size="sm" variant="outline" onClick={() => setAmending(true)}><Plus className="mr-1 h-4 w-4" aria-hidden />{t('Add')}</Button> : undefined}>
          {c.amendments.length === 0 && <p className="text-sm text-muted-foreground">{t('No amendments')}</p>}
          <ul className="divide-y">
            {c.amendments.map((a) => (
              <li key={a.id} className="py-2 text-sm">
                <div className="flex items-center gap-2"><span className="font-medium">{a.title}</span><Pill tone={a.signed ? 'forest' : 'neutral'}>{a.signed ? t('signed') : t('draft')}</Pill></div>
                <div className="text-xs text-muted-foreground">{a.value_delta !== null && c.terms_visible && `${fmtMoney(a.value_delta, c.currency, lang)} · `}{a.new_valid_to && `${t('until')} ${fmtDate(a.new_valid_to, lang)}`}</div>
              </li>
            ))}
          </ul>
        </Section>
      </div>
      <div className="mt-4"><DocumentsPanel entityType="contract" entityId={c.id} /></div>
      <SignDialog endpoint={`/commercial/contracts/${c.id}/sign`} title={c.title} open={signing} onOpenChange={setSigning} />
      <MilestoneDialog contractId={c.id} currency={c.currency} open={milestone} onOpenChange={setMilestone} />
      <AmendmentDialog contractId={c.id} open={amending} onOpenChange={setAmending} />
    </>
  )
}
