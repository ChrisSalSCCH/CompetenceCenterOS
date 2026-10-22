import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { ArrowRight, Sparkles } from 'lucide-react'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import type { SearchHit } from '@/lib/types'
import { Pill } from '@/components/kit'

const TYPE_LABEL: Record<string, string> = {
  circle: 'Circle', role: 'Role', person: 'Person', proposal: 'Proposal', project: 'Project', task: 'Task', meeting: 'Meeting', tension: 'Tension',
}

export function SearchPalette({ open, onOpenChange }: Readonly<{ open: boolean; onOpenChange: (v: boolean) => void }>) {
  const { t } = useT()
  const navigate = useNavigate()
  const [text, setText] = useState('')
  const [debounced, setDebounced] = useState('')

  useEffect(() => {
    const id = setTimeout(() => setDebounced(text.trim()), 220)
    return () => clearTimeout(id)
  }, [text])

  const { data, isFetching } = useGet<{ results: SearchHit[] }>(open && debounced.length >= 2 ? '/search' : null, { q: debounced })
  const results = data?.results ?? []

  const go = (to: string) => {
    onOpenChange(false)
    setText('')
    navigate(to)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="overflow-hidden p-0 sm:max-w-2xl">
        <DialogTitle className="sr-only">{t('Search')}</DialogTitle>
        <DialogDescription className="sr-only">{t('Search across circles, roles, people, responsibilities, proposals, projects, tasks and meetings')}</DialogDescription>
        <Command shouldFilter={false} className="[&_[cmdk-input-wrapper]]:px-3">
          <CommandInput value={text} onValueChange={setText} placeholder={t('Try: project acquisition, personnel development, who decides ...')} />
          <CommandList className="max-h-[60vh]">
            {debounced.length >= 2 && (
              <CommandGroup heading={t('Circle Intelligence')}>
                <CommandItem value={`ask-${debounced}`} onSelect={() => go(`/assistant?q=${encodeURIComponent(debounced)}`)}>
                  <Sparkles className="mr-2 h-4 w-4 text-primary" />
                  {t('Ask the assistant')}: “{debounced}”
                </CommandItem>
                <CommandItem value={`all-${debounced}`} onSelect={() => go(`/search?q=${encodeURIComponent(debounced)}`)}>
                  <ArrowRight className="mr-2 h-4 w-4" />
                  {t('Show all results')}
                </CommandItem>
              </CommandGroup>
            )}
            {debounced.length >= 2 && !isFetching && results.length === 0 && <CommandEmpty>{t('Nothing found.')}</CommandEmpty>}
            {results.length > 0 && (
              <CommandGroup heading={t('Results')}>
                {results.slice(0, 12).map((r) => (
                  <CommandItem key={`${r.type}-${r.id}`} value={`${r.type}-${r.id}`} onSelect={() => go(r.link)} className="items-start">
                    <Pill tone="neutral" className="mr-2 mt-0.5">{t(TYPE_LABEL[r.type] ?? r.type)}</Pill>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium">{r.title}</span>
                      <span className="block truncate text-xs text-muted-foreground">{r.snippet && r.snippet.field !== 'name' ? `${r.snippet.field}: ${r.snippet.text}` : r.subtitle}</span>
                    </span>
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
            {debounced.length < 2 && (
              <CommandGroup heading={t('Go to')}>
                {[['/organization', 'Organization'], ['/governance', 'Governance'], ['/work', 'Projects & Tasks'], ['/meetings', 'Meetings'], ['/assistant', 'AI Assistant']].map(([to, label]) => (
                  <CommandItem key={to} value={to} onSelect={() => go(to)}>
                    {t(label)}
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
          </CommandList>
        </Command>
      </DialogContent>
    </Dialog>
  )
}
