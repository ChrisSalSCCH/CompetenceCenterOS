import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { Check, ChevronRight, Pencil, Undo2, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ErrorBlock, ItemList, LoadingBlock, ModePill, PageHeader, Pill, Section, StatusPill, type Tone } from '@/components/kit'
import { HistoryTimeline } from '@/components/HistoryTimeline'
import { useSession } from '@/contexts/SessionContext'
import { fmtDateTime, useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import type { GovMode, HistoryEntry } from '@/lib/types'

interface Comment {
  id: string
  kind: string
  body: string
  status: 'open' | 'resolved' | 'withdrawn'
  resolution_note: string | null
  created_at: string
  author_id: string
  author_name: string
}

interface ProposalFull {
  id: string
  title: string
  description: string
  reason: string
  expected_impact: string
  proposal_type: string
  workflow: GovMode
  status: string
  circle_id: string
  circle_name: string
  initiator_id: string
  initiator_name: string
  decided_by_name: string | null
  decided_at: string | null
  decision_note: string | null
  ai_generated: boolean
  created_at: string
  comments: Comment[]
  stages: string[]
  open_objections: number
  next_status: string | null
  acceptance_blocker: string | null
  preview: { op: string; id: string | null; name: string | null; data: Record<string, unknown> }[]
  applied_changes: HistoryEntry[]
  source_tension: { id: string; title: string } | null
  can_decide: boolean
  can_advance: boolean
  can_edit: boolean
  can_withdraw: boolean
}

const OP_LABEL: Record<string, string> = {
  create_role: 'Create role', update_role: 'Modify role', delete_role: 'Remove role', create_circle: 'Create circle', update_circle: 'Modify circle', delete_circle: 'Remove circle',
}
const KIND_TONE: Record<string, Tone> = { question: 'ochre', answer: 'neutral', reaction: 'forest', objection: 'danger', comment: 'neutral', integration: 'primary' }
const STAGE_LABEL: Record<string, string> = {
  submitted: 'Proposal', clarifying: 'Clarifying questions', reactions: 'Reactions', objections: 'Objections', integration: 'Integration',
}

function stageClass(current: boolean, done: boolean): string {
  if (current) return 'border-primary bg-primary text-primary-foreground'
  return done ? 'border-[hsl(var(--forest)/0.4)] bg-[hsl(var(--forest)/0.1)]' : 'text-muted-foreground'
}

function kindsFor(workflow: GovMode, status: string): string[] {
  if (workflow === 'approval') return ['question', 'answer', 'comment']
  if (workflow === 'consent') return ['question', 'answer', 'reaction', 'objection', 'comment', ...(status === 'objections' ? ['integration'] : [])]
  const map: Record<string, string[]> = {
    draft: ['comment'], submitted: ['question', 'answer', 'reaction', 'comment'], clarifying: ['question', 'answer', 'reaction', 'comment'],
    reactions: ['reaction', 'comment'], objections: ['objection', 'integration', 'comment'], integration: ['objection', 'integration', 'comment'],
  }
  return map[status] ?? ['comment']
}

export default function ProposalDetail() {
  const { id } = useParams()
  const { t, lang } = useT()
  const act = useAct()
  const navigate = useNavigate()
  const { isObserver } = useSession()
  const { data, isLoading, error } = useGet<ProposalFull>(id ? `/proposals/${id}` : null)
  const [kind, setKind] = useState('comment')
  const [body, setBody] = useState('')
  const [decision, setDecision] = useState<'accepted' | 'rejected' | null>(null)
  const [rationale, setRationale] = useState('')

  if (isLoading) return <LoadingBlock rows={5} />
  if (error || !data) return <ErrorBlock message={error?.message} />
  const closed = ['accepted', 'rejected', 'withdrawn'].includes(data.status)
  const kinds = kindsFor(data.workflow, data.status)
  const kindValue = kinds.includes(kind) ? kind : kinds[0]
  const stageIndex = data.stages.indexOf(data.status)

  const post = async () => {
    const res = await act('post', `/proposals/${data.id}/comments`, { kind: kindValue, body })
    if (res) setBody('')
  }
  const decide = async () => {
    if (!decision) return
    const res = await act('post', `/proposals/${data.id}/decide`, { outcome: decision, rationale })
    if (res) {
      setDecision(null)
      setRationale('')
    }
  }

  return (
    <>
      <PageHeader
        eyebrow={<Link to="/governance" className="hover:text-primary">{t('Governance')}</Link>}
        title={data.title}
        subtitle={`${data.circle_name} · ${t('initiated by')} ${data.initiator_name} · ${fmtDateTime(data.created_at, lang)}`}
        actions={
          <>
            {data.ai_generated && <Pill tone="ochre">{t('AI draft')}</Pill>}
            <ModePill mode={data.workflow} />
            <StatusPill status={data.status} />
          </>
        }
      />

      {data.stages.length > 1 && (
        <ol className="reveal mb-6 flex flex-wrap items-center gap-1" aria-label={t('Workflow stages')}>
          {[...data.stages, closed ? data.status : 'decision'].map((s, i) => {
            const done = closed || i < stageIndex
            const current = !closed && i === stageIndex
            return (
              <li key={s} className="flex items-center gap-1">
                <span className={`rounded-full border px-3 py-1 text-xs font-medium ${stageClass(current, done)}`}>
                  {t(STAGE_LABEL[s] ?? (s === 'decision' ? 'Decision' : s))}
                </span>
                {i < data.stages.length && <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />}
              </li>
            )
          })}
        </ol>
      )}

      {data.status === 'draft' && (
        <div className="mb-4 flex flex-wrap items-center gap-2 rounded-lg border border-dashed p-3 text-sm">
          <Pill>{t('draft')}</Pill> {t('This proposal is not yet visible to the decision makers.')}
          {data.can_edit && <Button size="sm" onClick={() => navigate(`/governance/proposals/new?edit=${data.id}`)}><Pencil className="mr-1 h-4 w-4" />{t('Edit and submit')}</Button>}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Section title={t('Proposal')} index={1}>
            {data.source_tension && <p className="mb-3 text-xs text-muted-foreground">{t('Raised from tension')}: <span className="font-medium text-foreground">{data.source_tension.title}</span></p>}
            {data.description && <p className="mb-4 text-sm">{data.description}</p>}
            <div className="grid gap-4 md:grid-cols-2">
              <div><div className="font-mono-label mb-1 text-muted-foreground">{t('Reason for change')}</div><p className="text-sm">{data.reason || '–'}</p></div>
              <div><div className="font-mono-label mb-1 text-muted-foreground">{t('Expected impact')}</div><p className="text-sm">{data.expected_impact || '–'}</p></div>
            </div>
          </Section>

          <Section title={t('Proposed modifications')} index={2}>
            {data.preview.length === 0 && <p className="text-sm text-muted-foreground">{t('No modifications defined yet.')}</p>}
            <div className="space-y-3">
              {data.preview.map((p, i) => (
                <div key={i} className="rounded-xl border p-3">
                  <div className="mb-2 flex items-center gap-2"><Pill tone={p.op.startsWith('delete') ? 'danger' : p.op.startsWith('create') ? 'forest' : 'primary'}>{t(OP_LABEL[p.op] ?? p.op)}</Pill><span className="text-sm font-medium">{p.name}</span></div>
                  {typeof p.data.purpose === 'string' && p.data.purpose && <p className="mb-2 text-sm">{p.data.purpose}</p>}
                  <div className="grid gap-3 md:grid-cols-3">
                    {(['accountabilities', 'domains', 'authorities'] as const).map((k) => Array.isArray(p.data[k]) && (p.data[k] as unknown[]).length > 0 && (
                      <div key={k}><div className="font-mono-label mb-1 text-muted-foreground">{t(k === 'authorities' ? 'Decision authorities' : k === 'domains' ? 'Domains' : 'Accountabilities')}</div><ItemList items={p.data[k] as { text: string }[]} empty="" /></div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </Section>

          <Section title={`${t('Discussion')} (${data.comments.length})`} index={3}>
            <ul className="space-y-3">
              {data.comments.map((c) => (
                <li key={c.id} className={`rounded-xl border p-3 ${c.kind === 'objection' && c.status === 'open' ? 'border-destructive/40 bg-destructive/5' : ''}`}>
                  <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <Pill tone={KIND_TONE[c.kind]}>{t(c.kind)}</Pill>
                    <span className="font-medium text-foreground">{c.author_name}</span>
                    {fmtDateTime(c.created_at, lang)}
                    {c.kind === 'objection' && <StatusPill status={c.status === 'open' ? 'open' : c.status === 'resolved' ? 'resolved' : 'withdrawn'} />}
                  </div>
                  <p className="text-sm">{c.body}</p>
                  {c.kind === 'objection' && c.status === 'open' && !closed && !isObserver && (
                    <div className="mt-2 flex gap-2">
                      {data.can_decide && <Button size="sm" variant="outline" onClick={() => act('patch', `/proposal-comments/${c.id}`, { status: 'resolved', resolution_note: 'Integrated' })}><Check className="mr-1 h-3.5 w-3.5" />{t('Mark as integrated')}</Button>}
                      <Button size="sm" variant="ghost" onClick={() => act('patch', `/proposal-comments/${c.id}`, { status: 'withdrawn' })}><Undo2 className="mr-1 h-3.5 w-3.5" />{t('Withdraw')}</Button>
                    </div>
                  )}
                </li>
              ))}
              {data.comments.length === 0 && <p className="text-sm text-muted-foreground">{t('No questions, reactions or objections yet.')}</p>}
            </ul>
            {!closed && !isObserver && (
              <div className="mt-4 grid gap-2 border-t pt-4">
                <div className="flex items-center gap-2">
                  <Label className="text-xs">{t('Add')}</Label>
                  <Select value={kindValue} onValueChange={setKind}>
                    <SelectTrigger className="w-48" aria-label={t('Type of contribution')}><SelectValue /></SelectTrigger>
                    <SelectContent>{kinds.map((k) => <SelectItem key={k} value={k}>{t(k)}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <Textarea rows={2} value={body} onChange={(e) => setBody(e.target.value)} aria-label={t('Your contribution')} placeholder={kindValue === 'objection' ? t('Explain which harm or limitation the proposal causes...') : t('Write here...')} />
                <Button className="w-fit" size="sm" onClick={post} disabled={!body.trim()}>{t('Post')}</Button>
              </div>
            )}
          </Section>

          {data.applied_changes.length > 0 && (
            <Section title={t('Changes applied to the organization')} index={4}>
              <HistoryTimeline entries={data.applied_changes} showEntity />
            </Section>
          )}
        </div>

        <div className="space-y-4">
          <Section title={t('Decision')} index={2}>
            {closed ? (
              <div className="space-y-2 text-sm">
                <StatusPill status={data.status} />
                {data.decided_by_name && <p>{t('Decided by')} <strong>{data.decided_by_name}</strong> · {fmtDateTime(data.decided_at, lang)}</p>}
                {data.decision_note && <p className="italic">“{data.decision_note}”</p>}
                {data.status === 'rejected' && <p className="text-xs text-muted-foreground">{t('Rejected proposals do not change the organization.')}</p>}
              </div>
            ) : (
              <div className="space-y-3 text-sm">
                <p className="text-muted-foreground">{data.open_objections > 0 ? `${data.open_objections} ${t('open objection(s) must be integrated before acceptance.')}` : t('No open objections.')}</p>
                {data.acceptance_blocker && data.status !== 'draft' && <p className="rounded-lg bg-muted p-2 text-xs">{data.acceptance_blocker}</p>}
                {data.can_advance && data.next_status && <Button className="w-full" variant="outline" onClick={() => act('post', `/proposals/${data.id}/advance`)}>{t('Advance to')}: {t(STAGE_LABEL[data.next_status] ?? data.next_status)}</Button>}
                {data.can_decide && (
                  <div className="flex gap-2">
                    <Button className="flex-1" onClick={() => setDecision('accepted')} disabled={Boolean(data.acceptance_blocker)}><Check className="mr-1 h-4 w-4" />{t('Accept')}</Button>
                    <Button className="flex-1" variant="outline" onClick={() => setDecision('rejected')}><X className="mr-1 h-4 w-4" />{t('Reject')}</Button>
                  </div>
                )}
                {!data.can_decide && data.status !== 'draft' && <p className="text-xs text-muted-foreground">{t('Only holders of a governance role for this circle can decide.')}</p>}
                {data.can_withdraw && <Button variant="ghost" size="sm" onClick={() => act('post', `/proposals/${data.id}/withdraw`)}>{t('Withdraw proposal')}</Button>}
              </div>
            )}
          </Section>
        </div>
      </div>

      <Dialog open={decision !== null} onOpenChange={(v) => !v && setDecision(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-display text-xl">{decision === 'accepted' ? t('Accept proposal') : t('Reject proposal')}</DialogTitle>
            <DialogDescription>{decision === 'accepted' ? t('All modifications are applied together in one transaction and recorded in the governance history.') : t('The organization stays unchanged. The decision is recorded.')}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-1.5"><Label htmlFor="rat">{t('Rationale')}</Label><Textarea id="rat" rows={3} value={rationale} onChange={(e) => setRationale(e.target.value)} /></div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDecision(null)}>{t('Cancel')}</Button>
            <Button onClick={decide}>{t('Confirm decision')}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
