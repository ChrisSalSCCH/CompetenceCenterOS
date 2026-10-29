import { useState } from 'react'
import { Link } from 'react-router'
import { CheckCircle2, GitMerge, Wrench } from 'lucide-react'
import { ExportMenu } from '@/components/management/ExportMenu'
import { FixDialog } from '@/components/management/FixDialog'
import { Button } from '@/components/ui/button'
import { EmptyState, ErrorBlock, LoadingBlock, PageHeader, Pill, Section, type Tone } from '@/components/kit'
import { useSession } from '@/contexts/SessionContext'
import { useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import type { QualityData, QualityIssue } from '@/lib/management-types'

const SEVERITY_TONE: Record<QualityIssue['severity'], Tone> = { error: 'danger', warning: 'ochre', info: 'neutral' }

export default function DataQuality() {
  const { t } = useT()
  const act = useAct()
  const { isObserver } = useSession()
  const [kind, setKind] = useState<string | null>(null)
  const [fixing, setFixing] = useState<QualityIssue | null>(null)
  const { data, isLoading, error } = useGet<QualityData>('/management/data-quality', { kind })

  const merge = async (issue: QualityIssue) => {
    if (issue.fix?.action !== 'merge_contacts') return
    await act('post', '/management/contacts/merge', { keep_id: issue.fix.keep_id, merge_ids: issue.fix.merge_ids })
  }

  return (
    <>
      <PageHeader
        eyebrow={t('Management')}
        title={t('Data quality')}
        subtitle={t('Gaps that distort reports: missing owners, overdue dates, duplicate contacts. Fix them here directly.')}
        actions={<ExportMenu sets={['data_quality']} />}
      />
      {isLoading && <LoadingBlock />}
      {error && <ErrorBlock message={error.message} />}
      {data && (
        <>
          <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label={t('Filter by kind')}>
            <Button size="sm" variant={kind === null ? 'default' : 'outline'} aria-pressed={kind === null} onClick={() => setKind(null)}>{t('All')}</Button>
            {Object.entries(data.by_kind).map(([k, n]) => (
              <Button key={k} size="sm" variant={kind === k ? 'default' : 'outline'} aria-pressed={kind === k} onClick={() => setKind(k)}>{t(k.replaceAll('_', ' '))} ({n})</Button>
            ))}
          </div>
          <Section>
            {data.items.length === 0 ? (
              <EmptyState title={t('No findings')} hint={t('Your data is complete for all checks.')} action={<CheckCircle2 className="h-5 w-5 text-[hsl(var(--forest))]" aria-hidden />} />
            ) : (
              <ul className="divide-y">
                {data.items.map((i) => (
                  <li key={i.id} className="flex flex-wrap items-center gap-3 py-2.5">
                    <Pill tone={SEVERITY_TONE[i.severity]}>{t(i.severity)}</Pill>
                    <div className="min-w-0 flex-1">
                      <Link to={i.link} className="font-medium hover:underline">{i.label}</Link>
                      <p className="text-xs text-muted-foreground">{t(i.message)}</p>
                    </div>
                    {!isObserver && i.fix?.action === 'merge_contacts' && (
                      <Button size="sm" variant="outline" onClick={() => void merge(i)}><GitMerge className="mr-1 h-3.5 w-3.5" aria-hidden />{t('Merge duplicates')}</Button>
                    )}
                    {!isObserver && i.fix && i.fix.action !== 'merge_contacts' && (
                      <Button size="sm" variant="outline" onClick={() => setFixing(i)}><Wrench className="mr-1 h-3.5 w-3.5" aria-hidden />{t('Fix')}</Button>
                    )}
                  </li>
                ))}
              </ul>
            )}
            {data.truncated && <p className="mt-2 text-xs text-muted-foreground">{t('Only the first 300 findings are shown. Filter by kind to see more.')}</p>}
          </Section>
        </>
      )}
      <FixDialog issue={fixing} onClose={() => setFixing(null)} />
    </>
  )
}
