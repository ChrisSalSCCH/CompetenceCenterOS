import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { Bookmark, Search, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { EmptyState, ErrorBlock, LoadingBlock, PageHeader, Pill, Section } from '@/components/kit'
import { useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import type { SearchHit } from '@/lib/types'

interface RoleHit {
  role_id: string
  role_name: string
  circle_name: string
  holders: { user_id: string; name: string }[]
  accountabilities: string[]
  domains: string[]
  decision_authorities: string[]
  score: number
}

const ORDER = ['role', 'circle', 'person', 'proposal', 'project', 'customer', 'contact', 'catalog', 'task', 'meeting', 'tension']
const LABEL: Record<string, string> = { role: 'Roles', circle: 'Circles', person: 'People', proposal: 'Proposals', project: 'Projects', customer: 'Companies', contact: 'Contacts', catalog: 'Technologies & Competencies', task: 'Tasks', meeting: 'Meetings', tension: 'Tensions' }

export default function SearchPage() {
  const { t } = useT()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const act = useAct()
  const q = params.get('q') ?? ''
  const [text, setText] = useState(q)
  const { data, isLoading, error } = useGet<{ results: SearchHit[] }>(q.length >= 2 ? '/search' : null, { q })
  const { data: resp } = useGet<{ roles: RoleHit[] }>(q.length >= 2 ? '/responsibilities' : null, { q })
  const { data: saved } = useGet<{ id: string; name: string; query: string }[]>('/saved-filters')
  const results = data?.results ?? []

  return (
    <>
      <PageHeader title={t('Search')} subtitle={t('Finds responsibilities, not only names: a phrase inside an accountability leads you to the role.')} />
      <form className="mb-4 flex gap-2" onSubmit={(e) => { e.preventDefault(); setParams({ q: text.trim() }) }}>
        <div className="relative max-w-xl flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input className="pl-9" value={text} onChange={(e) => setText(e.target.value)} placeholder={t('e.g. project acquisition')} aria-label={t('Search')} />
        </div>
        <Button type="submit">{t('Search')}</Button>
        {q && <Button type="button" variant="outline" onClick={() => act('post', '/saved-filters', { name: q.slice(0, 80), query: q })}><Bookmark className="mr-1 h-4 w-4" />{t('Save search')}</Button>}
        {q && <Button type="button" variant="ghost" onClick={() => navigate(`/assistant?q=${encodeURIComponent(q)}`)}>{t('Ask the assistant')}</Button>}
      </form>

      {(saved ?? []).length > 0 && (
        <div className="mb-6 flex flex-wrap items-center gap-2">
          <span className="font-mono-label text-muted-foreground">{t('Saved searches')}</span>
          {saved?.map((s) => (
            <span key={s.id} className="flex items-center rounded-full border bg-card text-sm">
              <button type="button" className="px-3 py-1 hover:text-primary" onClick={() => { setText(s.query); setParams({ q: s.query }) }}>{s.name}</button>
              <button type="button" className="pr-2 text-muted-foreground hover:text-destructive" aria-label={t('Delete saved search')} onClick={() => act('delete', `/saved-filters/${s.id}`)}><Trash2 className="h-3.5 w-3.5" /></button>
            </span>
          ))}
        </div>
      )}

      {q.length < 2 && <EmptyState title={t('Type at least two characters')} />}
      {isLoading && <LoadingBlock />}
      {error && <ErrorBlock message={error.message} />}

      {resp && resp.roles.length > 0 && (
        <Section title={t('Who is responsible?')} className="mb-4">
          <p className="mb-3 text-xs text-muted-foreground">{t('Matches are shown separately as accountability (ongoing activity), domain (exclusive control) and decision authority (the right to decide).')}</p>
          <div className="grid gap-3 md:grid-cols-2">
            {resp.roles.slice(0, 4).map((r) => (
              <Link key={r.role_id} to={`/organization/roles/${r.role_id}`} className="paper-card interactive block p-3">
                <div className="font-display text-base font-semibold">{r.role_name}</div>
                <div className="mb-2 text-xs text-muted-foreground">{r.circle_name} · {r.holders.map((h) => h.name).join(', ') || t('unfilled')}</div>
                {r.accountabilities.map((a) => <div key={a} className="text-sm"><Pill tone="primary" className="mr-1">{t('accountable')}</Pill>{a}</div>)}
                {r.domains.map((a) => <div key={a} className="text-sm"><Pill tone="ochre" className="mr-1">{t('domain')}</Pill>{a}</div>)}
                {r.decision_authorities.map((a) => <div key={a} className="text-sm"><Pill tone="forest" className="mr-1">{t('decides')}</Pill>{a}</div>)}
              </Link>
            ))}
          </div>
        </Section>
      )}

      {data && results.length === 0 && <EmptyState title={t('Nothing found.')} hint={t('Try fewer or different words.')} />}
      <div className="space-y-4">
        {ORDER.map((type) => {
          const hits = results.filter((r) => r.type === type)
          if (hits.length === 0) return null
          return (
            <Section key={type} title={`${t(LABEL[type])} (${hits.length})`}>
              <ul className="divide-y">
                {hits.map((h) => (
                  <li key={h.id}>
                    <Link to={h.link} className="block py-2.5 hover:text-primary">
                      <span className="text-sm font-medium">{h.title}</span>
                      <span className="block text-xs text-muted-foreground">{h.subtitle}</span>
                      {h.snippet && h.snippet.field !== 'name' && h.snippet.field !== 'title' && <span className="block text-xs"><span className="font-mono-label text-primary">{h.snippet.field}</span> {h.snippet.text}</span>}
                    </Link>
                  </li>
                ))}
              </ul>
            </Section>
          )
        })}
      </div>
    </>
  )
}
