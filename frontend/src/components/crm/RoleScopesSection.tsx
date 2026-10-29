import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { Button } from '@/components/ui/button'
import { CatalogPicker, type PickedEntry } from '@/components/CatalogPicker'
import { Pill, Section } from '@/components/kit'
import { useSession } from '@/contexts/SessionContext'
import { useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import type { CatalogKind, RoleScope } from '@/lib/portfolio-types'

interface Competency {
  id: string
  name: string
  kind: CatalogKind
}

export function RoleScopesSection({ roleId }: Readonly<{ roleId: string }>) {
  const { t } = useT()
  const act = useAct()
  const { isObserver } = useSession()
  const { data: scopes } = useGet<RoleScope[]>('/crm/role-scopes', { role_id: roleId })
  const { data: competencies } = useGet<Competency[]>(`/roles/${roleId}/competencies`)
  const [draft, setDraft] = useState<PickedEntry[]>([])
  const [dirty, setDirty] = useState(false)
  useEffect(() => {
    setDraft((competencies ?? []).map((c) => ({ id: c.id, name: c.name, kind: c.kind })))
    setDirty(false)
  }, [competencies])

  return (
    <Section title={`${t('Customers')} & ${t('Technologies & Competencies')}`} index={6}>
      <div className="space-y-4">
        <div>
          <div className="font-mono-label mb-1 text-muted-foreground">{t('Scope')}</div>
          {(scopes ?? []).length === 0 ? <p className="text-sm italic text-muted-foreground">–</p> : (
            <ul className="space-y-1.5">
              {(scopes ?? []).map((s) => (
                <li key={s.id} className="flex flex-wrap items-center gap-2 text-sm">
                  <Link to={`/people/${s.user_id}`} className="font-medium hover:text-primary">{s.user_name}</Link>
                  <span className="text-muted-foreground">→</span>
                  {s.crm_org_id
                    ? <Link to={`/crm/organizations/${s.crm_org_id}`} className="text-primary hover:underline">{s.org_name}</Link>
                    : <Link to={`/projects/${s.project_id}`} className="text-primary hover:underline">{s.project_name}</Link>}
                  <Pill>{s.scope_type === 'organization' ? t('Customer') : t('Project')}</Pill>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <div className="font-mono-label mb-1 text-muted-foreground">{t('Competencies')}</div>
          {isObserver ? (
            <div className="flex flex-wrap gap-1.5">{draft.map((d) => <Pill key={d.id} tone="primary">{d.name}</Pill>)}</div>
          ) : (
            <>
              <CatalogPicker value={draft} onChange={(v) => { setDraft(v); setDirty(true) }} />
              {dirty && <Button className="mt-2" size="sm" onClick={() => act('put', `/roles/${roleId}/competencies`, { entry_ids: draft.map((d) => d.id) })}>{t('Save')}</Button>}
            </>
          )}
        </div>
      </div>
    </Section>
  )
}
