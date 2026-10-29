import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { ArrowLeft, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { ErrorBlock, LoadingBlock, PageHeader, Pill, StatusPill } from '@/components/kit'
import { OverviewTab } from '@/components/project/OverviewTab'
import { KnowledgeTab } from '@/components/project/KnowledgeTab'
import { TechTab } from '@/components/project/TechTab'
import { TeamTab } from '@/components/project/TeamTab'
import { FinanceTab } from '@/components/project/FinanceTab'
import { DocsTab } from '@/components/project/DocsTab'
import { CommTab } from '@/components/project/CommTab'
import { HistoryTab } from '@/components/project/HistoryTab'
import { useSession } from '@/contexts/SessionContext'
import { useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import { classificationTone, phaseTone } from '@/lib/portfolio'
import type { ProjectDetailData } from '@/lib/portfolio-types'

const TABS = ['overview', 'knowledge', 'tech', 'team', 'finance', 'documents', 'communication', 'history'] as const
type TabKey = (typeof TABS)[number]

export default function ProjectDetail() {
  const { t } = useT()
  const { id } = useParams()
  const navigate = useNavigate()
  const act = useAct()
  const { isAdmin } = useSession()
  const [params, setParams] = useSearchParams()
  const { data: p, isLoading, error } = useGet<ProjectDetailData>(id ? `/portfolio/${id}` : null)
  const requested = params.get('tab')
  const tab: TabKey = TABS.find((x) => x === requested) ?? 'overview'

  if (isLoading) return <LoadingBlock rows={5} />
  if (error || !p) return <ErrorBlock message={error?.status === 404 ? t('Project not found') : error?.message} />

  const remove = async () => {
    const ok = await act('delete', `/portfolio/${p.id}`)
    if (ok) navigate('/projects')
  }

  return (
    <>
      <Link to="/projects" className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-primary"><ArrowLeft className="h-4 w-4" aria-hidden />{t('Back to portfolio')}</Link>
      <PageHeader
        eyebrow={p.project_no}
        title={p.name}
        subtitle={p.short_name ?? undefined}
        actions={
          <>
            <Pill tone={classificationTone(p.classification)}>{t(p.classification)}</Pill>
            <Pill>{t(p.category)}</Pill>
            <Pill tone={phaseTone(p.phase)}>{t(p.phase)}</Pill>
            <StatusPill status={p.status} />
            {p.is_research && <Pill tone="forest">{t('Research project')}</Pill>}
            {p.ai_relevant && <Pill tone="ochre">{t('AI relevant')}</Pill>}
            {isAdmin && (
              <ConfirmDialog
                trigger={<Button variant="ghost" size="icon" aria-label={t('Delete project')}><Trash2 className="h-4 w-4" /></Button>}
                title={t('Delete project')} description={t('This project and its links will be removed from the portfolio.')} onConfirm={remove}
              />
            )}
          </>
        }
      />
      <Tabs value={tab} onValueChange={(v) => setParams({ tab: v }, { replace: true })} className="space-y-4">
        <TabsList className="h-auto flex-wrap justify-start">
          <TabsTrigger value="overview">{t('Overview')}</TabsTrigger>
          <TabsTrigger value="knowledge">{t('Project Knowledge')}</TabsTrigger>
          <TabsTrigger value="tech">{t('Technology & Architecture')}</TabsTrigger>
          <TabsTrigger value="team">{t('Team & Roles')}</TabsTrigger>
          <TabsTrigger value="finance">{t('Finance & Reporting')}</TabsTrigger>
          <TabsTrigger value="documents">{t('Documents')}</TabsTrigger>
          <TabsTrigger value="communication">{t('Communication & References')}</TabsTrigger>
          <TabsTrigger value="history">{t('History')}</TabsTrigger>
        </TabsList>
        <TabsContent value="overview"><OverviewTab p={p} /></TabsContent>
        <TabsContent value="knowledge"><KnowledgeTab p={p} /></TabsContent>
        <TabsContent value="tech"><TechTab p={p} /></TabsContent>
        <TabsContent value="team"><TeamTab p={p} /></TabsContent>
        <TabsContent value="finance"><FinanceTab p={p} /></TabsContent>
        <TabsContent value="documents"><DocsTab p={p} /></TabsContent>
        <TabsContent value="communication"><CommTab p={p} /></TabsContent>
        <TabsContent value="history"><HistoryTab projectId={p.id} /></TabsContent>
      </Tabs>
    </>
  )
}
