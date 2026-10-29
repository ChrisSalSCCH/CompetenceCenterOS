import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ComboPicker } from '@/components/ComboPicker'
import { useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import { customerRuleViolated, fullName } from '@/lib/portfolio'
import type { CrmContactRow, CrmOrgRow, OrgRelation, ProjectDetailData } from '@/lib/portfolio-types'

const RELATIONS: OrgRelation[] = ['customer', 'partner', 'research_partner', 'funder', 'subcontractor', 'other']

interface OrgDraft { id: string; relation: OrgRelation }
interface ContactDraft { id: string; role: string }

export function ProjectLinksDialog({ p, open, onOpenChange }: Readonly<{ p: ProjectDetailData; open: boolean; onOpenChange: (v: boolean) => void }>) {
  const { t } = useT()
  const act = useAct()
  const { data: orgs } = useGet<CrmOrgRow[]>(open ? '/crm/organizations' : null)
  const { data: contacts } = useGet<CrmContactRow[]>(open ? '/crm/contacts' : null)
  const [orgDraft, setOrgDraft] = useState<OrgDraft[]>([])
  const [contactDraft, setContactDraft] = useState<ContactDraft[]>([])

  useEffect(() => {
    if (open) {
      setOrgDraft(p.orgs.map((o) => ({ id: o.id, relation: o.relation })))
      setContactDraft(p.contacts.map((c) => ({ id: c.id, role: c.contact_role ?? '' })))
    }
  }, [open, p])

  const orgName = (id: string) => orgs?.find((o) => o.id === id)?.name ?? p.orgs.find((o) => o.id === id)?.name ?? id
  const contactName = (id: string) => {
    const c = contacts?.find((x) => x.id === id)
    if (c) return fullName(c)
    const known = p.contacts.find((x) => x.id === id)
    return known ? fullName(known) : id
  }
  const missingCustomer = customerRuleViolated(p.classification, orgDraft.filter((o) => o.relation === 'customer').length)

  const save = async () => {
    const a = await act('put', `/portfolio/${p.id}/orgs`, { items: orgDraft.map((o) => ({ crm_org_id: o.id, relation: o.relation })) })
    if (!a) return
    const b = await act('put', `/portfolio/${p.id}/contacts`, { items: contactDraft.map((c) => ({ contact_id: c.id, contact_role: c.role.trim() || null })) })
    if (b) onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="font-display text-xl">{t('Linked organizations')}</DialogTitle>
          <DialogDescription>{p.classification === 'customer' ? t('Customer projects need at least one customer organization.') : t('Customer contacts')}</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <ul className="space-y-2">
            {orgDraft.map((o) => (
              <li key={`${o.id}-${o.relation}`} className="flex items-center gap-2">
                <span className="flex-1 truncate text-sm font-medium">{orgName(o.id)}</span>
                <Select value={o.relation} onValueChange={(v) => setOrgDraft((d) => d.map((x) => (x === o ? { ...x, relation: v as OrgRelation } : x)))}>
                  <SelectTrigger className="w-44" aria-label={t('Relationship')}><SelectValue /></SelectTrigger>
                  <SelectContent>{RELATIONS.map((r) => <SelectItem key={r} value={r}>{t(r.replaceAll('_', ' '))}</SelectItem>)}</SelectContent>
                </Select>
                <Button variant="ghost" size="icon" aria-label={t('Remove')} onClick={() => setOrgDraft((d) => d.filter((x) => x !== o))}><X className="h-4 w-4" /></Button>
              </li>
            ))}
          </ul>
          <ComboPicker options={(orgs ?? []).map((o) => ({ id: o.id, label: o.name, hint: o.city }))} value={[]} onChange={(v) => v[0] && setOrgDraft((d) => [...d, { id: v[0], relation: p.classification === 'customer' && !d.some((x) => x.relation === 'customer') ? 'customer' : 'partner' }])} placeholder={t('Add')} ariaLabel={t('Add')} />
          {missingCustomer && <p className="text-xs text-destructive" role="alert">{t('Customer projects need at least one customer organization.')}</p>}

          <h3 className="pt-2 font-display text-base font-semibold">{t('Customer contacts')}</h3>
          <ul className="space-y-2">
            {contactDraft.map((c) => (
              <li key={c.id} className="flex items-center gap-2">
                <span className="flex-1 truncate text-sm font-medium">{contactName(c.id)}</span>
                <Input className="w-44" value={c.role} maxLength={60} placeholder={t('Contact role')} aria-label={t('Contact role')} onChange={(e) => setContactDraft((d) => d.map((x) => (x.id === c.id ? { ...x, role: e.target.value } : x)))} />
                <Button variant="ghost" size="icon" aria-label={t('Remove')} onClick={() => setContactDraft((d) => d.filter((x) => x.id !== c.id))}><X className="h-4 w-4" /></Button>
              </li>
            ))}
          </ul>
          <ComboPicker
            options={(contacts ?? []).filter((c) => !contactDraft.some((d) => d.id === c.id)).map((c) => ({ id: c.id, label: fullName(c), hint: c.orgs.map((o) => o.name).join(', ') }))}
            value={[]}
            onChange={(v) => v[0] && setContactDraft((d) => [...d, { id: v[0], role: '' }])}
            placeholder={t('Add')}
            ariaLabel={t('Customer contacts')}
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t('Cancel')}</Button>
          <Button onClick={save} disabled={missingCustomer}>{t('Save')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
