import { useEffect, useState } from 'react'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ComboPicker } from '@/components/ComboPicker'
import { useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import { CRM_RELATIONS } from '@/lib/portfolio'
import type { CatalogEntry, CrmOrgDetail, CrmOrgRow, CrmRelationType } from '@/lib/portfolio-types'
import type { PersonRow } from '@/lib/types'

const SIZES = ['micro', 'small', 'medium', 'large', 'public'] as const
const NONE = 'none'

interface FormState {
  name: string
  legal_name: string
  vat_id: string
  website: string
  industry: string
  city: string
  country: string
  address: string
  size_class: string
  parent: string[]
  relation_types: CrmRelationType[]
  owner: string[]
  customer_since: string
  status: 'active' | 'inactive'
  notes: string
}

function initial(org: CrmOrgDetail | null): FormState {
  return {
    name: org?.name ?? '', legal_name: org?.legal_name ?? '', vat_id: org?.vat_id ?? '', website: org?.website ?? '', industry: org?.industry_entry_id ?? NONE,
    city: org?.city ?? '', country: org?.country ?? 'Austria', address: org?.address ?? '', size_class: org?.size_class ?? NONE,
    parent: org?.parent_id ? [org.parent_id] : [], relation_types: org?.relation_types ?? ['customer'], owner: org?.owner_user_id ? [org.owner_user_id] : [],
    customer_since: org?.customer_since ?? '', status: org?.status ?? 'active', notes: org?.notes ?? '',
  }
}

const VAT_RE = /^[A-Za-z0-9 .-]{4,40}$/

export function OrgFormDialog({ org, open, onOpenChange }: Readonly<{ org: CrmOrgDetail | null; open: boolean; onOpenChange: (v: boolean) => void }>) {
  const { t } = useT()
  const act = useAct()
  const { data: industries } = useGet<CatalogEntry[]>(open ? '/catalog' : null, { kind: 'industry' })
  const { data: orgs } = useGet<CrmOrgRow[]>(open ? '/crm/organizations' : null)
  const { data: people } = useGet<PersonRow[]>(open ? '/people' : null)
  const [f, setF] = useState<FormState>(initial(org))
  useEffect(() => {
    if (open) setF(initial(org))
  }, [open, org])
  const patch = (p: Partial<FormState>) => setF((x) => ({ ...x, ...p }))

  const toggleRelation = (r: CrmRelationType, on: boolean) => patch({ relation_types: on ? [...f.relation_types, r] : f.relation_types.filter((x) => x !== r) })
  const vatInvalid = f.vat_id.trim() !== '' && !VAT_RE.test(f.vat_id.trim())
  const webInvalid = f.website.trim() !== '' && !/^https?:\/\//.test(f.website.trim())
  const canSave = f.name.trim().length >= 2 && f.relation_types.length > 0 && !vatInvalid && !webInvalid

  const save = async () => {
    const body = {
      name: f.name.trim(), legal_name: f.legal_name.trim() || null, vat_id: f.vat_id.trim() || null, website: f.website.trim() || null,
      industry_entry_id: f.industry === NONE ? null : f.industry, city: f.city.trim() || null, country: f.country.trim() || null, address: f.address.trim() || null,
      size_class: f.size_class === NONE ? null : f.size_class, parent_id: f.parent[0] ?? null, relation_types: f.relation_types, owner_user_id: f.owner[0] ?? null,
      customer_since: f.customer_since || null, status: f.status, notes: f.notes,
    }
    const res = org ? await act('patch', `/crm/organizations/${org.id}`, body) : await act('post', '/crm/organizations', body)
    if (res) onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader><DialogTitle className="font-display text-xl">{org ? t('Edit') : t('New organization')}</DialogTitle></DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="grid gap-1.5"><Label htmlFor="co-name">{t('Name')} *</Label><Input id="co-name" value={f.name} maxLength={200} onChange={(e) => patch({ name: e.target.value })} autoFocus /></div>
            <div className="grid gap-1.5"><Label htmlFor="co-legal">{t('Legal name')}</Label><Input id="co-legal" value={f.legal_name} maxLength={250} onChange={(e) => patch({ legal_name: e.target.value })} /></div>
            <div className="grid gap-1.5"><Label htmlFor="co-vat">{t('VAT ID')}</Label><Input id="co-vat" value={f.vat_id} maxLength={40} aria-invalid={vatInvalid} onChange={(e) => patch({ vat_id: e.target.value })} /></div>
            <div className="grid gap-1.5"><Label htmlFor="co-web">{t('Website')}</Label><Input id="co-web" value={f.website} maxLength={300} placeholder="https://" aria-invalid={webInvalid} onChange={(e) => patch({ website: e.target.value })} /></div>
          </div>
          <fieldset className="rounded-lg border p-3">
            <legend className="px-1 text-xs font-medium text-muted-foreground">{t('Relationship types')} *</legend>
            <div className="flex flex-wrap gap-x-4 gap-y-2">
              {CRM_RELATIONS.map((r) => (
                <Label key={r} className="flex items-center gap-2 text-sm font-normal">
                  <Checkbox checked={f.relation_types.includes(r)} onCheckedChange={(v) => toggleRelation(r, v === true)} />
                  {t(r.replaceAll('_', ' '))}
                </Label>
              ))}
            </div>
          </fieldset>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="grid gap-1.5">
              <Label>{t('Industry')}</Label>
              <Select value={f.industry} onValueChange={(v) => patch({ industry: v })}>
                <SelectTrigger aria-label={t('Industry')}><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value={NONE}>–</SelectItem>{(industries ?? []).map((i) => <SelectItem key={i.id} value={i.id}>{i.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label>{t('Size')}</Label>
              <Select value={f.size_class} onValueChange={(v) => patch({ size_class: v })}>
                <SelectTrigger aria-label={t('Size')}><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value={NONE}>–</SelectItem>{SIZES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label>{t('Status')}</Label>
              <Select value={f.status} onValueChange={(v) => patch({ status: v as 'active' | 'inactive' })}>
                <SelectTrigger aria-label={t('Status')}><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="active">{t('active')}</SelectItem><SelectItem value="inactive">{t('inactive')}</SelectItem></SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="grid gap-1.5"><Label htmlFor="co-city">{t('City')}</Label><Input id="co-city" value={f.city} maxLength={120} onChange={(e) => patch({ city: e.target.value })} /></div>
            <div className="grid gap-1.5"><Label htmlFor="co-country">{t('Country')}</Label><Input id="co-country" value={f.country} maxLength={80} onChange={(e) => patch({ country: e.target.value })} /></div>
            <div className="grid gap-1.5"><Label htmlFor="co-since">{t('Customer since')}</Label><Input id="co-since" type="date" value={f.customer_since} onChange={(e) => patch({ customer_since: e.target.value })} /></div>
          </div>
          <div className="grid gap-1.5"><Label htmlFor="co-addr">{t('Address')}</Label><Input id="co-addr" value={f.address} maxLength={300} onChange={(e) => patch({ address: e.target.value })} /></div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="grid gap-1.5">
              <Label>{t('Parent organization')}</Label>
              <ComboPicker options={(orgs ?? []).filter((o) => o.id !== org?.id).map((o) => ({ id: o.id, label: o.name, hint: o.city }))} value={f.parent} onChange={(v) => patch({ parent: v.slice(-1) })} placeholder={t('Parent organization')} />
              {f.parent.length > 0 && <button type="button" className="text-left text-xs text-muted-foreground hover:text-destructive" onClick={() => patch({ parent: [] })}>{t('Remove')}</button>}
            </div>
            <div className="grid gap-1.5">
              <Label>{t('Relationship owner')}</Label>
              <ComboPicker options={(people ?? []).map((p) => ({ id: p.id, label: p.name, hint: p.job_title }))} value={f.owner} onChange={(v) => patch({ owner: v.slice(-1) })} placeholder={t('Relationship owner')} />
              {f.owner.length > 0 && <button type="button" className="text-left text-xs text-muted-foreground hover:text-destructive" onClick={() => patch({ owner: [] })}>{t('Remove')}</button>}
            </div>
          </div>
          <div className="grid gap-1.5"><Label htmlFor="co-notes">{t('Notes')}</Label><Textarea id="co-notes" rows={3} value={f.notes} maxLength={5000} onChange={(e) => patch({ notes: e.target.value })} /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t('Cancel')}</Button>
          <Button onClick={save} disabled={!canSave}>{t('Save')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
