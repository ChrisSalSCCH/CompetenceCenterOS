import { EmptyState, ErrorBlock, LoadingBlock, Section } from '@/components/kit'
import { fmtDateTime, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'

interface AuditRow {
  id: string
  action: string
  summary: string
  created_at: string
  actor_name: string | null
}

export function HistoryTab({ projectId }: Readonly<{ projectId: string }>) {
  const { t, lang } = useT()
  const { data, isLoading, error } = useGet<AuditRow[]>(`/portfolio/${projectId}/history`)
  return (
    <Section title={t('History')}>
      <p className="mb-3 text-xs text-muted-foreground">{t('Changes to this project are recorded in the audit log of Administration.')}</p>
      {isLoading && <LoadingBlock rows={3} />}
      {error && <ErrorBlock message={error.message} />}
      {data && data.length === 0 && <EmptyState title={t('History')} />}
      <ol className="space-y-2 border-l pl-4">
        {(data ?? []).map((a) => (
          <li key={a.id} className="text-sm">
            <span className="font-medium">{a.action.replace('project.', '').replaceAll('_', ' ')}</span>
            <span className="text-muted-foreground"> · {a.actor_name ?? '–'} · {fmtDateTime(a.created_at, lang)}</span>
            {a.summary && <div className="text-xs text-muted-foreground">{a.summary}</div>}
          </li>
        ))}
      </ol>
    </Section>
  )
}
