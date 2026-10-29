import { DocumentsPanel } from '@/components/DocumentsPanel'
import type { ProjectDetailData } from '@/lib/portfolio-types'

/** Project documents: links and uploaded files with versions and confidentiality levels. */
export function DocsTab({ p }: Readonly<{ p: ProjectDetailData }>) {
  return <DocumentsPanel entityType="project" entityId={p.id} />
}
