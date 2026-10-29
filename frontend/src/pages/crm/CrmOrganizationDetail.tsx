import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { ArrowLeft, Pencil, Plus, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { ActivityDialog } from '@/components/crm/ActivityDialog'
import { ContactFormDialog } from '@/components/crm/ContactFormDialog'
import { OrgFormDialog } from '@/components/crm/OrgFormDialog'
import { RoleScopeDialog } from '@/components/crm/RoleScopeDialog'
import { Avatar, EmptyState, ErrorBlock, LoadingBlock, PageHeader, Pill, Section, StatusPill } from '@/components/kit'
import { useSession } from '@/contexts/SessionContext'
import { fmtDate, fmtDateTime, useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import { classificationTone, daysSince, fullName, phaseTone } from '@/lib/portfolio'
import type { CrmOrgDetail } from '@/lib/portfolio-types'

function Fact({ label, children }: Readonly<{ label: string; children: React.ReactNode }>) {
  return (
    <div>
      <dt className="font-mono-label text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 text-sm">{children || '–'}</dd>
    </div>
  )
}

export default function CrmOrganizationDetail() {
  const { t, lang } = useT()
  const { id } = useParams()
  const navigate = useNavigate()
  const act = useAct()
  const { isObserver, isAdmin } = useSession()
  const { data: o, isLoading, error } = useGet<CrmOrgDetail>(id ? `/crm/organizations/${id}` : null)
  const [editing, setEditing] = useState(false)
  const [logging, setLogging] = useState(false)
  const [scoping, setScoping] = useState(false)
  const [addingContact, setAddingContact] = useState(false)

  if (isLoading) return <LoadingBlock rows={5} />
  if (error || !o) return <ErrorBlock message={error?.message} />

  const quiet = daysSince(o.last_activity_at)
  const remove = async () => {
    const ok = await act('delete', `/crm/organizations/${o.id}`)
    if (ok) navigate('/crm/organizations')
  }

  return (
    <>
      <Link to="/crm/organizations" className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-primary"><ArrowLeft className="h-4 w-4" aria-hidden />{t('Companies')}</Link>
      <PageHeader
        eyebrow={[o.city, o.country].filter(Boolean).join(', ')}
        title={o.name}
        subtitle={o.parent_name ? `${t('Parent organization')}: ${o.parent_name}` : o.legal_name ?? undefined}
        actions={
          <>
            {o.relation_types.map((r) => <Pill key={r} tone={r === 'customer' ? 'ink' : 'neutral'}>{t(r.replaceAll('_', ' '))}</Pill>)}
            {o.status === 'inactive' && <Pill>{t('inactive')}</Pill>}
            {!isObserver && <Button size="sm" variant="outline" onClick={() => setEditing(true)}><Pencil className="mr-1 h-3.5 w-3.5" aria-hidden />{t('Edit')}</Button>}
            {!isObserver && <Button size="sm" onClick={() => setLogging(true)}><Plus className="mr-1 h-3.5 w-3.5" aria-hidden />{t('Log activity')}</Button>}
            {isAdmin && (
              <ConfirmDialog
                trigger={<Button size="icon" variant="ghost" aria-label={t('Delete')}><Trash2 className="h-4 w-4" /></Button>}
                title={t('Delete')} description={o.name} onConfirm={remove}
              />
            )}
          </>
        }
      />

      <Tabs defaultValue="overview" className="space-y-4">
        <TabsList className="h-auto flex-wrap justify-start">
          <TabsTrigger value="overview">{t('360° view')}</TabsTrigger>
          <TabsTrigger value="projects">{t('Projects')} ({o.stats.projects})</TabsTrigger>
          <TabsTrigger value="contacts">{t('Contacts')} ({o.stats.contacts})</TabsTrigger>
          <TabsTrigger value="activities">{t('Activities')} ({o.activities.length})</TabsTrigger>
          <TabsTrigger value="roles">{t('Roles & responsibility')} ({o.roles.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-4">
          <Section>
            <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Fact label={t('Relationship owner')}>{o.owner_name}</Fact>
              <Fact label={t('Industry')}>{o.industry}</Fact>
              <Fact label={t('Customer since')}>{fmtDate(o.customer_since, lang)}</Fact>
              <Fact label={t('Last activity')}>{o.last_activity_at ? <span className={quiet !== null && quiet > 90 ? 'text-destructive' : ''}>{fmtDate(o.last_activity_at, lang)}</span> : t('No contact yet')}</Fact>
              <Fact label={t('VAT ID')}>{o.vat_id}</Fact>
              <Fact label={t('Website')}>{o.website ? <a href={o.website} target="_blank" rel="noreferrer noopener" className="text-primary hover:underline">{o.website}</a> : null}</Fact>
              <Fact label={t('Address')}>{o.address}</Fact>
              <Fact label={t('Size')}>{o.size_class}</Fact>
            </dl>
            {o.children.length > 0 && <p className="mt-4 text-sm"><span className="font-mono-label mr-2 text-muted-foreground">{t('Subsidiaries')}</span>{o.children.map((c, i) => <span key={c.id}>{i > 0 && ', '}<Link to={`/crm/organizations/${c.id}`} className="text-primary hover:underline">{c.name}</Link></span>)}</p>}
            {o.notes && <p className="mt-4 whitespace-pre-wrap text-sm">{o.notes}</p>}
          </Section>
          <div className="grid gap-4 lg:grid-cols-2">
            <Section title={t('Next steps')}>
              {o.next_steps.length === 0 ? <p className="text-sm italic text-muted-foreground">{t('No open next steps')}</p> : (
                <ul className="space-y-2">
                  {o.next_steps.map((a) => (
                    <li key={a.id} className="text-sm">
                      <Link to={`/work?task=${a.follow_up_task_id}`} className="font-medium hover:text-primary">{a.follow_up_title}</Link>
                      <span className="ml-2 text-xs text-muted-foreground">{fmtDate(a.follow_up_due, lang)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Section>
            <Section title={t('Roles & responsibility')}>
              {o.roles.length === 0 ? <p className="text-sm italic text-muted-foreground">{t('No roles assigned to this customer')}</p> : (
                <ul className="space-y-1.5">
                  {o.roles.slice(0, 5).map((r) => (
                    <li key={r.scope_id} className="flex items-center gap-2 text-sm">
                      <Avatar name={r.name} size={22} /><Link to={`/people/${r.user_id}`} className="font-medium hover:text-primary">{r.name}</Link>
                      <Link to={`/organization/roles/${r.role_id}`} className="text-xs text-muted-foreground hover:text-primary">{r.role_name}</Link>
                    </li>
                  ))}
                </ul>
              )}
            </Section>
          </div>
        </TabsContent>

        <TabsContent value="projects">
          <Section>
            {o.projects.length === 0 && <EmptyState title={t('Projects')} />}
            <ul className="divide-y">
              {o.projects.map((p) => (
                <li key={`${p.id}-${p.relation}`} className="flex flex-wrap items-center gap-2 py-2.5">
                  <Link to={`/projects/${p.id}`} className="font-display text-base font-semibold hover:text-primary">{p.name}</Link>
                  <Pill tone={classificationTone(p.classification)}>{t(p.classification)}</Pill>
                  <Pill tone={phaseTone(p.phase)}>{t(p.phase)}</Pill>
                  <StatusPill status={p.status} />
                  <Pill>{t(p.relation.replaceAll('_', ' '))}</Pill>
                  <span className="ml-auto text-xs text-muted-foreground">{fmtDate(p.start_date, lang)} – {fmtDate(p.due_date, lang)}</span>
                </li>
              ))}
            </ul>
          </Section>
        </TabsContent>

        <TabsContent value="contacts">
          <Section action={!isObserver && <Button size="sm" variant="outline" onClick={() => setAddingContact(true)}><Plus className="mr-1 h-3.5 w-3.5" aria-hidden />{t('New contact')}</Button>}>
            {isObserver && <p className="mb-2 text-xs text-muted-foreground">{t('Contact details are hidden for read-only observers.')}</p>}
            {o.contacts.length === 0 && <EmptyState title={t('Contacts')} />}
            <ul className="grid gap-3 md:grid-cols-2">
              {o.contacts.map((c) => (
                <li key={c.id} className="rounded-xl border p-3">
                  <div className="flex items-center gap-2">
                    <Avatar name={fullName(c)} size={32} />
                    <div className="min-w-0">
                      <div className="font-medium">{fullName(c)} {c.is_primary && <Pill tone="primary">{t('Primary contact')}</Pill>}</div>
                      <div className="truncate text-xs text-muted-foreground">{[c.job_title, c.contact_role].filter(Boolean).join(' · ')}</div>
                    </div>
                  </div>
                  {(c.email || c.phone) && <div className="mt-2 text-xs text-muted-foreground">{[c.email, c.phone].filter(Boolean).join(' · ')}</div>}
                </li>
              ))}
            </ul>
          </Section>
        </TabsContent>

        <TabsContent value="activities">
          <Section>
            {o.activities.length === 0 && <EmptyState title={t('No activities yet')} />}
            <ol className="space-y-3 border-l pl-4">
              {o.activities.map((a) => (
                <li key={a.id}>
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <Pill>{t(a.kind)}</Pill><span className="font-medium">{a.subject}</span>
                    <span className="text-xs text-muted-foreground">{fmtDateTime(a.occurred_at, lang)}{a.author_name && ` · ${a.author_name}`}</span>
                    {!isObserver && (
                      <button type="button" className="ml-auto text-xs text-muted-foreground hover:text-destructive" onClick={() => act('delete', `/crm/activities/${a.id}`)}>{t('Remove')}</button>
                    )}
                  </div>
                  {a.body && <p className="mt-1 whitespace-pre-wrap text-sm text-muted-foreground">{a.body}</p>}
                  <div className="mt-1 flex flex-wrap gap-2 text-xs text-muted-foreground">
                    {a.contact_name && <span>{a.contact_name}</span>}
                    {a.project_name && a.project_id && <Link to={`/projects/${a.project_id}`} className="text-primary hover:underline">{a.project_name}</Link>}
                    {a.follow_up_title && <Link to={`/work?task=${a.follow_up_task_id}`} className="text-primary hover:underline">→ {a.follow_up_title}</Link>}
                  </div>
                </li>
              ))}
            </ol>
          </Section>
        </TabsContent>

        <TabsContent value="roles">
          <Section action={!isObserver && <Button size="sm" variant="outline" onClick={() => setScoping(true)}>{t('Assign a role')}</Button>}>
            {o.roles.length === 0 && <EmptyState title={t('No roles assigned to this customer')} />}
            <ul className="divide-y">
              {o.roles.map((r) => (
                <li key={r.scope_id} className="flex flex-wrap items-center gap-2 py-2.5">
                  <Avatar name={r.name} size={26} />
                  <Link to={`/people/${r.user_id}`} className="font-medium hover:text-primary">{r.name}</Link>
                  <Link to={`/organization/roles/${r.role_id}`} className="text-sm text-muted-foreground hover:text-primary">{r.role_name}</Link>
                  <Pill>{r.scope_type === 'project' && r.project_name ? r.project_name : t('Customer')}</Pill>
                  {!isObserver && <button type="button" className="ml-auto text-xs text-muted-foreground hover:text-destructive" onClick={() => act('delete', `/crm/role-scopes/${r.scope_id}`)}>{t('Remove')}</button>}
                </li>
              ))}
            </ul>
          </Section>
        </TabsContent>
      </Tabs>

      <OrgFormDialog org={o} open={editing} onOpenChange={setEditing} />
      <ActivityDialog org={o} open={logging} onOpenChange={setLogging} />
      <RoleScopeDialog open={scoping} onOpenChange={setScoping} scopeType="organization" targetId={o.id} />
      <ContactFormDialog open={addingContact} onOpenChange={setAddingContact} presetOrgId={o.id} />
    </>
  )
}
