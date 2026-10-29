import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ComboPicker } from '@/components/ComboPicker'
import { CatalogPicker, type PickedEntry } from '@/components/CatalogPicker'
import { useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import { CATEGORIES, customerRuleViolated } from '@/lib/portfolio'
import type { Category, Classification, CrmOrgRow } from '@/lib/portfolio-types'
import type { PersonRow, Structure } from '@/lib/types'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  defaultClassification?: Classification
}

export function ProjectCreateDialog({ open, onOpenChange, defaultClassification = 'customer' }: Readonly<Props>) {
  const { t } = useT()
  const act = useAct()
  const navigate = useNavigate()
  const { data: structure } = useGet<Structure>(open ? '/structure' : null)
  const { data: people } = useGet<PersonRow[]>(open ? '/people' : null)
  const { data: customers } = useGet<CrmOrgRow[]>(open ? '/crm/organizations' : null)

  const [classification, setClassification] = useState<Classification>(defaultClassification)
  const [name, setName] = useState('')
  const [shortName, setShortName] = useState('')
  const [projectNo, setProjectNo] = useState('')
  const [category, setCategory] = useState<Category>('development')
  const [circleId, setCircleId] = useState('')
  const [managerId, setManagerId] = useState('')
  const [customerIds, setCustomerIds] = useState<string[]>([])
  const [entries, setEntries] = useState<PickedEntry[]>([])
  const [description, setDescription] = useState('')
  const [isResearch, setIsResearch] = useState(false)
  const [aiRelevant, setAiRelevant] = useState(false)
  const [fundingProgram, setFundingProgram] = useState('')
  const [fundingAgency, setFundingAgency] = useState('')
  const [fundingRef, setFundingRef] = useState('')
  const [startDate, setStartDate] = useState('')
  const [dueDate, setDueDate] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (open) {
      setClassification(defaultClassification)
      setName('')
      setShortName('')
      setProjectNo('')
      setCategory('development')
      setManagerId('')
      setCustomerIds([])
      setEntries([])
      setDescription('')
      setIsResearch(false)
      setAiRelevant(false)
      setFundingProgram('')
      setFundingAgency('')
      setFundingRef('')
      setStartDate('')
      setDueDate('')
    }
  }, [open, defaultClassification])

  useEffect(() => {
    if (open && !circleId && structure?.circles.length) setCircleId(structure.circles.find((c) => c.parent_id)?.id ?? structure.circles[0].id)
  }, [open, circleId, structure])

  const missingCustomer = customerRuleViolated(classification, customerIds.length)
  const nameInvalid = name.trim().length < 3
  const dateInvalid = startDate !== '' && dueDate !== '' && dueDate < startDate
  const canSave = !nameInvalid && circleId !== '' && !missingCustomer && !dateInvalid && !busy

  const save = async () => {
    setBusy(true)
    const res = await act<{ id: string }>('post', '/portfolio', {
      name: name.trim(),
      description,
      circle_id: circleId,
      classification,
      category,
      short_name: shortName.trim() || null,
      project_no: projectNo.trim() || null,
      manager_id: managerId || null,
      start_date: startDate || null,
      due_date: dueDate || null,
      is_research: isResearch,
      ai_relevant: aiRelevant,
      funding_program: isResearch ? fundingProgram.trim() || null : null,
      funding_agency: isResearch ? fundingAgency.trim() || null : null,
      funding_ref: isResearch ? fundingRef.trim() || null : null,
      customer_org_ids: classification === 'customer' ? customerIds : [],
      entry_ids: entries.map((e) => e.id),
      status: 'active',
    })
    setBusy(false)
    if (res) {
      onOpenChange(false)
      navigate(`/projects/${res.id}`)
    }
  }

  const customerOptions = (customers ?? []).filter((c) => c.status === 'active').map((c) => ({ id: c.id, label: c.name, hint: c.city }))

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="font-display text-xl">{t('Create a project')}</DialogTitle>
          <DialogDescription>{t('Customer projects need at least one customer organization.')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <RadioGroup value={classification} onValueChange={(v) => setClassification(v as Classification)} className="grid grid-cols-2 gap-2" aria-label={t('Classification')}>
            {(['customer', 'internal'] as const).map((c) => (
              <Label key={c} htmlFor={`cls-${c}`} className="flex cursor-pointer items-center gap-2 rounded-lg border p-3 has-[:checked]:border-primary has-[:checked]:bg-primary/5">
                <RadioGroupItem id={`cls-${c}`} value={c} />
                {t(c === 'customer' ? 'Customer' : 'Internal')}
              </Label>
            ))}
          </RadioGroup>

          <div className="grid gap-1.5">
            <Label htmlFor="pc-name">{t('Name')} *</Label>
            <Input id="pc-name" value={name} maxLength={200} onChange={(e) => setName(e.target.value)} aria-invalid={name !== '' && nameInvalid} autoFocus />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="grid gap-1.5">
              <Label htmlFor="pc-short">{t('Short name')}</Label>
              <Input id="pc-short" value={shortName} maxLength={60} onChange={(e) => setShortName(e.target.value)} />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="pc-no">{t('Project number')}</Label>
              <Input id="pc-no" value={projectNo} maxLength={40} onChange={(e) => setProjectNo(e.target.value)} />
            </div>
          </div>

          {classification === 'customer' && (
            <div className="grid gap-1.5">
              <Label>{t('Customer organizations')} *</Label>
              <ComboPicker multiple options={customerOptions} value={customerIds} onChange={setCustomerIds} placeholder={t('Choose customers')} />
              {missingCustomer && <p className="text-xs text-destructive" role="alert">{t('Customer projects need at least one customer organization.')}</p>}
            </div>
          )}

          <div className="grid gap-3 sm:grid-cols-3">
            <div className="grid gap-1.5">
              <Label>{t('Category')}</Label>
              <Select value={category} onValueChange={(v) => setCategory(v as Category)}>
                <SelectTrigger aria-label={t('Category')}><SelectValue /></SelectTrigger>
                <SelectContent>{CATEGORIES.map((c) => <SelectItem key={c} value={c}>{t(c)}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label>{t('Circle')} *</Label>
              <Select value={circleId} onValueChange={setCircleId}>
                <SelectTrigger aria-label={t('Circle')}><SelectValue /></SelectTrigger>
                <SelectContent>{(structure?.circles ?? []).map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label>{t('Project manager')}</Label>
              <ComboPicker options={(people ?? []).map((p) => ({ id: p.id, label: p.name, hint: p.job_title }))} value={managerId ? [managerId] : []} onChange={(v) => setManagerId(v[0] ?? '')} placeholder={t('Project manager')} />
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="grid gap-1.5">
              <Label htmlFor="pc-start">{t('Start')}</Label>
              <Input id="pc-start" type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="pc-end">{t('End')}</Label>
              <Input id="pc-end" type="date" value={dueDate} aria-invalid={dateInvalid} onChange={(e) => setDueDate(e.target.value)} />
            </div>
          </div>

          <div className="grid gap-1.5">
            <Label>{t('Technologies, methods and topics')}</Label>
            <CatalogPicker value={entries} onChange={setEntries} />
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor="pc-desc">{t('Description')}</Label>
            <Textarea id="pc-desc" rows={3} value={description} maxLength={10000} onChange={(e) => setDescription(e.target.value)} />
          </div>

          <div className="flex flex-wrap gap-x-6 gap-y-2">
            <Label className="flex items-center gap-2"><Switch checked={isResearch} onCheckedChange={setIsResearch} />{t('This is a research project')}</Label>
            <Label className="flex items-center gap-2"><Switch checked={aiRelevant} onCheckedChange={setAiRelevant} />{t('Uses AI methods')}</Label>
          </div>
          {isResearch && (
            <fieldset className="grid gap-3 rounded-lg border bg-muted/30 p-3 sm:grid-cols-3">
              <legend className="px-1 text-xs font-medium text-muted-foreground">{t('Research & funding')}</legend>
              <div className="grid gap-1.5"><Label htmlFor="pc-fp">{t('Funding program')}</Label><Input id="pc-fp" value={fundingProgram} maxLength={160} onChange={(e) => setFundingProgram(e.target.value)} /></div>
              <div className="grid gap-1.5"><Label htmlFor="pc-fa">{t('Funding agency')}</Label><Input id="pc-fa" value={fundingAgency} maxLength={160} onChange={(e) => setFundingAgency(e.target.value)} /></div>
              <div className="grid gap-1.5"><Label htmlFor="pc-fr">{t('Funding reference')}</Label><Input id="pc-fr" value={fundingRef} maxLength={80} onChange={(e) => setFundingRef(e.target.value)} /></div>
            </fieldset>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t('Cancel')}</Button>
          <Button onClick={save} disabled={!canSave}>{t('Create')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
