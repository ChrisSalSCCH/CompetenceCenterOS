import { useEffect, useState } from 'react'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ComboPicker } from '@/components/ComboPicker'
import { useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import { CATEGORIES, PHASES, PROJECT_STATUSES, customerRuleViolated } from '@/lib/portfolio'
import type { Category, Classification, Phase, ProjectDetailData } from '@/lib/portfolio-types'
import type { PersonRow } from '@/lib/types'

type FormState = ReturnType<typeof toForm>

export function ProjectEditDialog({ p, open, onOpenChange }: Readonly<{ p: ProjectDetailData; open: boolean; onOpenChange: (v: boolean) => void }>) {
  const { t } = useT()
  const act = useAct()
  const { data: people } = useGet<PersonRow[]>(open ? '/people' : null)
  const [form, setForm] = useState(() => toForm(p))
  useEffect(() => {
    if (open) setForm(toForm(p))
  }, [open, p])
  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((f) => ({ ...f, [key]: value }))
  }

  const customerCount = p.orgs.filter((o) => o.relation === 'customer').length
  const missingCustomer = customerRuleViolated(form.classification, customerCount)
  const dateInvalid = form.start_date !== '' && form.due_date !== '' && form.due_date < form.start_date
  const canSave = form.name.trim().length >= 3 && !missingCustomer && !dateInvalid

  const save = async () => {
    const res = await act('patch', `/portfolio/${p.id}`, {
      name: form.name.trim(),
      description: form.description,
      classification: form.classification,
      category: form.category,
      phase: form.phase,
      status: form.status,
      short_name: form.short_name.trim() || null,
      project_no: form.project_no.trim() || null,
      org_unit: form.org_unit.trim() || null,
      manager_id: form.manager_id || null,
      start_date: form.start_date || null,
      due_date: form.due_date || null,
      is_research: form.is_research,
      ai_relevant: form.ai_relevant,
      funding_program: form.funding_program.trim() || null,
      funding_agency: form.funding_agency.trim() || null,
      funding_ref: form.funding_ref.trim() || null,
    })
    if (res) onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader><DialogTitle className="font-display text-xl">{t('Phase, status and dates')}</DialogTitle></DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1.5"><Label htmlFor="pe-name">{t('Name')} *</Label><Input id="pe-name" value={form.name} maxLength={200} onChange={(e) => set('name', e.target.value)} /></div>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="grid gap-1.5"><Label htmlFor="pe-short">{t('Short name')}</Label><Input id="pe-short" value={form.short_name} maxLength={60} onChange={(e) => set('short_name', e.target.value)} /></div>
            <div className="grid gap-1.5"><Label htmlFor="pe-no">{t('Project number')}</Label><Input id="pe-no" value={form.project_no} maxLength={40} onChange={(e) => set('project_no', e.target.value)} /></div>
            <div className="grid gap-1.5"><Label htmlFor="pe-unit">{t('Organizational unit')}</Label><Input id="pe-unit" value={form.org_unit} maxLength={120} onChange={(e) => set('org_unit', e.target.value)} /></div>
          </div>
          <div className="grid gap-3 sm:grid-cols-4">
            <div className="grid gap-1.5">
              <Label>{t('Classification')}</Label>
              <Select value={form.classification} onValueChange={(v) => set('classification', v as Classification)}>
                <SelectTrigger aria-label={t('Classification')}><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="customer">{t('Customer')}</SelectItem><SelectItem value="internal">{t('Internal')}</SelectItem></SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label>{t('Category')}</Label>
              <Select value={form.category} onValueChange={(v) => set('category', v as Category)}>
                <SelectTrigger aria-label={t('Category')}><SelectValue /></SelectTrigger>
                <SelectContent>{CATEGORIES.map((c) => <SelectItem key={c} value={c}>{t(c)}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label>{t('Phase')}</Label>
              <Select value={form.phase} onValueChange={(v) => set('phase', v as Phase)}>
                <SelectTrigger aria-label={t('Phase')}><SelectValue /></SelectTrigger>
                <SelectContent>{PHASES.map((c) => <SelectItem key={c} value={c}>{t(c)}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label>{t('Status')}</Label>
              <Select value={form.status} onValueChange={(v) => set('status', v)}>
                <SelectTrigger aria-label={t('Status')}><SelectValue /></SelectTrigger>
                <SelectContent>{PROJECT_STATUSES.map((c) => <SelectItem key={c} value={c}>{t(c.replaceAll('_', ' '))}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </div>
          {missingCustomer && <p className="text-xs text-destructive" role="alert">{t('Customer projects need at least one customer organization.')}</p>}
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="grid gap-1.5">
              <Label>{t('Project manager')}</Label>
              <ComboPicker options={(people ?? []).map((x) => ({ id: x.id, label: x.name, hint: x.job_title }))} value={form.manager_id ? [form.manager_id] : []} onChange={(v) => set('manager_id', v[0] ?? '')} placeholder={t('Project manager')} />
            </div>
            <div className="grid gap-1.5"><Label htmlFor="pe-start">{t('Start')}</Label><Input id="pe-start" type="date" value={form.start_date} onChange={(e) => set('start_date', e.target.value)} /></div>
            <div className="grid gap-1.5"><Label htmlFor="pe-end">{t('End')}</Label><Input id="pe-end" type="date" value={form.due_date} aria-invalid={dateInvalid} onChange={(e) => set('due_date', e.target.value)} /></div>
          </div>
          <div className="grid gap-1.5"><Label htmlFor="pe-desc">{t('Description')}</Label><Textarea id="pe-desc" rows={4} value={form.description} maxLength={10000} onChange={(e) => set('description', e.target.value)} /></div>
          <div className="flex flex-wrap gap-x-6 gap-y-2">
            <Label className="flex items-center gap-2"><Switch checked={form.is_research} onCheckedChange={(v) => set('is_research', v)} />{t('This is a research project')}</Label>
            <Label className="flex items-center gap-2"><Switch checked={form.ai_relevant} onCheckedChange={(v) => set('ai_relevant', v)} />{t('Uses AI methods')}</Label>
          </div>
          {form.is_research && (
            <fieldset className="grid gap-3 rounded-lg border bg-muted/30 p-3 sm:grid-cols-3">
              <legend className="px-1 text-xs font-medium text-muted-foreground">{t('Research & funding')}</legend>
              <div className="grid gap-1.5"><Label htmlFor="pe-fp">{t('Funding program')}</Label><Input id="pe-fp" value={form.funding_program} maxLength={160} onChange={(e) => set('funding_program', e.target.value)} /></div>
              <div className="grid gap-1.5"><Label htmlFor="pe-fa">{t('Funding agency')}</Label><Input id="pe-fa" value={form.funding_agency} maxLength={160} onChange={(e) => set('funding_agency', e.target.value)} /></div>
              <div className="grid gap-1.5"><Label htmlFor="pe-fr">{t('Funding reference')}</Label><Input id="pe-fr" value={form.funding_ref} maxLength={80} onChange={(e) => set('funding_ref', e.target.value)} /></div>
            </fieldset>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t('Cancel')}</Button>
          <Button onClick={save} disabled={!canSave}>{t('Save')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function toForm(p: ProjectDetailData) {
  return {
    name: p.name,
    description: p.description,
    classification: p.classification,
    category: p.category,
    phase: p.phase,
    status: p.status as string,
    short_name: p.short_name ?? '',
    project_no: p.project_no ?? '',
    org_unit: p.org_unit ?? '',
    manager_id: p.manager_id ?? '',
    start_date: p.start_date ?? '',
    due_date: p.due_date ?? '',
    is_research: p.is_research,
    ai_relevant: p.ai_relevant,
    funding_program: p.funding_program ?? '',
    funding_agency: p.funding_agency ?? '',
    funding_ref: p.funding_ref ?? '',
  }
}
