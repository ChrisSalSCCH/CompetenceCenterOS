import { useEffect, useState } from 'react'
import { BadgeCheck, Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Pill } from '@/components/kit'
import { fmtDate, useAct } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import { KNOWLEDGE_SECTIONS, VERIFICATION_LABEL, VERIFICATION_TONE } from '@/lib/portfolio'
import type { KnowledgeSectionData, Verification } from '@/lib/portfolio-types'

export function VerificationBadge({ state }: Readonly<{ state: Verification }>) {
  const { t } = useT()
  return (
    <Pill tone={VERIFICATION_TONE[state]}>
      {state === 'ai_draft' ? <Sparkles className="h-3 w-3" aria-hidden /> : <BadgeCheck className="h-3 w-3" aria-hidden />}
      {t(VERIFICATION_LABEL[state])}
    </Pill>
  )
}

interface Props {
  projectId: string
  data: KnowledgeSectionData
  canEdit: boolean
}

export function KnowledgeSectionEditor({ projectId, data, canEdit }: Readonly<Props>) {
  const { t, lang } = useT()
  const act = useAct()
  const meta = KNOWLEDGE_SECTIONS.find((s) => s.key === data.section)
  const [text, setText] = useState(data.content)
  useEffect(() => setText(data.content), [data.content])
  const dirty = text !== data.content
  const base = `/portfolio/${projectId}/knowledge/${data.section}`

  const setState = (verification: Verification) => act('put', base, { verification })

  return (
    <div className="rounded-xl border bg-card p-4">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-display text-lg font-semibold">{t(meta?.label ?? data.section)}</h3>
        <VerificationBadge state={data.verification} />
      </div>
      {canEdit ? (
        <Textarea rows={4} value={text} maxLength={20000} onChange={(e) => setText(e.target.value)} placeholder={t(meta?.hint ?? '')} aria-label={t(meta?.label ?? data.section)} />
      ) : (
        <p className="whitespace-pre-wrap text-sm">{data.content || <span className="italic text-muted-foreground">–</span>}</p>
      )}
      {data.verified_at && data.verified_by_name && (
        <p className="mt-2 text-xs text-muted-foreground">{t('Verified by')} {data.verified_by_name} · {fmtDate(data.verified_at, lang)}</p>
      )}
      {canEdit && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Button size="sm" disabled={!dirty} onClick={() => act('put', base, { content: text })}>{t('Save')}</Button>
          {!dirty && data.content && data.verification !== 'verified' && data.verification !== 'approved' && <Button size="sm" variant="outline" onClick={() => setState('verified')}>{t('Mark as verified')}</Button>}
          {!dirty && data.content && data.verification === 'verified' && <Button size="sm" variant="outline" onClick={() => setState('approved')}>{t('Approve')}</Button>}
          {!dirty && data.content && data.verification === 'unverified' && <Button size="sm" variant="ghost" onClick={() => setState('ai_draft')}>{t('Mark as AI draft')}</Button>}
          {dirty && <span className="text-xs text-muted-foreground">{t('Editing the text resets the section to unverified.')}</span>}
        </div>
      )}
    </div>
  )
}
