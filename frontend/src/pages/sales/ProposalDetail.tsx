import { useRef, useState } from 'react'
import { Link, useParams } from 'react-router'
import { ArrowLeft, GitCompare, Lock } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { DocumentsPanel } from '@/components/DocumentsPanel'
import { ErrorBlock, LoadingBlock, PageHeader, Pill, Section, type Tone } from '@/components/kit'
import { ApprovalSteps } from '@/components/sales/ApprovalSteps'
import { CompareDialog } from '@/components/sales/ProposalDialogs'
import { VersionEditor } from '@/components/sales/VersionEditor'
import { fmtDate, fmtDateTime, useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import { PROPOSAL_TONE, fmtMoney } from '@/lib/sales'
import type { ProposalData, VersionData, VersionStatus } from '@/lib/sales-types'
import { cn } from '@/lib/utils'

const VERSION_TONE: Record<VersionStatus, Tone> = { draft: 'neutral', in_approval: 'ochre', approved: 'forest', submitted: 'primary', superseded: 'neutral', rejected: 'danger' }

export default function ProposalDetail() {
  const { t, lang } = useT()
  const { id } = useParams()
  const act = useAct()
  const { data: p, isLoading, error } = useGet<ProposalData>(id ? `/commercial/proposals/${id}` : null)
  const [picked, setPicked] = useState<string | null>(null)
  const [comparing, setComparing] = useState(false)
  const saveRef = useRef<(() => Promise<boolean>) | null>(null)
  const selectedId = picked ?? p?.current_version_id ?? null
  const useCurrent = !p || selectedId === p.current?.id
  const { data: other } = useGet<VersionData>(!useCurrent && id && selectedId ? `/commercial/proposals/${id}/versions/${selectedId}` : null)

  if (isLoading) return <LoadingBlock rows={5} />
  if (error || !p) return <ErrorBlock message={error?.status === 404 ? t('Proposal not found') : error?.message} />
  const v = useCurrent ? p.current : other ?? null
  const base = `/commercial/proposals/${p.id}`
  const newVersion = async (kind: 'revision' | 'alternative') => {
    const res = await act<{ id: string }>('post', `${base}/versions`, { kind, from_version_id: v?.id ?? null })
    if (res) setPicked(res.id)
  }
  const requestApproval = async () => {
    const saved = saveRef.current ? await saveRef.current() : true
    if (saved && v) await act('post', `${base}/versions/${v.id}/request-approval`)
  }
  const sendToCustomer = () => v && act('post', `${base}/versions/${v.id}/submit`)
  const outcome = (value: 'accepted' | 'rejected' | 'withdrawn') => act('post', `${base}/outcome`, { outcome: value })
  const editable = Boolean(v?.editable)

  return (
    <>
      <Link to={`/sales/opportunities/${p.opportunity.id}?tab=proposals`} className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-primary"><ArrowLeft className="h-4 w-4" aria-hidden />{p.opportunity.number} · {p.opportunity.title}</Link>
      <PageHeader
        eyebrow={p.number}
        title={p.title}
        subtitle={p.valid_until ? `${t('Valid until')} ${fmtDate(p.valid_until, lang)}` : undefined}
        actions={
          <>
            <Pill tone={PROPOSAL_TONE[p.status]}>{t(p.status.replaceAll('_', ' '))}</Pill>
            {p.versions.length > 1 && <Button variant="outline" onClick={() => setComparing(true)}><GitCompare className="mr-1 h-4 w-4" aria-hidden />{t('Compare versions')}</Button>}
          </>
        }
      />

      <Section className="mb-4" title={t('Versions')} action={p.can_edit ? (
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => newVersion('revision')}>{t('New revision')}</Button>
          <Button size="sm" variant="outline" onClick={() => newVersion('alternative')}>{t('New alternative')}</Button>
        </div>
      ) : undefined}>
        <ul className="flex flex-wrap gap-2">
          {p.versions.map((ver) => (
            <li key={ver.id}>
              <button
                type="button"
                aria-pressed={ver.id === selectedId}
                onClick={() => setPicked(ver.id)}
                className={cn('rounded-lg border px-3 py-2 text-left text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring', ver.id === selectedId ? 'border-primary bg-primary/5' : 'hover:bg-muted')}
              >
                <span className="flex items-center gap-2 font-medium">v{ver.version_no}{ver.locked_at && <Lock className="h-3 w-3" aria-label={t('locked')} />}<Pill tone={VERSION_TONE[ver.status]}>{t(ver.status.replaceAll('_', ' '))}</Pill></span>
                <span className="block text-xs text-muted-foreground">{t(ver.kind)}{ver.label && ` · ${ver.label}`} · {fmtMoney(ver.price_total, ver.currency, lang)}</span>
                <span className="block text-[11px] text-muted-foreground">{ver.author_name} · {fmtDateTime(ver.submitted_at ?? ver.locked_at, lang)}</span>
              </button>
            </li>
          ))}
        </ul>
      </Section>

      {!v && <LoadingBlock rows={3} />}
      {v && (
        <div className="space-y-4">
          {v.locked_at && (
            <p className="flex items-start gap-2 rounded-lg border border-[hsl(var(--forest)/0.3)] bg-[hsl(var(--forest)/0.07)] p-3 text-sm">
              <Lock className="mt-0.5 h-4 w-4 text-[hsl(var(--forest))]" aria-hidden />
              <span>{t('This version is approved and locked since')} {fmtDateTime(v.locked_at, lang)}. {t('Changes always create a new version.')} <span className="font-mono text-[11px] text-muted-foreground">{v.snapshot_hash?.slice(0, 12)}</span></span>
            </p>
          )}
          <ApprovalSteps version={v} />
          <VersionEditor version={v} readOnly={!editable} onSaved={() => undefined} registerSave={(fn) => { saveRef.current = fn }} />
          {p.can_edit && (
            <Section>
              <div className="flex flex-wrap items-center gap-2">
                {editable && <Button variant="outline" onClick={() => saveRef.current?.()}>{t('Save')}</Button>}
                {editable && <Button onClick={requestApproval}>{t('Request approval')}</Button>}
                {v.status === 'approved' && <Button onClick={sendToCustomer}>{t('Mark as sent to customer')}</Button>}
                {p.status === 'submitted' && (
                  <>
                    <Button onClick={() => outcome('accepted')}>{t('Customer accepted')}</Button>
                    <Button variant="outline" onClick={() => outcome('rejected')}>{t('Customer declined')}</Button>
                  </>
                )}
                {(p.status === 'submitted' || p.status === 'approved') && (
                  <ConfirmDialog trigger={<Button variant="ghost">{t('Withdraw proposal')}</Button>} title={t('Withdraw proposal')} description={p.title} onConfirm={() => outcome('withdrawn')} />
                )}
              </div>
            </Section>
          )}
        </div>
      )}
      <div className="mt-4"><DocumentsPanel entityType="proposal" entityId={p.id} /></div>
      <CompareDialog proposalId={p.id} versions={p.versions} open={comparing} onOpenChange={setComparing} />
    </>
  )
}
