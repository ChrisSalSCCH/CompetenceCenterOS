import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ItemsEditor, cleanItems, toEditItems, type EditItem } from '@/components/ItemsEditor'
import { ModePill } from '@/components/kit'
import { useSession } from '@/contexts/SessionContext'
import { useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import { descendantIds, effectiveMode } from '@/lib/structure'
import type { CircleNode, RoleNode, SubmitResult } from '@/lib/types'

export function useSubmitFeedback() {
  const { t } = useT()
  const navigate = useNavigate()
  return (res: SubmitResult | null): boolean => {
    if (!res) return false
    if (res.applied) {
      toast.success(t('Change applied and recorded in the governance history.'))
    } else {
      toast.info(t('Submitted as a governance proposal - this circle does not allow direct changes for you.'), {
        action: { label: t('Open proposal'), onClick: () => navigate(`/governance/proposals/${res.proposal_id}`) },
      })
    }
    return true
  }
}

function PolicyHint({ circles, circleId }: Readonly<{ circles: CircleNode[]; circleId: string }>) {
  const { t } = useT()
  const { session, canGovern } = useSession()
  if (!session || !circleId) return null
  const mode = effectiveMode(circles, circleId, session.organization.default_governance_mode)
  const direct = mode === 'direct' && canGovern(circleId)
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-dashed bg-muted/50 p-3 text-xs">
      <ModePill mode={mode} />
      <span>{direct ? t('You are authorized: the change is applied immediately and recorded in the history.') : t('This change will be submitted as a governance proposal and only takes effect after the decision.')}</span>
    </div>
  )
}

interface CircleFormProps {
  open: boolean
  onOpenChange: (v: boolean) => void
  circles: CircleNode[]
  circle?: CircleNode
  parentId?: string
}

