import { useState } from 'react'
import { Plus, Trash2, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ComboPicker } from '@/components/ComboPicker'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState, ErrorBlock, LoadingBlock, PageHeader, Pill, Section } from '@/components/kit'
import { useSession } from '@/contexts/SessionContext'
import { useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import { CATALOG_KINDS, KIND_SINGULAR, exactSuggestion } from '@/lib/portfolio'
import type { CatalogEntry, CatalogKind, CatalogSuggestion } from '@/lib/portfolio-types'

function MergeDialog({ entry, candidates, onClose }: Readonly<{ entry: CatalogEntry | null; candidates: CatalogEntry[]; onClose: () => void }>) {
  const { t } = useT()
  const act = useAct()
  const [target, setTarget] = useState<string[]>([])
  const run = async () => {
    if (!entry || !target[0]) return
    const ok = await act('post', `/catalog/${entry.id}/merge`, { target_id: target[0] })
    if (ok) {
      setTarget([])
      onClose()
    }
  }
  return (
    <Dialog open={entry !== null} onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="font-display text-xl">{t('Merge into another entry')}: {entry?.name}</DialogTitle>
          <DialogDescription>{t('All links move to the target entry. This entry becomes an alias of it. This cannot be undone.')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-1.5">
          <Label>{t('Target entry')}</Label>
          <ComboPicker options={candidates.filter((c) => c.id !== entry?.id).map((c) => ({ id: c.id, label: c.name, hint: c.category }))} value={target} onChange={setTarget} placeholder={t('Search entries')} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>{t('Cancel')}</Button>
          <Button onClick={run} disabled={!target[0]}>{t('Merge')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function NewEntryForm({ kind }: Readonly<{ kind: CatalogKind }>) {
  const { t } = useT()
  const act = useAct()
  const [name, setName] = useState('')
  const [category, setCategory] = useState('')
  const [aliases, setAliases] = useState('')
  const { data } = useGet<CatalogSuggestion[]>(name.trim() ? '/catalog/suggest' : null, { kind, text: name.trim() })
  const similar = exactSuggestion(data ?? [], name)

  const create = async () => {
    const ok = await act('post', '/catalog', {
      kind, name: name.trim(), category: category.trim() || null,
      aliases: aliases.split(',').map((a) => a.trim()).filter(Boolean),
    })
    if (ok) {
      setName('')
      setCategory('')
      setAliases('')
    }
  }

  return (
    <div className="mt-4 rounded-xl border bg-muted/30 p-3">
      <div className="grid gap-2 md:grid-cols-[1fr_12rem_1fr_auto]">
        <Input value={name} maxLength={120} placeholder={`${t('New entry')} (${t(KIND_SINGULAR[kind])})`} aria-label={t('Name')} onChange={(e) => setName(e.target.value)} />
        <Input value={category} maxLength={60} placeholder={t('Category (optional)')} aria-label={t('Category (optional)')} onChange={(e) => setCategory(e.target.value)} />
        <Input value={aliases} maxLength={400} placeholder={`${t('Aliases')} (a, b, c)`} aria-label={t('Aliases')} onChange={(e) => setAliases(e.target.value)} />
        <Button onClick={create} disabled={!name.trim() || !!similar}><Plus className="mr-1 h-4 w-4" aria-hidden />{t('Create')}</Button>
      </div>
      {similar && <p className="mt-2 text-xs text-[hsl(var(--ochre))]" role="alert">{t('A similar entry exists already')}: {similar.name}{similar.matched_alias ? ` (${t('also known as')} ${similar.matched_alias})` : ''}</p>}
    </div>
  )
}

function AliasAdder({ entry }: Readonly<{ entry: CatalogEntry }>) {
  const { t } = useT()
  const act = useAct()
  const [value, setValue] = useState('')
  const add = async () => {
    const ok = await act('post', `/catalog/${entry.id}/aliases`, { alias: value.trim() })
    if (ok) setValue('')
  }
  return (
    <form className="flex gap-1" onSubmit={(e) => { e.preventDefault(); if (value.trim()) add() }}>
      <Input className="h-7 w-32 text-xs" value={value} maxLength={120} placeholder={t('Add alias')} aria-label={`${t('Add alias')}: ${entry.name}`} onChange={(e) => setValue(e.target.value)} />
    </form>
  )
}

export default function Catalog() {
  const { t } = useT()
  const act = useAct()
  const { isObserver, isAdmin } = useSession()
  const [kind, setKind] = useState<CatalogKind>('technology')
  const [search, setSearch] = useState('')
  const [merging, setMerging] = useState<CatalogEntry | null>(null)
  const { data, isLoading, error } = useGet<CatalogEntry[]>('/catalog', { kind, search: search.trim() || undefined })
  const { data: all } = useGet<CatalogEntry[]>('/catalog', { kind })

  return (
    <>
      <PageHeader title={t('Technologies & Competencies')} subtitle={t('Controlled vocabulary used by projects, roles and customers. Aliases make different spellings find the same entry.')} />
      <Tabs value={kind} onValueChange={(v) => { setKind(v as CatalogKind); setSearch('') }} className="mb-4">
        <TabsList className="h-auto flex-wrap justify-start">
          {CATALOG_KINDS.map((k) => <TabsTrigger key={k.kind} value={k.kind}>{t(k.label)}</TabsTrigger>)}
        </TabsList>
      </Tabs>
      <Section>
        <Input className="mb-3 max-w-sm" value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t('Search entries')} aria-label={t('Search entries')} />
        {isLoading && <LoadingBlock rows={4} />}
        {error && <ErrorBlock message={error.message} />}
        {data && data.length === 0 && <EmptyState title={t('No entries yet')} />}
        <ul className="divide-y">
          {(data ?? []).map((e) => (
            <li key={e.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2.5">
              <span className="min-w-40 font-display text-base font-semibold">{e.name}</span>
              {e.category && <Pill>{e.category}</Pill>}
              <span className="flex flex-1 flex-wrap items-center gap-1">
                {e.aliases.map((a) => (
                  <Pill key={a.id} tone="neutral" className="gap-1 pr-1">
                    {a.alias}
                    {!isObserver && <button type="button" aria-label={`${t('Remove')} ${a.alias}`} className="rounded-full p-0.5 hover:bg-muted" onClick={() => act('delete', `/catalog/aliases/${a.id}`)}><X className="h-3 w-3" /></button>}
                  </Pill>
                ))}
                {!isObserver && <AliasAdder entry={e} />}
              </span>
              <span className="text-xs text-muted-foreground">{t('Used by')} {e.usage_count}</span>
              {isAdmin && (
                <>
                  <Button size="sm" variant="outline" onClick={() => setMerging(e)}>{t('Merge')}</Button>
                  <ConfirmDialog
                    trigger={<Button size="icon" variant="ghost" aria-label={`${t('Delete')} ${e.name}`} disabled={e.usage_count > 0} title={e.usage_count > 0 ? t('Entries in use cannot be deleted - merge them instead.') : undefined}><Trash2 className="h-4 w-4" /></Button>}
                    title={t('Delete')} description={e.name} onConfirm={() => act('delete', `/catalog/${e.id}`)}
                  />
                </>
              )}
            </li>
          ))}
        </ul>
        {!isObserver && <NewEntryForm kind={kind} />}
      </Section>
      <MergeDialog entry={merging} candidates={all ?? []} onClose={() => setMerging(null)} />
    </>
  )
}
