import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { ArrowLeft, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
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
import type { CrmOrgRow } from '@/lib/portfolio-types'
import { COVERAGE_TONE } from '@/lib/sales'
import type { NdaDetailData, NdaRow, OppRow } from '@/lib/sales-types'

const KINDS = ['mutual', 'one_way_in', 'one_way_out'] as const
const KIND_LABEL: Record<string, string> = { mutual: 'Mutual', one_way_in: 'One-way (we receive)', one_way_out: 'One-way (we disclose)' }

export function CoveragePill({ coverage }: Readonly<{ coverage: NdaRow['coverage'] }>) {
  const { t } = useT()
  return <Pill tone={COVERAGE_TONE[coverage]}>{t(coverage.replaceAll('_', ' '))}</Pill>
}

function NdaFormDialog({ open, onOpenChange }: Readonly<{ open: boolean; onOpenChange: (v: boolean) => void }>) {
  const { t } = useT()
  const act = useAct()
  const { data: orgs } = useGet<CrmOrgRow[]>(open ? '/crm/organizations' : null)
  const { data: opps } = useGet<OppRow[]>(open ? '/commercial/opportunities' : null, { open_only: true })
  const [customer, setCustomer] = useState<string[]>([])
  const [title, setTitle] = useState('')
  const [kind, setKind] = useState<string>('mutual')
  const [validTo, setValidTo] = useState('')
  const [recipients, setRecipients] = useState('')
  const [purpose, setPurpose] = useState('')
  const [oppIds, setOppIds] = useState<string[]>([])
  useEffect(() => {
    if (open) {
      setCustomer([])
      setTitle('')
      setKind('mutual')
      setValidTo('')
      setRecipients('')
      setPurpose('')
      setOppIds([])
    }
  }, [open])
  const save = async () => {
    const res = await act('post', '/commercial/ndas', {
      crm_org_id: customer[0], title: title.trim(), nda_kind: kind, valid_to: validTo || null, recipients, purpose, opportunity_ids: oppIds,
    })
    if (res) onOpenChange(false)
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader><DialogTitle className="font-display text-xl">{t('New NDA')}</DialogTitle></DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1.5"><Label>{t('Customer')} *</Label><ComboPicker options={(orgs ?? []).map((o) => ({ id: o.id, label: o.name, hint: o.city }))} value={customer} onChange={(v) => setCustomer(v.slice(-1))} placeholder={t('Choose customer')} /></div>
          <div className="grid gap-1.5"><Label htmlFor="nda-title">{t('Title')} *</Label><Input id="nda-title" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} /></div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="grid gap-1.5">
              <Label>{t('Kind')}</Label>
              <Select value={kind} onValueChange={setKind}>
                <SelectTrigger aria-label={t('Kind')}><SelectValue /></SelectTrigger>
                <SelectContent>{KINDS.map((k) => <SelectItem key={k} value={k}>{t(KIND_LABEL[k])}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5"><Label htmlFor="nda-to">{t('Valid until')}</Label><Input id="nda-to" type="date" value={validTo} onChange={(e) => setValidTo(e.target.value)} /></div>
          </div>
          <div className="grid gap-1.5"><Label>{t('Covers opportunities')}</Label><ComboPicker multiple options={(opps ?? []).map((o) => ({ id: o.id, label: o.title, hint: o.number }))} value={oppIds} onChange={setOppIds} placeholder={t('Choose opportunities')} /></div>
          <div className="grid gap-1.5"><Label htmlFor="nda-rec">{t('Recipients')}</Label><Input id="nda-rec" value={recipients} maxLength={2000} onChange={(e) => setRecipients(e.target.value)} /></div>
          <div className="grid gap-1.5"><Label htmlFor="nda-purpose">{t('Purpose')}</Label><Textarea id="nda-purpose" rows={2} value={purpose} maxLength={5000} onChange={(e) => setPurpose(e.target.value)} /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t('Cancel')}</Button>
          <Button onClick={save} disabled={customer.length === 0 || title.trim().length < 3}>{t('Create')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function NdaList() {
  const { t, lang } = useT()
  const { isObserver } = useSession()
  const [creating, setCreating] = useState(false)
  const { data, isLoading, error } = useGet<NdaRow[]>('/commercial/ndas')
  return (
    <>
      <PageHeader title={t('NDAs')} subtitle={t('Confidentiality agreements per customer, with validity and coverage.')} actions={!isObserver && <Button onClick={() => setCreating(true)}><Plus className="mr-1 h-4 w-4" aria-hidden />{t('New NDA')}</Button>} />
      <div className="mb-4"><InfoNotice>{t('A signed NDA proves confidentiality. It does not release anything for publication or as a reference.')}</InfoNotice></div>
      {isLoading && <LoadingBlock />}
      {error && <ErrorBlock message={error.message} />}
      {data && data.length === 0 && <EmptyState title={t('No NDAs yet')} />}
      {data && data.length > 0 && (
        <Section className="overflow-x-auto p-0 md:p-0">
          <Table>
            <TableHeader><TableRow><TableHead>{t('NDA')}</TableHead><TableHead>{t('Customer')}</TableHead><TableHead>{t('Kind')}</TableHead><TableHead>{t('Coverage')}</TableHead><TableHead>{t('Valid from')}</TableHead><TableHead>{t('Valid until')}</TableHead></TableRow></TableHeader>
            <TableBody>
              {data.map((n) => (
                <TableRow key={n.id}>
                  <TableCell><Link to={`/sales/ndas/${n.id}`} className="font-display text-base font-semibold hover:text-primary">{n.title}</Link><div className="font-mono-label text-muted-foreground">{n.number}</div></TableCell>
                  <TableCell className="text-sm">{n.customer_name}</TableCell>
                  <TableCell className="text-sm">{t(KIND_LABEL[n.nda_kind])}</TableCell>
                  <TableCell><CoveragePill coverage={n.coverage} /></TableCell>
                  <TableCell className="text-sm">{fmtDate(n.valid_from, lang)}</TableCell>
                  <TableCell className="text-sm">{fmtDate(n.valid_to, lang)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Section>
      )}
      <NdaFormDialog open={creating} onOpenChange={setCreating} />
    </>
  )
}

export function NdaDetail() {
  const { t, lang } = useT()
  const { id } = useParams()
  const act = useAct()
  const [signing, setSigning] = useState(false)
  const { data: n, isLoading, error } = useGet<NdaDetailData>(id ? `/commercial/ndas/${id}` : null)
  if (isLoading) return <LoadingBlock rows={4} />
  if (error || !n) return <ErrorBlock message={error?.status === 404 ? t('NDA not found') : error?.message} />
  const open = n.status === 'draft' || n.status === 'in_review'
  return (
    <>
      <Link to="/sales/ndas" className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-primary"><ArrowLeft className="h-4 w-4" aria-hidden />{t('Back to NDAs')}</Link>
      <PageHeader
        eyebrow={n.number}
        title={n.title}
        subtitle={<Link to={`/crm/organizations/${n.customer.id}`} className="hover:text-primary">{n.customer.name}</Link>}
        actions={
          <>
            <CoveragePill coverage={n.coverage} />
            {n.can_edit && open && <Button onClick={() => setSigning(true)}>{t('Record signature')}</Button>}
            {n.can_edit && n.status === 'signed' && <ConfirmDialog trigger={<Button variant="outline">{t('Terminate')}</Button>} title={t('Terminate')} description={n.title} onConfirm={() => act('post', `/commercial/ndas/${n.id}/terminate`)} />}
          </>
        }
      />
      <div className="mb-4"><InfoNotice>{t(n.notice)}</InfoNotice></div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Section title={t('Terms')}>
          <dl className="grid gap-3 sm:grid-cols-2 text-sm">
            <div><dt className="font-mono-label text-muted-foreground">{t('Kind')}</dt><dd>{t(KIND_LABEL[n.nda_kind])}</dd></div>
            <div><dt className="font-mono-label text-muted-foreground">{t('Valid from')}</dt><dd>{fmtDate(n.valid_from, lang)}</dd></div>
            <div><dt className="font-mono-label text-muted-foreground">{t('Valid until')}</dt><dd>{fmtDate(n.valid_to, lang)}</dd></div>
            <div><dt className="font-mono-label text-muted-foreground">{t('Signed on')}</dt><dd>{fmtDate(n.signed_at, lang)}{n.signed_by_name && ` · ${n.signed_by_name}`}{n.signatory_name && ` (${n.signatory_name})`}</dd></div>
            <div className="sm:col-span-2"><dt className="font-mono-label text-muted-foreground">{t('Recipients')}</dt><dd>{n.recipients || '–'}</dd></div>
            <div className="sm:col-span-2"><dt className="font-mono-label text-muted-foreground">{t('Purpose')}</dt><dd className="whitespace-pre-line">{n.purpose || '–'}</dd></div>
          </dl>
        </Section>
        <Section title={t('Covers')}>
          {n.opportunities.length === 0 && n.projects.length === 0 && <p className="text-sm text-muted-foreground">{t('Applies to the customer in general.')}</p>}
          <ul className="space-y-1 text-sm">
            {n.opportunities.map((o) => <li key={o.id}><Link to={`/sales/opportunities/${o.id}`} className="text-primary hover:underline">{o.number} · {o.title}</Link></li>)}
            {n.projects.map((p) => <li key={p.id}><Link to={`/projects/${p.id}`} className="text-primary hover:underline">{p.name}</Link></li>)}
          </ul>
        </Section>
      </div>
      <div className="mt-4"><DocumentsPanel entityType="nda" entityId={n.id} /></div>
      <SignDialog endpoint={`/commercial/ndas/${n.id}/sign`} title={n.title} open={signing} onOpenChange={setSigning} />
    </>
  )
}
