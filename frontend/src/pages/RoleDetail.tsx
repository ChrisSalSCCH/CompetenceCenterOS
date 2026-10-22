import { useState } from 'react'
import { Link, useParams } from 'react-router'
import { ExternalLink, Pencil, Plus, Star, Trash2, UserMinus, UserPlus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Avatar, EmptyState, ErrorBlock, ItemList, LoadingBlock, ModePill, PageHeader, Pill, PriorityPill, Section, StatusPill } from '@/components/kit'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { HistoryTimeline } from '@/components/HistoryTimeline'
import { RoleFormDialog, useSubmitFeedback } from '@/components/StructureForms'
import { useSession } from '@/contexts/SessionContext'
import { fmtDate, useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import type { GovMode, HistoryEntry, PersonRow, RoleNode, Structure, SubmitResult, TaskStatus } from '@/lib/types'

interface RoleFull extends RoleNode {
  circle_name: string
  breadcrumb: { id: string; name: string }[]
  related_roles: { id: string; name: string; circle_id: string; relation: string; note: string | null }[]
  tasks: { id: string; title: string; status: TaskStatus; priority: string; due_date: string | null; assignee_name: string | null }[]
  projects: { id: string; name: string; status: string; priority: string; due_date: string | null }[]
  metrics: { id: string; name: string; unit: string; target_value: number; current_value: number }[]
  documents: { id: string; name: string; url: string }[]
  tensions: { id: string; title: string; status: string; priority: string }[]
  history: HistoryEntry[]
  effective_mode: GovMode
  can_govern: boolean
}

export default function RoleDetail() {
  const { id } = useParams()
  const { t, lang } = useT()
  const act = useAct()
  const feedback = useSubmitFeedback()
  const { isObserver } = useSession()
  const { data, isLoading, error } = useGet<RoleFull>(id ? `/roles/${id}` : null)
  const { data: structure } = useGet<Structure>('/structure')
  const [editOpen, setEditOpen] = useState(false)
  const [assignOpen, setAssignOpen] = useState(false)
  const [docOpen, setDocOpen] = useState(false)
  const { data: people } = useGet<PersonRow[]>(assignOpen ? '/people' : null)
  const [person, setPerson] = useState('')
  const [focus, setFocus] = useState('')
  const [docName, setDocName] = useState('')
  const [docUrl, setDocUrl] = useState('')

  if (isLoading) return <LoadingBlock rows={6} />
  if (error || !data) return <ErrorBlock message={error?.message} />
  const circles = structure?.circles ?? []
  const holderIds = new Set(data.holders.map((h) => h.user_id))

  const assign = async () => {
    if (!person) return
    const res = await act('post', `/roles/${data.id}/assignments`, { user_id: person, focus: focus.trim() || null })
    if (res) {
      setAssignOpen(false)
      setPerson('')
      setFocus('')
    }
  }
  const addDoc = async () => {
    const res = await act('post', '/attachments', { entity_type: 'role', entity_id: data.id, name: docName.trim(), url: docUrl.trim() })
    if (res) {
      setDocOpen(false)
      setDocName('')
      setDocUrl('')
    }
  }
  const remove = async () => {
    feedback(await act<SubmitResult>('delete', `/roles/${data.id}`))
  }

  return (
    <>
      <PageHeader
        eyebrow={
          <span className="flex flex-wrap items-center gap-1">
            <Link to="/organization" className="hover:text-primary">{t('Organization')}</Link>
            {data.breadcrumb.map((b) => <span key={b.id}> / <Link to={`/organization/circles/${b.id}`} className="hover:text-primary">{b.name}</Link></span>)}
          </span>
        }
        title={data.name}
        actions={
          <>
            <ModePill mode={data.effective_mode} />
            {data.can_govern && <Pill tone="ink">{t('Governance authority')}</Pill>}
            {!isObserver && <Button variant="outline" size="sm" onClick={() => setEditOpen(true)}><Pencil className="mr-1 h-4 w-4" />{t('Edit')}</Button>}
            {!isObserver && (
              <ConfirmDialog
                trigger={<Button variant="ghost" size="sm" className="text-destructive"><Trash2 className="mr-1 h-4 w-4" />{t('Remove')}</Button>}
                title={t('Remove this role?')}
                description={t('Assignments end. Depending on the governance workflow this creates a proposal.')}
                onConfirm={remove}
              />
            )}
          </>
        }
      />

      <div className="reveal stripe-primary mb-6 rounded-2xl border border-primary/20 p-5 md:p-7" style={{ ['--i' as string]: 1 }}>
        <div className="font-mono-label mb-2 text-primary">{t('Purpose')}</div>
        <p className="font-display text-2xl leading-snug md:text-3xl">{data.purpose || t('No purpose defined.')}</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Section title={t('Responsibilities')} index={2}>
            <p className="mb-4 rounded-lg bg-muted/60 p-3 text-xs text-muted-foreground">
              {t('Accountability, domain ownership and decision authority are different things: a role may be accountable for an activity without being allowed to decide about it.')}
            </p>
            <div className="grid gap-5 md:grid-cols-2">
              <div>
                <div className="font-mono-label mb-2 text-muted-foreground">{t('Accountabilities')} · <span className="normal-case tracking-normal">{t('ongoing activities')}</span></div>
                <ItemList items={data.accountabilities} empty={t('None defined')} />
              </div>
              <div>
                <div className="font-mono-label mb-2 text-muted-foreground">{t('Domains')} · <span className="normal-case tracking-normal">{t('exclusively controlled')}</span></div>
                <ItemList items={data.domains} empty={t('None defined')} />
              </div>
            </div>
            <div className="mt-5 rounded-xl border border-[hsl(var(--forest)/0.35)] bg-[hsl(var(--forest)/0.06)] p-4">
              <div className="font-mono-label mb-2 text-[hsl(var(--forest))]">{t('Explicit decision authorities')}</div>
              <ItemList items={data.authorities} empty={t('No explicit decision authority. Without it, this role cannot be assumed to decide.')} />
            </div>
            {data.policies.length > 0 && (
              <div className="mt-5">
                <div className="font-mono-label mb-2 text-muted-foreground">{t('Policies')}</div>
                <ItemList items={data.policies} empty="" />
              </div>
            )}
          </Section>

          <Section title={t('Open tasks')} index={3}>
            {data.tasks.length === 0 ? <EmptyState title={t('No open tasks for this role')} /> : (
              <ul className="divide-y">
                {data.tasks.map((x) => (
                  <li key={x.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                    <div><div className="text-sm">{x.title}</div><div className="text-xs text-muted-foreground">{x.assignee_name ?? t('unassigned')} · {fmtDate(x.due_date, lang)}</div></div>
                    <StatusPill status={x.status} />
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section title={t('Active projects')} index={4}>
            {data.projects.length === 0 ? <EmptyState title={t('This role owns no projects')} /> : (
              <ul className="divide-y">
                {data.projects.map((p) => (
                  <li key={p.id} className="flex items-center justify-between gap-2 py-2">
                    <span className="text-sm font-medium">{p.name}</span>
                    <span className="flex gap-2"><PriorityPill priority={p.priority} /><StatusPill status={p.status} /></span>
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section title={t('Governance history')} index={5}>
            <HistoryTimeline entries={data.history} />
          </Section>
        </div>

        <div className="space-y-4">
          <Section
            title={t('Role holders')}
            index={2}
            action={data.can_govern && !isObserver ? <Button size="sm" variant="outline" onClick={() => setAssignOpen(true)}><UserPlus className="mr-1 h-4 w-4" />{t('Assign')}</Button> : undefined}
          >
            {data.holders.length === 0 && <Pill tone="ochre">{t('unfilled')}</Pill>}
            <ul className="space-y-2">
              {data.holders.map((h) => (
                <li key={h.assignment_id} className="flex items-center gap-2">
                  <Avatar name={h.name} color={h.avatar_color} size={32} />
                  <Link to={`/people/${h.user_id}`} className="flex-1 text-sm hover:text-primary">
                    <span className="flex items-center gap-1 font-medium">{h.name}{data.lead_user_id === h.user_id && <Star className="h-3.5 w-3.5 fill-[hsl(var(--ochre))] text-[hsl(var(--ochre))]" aria-label={t('Role lead')} />}</span>
                    {h.focus && <span className="block text-xs text-muted-foreground">{h.focus}</span>}
                  </Link>
                  {data.can_govern && !isObserver && (
                    <>
                      {data.holders.length > 1 && data.lead_user_id !== h.user_id && (
                        <Button variant="ghost" size="icon" className="h-7 w-7" aria-label={t('Make role lead')} onClick={() => act('put', `/roles/${data.id}/lead`, { lead_user_id: h.user_id })}><Star className="h-4 w-4" /></Button>
                      )}
                      <Button variant="ghost" size="icon" className="h-7 w-7" aria-label={t('Unassign')} onClick={() => act('delete', `/assignments/${h.assignment_id}`)}><UserMinus className="h-4 w-4" /></Button>
                    </>
                  )}
                </li>
              ))}
            </ul>
            <p className="mt-3 text-xs text-muted-foreground">{data.allow_multiple ? t('Several people may hold this role.') : t('Single role holder.')}</p>
          </Section>

          <Section title={t('Related roles')} index={3}>
            {data.related_roles.length === 0 ? <p className="text-sm text-muted-foreground">{t('No related roles.')}</p> : (
              <ul className="space-y-2">
                {data.related_roles.map((r) => (
                  <li key={r.id}>
                    <Link to={`/organization/roles/${r.id}`} className="block text-sm hover:text-primary">
                      <span className="font-medium">{r.name}</span>{' '}
                      <Pill tone={r.relation === 'overlap' ? 'ochre' : 'neutral'}>{r.relation === 'overlap' ? t('possible overlap') : t('same circle')}</Pill>
                      {r.note && <span className="block text-xs text-muted-foreground">{r.note}</span>}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section title={t('KPIs')} index={4}>
            {data.metrics.length === 0 ? <p className="text-sm text-muted-foreground">{t('No KPIs assigned.')}</p> : (
              <ul className="space-y-1.5 text-sm">
                {data.metrics.map((m) => <li key={m.id} className="flex justify-between"><span>{m.name}</span><span className="font-mono text-xs">{m.current_value} / {m.target_value} {m.unit}</span></li>)}
              </ul>
            )}
          </Section>

          <Section title={t('Documents')} index={5} action={!isObserver ? <Button size="sm" variant="outline" onClick={() => setDocOpen(true)}><Plus className="mr-1 h-4 w-4" />{t('Add link')}</Button> : undefined}>
            {data.documents.length === 0 ? <p className="text-sm text-muted-foreground">{t('No documents linked. File upload is planned; links to documents are supported.')}</p> : (
              <ul className="space-y-1.5">
                {data.documents.map((d) => (
                  <li key={d.id} className="flex items-center justify-between gap-2 text-sm">
                    <a href={d.url} target="_blank" rel="noreferrer noopener" className="flex items-center gap-1 text-primary hover:underline"><ExternalLink className="h-3.5 w-3.5" />{d.name}</a>
                    {!isObserver && <Button variant="ghost" size="icon" className="h-6 w-6" aria-label={t('Remove')} onClick={() => act('delete', `/attachments/${d.id}`)}><Trash2 className="h-3.5 w-3.5" /></Button>}
                  </li>
                ))}
              </ul>
            )}
          </Section>

          {data.tensions.length > 0 && (
            <Section title={t('Open tensions')} index={6}>
              <ul className="space-y-1.5 text-sm">{data.tensions.map((x) => <li key={x.id}>{x.title}</li>)}</ul>
            </Section>
          )}
        </div>
      </div>

      <RoleFormDialog open={editOpen} onOpenChange={setEditOpen} circles={circles} role={data} />

      <Dialog open={assignOpen} onOpenChange={setAssignOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-display text-xl">{t('Assign a person')}</DialogTitle>
            <DialogDescription>{t('One person can hold several roles across circles. A single-holder role must be vacated first.')}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-3">
            <div className="grid gap-1.5">
              <Label>{t('Person')}</Label>
              <Select value={person} onValueChange={setPerson}>
                <SelectTrigger aria-label={t('Person')}><SelectValue placeholder={t('Choose a person')} /></SelectTrigger>
                <SelectContent>{(people ?? []).filter((p) => !holderIds.has(p.id)).map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="focus">{t('Focus (optional)')}</Label>
              <Input id="focus" value={focus} maxLength={200} onChange={(e) => setFocus(e.target.value)} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAssignOpen(false)}>{t('Cancel')}</Button>
            <Button onClick={assign} disabled={!person}>{t('Assign')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={docOpen} onOpenChange={setDocOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle className="font-display text-xl">{t('Add document link')}</DialogTitle></DialogHeader>
          <div className="grid gap-3">
            <div className="grid gap-1.5"><Label htmlFor="dn">{t('Name')}</Label><Input id="dn" value={docName} maxLength={200} onChange={(e) => setDocName(e.target.value)} /></div>
            <div className="grid gap-1.5"><Label htmlFor="du">URL</Label><Input id="du" type="url" placeholder="https://" value={docUrl} onChange={(e) => setDocUrl(e.target.value)} /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDocOpen(false)}>{t('Cancel')}</Button>
            <Button onClick={addDoc} disabled={!docName.trim() || !docUrl.trim()}>{t('Add')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
