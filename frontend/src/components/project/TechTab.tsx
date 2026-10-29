import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { Button } from '@/components/ui/button'
import { CatalogPicker, type PickedEntry } from '@/components/CatalogPicker'
import { EmptyState, Pill, Section } from '@/components/kit'
import { KnowledgeSectionEditor } from '@/components/project/KnowledgeSectionEditor'
import { useAct } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import { CATALOG_KINDS, KIND_SINGULAR } from '@/lib/portfolio'
import type { CatalogKind, ProjectDetailData } from '@/lib/portfolio-types'

export function TechTab({ p }: Readonly<{ p: ProjectDetailData }>) {
  const { t } = useT()
  const act = useAct()
  const [editing, setEditing] = useState(false)
  const initial: PickedEntry[] = p.entries.map((e) => ({ id: e.id, name: e.name, kind: e.kind }))
  const [draft, setDraft] = useState<PickedEntry[]>(initial)
  const signature = p.entries.map((e) => e.id).join(',')
  useEffect(() => setDraft(p.entries.map((e) => ({ id: e.id, name: e.name, kind: e.kind }))), [signature]) // eslint-disable-line react-hooks/exhaustive-deps

  const save = async () => {
    const res = await act('put', `/portfolio/${p.id}/entries`, { items: draft.map((d) => ({ entry_id: d.id })) })
    if (res) setEditing(false)
  }
  const byKind = CATALOG_KINDS.map((k) => ({ ...k, items: p.entries.filter((e) => e.kind === k.kind) })).filter((g) => g.items.length > 0)
  const sections = p.knowledge.sections.filter((s) => s.section === 'architecture' || (s.section === 'ai_usage' && p.ai_relevant))

  return (
    <div className="space-y-4">
      <Section
        title={t('Technologies, methods and topics')}
        action={p.can_manage && (editing ? (
          <span className="flex gap-2"><Button size="sm" variant="outline" onClick={() => { setEditing(false); setDraft(initial) }}>{t('Cancel')}</Button><Button size="sm" onClick={save}>{t('Save')}</Button></span>
        ) : <Button size="sm" variant="outline" onClick={() => setEditing(true)}>{t('Edit tags')}</Button>)}
      >
        {editing ? <CatalogPicker value={draft} onChange={setDraft} /> : (
          <>
            {byKind.length === 0 && <EmptyState title={t('No tags yet')} />}
            <div className="space-y-3">
              {byKind.map((g) => (
                <div key={g.kind}>
                  <div className="font-mono-label mb-1 text-muted-foreground">{t(KIND_SINGULAR[g.kind as CatalogKind])}</div>
                  <div className="flex flex-wrap gap-1.5">
                    {g.items.map((e) => <Link key={e.id} to={`/projects?entry=${e.id}`}><Pill tone="primary">{e.name}</Pill></Link>)}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </Section>
      <div className="grid gap-4 lg:grid-cols-2">
        {sections.map((s) => <KnowledgeSectionEditor key={s.section} projectId={p.id} data={s} canEdit={p.can_manage} />)}
      </div>
    </div>
  )
}
