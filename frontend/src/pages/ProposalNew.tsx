import { useEffect, useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router'
import { toast } from 'sonner'
import { Plus, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { ItemsEditor, cleanItems, toEditItems, type EditItem } from '@/components/ItemsEditor'
import { ErrorBlock, LoadingBlock, ModePill, PageHeader, Pill, Section } from '@/components/kit'
import { useSession } from '@/contexts/SessionContext'
import { useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import { effectiveMode } from '@/lib/structure'
import type { ChangeOpDraft, Structure } from '@/lib/types'

interface OpState {
  op: ChangeOpDraft['op']
  id: string
  name: string
  purpose: string
  circle_id: string
  parent_id: string
  multi: boolean
  govern: boolean
  acc: EditItem[]
  dom: EditItem[]
  aut: EditItem[]
  pol: EditItem[]
}

interface DraftState {
  circle_id?: string
  title?: string
  description?: string
  reason?: string
  expected_impact?: string
  proposal_type?: string
  changes?: ChangeOpDraft[]
  ai_generated?: boolean
}

interface ProposalFull extends DraftState {
  status: string
  changes: ChangeOpDraft[]
}

const TYPES = ['create_role', 'modify_role', 'remove_role', 'create_circle', 'restructure_circle', 'change_accountabilities', 'change_domains', 'update_policies', 'change_authorities']
const TYPE_LABEL: Record<string, string> = {
  create_role: 'Create role', modify_role: 'Modify role', remove_role: 'Remove role', create_circle: 'Create circle', restructure_circle: 'Restructure circle',
  change_accountabilities: 'Change accountabilities', change_domains: 'Change domains', update_policies: 'Update policies', change_authorities: 'Change decision authorities',
}
const OP_LABEL: Record<string, string> = {
  create_role: 'Create role', update_role: 'Modify role', delete_role: 'Remove role', create_circle: 'Create circle', update_circle: 'Modify circle', delete_circle: 'Remove circle',
}

function blank(op: ChangeOpDraft['op'], circleId: string): OpState {
  return { op, id: '', name: '', purpose: '', circle_id: circleId, parent_id: circleId, multi: false, govern: false, acc: [], dom: [], aut: [], pol: [] }
}

function fromDraft(c: ChangeOpDraft, circleId: string): OpState {
  const d = c.data as Record<string, unknown>
  const items = (v: unknown): EditItem[] => toEditItems(Array.isArray(v) ? (v as { text: string; detail: null; level: null }[]).map((x) => ({ text: x.text, detail: null, level: (x as { level?: null }).level ?? null })) : [])
  return {
    ...blank(c.op, (d.circle_id as string) ?? circleId),
    id: c.id ?? '', name: (d.name as string) ?? '', purpose: (d.purpose as string) ?? '',
    parent_id: (d.parent_id as string) ?? circleId, multi: Boolean(d.allow_multiple), govern: Boolean(d.can_govern),
    acc: items(d.accountabilities), dom: items(d.domains), aut: items(d.authorities), pol: items(d.policies),
  }
}

function toDraft(s: OpState): ChangeOpDraft {
  if (s.op === 'delete_role' || s.op === 'delete_circle') return { op: s.op, id: s.id, data: {} }
  const isRole = s.op.endsWith('role')
  const data: Record<string, unknown> = { name: s.name.trim(), purpose: s.purpose, accountabilities: cleanItems(s.acc), domains: cleanItems(s.dom), policies: cleanItems(s.pol) }
  if (isRole) {
    data.authorities = cleanItems(s.aut, true)
    data.allow_multiple = s.multi
    data.can_govern = s.govern
    data.circle_id = s.circle_id
  } else if (s.op === 'create_circle') {
    data.parent_id = s.parent_id
  } else if (s.parent_id) {
    data.parent_id = s.parent_id
  }
  return s.op.startsWith('create') ? { op: s.op, data } : { op: s.op, id: s.id, data }
}

function OpEditor({ state, onChange, onRemove, structure }: Readonly<{ state: OpState; onChange: (s: OpState) => void; onRemove: () => void; structure: Structure }>) {
  const { t } = useT()
  const isRole = state.op.endsWith('role')
  const isDelete = state.op.startsWith('delete')
  const isUpdate = state.op.startsWith('update')
  const targets = isRole ? structure.roles : structure.circles.filter((c) => c.parent_id !== null)
  const pick = (id: string) => {
    if (isRole) {
      const r = structure.roles.find((x) => x.id === id)
      if (r) onChange({ ...state, id, name: r.name, purpose: r.purpose, circle_id: r.circle_id, multi: r.allow_multiple, govern: r.can_govern, acc: toEditItems(r.accountabilities), dom: toEditItems(r.domains), aut: toEditItems(r.authorities), pol: toEditItems(r.policies) })
    } else {
      const c = structure.circles.find((x) => x.id === id)
      if (c) onChange({ ...state, id, name: c.name, purpose: c.purpose, parent_id: c.parent_id ?? '', acc: toEditItems(c.accountabilities), dom: toEditItems(c.domains), pol: toEditItems(c.policies) })
    }
  }
  return (
    <div className="rounded-xl border bg-muted/30 p-4">
      <div className="mb-3 flex items-center justify-between">
        <Pill tone="primary">{t(OP_LABEL[state.op])}</Pill>
        <Button variant="ghost" size="icon" aria-label={t('Remove modification')} onClick={onRemove}><Trash2 className="h-4 w-4" /></Button>
      </div>
      <div className="grid gap-3">
        {(isUpdate || isDelete) && (
          <div className="grid gap-1.5">
            <Label>{isRole ? t('Role') : t('Circle')}</Label>
            <Select value={state.id} onValueChange={pick}>
              <SelectTrigger aria-label={isRole ? t('Role') : t('Circle')}><SelectValue placeholder={t('Choose')} /></SelectTrigger>
              <SelectContent>{targets.map((x) => <SelectItem key={x.id} value={x.id}>{x.name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
        )}
        {!isDelete && (
          <>
            <div className="grid gap-1.5"><Label>{t('Name')}</Label><Input value={state.name} maxLength={120} onChange={(e) => onChange({ ...state, name: e.target.value })} /></div>
            <div className="grid gap-1.5"><Label>{t('Purpose')}</Label><Textarea rows={2} value={state.purpose} maxLength={2000} onChange={(e) => onChange({ ...state, purpose: e.target.value })} /></div>
            {isRole && (
              <div className="grid gap-1.5">
                <Label>{t('Circle')}</Label>
                <Select value={state.circle_id} onValueChange={(v) => onChange({ ...state, circle_id: v })}>
                  <SelectTrigger aria-label={t('Circle')}><SelectValue /></SelectTrigger>
                  <SelectContent>{structure.circles.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            )}
            {!isRole && state.parent_id !== '' && (
              <div className="grid gap-1.5">
                <Label>{t('Parent circle')}</Label>
                <Select value={state.parent_id} onValueChange={(v) => onChange({ ...state, parent_id: v })}>
                  <SelectTrigger aria-label={t('Parent circle')}><SelectValue /></SelectTrigger>
                  <SelectContent>{structure.circles.filter((c) => c.id !== state.id).map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            )}
            <ItemsEditor label={t('Accountabilities')} items={state.acc} onChange={(v) => onChange({ ...state, acc: v })} />
            <ItemsEditor label={t('Domains')} items={state.dom} onChange={(v) => onChange({ ...state, dom: v })} />
            {isRole && <ItemsEditor label={t('Decision authorities')} items={state.aut} onChange={(v) => onChange({ ...state, aut: v })} withLevel />}
            <ItemsEditor label={t('Policies')} items={state.pol} onChange={(v) => onChange({ ...state, pol: v })} />
            {isRole && (
              <div className="flex flex-wrap gap-6">
                <label className="flex items-center gap-2 text-sm"><Switch checked={state.multi} onCheckedChange={(v) => onChange({ ...state, multi: v })} />{t('Allow multiple role holders')}</label>
                <label className="flex items-center gap-2 text-sm"><Switch checked={state.govern} onCheckedChange={(v) => onChange({ ...state, govern: v })} />{t('Governance authority')}</label>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

export default function ProposalNew() {
  const { t } = useT()
  const navigate = useNavigate()
  const act = useAct()
  const location = useLocation()
  const [params] = useSearchParams()
  const editId = params.get('edit')
  const { session } = useSession()
  const { data: structure, isLoading } = useGet<Structure>('/structure')
  const { data: existing } = useGet<ProposalFull>(editId ? `/proposals/${editId}` : null)
  const draft = (location.state as { draft?: DraftState } | null)?.draft

  const [circle, setCircle] = useState(params.get('circle') ?? draft?.circle_id ?? '')
  const [title, setTitle] = useState(draft?.title ?? '')
  const [description, setDescription] = useState(draft?.description ?? '')
  const [reason, setReason] = useState(draft?.reason ?? '')
  const [impact, setImpact] = useState(draft?.expected_impact ?? '')
  const [ptype, setPtype] = useState(draft?.proposal_type ?? 'modify_role')
  const [ops, setOps] = useState<OpState[]>([])
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    if (!structure || loaded) return
    const root = structure.circles.find((c) => !c.parent_id)?.id ?? ''
    if (editId && existing) {
      setCircle(existing.circle_id ?? root)
      setTitle(existing.title ?? '')
      setDescription(existing.description ?? '')
      setReason(existing.reason ?? '')
      setImpact(existing.expected_impact ?? '')
      setPtype(existing.proposal_type ?? 'modify_role')
      setOps((existing.changes ?? []).map((c) => fromDraft(c, existing.circle_id ?? root)))
      setLoaded(true)
    } else if (!editId) {
      if (!circle) setCircle(root)
      setOps((draft?.changes ?? []).map((c) => fromDraft(c, draft?.circle_id ?? root)))
      setLoaded(true)
    }
  }, [structure, existing, editId, draft, loaded, circle])

  if (isLoading || !structure) return <LoadingBlock rows={4} />
  if (editId && existing && existing.status !== 'draft') return <ErrorBlock message={t('Only drafts can be edited.')} />

  const mode = circle ? effectiveMode(structure.circles, circle, session?.organization.default_governance_mode ?? 'consent') : null
  const addOp = (op: ChangeOpDraft['op']) => setOps((o) => [...o, blank(op, circle)])

  const save = async (submit: boolean) => {
    if (title.trim().length < 3) return toast.error(t('A title is required.'))
    if (submit && ops.length === 0) return toast.error(t('Add at least one modification before submitting.'))
    const changes = ops.map(toDraft)
    if (editId) {
      const r1 = await act('patch', `/proposals/${editId}`, { title: title.trim(), description, reason, expected_impact: impact, proposal_type: ptype, changes })
      if (!r1) return
      if (submit && !(await act('post', `/proposals/${editId}/submit`))) return
      navigate(`/governance/proposals/${editId}`)
      return
    }
    const res = await act<{ id: string }>('post', '/proposals', {
      circle_id: circle, title: title.trim(), description, reason, expected_impact: impact, proposal_type: ptype, changes, submit,
      ai_generated: draft?.ai_generated ?? false,
    })
    if (res) navigate(`/governance/proposals/${res.id}`)
  }

  return (
    <>
      <PageHeader title={editId ? t('Edit proposal') : t('New governance proposal')} subtitle={t('Describe the tension, propose concrete modifications and submit them into the circle\'s workflow.')} />
      {draft?.ai_generated && <div className="mb-4 rounded-lg border border-dashed border-[hsl(var(--ochre)/0.5)] bg-[hsl(var(--ochre)/0.08)] p-3 text-sm">{t('This draft was generated by Circle Intelligence. Review and adjust it - nothing has been changed yet.')}</div>}
      <div className="space-y-4">
        <Section title={t('Basics')} index={1}>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="grid gap-1.5 md:col-span-2"><Label htmlFor="p-title">{t('Title')}</Label><Input id="p-title" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} /></div>
            <div className="grid gap-1.5">
              <Label>{t('Related circle')}</Label>
              <Select value={circle} onValueChange={setCircle} disabled={Boolean(editId)}>
                <SelectTrigger aria-label={t('Related circle')}><SelectValue /></SelectTrigger>
                <SelectContent>{structure.circles.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent>
              </Select>
              {mode && <div className="flex items-center gap-2 text-xs text-muted-foreground"><ModePill mode={mode} />{t('Workflow in force for this circle')}</div>}
            </div>
            <div className="grid gap-1.5">
              <Label>{t('Type')}</Label>
              <Select value={ptype} onValueChange={setPtype}>
                <SelectTrigger aria-label={t('Type')}><SelectValue /></SelectTrigger>
                <SelectContent>{TYPES.map((x) => <SelectItem key={x} value={x}>{t(TYPE_LABEL[x])}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5"><Label htmlFor="p-desc">{t('Description')}</Label><Textarea id="p-desc" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} /></div>
            <div className="grid gap-1.5"><Label htmlFor="p-reason">{t('Reason for change (the tension)')}</Label><Textarea id="p-reason" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} /></div>
            <div className="grid gap-1.5 md:col-span-2"><Label htmlFor="p-impact">{t('Expected impact')}</Label><Textarea id="p-impact" rows={2} value={impact} onChange={(e) => setImpact(e.target.value)} /></div>
          </div>
        </Section>

        <Section
          title={t('Proposed modifications')}
          index={2}
          action={
            <DropdownMenu>
              <DropdownMenuTrigger asChild><Button size="sm" variant="outline"><Plus className="mr-1 h-4 w-4" />{t('Add modification')}</Button></DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {(['create_role', 'update_role', 'delete_role', 'create_circle', 'update_circle'] as const).map((o) => <DropdownMenuItem key={o} onSelect={() => addOp(o)}>{t(OP_LABEL[o])}</DropdownMenuItem>)}
              </DropdownMenuContent>
            </DropdownMenu>
          }
        >
          {ops.length === 0 && <p className="text-sm text-muted-foreground">{t('No modifications yet. When the proposal is accepted, all modifications are applied together in one auditable transaction; if it is rejected nothing changes.')}</p>}
          <div className="space-y-3">
            {ops.map((o, i) => (
              <OpEditor key={i} state={o} structure={structure} onChange={(s) => setOps(ops.map((x, j) => (j === i ? s : x)))} onRemove={() => setOps(ops.filter((_, j) => j !== i))} />
            ))}
          </div>
        </Section>

        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => navigate(-1)}>{t('Cancel')}</Button>
          <Button variant="secondary" onClick={() => save(false)}>{t('Save draft')}</Button>
          <Button onClick={() => save(true)}>{t('Submit proposal')}</Button>
        </div>
      </div>
    </>
  )
}
