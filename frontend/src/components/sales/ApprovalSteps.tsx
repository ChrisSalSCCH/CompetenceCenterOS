import { useState } from 'react'
import { Check, Clock, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Pill, Section, type Tone } from '@/components/kit'
import { fmtDateTime, useAct } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import type { ApprovalStep, VersionData } from '@/lib/sales-types'

const ICON = { approved: Check, rejected: X, pending: Clock } as const
const TONE: Record<ApprovalStep['status'], Tone> = { approved: 'forest', rejected: 'danger', pending: 'ochre' }

function StepRow({ version, step }: Readonly<{ version: VersionData; step: ApprovalStep }>) {
  const { t, lang } = useT()
  const act = useAct()
  const [note, setNote] = useState('')
  const Icon = ICON[step.status]
  const decide = (decision: 'approve' | 'reject') =>
    act('post', `/commercial/proposals/${version.proposal_id}/versions/${version.id}/approvals/${step.id}`, { decision, note: note.trim() || null })
  const noteMissing = step.needs_override_note && note.trim().length < 3
  return (
    <li className="rounded-lg border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Icon className="h-4 w-4" aria-hidden />
        <span className="font-medium">{step.step_order}. {step.label}</span>
        {step.role_name && <span className="text-xs text-muted-foreground">{step.role_name}</span>}
        <Pill className="ml-auto" tone={TONE[step.status]}>{t(step.status)}</Pill>
      </div>
      {step.decided_at && <p className="mt-1 text-xs text-muted-foreground">{step.decided_by_name} · {fmtDateTime(step.decided_at, lang)}{step.admin_override && ` · ${t('administrator override')}`}</p>}
      {step.note && <p className="mt-1 text-sm">{step.note}</p>}
      {step.can_decide && (
        <div className="mt-2 grid gap-2">
          <Textarea rows={2} value={note} maxLength={2000} placeholder={step.needs_override_note ? `${t('Administrator note')} *` : t('Note (required when rejecting)')} aria-label={t('Note')} onChange={(e) => setNote(e.target.value)} />
          <div className="flex gap-2">
            <Button size="sm" disabled={noteMissing} onClick={() => decide('approve')}>{t('Approve')}</Button>
            <Button size="sm" variant="destructive" disabled={note.trim().length < 3} onClick={() => decide('reject')}>{t('Reject')}</Button>
          </div>
        </div>
      )}
    </li>
  )
}

export function ApprovalSteps({ version }: Readonly<{ version: VersionData }>) {
  const { t } = useT()
  if (version.approvals.length === 0) return null
  return (
    <Section title={t('Approval')}>
      <ol className="space-y-2">{version.approvals.map((s) => <StepRow key={s.id} version={version} step={s} />)}</ol>
    </Section>
  )
}
