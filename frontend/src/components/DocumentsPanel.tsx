import { useEffect, useState } from 'react'
import { ExternalLink, FileText, Link2, Lock, Plus, Trash2, Upload } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { ComboPicker } from '@/components/ComboPicker'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState, Pill, Section, type Tone } from '@/components/kit'
import api from '@/lib/api'
import { fmtDate, useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import type { DocCategory, DocConfidentiality, DocEntity, DocKind, DocumentItem, DocumentList } from '@/lib/sales-types'
import type { PersonRow } from '@/lib/types'
import { fmtBytes, uploadFile } from '@/lib/upload'

const CATEGORIES: DocCategory[] = ['contract', 'proposal', 'nda', 'report', 'technical', 'other']
const LEVELS: DocConfidentiality[] = ['internal', 'restricted', 'confidential']
const LEVEL_TONE: Record<DocConfidentiality, Tone> = { internal: 'neutral', restricted: 'ochre', confidential: 'danger' }
const URL_RE = /^https:\/\/\S{3,}$/

interface Target {
  entityType: DocEntity
  entityId: string
}

async function openDocument(id: string, version?: number): Promise<void> {
  const res = await api.get<{ url: string }>(`/documents/${id}/download`, { params: version ? { version } : undefined })
  window.open(res.data.url, '_blank', 'noopener,noreferrer')
}

function AddDialog({ target, open, onOpenChange, versionOf }: Readonly<{ target: Target; open: boolean; onOpenChange: (v: boolean) => void; versionOf: DocumentItem | null }>) {
  const { t } = useT()
  const act = useAct()
  const { data: people } = useGet<PersonRow[]>(open ? '/people' : null)
  const [kind, setKind] = useState<DocKind>('file')
  const [file, setFile] = useState<File | null>(null)
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [category, setCategory] = useState<DocCategory>('other')
  const [level, setLevel] = useState<DocConfidentiality>('internal')
  const [description, setDescription] = useState('')
  const [comment, setComment] = useState('')
  const [access, setAccess] = useState<string[]>([])
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (open) {
      setKind('file')
      setFile(null)
      setName('')
      setUrl('')
      setCategory('other')
      setLevel('internal')
      setDescription('')
      setComment('')
      setAccess([])
    }
  }, [open])

  const urlOk = URL_RE.test(url.trim())
  const sourceOk = kind === 'file' ? file !== null : urlOk
  const canSave = sourceOk && (versionOf !== null || name.trim().length > 0) && !busy

  const save = async () => {
    setBusy(true)
    try {
      const stored = kind === 'file' && file ? await uploadFile(file, 'documents') : null
      const source = {
        storage_kind: kind,
        url: kind === 'file' ? null : url.trim(),
        file_key: stored?.file_key ?? null,
        filename: file?.name ?? null,
        content_type: stored?.content_type ?? null,
        size_bytes: stored?.size ?? null,
      }
      const res = versionOf
        ? await act('post', `/documents/${versionOf.id}/versions`, { ...source, comment: comment.trim() || null })
        : await act('post', '/documents', {
          entity_type: target.entityType, entity_id: target.entityId, name: name.trim(), category, confidentiality: level, description,
          access_user_ids: level === 'internal' ? [] : access, ...source,
        })
      if (res) onOpenChange(false)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : t('Upload failed'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="font-display text-xl">{versionOf ? t('New version') : t('Add document')}</DialogTitle>
          {versionOf && <DialogDescription>{versionOf.name}</DialogDescription>}
        </DialogHeader>
        <div className="grid gap-3">
          <Tabs value={kind} onValueChange={(v) => setKind(v as DocKind)}>
            <TabsList>
              <TabsTrigger value="file"><Upload className="mr-1 h-4 w-4" aria-hidden />{t('Upload file')}</TabsTrigger>
              <TabsTrigger value="link"><Link2 className="mr-1 h-4 w-4" aria-hidden />{t('Link')}</TabsTrigger>
              <TabsTrigger value="sharepoint">SharePoint</TabsTrigger>
            </TabsList>
          </Tabs>
          {kind === 'file' ? (
            <div className="grid gap-1.5">
              <Label htmlFor="doc-file">{t('File')} *</Label>
              <Input id="doc-file" type="file" onChange={(e) => { const f = e.target.files?.[0] ?? null; setFile(f); if (f && !name && !versionOf) setName(f.name) }} />
              <p className="text-xs text-muted-foreground">{t('The file goes straight to secure storage. Size and type are checked by the server.')}</p>
            </div>
          ) : (
            <div className="grid gap-1.5">
              <Label htmlFor="doc-url">{t('Link')} *</Label>
              <Input id="doc-url" value={url} maxLength={1000} placeholder="https://" aria-invalid={url !== '' && !urlOk} onChange={(e) => setUrl(e.target.value)} />
            </div>
          )}
          {versionOf ? (
            <div className="grid gap-1.5"><Label htmlFor="doc-comment">{t('What changed?')}</Label><Input id="doc-comment" value={comment} maxLength={500} onChange={(e) => setComment(e.target.value)} /></div>
          ) : (
            <>
              <div className="grid gap-1.5"><Label htmlFor="doc-name">{t('Name')} *</Label><Input id="doc-name" value={name} maxLength={200} onChange={(e) => setName(e.target.value)} /></div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="grid gap-1.5">
                  <Label>{t('Category')}</Label>
                  <Select value={category} onValueChange={(v) => setCategory(v as DocCategory)}>
                    <SelectTrigger aria-label={t('Category')}><SelectValue /></SelectTrigger>
                    <SelectContent>{CATEGORIES.map((c) => <SelectItem key={c} value={c}>{t(c)}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <div className="grid gap-1.5">
                  <Label>{t('Confidentiality')}</Label>
                  <Select value={level} onValueChange={(v) => setLevel(v as DocConfidentiality)}>
                    <SelectTrigger aria-label={t('Confidentiality')}><SelectValue /></SelectTrigger>
                    <SelectContent>{LEVELS.map((c) => <SelectItem key={c} value={c}>{t(c)}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
              </div>
              {level !== 'internal' && (
                <div className="grid gap-1.5">
                  <Label>{t('People with access')}</Label>
                  <ComboPicker multiple options={(people ?? []).map((p) => ({ id: p.id, label: p.name, hint: p.job_title }))} value={access} onChange={setAccess} placeholder={t('Choose people')} />
                  <p className="text-xs text-muted-foreground">{level === 'restricted' ? t('Restricted: the team of this record, administrators and the people listed.') : t('Confidential: administrators, you and the people listed.')}</p>
                </div>
              )}
              <div className="grid gap-1.5"><Label htmlFor="doc-desc">{t('Description')}</Label><Textarea id="doc-desc" rows={2} value={description} maxLength={1000} onChange={(e) => setDescription(e.target.value)} /></div>
            </>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t('Cancel')}</Button>
          <Button onClick={save} disabled={!canSave}>{busy ? t('Uploading ...') : t('Save')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function DocumentsPanel({ entityType, entityId }: Readonly<{ entityType: DocEntity; entityId: string }>) {
  const { t, lang } = useT()
  const act = useAct()
  const { data } = useGet<DocumentList>('/documents', { entity_type: entityType, entity_id: entityId })
  const [adding, setAdding] = useState(false)
  const [versionOf, setVersionOf] = useState<DocumentItem | null>(null)
  const target: Target = { entityType, entityId }
  const canEdit = data?.can_edit ?? false

  return (
    <Section title={t('Documents')} action={canEdit ? <Button size="sm" onClick={() => { setVersionOf(null); setAdding(true) }}><Plus className="mr-1 h-4 w-4" aria-hidden />{t('Add document')}</Button> : undefined}>
      {data && data.items.length === 0 && <EmptyState title={t('No documents yet')} hint={t('Upload a file or link a document.')} />}
      <ul className="divide-y">
        {(data?.items ?? []).map((d) => (
          <li key={d.id} className="flex flex-wrap items-center gap-2 py-2.5">
            <FileText className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
            <div className="min-w-0 flex-1">
              <button type="button" className="flex items-center gap-1.5 truncate text-left text-sm font-medium text-primary hover:underline" onClick={() => openDocument(d.id)}>
                {d.name}<ExternalLink className="h-3 w-3" aria-hidden />
              </button>
              <div className="text-xs text-muted-foreground">
                v{d.current_version} · {d.is_link ? t('Link') : fmtBytes(d.size_bytes)} · {fmtDate(d.created_at, lang)}{d.author_name && ` · ${d.author_name}`}
              </div>
            </div>
            <Pill>{t(d.category)}</Pill>
            <Pill tone={LEVEL_TONE[d.confidentiality]}>{d.confidentiality !== 'internal' && <Lock className="h-3 w-3" aria-hidden />}{t(d.confidentiality)}</Pill>
            {canEdit && <Button variant="ghost" size="sm" onClick={() => { setVersionOf(d); setAdding(true) }}>{t('New version')}</Button>}
            {canEdit && (
              <ConfirmDialog
                trigger={<Button variant="ghost" size="icon" aria-label={t('Remove')}><Trash2 className="h-4 w-4" /></Button>}
                title={t('Remove')} description={d.name} onConfirm={() => act('delete', `/documents/${d.id}`)}
              />
            )}
          </li>
        ))}
      </ul>
      {data && data.hidden_count > 0 && <p className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground"><Lock className="h-3 w-3" aria-hidden />{data.hidden_count} {t('documents are hidden because you have no access')}</p>}
      <AddDialog target={target} open={adding} onOpenChange={setAdding} versionOf={versionOf} />
    </Section>
  )
}