export function CircleFormDialog({ open, onOpenChange, circles, circle, parentId }: Readonly<CircleFormProps>) {
  const { t } = useT()
  const act = useAct()
  const feedback = useSubmitFeedback()
  const [name, setName] = useState('')
  const [purpose, setPurpose] = useState('')
  const [description, setDescription] = useState('')
  const [parent, setParent] = useState('')
  const [mode, setMode] = useState('inherit')
  const [acc, setAcc] = useState<EditItem[]>([])
  const [dom, setDom] = useState<EditItem[]>([])
  const [pol, setPol] = useState<EditItem[]>([])
  const [reason, setReason] = useState('')

  useEffect(() => {
    if (!open) return
    setName(circle?.name ?? '')
    setPurpose(circle?.purpose ?? '')
    setDescription(circle?.description ?? '')
    setParent(circle?.parent_id ?? parentId ?? '')
    setMode(circle?.governance_mode ?? 'inherit')
    setAcc(toEditItems(circle?.accountabilities))
    setDom(toEditItems(circle?.domains))
    setPol(toEditItems(circle?.policies))
    setReason('')
  }, [open, circle, parentId])

  const blocked = circle ? new Set([circle.id, ...descendantIds(circles, circle.id)]) : new Set<string>()
  const parents = circles.filter((c) => !blocked.has(c.id))
  const isRoot = circle ? circle.parent_id === null : false

  const submit = async () => {
    if (!name.trim()) return toast.error(t('A name is required.'))
    if (!circle && !parent) return toast.error(t('Choose a parent circle.'))
    const body: Record<string, unknown> = {
      name: name.trim(), purpose, description,
      governance_mode: mode === 'inherit' ? null : mode,
      accountabilities: cleanItems(acc), domains: cleanItems(dom), policies: cleanItems(pol), reason,
    }
    if (!isRoot && (!circle || parent !== circle.parent_id)) body.parent_id = parent
    const res = circle ? await act<SubmitResult>('patch', `/circles/${circle.id}`, body) : await act<SubmitResult>('post', '/circles', body)
    if (feedback(res)) onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="font-display text-xl">{circle ? t('Edit circle') : t('New circle')}</DialogTitle>
          <DialogDescription>{t('A circle is a group of roles with a shared purpose. Circles can be nested without limit.')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <PolicyHint circles={circles} circleId={circle?.id ?? parent} />
          <div className="grid gap-1.5">
            <Label htmlFor="c-name">{t('Name')}</Label>
            <Input id="c-name" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />
          </div>
          {!isRoot && (
            <div className="grid gap-1.5">
              <Label>{t('Parent circle')}</Label>
              <Select value={parent} onValueChange={setParent}>
                <SelectTrigger aria-label={t('Parent circle')}><SelectValue placeholder={t('Choose a parent circle.')} /></SelectTrigger>
                <SelectContent>{parents.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          )}
          <div className="grid gap-1.5">
            <Label htmlFor="c-purpose">{t('Purpose')}</Label>
            <Textarea id="c-purpose" value={purpose} maxLength={2000} rows={2} onChange={(e) => setPurpose(e.target.value)} />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="c-desc">{t('Description')}</Label>
            <Textarea id="c-desc" value={description} maxLength={10000} rows={3} onChange={(e) => setDescription(e.target.value)} />
          </div>
          <div className="grid gap-1.5">
            <Label>{t('Governance workflow')}</Label>
            <Select value={mode} onValueChange={setMode}>
              <SelectTrigger aria-label={t('Governance workflow')}><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="inherit">{t('Inherit from parent circle')}</SelectItem>
                <SelectItem value="direct">{t('Direct change')}</SelectItem>
                <SelectItem value="approval">{t('Approval')}</SelectItem>
                <SelectItem value="consent">{t('Consent')}</SelectItem>
                <SelectItem value="holacracy">{t('Structured (Holacracy)')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <ItemsEditor label={t('Accountabilities')} items={acc} onChange={setAcc} />
          <ItemsEditor label={t('Domains')} items={dom} onChange={setDom} />
          <ItemsEditor label={t('Policies')} items={pol} onChange={setPol} />
          <div className="grid gap-1.5">
            <Label htmlFor="c-reason">{t('Reason for the change')}</Label>
            <Textarea id="c-reason" value={reason} maxLength={2000} rows={2} onChange={(e) => setReason(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t('Cancel')}</Button>
          <Button onClick={submit}>{circle ? t('Save changes') : t('Create circle')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

interface RoleTemplate {
  key: string
  name: string
  purpose: string
  accountabilities: string[]
  domains: string[]
  authorities: string[]
}

interface RoleFormProps {
  open: boolean
  onOpenChange: (v: boolean) => void
  circles: CircleNode[]
  role?: RoleNode
  circleId?: string
}

export function RoleFormDialog({ open, onOpenChange, circles, role, circleId }: Readonly<RoleFormProps>) {
  const { t } = useT()
  const act = useAct()
  const feedback = useSubmitFeedback()
  const { data: templates } = useGet<RoleTemplate[]>(open && !role ? '/role-templates' : null)
  const [name, setName] = useState('')
  const [circle, setCircle] = useState('')
  const [purpose, setPurpose] = useState('')
  const [multiple, setMultiple] = useState(false)
  const [govern, setGovern] = useState(false)
  const [acc, setAcc] = useState<EditItem[]>([])
  const [dom, setDom] = useState<EditItem[]>([])
  const [aut, setAut] = useState<EditItem[]>([])
  const [pol, setPol] = useState<EditItem[]>([])
  const [reason, setReason] = useState('')
  const [templateKey, setTemplateKey] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setName(role?.name ?? '')
    setCircle(role?.circle_id ?? circleId ?? '')
    setPurpose(role?.purpose ?? '')
    setMultiple(role?.allow_multiple ?? false)
    setGovern(role?.can_govern ?? false)
    setAcc(toEditItems(role?.accountabilities))
    setDom(toEditItems(role?.domains))
    setAut(toEditItems(role?.authorities))
    setPol(toEditItems(role?.policies))
    setReason('')
    setTemplateKey(null)
  }, [open, role, circleId])

  const applyTemplate = (key: string) => {
    const tpl = templates?.find((x) => x.key === key)
    if (!tpl) return
    setTemplateKey(key)
    setName(tpl.name)
    setPurpose(tpl.purpose)
    setAcc(tpl.accountabilities.map((text) => ({ text })))
    setDom(tpl.domains.map((text) => ({ text })))
    setAut(tpl.authorities.map((text) => ({ text, level: 'decides' })))
  }

  const submit = async () => {
    if (!name.trim()) return toast.error(t('A name is required.'))
    if (!circle) return toast.error(t('Choose a circle.'))
    const body = {
      name: name.trim(), purpose, allow_multiple: multiple, can_govern: govern, circle_id: circle,
      accountabilities: cleanItems(acc), domains: cleanItems(dom), authorities: cleanItems(aut, true), policies: cleanItems(pol), reason,
      ...(templateKey && !role ? { template_key: templateKey } : {}),
    }
    const res = role ? await act<SubmitResult>('patch', `/roles/${role.id}`, body) : await act<SubmitResult>('post', '/roles', body)
    if (feedback(res)) onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="font-display text-xl">{role ? t('Edit role') : t('New role')}</DialogTitle>
          <DialogDescription>{t('Accountabilities are ongoing activities, domains are things the role controls, decision authorities define who may decide what. They are separate on purpose.')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <PolicyHint circles={circles} circleId={circle} />
          {!role && templates && (
            <div className="grid gap-1.5">
              <Label>{t('Start from a template (optional)')}</Label>
              <Select value={templateKey ?? ''} onValueChange={applyTemplate}>
                <SelectTrigger aria-label={t('Role template')}><SelectValue placeholder={t('Choose a template')} /></SelectTrigger>
                <SelectContent>{templates.map((x) => <SelectItem key={x.key} value={x.key}>{x.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          )}
          <div className="grid gap-1.5">
            <Label htmlFor="r-name">{t('Name')}</Label>
            <Input id="r-name" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="grid gap-1.5">
            <Label>{t('Circle')}</Label>
            <Select value={circle} onValueChange={setCircle}>
              <SelectTrigger aria-label={t('Circle')}><SelectValue placeholder={t('Choose a circle.')} /></SelectTrigger>
              <SelectContent>{circles.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="r-purpose">{t('Purpose')}</Label>
            <Textarea id="r-purpose" value={purpose} maxLength={2000} rows={2} onChange={(e) => setPurpose(e.target.value)} />
          </div>
          <ItemsEditor label={t('Accountabilities')} hint={t('Ongoing activities the role is expected to perform.')} items={acc} onChange={setAcc} />
          <ItemsEditor label={t('Domains')} hint={t('Things the role exclusively controls.')} items={dom} onChange={setDom} />
          <ItemsEditor label={t('Decision authorities')} hint={t('Decisions that this role may make, must consent to, or must be consulted on.')} items={aut} onChange={setAut} withLevel />
          <ItemsEditor label={t('Policies')} items={pol} onChange={setPol} />
          <div className="flex items-center justify-between rounded-lg border p-3">
            <div>
              <Label htmlFor="r-multi">{t('Allow multiple role holders')}</Label>
              <p className="text-xs text-muted-foreground">{t('Several people may fill this role at the same time.')}</p>
            </div>
            <Switch id="r-multi" checked={multiple} onCheckedChange={setMultiple} />
          </div>
          <div className="flex items-center justify-between rounded-lg border p-3">
            <div>
              <Label htmlFor="r-gov">{t('Governance authority')}</Label>
              <p className="text-xs text-muted-foreground">{t('Holders may change this circle\'s structure and decide proposals.')}</p>
            </div>
            <Switch id="r-gov" checked={govern} onCheckedChange={setGovern} />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="r-reason">{t('Reason for the change')}</Label>
            <Textarea id="r-reason" value={reason} maxLength={2000} rows={2} onChange={(e) => setReason(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t('Cancel')}</Button>
          <Button onClick={submit}>{role ? t('Save changes') : t('Create role')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
