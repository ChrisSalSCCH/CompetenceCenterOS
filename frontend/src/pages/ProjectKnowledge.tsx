import { useState } from 'react'
import { Link } from 'react-router'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { EmptyState, ErrorBlock, LoadingBlock, PageHeader, Pill, ProgressBar, Section } from '@/components/kit'
import { useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import { classificationTone, relevantSections } from '@/lib/portfolio'
import type { PortfolioRow } from '@/lib/portfolio-types'

export default function ProjectKnowledge() {
  const { t } = useT()
  const [search, setSearch] = useState('')
  const [reviewOnly, setReviewOnly] = useState(false)
  const { data, isLoading, error } = useGet<PortfolioRow[]>('/portfolio', { search: search.trim() || undefined })
  const rows = (data ?? []).filter((p) => !reviewOnly || p.knowledge_review > 0)

  return (
    <>
      <PageHeader title={t('Project Knowledge')} subtitle={t('Which projects have documented knowledge, and how reliable is it?')} />
      <Section className="mb-4">
        <div className="flex flex-wrap items-center gap-4">
          <Input className="max-w-sm" value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t('Search name, number, customer, technology ...')} aria-label={t('Search')} />
          <Label className="flex items-center gap-2 text-sm"><Switch checked={reviewOnly} onCheckedChange={setReviewOnly} />{t('Only projects with unverified content')}</Label>
        </div>
      </Section>
      {isLoading && <LoadingBlock />}
      {error && <ErrorBlock message={error.message} />}
      {data && rows.length === 0 && <EmptyState title={t('No projects match your filters')} />}
      {rows.length > 0 && (
        <Section className="overflow-x-auto p-0 md:p-0">
          <Table>
            <TableHeader>
              <TableRow><TableHead>{t('Project')}</TableHead><TableHead>{t('Classification')}</TableHead><TableHead className="w-56">{t('Filled')}</TableHead><TableHead>{t('Verified sections')}</TableHead><TableHead>{t('Sections to review')}</TableHead></TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((p) => {
                const relevant = relevantSections(p.classification, p.ai_relevant).length
                return (
                  <TableRow key={p.id}>
                    <TableCell><Link to={`/projects/${p.id}?tab=knowledge`} className="font-medium hover:text-primary">{p.name}</Link></TableCell>
                    <TableCell><Pill tone={classificationTone(p.classification)}>{t(p.classification)}</Pill></TableCell>
                    <TableCell><ProgressBar value={relevant ? p.knowledge_filled / relevant : 0} tone="forest" /></TableCell>
                    <TableCell className="text-sm">{p.knowledge_verified} / {p.knowledge_filled}</TableCell>
                    <TableCell>{p.knowledge_review > 0 ? <Pill tone="ochre">{p.knowledge_review}</Pill> : <span className="text-muted-foreground">0</span>}</TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </Section>
      )}
    </>
  )
}
