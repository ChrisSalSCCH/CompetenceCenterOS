import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { Button } from '@/components/ui/button'
import { ComboPicker } from '@/components/ComboPicker'
import { Avatar, EmptyState, Section } from '@/components/kit'
import { useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import type { ProjectDetailData } from '@/lib/portfolio-types'
import type { PersonRow } from '@/lib/types'

export function TeamTab({ p }: Readonly<{ p: ProjectDetailData }>) {
  const { t } = useT()
  const act = useAct()
  const { data: people } = useGet<PersonRow[]>(p.can_manage ? '/people' : null)
  const current = p.team.people.map((x) => x.user_id)
  const [draft, setDraft] = useState<string[]>(current)
  const signature = current.join(',')
  useEffect(() => setDraft(current), [signature]) // eslint-disable-line react-hooks/exhaustive-deps
  const dirty = draft.slice().sort().join(',') !== current.slice().sort().join(',')

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Section title={t('Project team')}>
        {p.manager_name && (
          <p className="mb-3 text-sm"><span className="font-mono-label mr-2 text-muted-foreground">{t('Project manager')}</span>{p.manager_name}</p>
        )}
        {p.can_manage ? (
          <div className="space-y-2">
            <ComboPicker multiple options={(people ?? []).map((x) => ({ id: x.id, label: x.name, hint: x.job_title }))} value={draft} onChange={setDraft} placeholder={t('Add a person')} />
            <Button size="sm" disabled={!dirty} onClick={() => act('patch', `/projects/${p.id}`, { person_ids: draft })}>{t('Save')}</Button>
          </div>
        ) : (
          <>
            {p.team.people.length === 0 && <EmptyState title={t('No team members yet')} />}
            <ul className="space-y-2">
              {p.team.people.map((x) => (
                <li key={x.user_id}><Link to={`/people/${x.user_id}`} className="flex items-center gap-2 text-sm hover:text-primary"><Avatar name={x.name} size={24} />{x.name}</Link></li>
              ))}
            </ul>
          </>
        )}
      </Section>

      <div className="space-y-4">
        <Section title={t('Holders of the owning role')}>
          {p.team.role_holders.length === 0 ? <p className="text-sm italic text-muted-foreground">–</p> : (
            <ul className="space-y-2">
              {p.team.role_holders.map((h) => (
                <li key={`${h.user_id}-${h.role_name}`} className="flex items-center gap-2 text-sm">
                  <Avatar name={h.name} size={24} />
                  <Link to={`/people/${h.user_id}`} className="font-medium hover:text-primary">{h.name}</Link>
                  <span className="text-xs text-muted-foreground">{h.role_name}{h.focus && ` · ${h.focus}`}</span>
                </li>
              ))}
            </ul>
          )}
        </Section>
        <Section title={t('Customer roles')}>
          {p.team.customer_roles.length === 0 ? <p className="text-sm italic text-muted-foreground">–</p> : (
            <ul className="space-y-2">
              {p.team.customer_roles.map((h) => (
                <li key={`${h.user_id}-${h.role_id}`} className="flex items-center gap-2 text-sm">
                  <Avatar name={h.name} size={24} />
                  <Link to={`/people/${h.user_id}`} className="font-medium hover:text-primary">{h.name}</Link>
                  <Link to={`/organization/roles/${h.role_id}`} className="text-xs text-muted-foreground hover:text-primary">{h.role_name}</Link>
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>
    </div>
  )
}
