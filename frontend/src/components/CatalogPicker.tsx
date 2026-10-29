import { useState } from 'react'
import { Plus, X } from 'lucide-react'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { Pill } from '@/components/kit'
import { useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import { CATALOG_KINDS, KIND_SINGULAR, exactSuggestion } from '@/lib/portfolio'
import type { CatalogKind, CatalogSuggestion } from '@/lib/portfolio-types'

export interface PickedEntry {
  id: string
  name: string
  kind: CatalogKind
}

interface Props {
  value: PickedEntry[]
  onChange: (next: PickedEntry[]) => void
  /** Restrict to one kind. Without it a kind selector is shown. */
  kind?: CatalogKind
  allowCreate?: boolean
  label?: string
}

export function CatalogPicker({ value, onChange, kind, allowCreate = true, label }: Readonly<Props>) {
  const { t } = useT()
  const act = useAct()
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const [chosenKind, setChosenKind] = useState<CatalogKind>('technology')
  const activeKind = kind ?? chosenKind
  const { data } = useGet<CatalogSuggestion[]>(open ? '/catalog/suggest' : null, { kind: kind, text })
  const suggestions = (data ?? []).filter((s) => !value.some((v) => v.id === s.id))
  const exact = exactSuggestion(data ?? [], text)

  const add = (entry: PickedEntry) => {
    onChange([...value, entry])
    setText('')
  }

  const create = async () => {
    const res = await act<{ id: string }>('post', '/catalog', { kind: activeKind, name: text.trim() })
    if (res) add({ id: res.id, name: text.trim(), kind: activeKind })
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1.5">
        {value.map((v) => (
          <Pill key={v.id} tone="primary" className="gap-1.5 pr-1">
            {v.name}
            <button type="button" onClick={() => onChange(value.filter((x) => x.id !== v.id))} aria-label={`${t('Remove')} ${v.name}`} className="rounded-full p-0.5 hover:bg-primary/20">
              <X className="h-3 w-3" aria-hidden />
            </button>
          </Pill>
        ))}
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <Button type="button" variant="outline" size="sm" className="h-7 gap-1 rounded-full px-3 text-xs">
              <Plus className="h-3 w-3" aria-hidden /> {label ?? t('Add')}
            </Button>
          </PopoverTrigger>
          <PopoverContent align="start" className="w-80 p-0">
            {!kind && (
              <div className="border-b p-2">
                <Select value={chosenKind} onValueChange={(v) => setChosenKind(v as CatalogKind)}>
                  <SelectTrigger aria-label={t('Kind')} className="h-8"><SelectValue /></SelectTrigger>
                  <SelectContent>{CATALOG_KINDS.map((k) => <SelectItem key={k.kind} value={k.kind}>{t(KIND_SINGULAR[k.kind])}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            )}
            <Command shouldFilter={false}>
              <CommandInput value={text} onValueChange={setText} placeholder={t('Search ...')} />
              <CommandList>
                <CommandEmpty>{t('No match.')}</CommandEmpty>
                <CommandGroup>
                  {suggestions
                    .filter((s) => kind || s.kind === chosenKind || text.trim() !== '')
                    .map((s) => (
                      <CommandItem key={s.id} value={s.id} onSelect={() => add({ id: s.id, name: s.name, kind: s.kind })}>
                        <span className="flex-1">{s.name}{s.matched_alias && <span className="ml-1 text-xs text-muted-foreground">({t('also known as')} {s.matched_alias})</span>}</span>
                        {!kind && <span className="text-[10px] text-muted-foreground">{t(KIND_SINGULAR[s.kind])}</span>}
                      </CommandItem>
                    ))}
                  {allowCreate && text.trim() !== '' && !exact && (
                    <CommandItem value="__create__" onSelect={create}>
                      <Plus className="mr-2 h-4 w-4" aria-hidden />
                      {t('Create “{name}”').replace('{name}', text.trim())}
                    </CommandItem>
                  )}
                </CommandGroup>
              </CommandList>
            </Command>
          </PopoverContent>
        </Popover>
      </div>
    </div>
  )
}
