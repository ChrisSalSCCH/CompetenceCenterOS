import { useEffect, useState } from 'react'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { ComboPicker } from '@/components/ComboPicker'
import { useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import type { CatalogEntry, PortfolioRow } from '@/lib/portfolio-types'
import type { OppDetail } from '@/lib/sales-types'
import type { PersonRow } from '@/lib/types'

interface ContactRow {
  id: string
  first_name: string
  last_name: string
  job_title: string | null
}

export function OppLinksDialog({ opp, open, onOpenChange }: Readonly<{ opp: OppDetail; open: boolean; onOpenChange: (v: boolean) => void }>) {
  const { t } = useT()
  const act = useAct()
  const { data: contacts } = useGet<ContactRow[]>(open ? '/crm/contacts' : null, { crm_org_id: opp.crm_org_id })
  const { data: allContacts } = useGet<ContactRow[]>(open ? '/crm/contacts' : null)
  const { data: people } = useGet<PersonRow[]>(open ? '/people' : null)
  const { data: catalog } = useGet<CatalogEntry[]>(open ? '/catalog' : null)
  const { data: projects } = useGet<PortfolioRow[]>(open ? '/portfolio' : null)
  const [contactIds, setContactIds] = useState<string[]>([])
  const [teamIds, setTeamIds] = useState<string[]>([])
  const [entryIds, setEntryIds] = useState<string[]>([])
  const [refIds, setRefIds] = useState<string[]>([])

  useEffect(() => {
    if (open) {
      setContactIds(opp.contacts.map((c) => c.id))
      setTeamIds(opp.team.map((m) => m.user_id))
      setEntryIds(opp.entries.map((e) => e.id))
      setRefIds(opp.references.map((r) => r.id))
    }
  }, [open, opp])

  const pool = allContacts ?? contacts ?? []
  const save = async () => {
    const roleOf = new Map(opp.contacts.map((c) => [c.id, c.contact_role]))
    const teamOf = new Map(opp.team.map((m) => [m.user_id, m]))
    const res = await act('put', `/commercial/opportunities/${opp.id}/links`, {
      contacts: contactIds.map((id) => ({ contact_id: id, contact_role: roleOf.get(id) ?? null })),
      team: teamIds.map((id) => ({ user_id: id, role_id: teamOf.get(id)?.role_id ?? null, team_role: teamOf.get(id)?.team_role ?? null })),
      entry_ids: entryIds,
      reference_project_ids: refIds,
    })
    if (res) onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader><DialogTitle className="font-display text-xl">{t('Contacts, team and references')}</DialogTitle></DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-1.5">
            <Label>{t('Customer contacts')}</Label>
            <ComboPicker multiple options={pool.map((c) => ({ id: c.id, label: `${c.first_name} ${c.last_name}`, hint: c.job_title }))} value={contactIds} onChange={setContactIds} placeholder={t('Choose contacts')} />
          </div>
          <div className="grid gap-1.5">
            <Label>{t('Our team')}</Label>
            <ComboPicker multiple options={(people ?? []).map((p) => ({ id: p.id, label: p.name, hint: p.job_title }))} value={teamIds} onChange={setTeamIds} placeholder={t('Choose people')} />
          </div>
          <div className="grid gap-1.5">
            <Label>{t('Technologies and topics')}</Label>
            <ComboPicker multiple options={(catalog ?? []).map((e) => ({ id: e.id, label: e.name, hint: e.kind.replaceAll('_', ' ') }))} value={entryIds} onChange={setEntryIds} placeholder={t('Choose entries')} />
          </div>
          <div className="grid gap-1.5">
            <Label>{t('Reference projects')}</Label>
            <ComboPicker multiple options={(projects ?? []).map((p) => ({ id: p.id, label: p.name, hint: p.project_no }))} value={refIds} onChange={setRefIds} placeholder={t('Choose projects')} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t('Cancel')}</Button>
          <Button onClick={save}>{t('Save')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
