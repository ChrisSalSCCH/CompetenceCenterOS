import { useState } from 'react'
import { Check, ChevronsUpDown, X } from 'lucide-react'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Button } from '@/components/ui/button'
import { Pill } from '@/components/kit'
import { useT } from '@/lib/i18n'
import { cn } from '@/lib/utils'

export interface ComboOption {
  id: string
  label: string
  hint?: string | null
}

interface Props {
  options: ComboOption[]
  value: string[]
  onChange: (next: string[]) => void
  multiple?: boolean
  placeholder: string
  ariaLabel?: string
}

export function ComboPicker({ options, value, onChange, multiple = false, placeholder, ariaLabel }: Readonly<Props>) {
  const { t } = useT()
  const [open, setOpen] = useState(false)
  const selected = options.filter((o) => value.includes(o.id))

  const toggle = (id: string) => {
    if (multiple) {
      onChange(value.includes(id) ? value.filter((v) => v !== id) : [...value, id])
    } else {
      onChange([id])
      setOpen(false)
    }
  }

  return (
    <div className="space-y-1.5">
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button type="button" variant="outline" role="combobox" aria-expanded={open} aria-label={ariaLabel ?? placeholder} className="w-full justify-between font-normal">
            <span className={cn('truncate', selected.length === 0 && 'text-muted-foreground')}>
              {!multiple && selected[0] ? selected[0].label : placeholder}
            </span>
            <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" aria-hidden />
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-[var(--radix-popover-trigger-width)] min-w-64 p-0">
          <Command>
            <CommandInput placeholder={t('Search ...')} />
            <CommandList>
              <CommandEmpty>{t('No match.')}</CommandEmpty>
              <CommandGroup>
                {options.map((o) => (
                  <CommandItem key={o.id} value={`${o.label} ${o.hint ?? ''}`} onSelect={() => toggle(o.id)}>
                    <Check className={cn('mr-2 h-4 w-4', value.includes(o.id) ? 'opacity-100' : 'opacity-0')} aria-hidden />
                    <span className="flex-1 truncate">{o.label}</span>
                    {o.hint && <span className="ml-2 truncate text-[11px] text-muted-foreground">{o.hint}</span>}
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
      {multiple && selected.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {selected.map((o) => (
            <Pill key={o.id} tone="primary" className="gap-1.5 pr-1">
              {o.label}
              <button type="button" onClick={() => toggle(o.id)} aria-label={`${t('Remove')} ${o.label}`} className="rounded-full p-0.5 hover:bg-primary/20">
                <X className="h-3 w-3" aria-hidden />
              </button>
            </Pill>
          ))}
        </div>
      )}
    </div>
  )
}
