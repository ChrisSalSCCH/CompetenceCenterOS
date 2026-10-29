import { useState } from 'react'
import { Link } from 'react-router'
import { Pencil } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { ProgressBar, Pill, Section, StatusPill, EmptyState } from '@/components/kit'
import { ProjectEditDialog } from '@/components/project/ProjectEditDialog'
import { ProjectLinksDialog } from '@/components/project/ProjectLinksDialog'
import { ResearchSection } from '@/components/project/ResearchSection'
import { ComboPicker } from '@/components/ComboPicker'
import { fmtDate, useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import { fullName } from '@/lib/portfolio'
import type { PortfolioRow, ProjectDetailData } from '@/lib/portfolio-types'

function Fact({ label, children }: Readonly<{ label: string; children: React.ReactNode }>) {
  return (
    <div>
      <dt className="font-mono-label text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 text-sm">{children || '–'}</dd>
    </div>
  )
}

export function OverviewTab({ p }: Readonly<{ p: ProjectDetailData }>) {
  const { t, lang } = useT()
  const act = useAct()
  const [editing, setEditing] = useState(false)
  const [linking, setLinking] = useState(false)
  const [researchOpen, setResearchOpen] = useState(true)
  const { data: all } = useGet<PortfolioRow[]>('/portfolio')
  const tasks = p.work.task_count
  const customer = p.classification === 'customer'

  const relationItems = p.relations.filter((r) => r.direction === 'outgoing').map((r) => ({ related_project_id: r.id, relation: r.relation, note: r.note }))
  const addRelation = (id: string | undefined) => {
    if (!id || relationItems.some((r) => r.related_project_id === id)) return
    act('put', `/portfolio/${p.id}/relations`, { items: [...relationItems, { related_project_id: id, relation: 'related', note: null }] })
  }
  const removeRelation = (id: string) => act('put', `/portfolio/${p.id}/relations`, { items: relationItems.filter((r) => r.related_project_id !== id) })

  return (
    <div className="space-y-4">
      <Section
        title={t('Overview')}
        action={p.can_manage && <Button size="sm" variant="outline" onClick={() => setEditing(true)}><Pencil className="mr-1 h-3.5 w-3.5" aria-hidden />{t('Edit')}</Button>}
      >
        {p.description && <p className="mb-4 whitespace-pre-wrap text-sm">{p.description}</p>}
        <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Fact label={t('Project manager')}>{p.manager_name}</Fact>
          <Fact label={t('Circle')}><Link to={`/organization/circles/${p.circle_id}`} className="hover:text-primary">{p.circle_name}</Link></Fact>
          <Fact label={t('Owning role')}>{p.owning_role_id ? <Link to={`/organization/roles/${p.owning_role_id}`} className="hover:text-primary">{p.owning_role_name}</Link> : null}</Fact>
          <Fact label={t('Organizational unit')}>{p.org_unit}</Fact>
          <Fact label={t('Start')}>{fmtDate(p.start_date, lang)}</Fact>
          <Fact label={t('End')}>{fmtDate(p.due_date, lang)}</Fact>
          <Fact label={t('Status')}><StatusPill status={p.status} /></Fact>
          <Fact label={t('Project number')}>{p.project_no}</Fact>
        </dl>
      </Section>

      {customer && (
        <Section
          title={t('Linked organizations')}
          action={p.can_manage && <Button size="sm" variant="outline" onClick={() => setLinking(true)}>{t('Edit links')}</Button>}
        >
          {p.orgs.length === 0 ? <EmptyState title={t('Customer projects need at least one customer organization.')} /> : (
            <ul className="grid gap-2 sm:grid-cols-2">
              {p.orgs.map((o) => (
                <li key={`${o.id}-${o.relation}`} className="flex items-center justify-between gap-2 rounded-lg border p-3">
                  <Link to={`/crm/organizations/${o.id}`} className="font-medium hover:text-primary">{o.name}</Link>
                  <Pill tone={o.relation === 'customer' ? 'ink' : 'neutral'}>{t(o.relation.replaceAll('_', ' '))}</Pill>
                </li>
              ))}
            </ul>
          )}
          {p.contacts.length > 0 && (
            <>
              <h3 className="mb-1 mt-4 font-display text-base font-semibold">{t('Customer contacts')}</h3>
              <ul className="grid gap-2 sm:grid-cols-2">
                {p.contacts.map((c) => (
                  <li key={c.id} className="rounded-lg border p-3 text-sm">
                    <div className="font-medium">{fullName(c)} {c.contact_role && <span className="font-normal text-muted-foreground">· {c.contact_role}</span>}</div>
                    <div className="text-xs text-muted-foreground">{c.job_title}{c.email && ` · ${c.email}`}</div>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Section>
      )}

      {p.is_research && (
        <Collapsible open={researchOpen} onOpenChange={setResearchOpen}>
          <Section title={t('Research & funding')} action={<CollapsibleTrigger asChild><Button size="sm" variant="ghost">{researchOpen ? t('Collapse') : t('Expand')}</Button></CollapsibleTrigger>}>
            <CollapsibleContent className="space-y-4">
              <dl className="grid gap-4 sm:grid-cols-3">
                <Fact label={t('Funding program')}>{p.funding_program}</Fact>
                <Fact label={t('Funding agency')}>{p.funding_agency}</Fact>
                <Fact label={t('Funding reference')}>{p.funding_ref}</Fact>
              </dl>
              {p.research_note && <p className="text-sm">{p.research_note}</p>}
              <ResearchSection p={p} />
            </CollapsibleContent>
          </Section>
        </Collapsible>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Section title={t('Related projects')}>
          {p.relations.length === 0 && <p className="text-sm italic text-muted-foreground">–</p>}
          <ul className="space-y-1.5">
            {p.relations.map((r) => (
              <li key={`${r.id}-${r.direction}`} className="flex items-center gap-2 text-sm">
                <Link to={`/projects/${r.id}`} className="font-medium hover:text-primary">{r.name}</Link>
                <Pill>{r.direction === 'incoming' ? `← ${r.relation.replaceAll('_', ' ')}` : r.relation.replaceAll('_', ' ')}</Pill>
                {p.can_manage && r.direction === 'outgoing' && <button type="button" className="ml-auto text-xs text-muted-foreground hover:text-destructive" onClick={() => removeRelation(r.id)}>{t('Remove')}</button>}
              </li>
            ))}
          </ul>
          {p.can_manage && (
            <div className="mt-3">
              <ComboPicker options={(all ?? []).filter((x) => x.id !== p.id).map((x) => ({ id: x.id, label: x.name, hint: x.project_no }))} value={[]} onChange={(v) => addRelation(v[0])} placeholder={t('Add')} ariaLabel={t('Related projects')} />
            </div>
          )}
        </Section>

        <Section title={t('Tasks')} action={<Link to={`/work?tab=projects&project=${p.id}`} className="text-xs text-primary hover:underline">{t('Open in Projects & Tasks')}</Link>}>
          {tasks === 0 ? <p className="text-sm italic text-muted-foreground">{t('No tasks yet')}</p> : (
            <>
              <ProgressBar value={tasks ? p.work.tasks_done / tasks : 0} tone="forest" />
              <ul className="mt-3 space-y-1.5">
                {p.work.tasks.slice(0, 5).map((x) => (
                  <li key={x.id} className="flex items-center justify-between gap-2 text-sm">
                    <Link to={`/work?task=${x.id}`} className="truncate hover:text-primary">{x.title}</Link>
                    <StatusPill status={x.status} />
                  </li>
                ))}
              </ul>
            </>
          )}
          {p.work.milestones.length > 0 && (
            <>
              <h3 className="mb-1 mt-4 font-display text-base font-semibold">{t('Milestones')}</h3>
              <ul className="space-y-1 text-sm">
                {p.work.milestones.map((m) => <li key={m.id} className={m.done ? 'text-muted-foreground line-through' : ''}>{m.title} <span className="text-xs text-muted-foreground">{fmtDate(m.due_date, lang)}</span></li>)}
              </ul>
            </>
          )}
        </Section>
      </div>

      <ProjectEditDialog p={p} open={editing} onOpenChange={setEditing} />
      <ProjectLinksDialog p={p} open={linking} onOpenChange={setLinking} />
    </div>
  )
}
