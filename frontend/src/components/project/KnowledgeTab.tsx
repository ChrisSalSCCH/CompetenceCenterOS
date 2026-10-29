import { ProgressBar, Section } from '@/components/kit'
import { KnowledgeSectionEditor } from '@/components/project/KnowledgeSectionEditor'
import { useT } from '@/lib/i18n'
import type { KnowledgeSection, ProjectDetailData } from '@/lib/portfolio-types'
import { relevantSections } from '@/lib/portfolio'

/** Sections shown in the Technology & Architecture tab instead. */
export const TECH_SECTIONS: KnowledgeSection[] = ['architecture', 'ai_usage']

export function KnowledgeTab({ p }: Readonly<{ p: ProjectDetailData }>) {
  const { t } = useT()
  const keys = relevantSections(p.classification, p.ai_relevant).map((s) => s.key).filter((k) => !TECH_SECTIONS.includes(k))
  const sections = p.knowledge.sections.filter((s) => keys.includes(s.section))
  const c = p.knowledge.completeness
  return (
    <div className="space-y-4">
      <Section title={t('Knowledge completeness')}>
        <ProgressBar value={c.relevant ? c.filled / c.relevant : 0} tone="forest" />
        <p className="mt-2 text-xs text-muted-foreground">{c.filled} / {c.relevant} {t('sections filled')} · {c.verified} {t('verified')} <span className="ml-1 rounded border px-1">{t('Calculated')}</span></p>
      </Section>
      <div className="grid gap-4 lg:grid-cols-2">
        {sections.map((s) => <KnowledgeSectionEditor key={s.section} projectId={p.id} data={s} canEdit={p.can_manage} />)}
      </div>
    </div>
  )
}
