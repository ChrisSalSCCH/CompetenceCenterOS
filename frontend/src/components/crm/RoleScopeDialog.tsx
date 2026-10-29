import { useState } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { ComboPicker } from '@/components/ComboPicker'
import { useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import type { Structure } from '@/lib/types'

interface Props {
  open: boolean
  onOpenChange: (v: boolean) => void
  scopeType: 'organization' | 'project'
  targetId: string
}

export function RoleScopeDialog({ open, onOpenChange, scopeType, targetId }: Readonly<Props>) {
  const { t } = useT()
  const act = useAct()
  const { data } = useGet<Structure>(open ? '/structure' : null)
  const [assignment, setAssignment] = useState<string[]>([])
  const circle = (id: string) => data?.circles.find((c) => c.id === id)?.name
  const options = (data?.roles ?? []).flatMap((r) =>
    r.holders.map((h) => ({ id: h.assignment_id, label: `${r.name} – ${h.name}`, hint: circle(r.circle_id) })),
  )

  const save = async () => {
    const body = scopeType === 'organization'
      ? { role_assignment_id: assignment[0], scope_type: scopeType, crm_org_id: targetId }
      : { role_assignment_id: assignment[0], scope_type: scopeType, project_id: targetId }
    const res = await act('post', '/crm/role-scopes', body)
    if (res) {
      setAssignment([])
      onOpenChange(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="font-display text-xl">{t('Assign a role')}</DialogTitle>
          <DialogDescription>{t('Key account roles and similar responsibilities for this customer. A scope gives context; it grants no approval authority.')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-1.5">
          <Label>{t('Role assignment')}</Label>
          <ComboPicker options={options} value={assignment} onChange={(v) => setAssignment(v.slice(-1))} placeholder={t('Role assignment')} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t('Cancel')}</Button>
          <Button onClick={save} disabled={!assignment[0]}>{t('Save')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
