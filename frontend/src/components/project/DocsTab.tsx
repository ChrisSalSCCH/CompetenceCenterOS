import { useState } from 'react'
import { ExternalLink, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState, Section } from '@/components/kit'
import { useAct } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import type { ProjectDetailData } from '@/lib/portfolio-types'

export function DocsTab({ p }: Readonly<{ p: ProjectDetailData }>) {
  const { t } = useT()
  const act = useAct()
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const urlValid = /^https?:\/\/\S{3,}$/.test(url.trim())

  const add = async () => {
    const ok = await act('post', `/portfolio/${p.id}/documents`, { name: name.trim(), url: url.trim() })
    if (ok) {
      setName('')
      setUrl('')
    }
  }

  return (
    <Section title={t('Documents')}>
      <p className="mb-3 text-xs text-muted-foreground">{t('Documents are stored as links in this version.')}</p>
      {p.documents.length === 0 && <EmptyState title={t('No documents linked')} />}
      <ul className="divide-y">
        {p.documents.map((d) => (
          <li key={d.id} className="flex items-center gap-2 py-2">
            <a href={d.url} target="_blank" rel="noreferrer noopener" className="flex flex-1 items-center gap-1.5 truncate text-sm font-medium text-primary hover:underline">
              {d.name}<ExternalLink className="h-3 w-3" aria-hidden />
            </a>
            {p.can_manage && (
              <ConfirmDialog
                trigger={<Button variant="ghost" size="icon" aria-label={t('Remove')}><Trash2 className="h-4 w-4" /></Button>}
                title={t('Remove')} description={d.name} onConfirm={() => act('delete', `/portfolio/${p.id}/documents/${d.id}`)}
              />
            )}
          </li>
        ))}
      </ul>
      {p.can_manage && (
        <div className="mt-3 flex flex-wrap gap-2">
          <Input className="w-48" value={name} maxLength={200} placeholder={t('Name')} aria-label={t('Name')} onChange={(e) => setName(e.target.value)} />
          <Input className="min-w-56 flex-1" value={url} maxLength={1000} placeholder={t('Link (https://...)')} aria-label={t('Link (https://...)')} aria-invalid={url !== '' && !urlValid} onChange={(e) => setUrl(e.target.value)} />
          <Button onClick={add} disabled={!name.trim() || !urlValid}>{t('Link a document')}</Button>
        </div>
      )}
    </Section>
  )
}
