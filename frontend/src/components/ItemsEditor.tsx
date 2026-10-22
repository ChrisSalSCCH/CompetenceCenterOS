import { Plus, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useT } from '@/lib/i18n'
import type { Item } from '@/lib/types'

export interface EditItem {
  text: string
  level?: Item['level']
}

export function toEditItems(items: Item[] | undefined): EditItem[] {
  return (items ?? []).map((i) => ({ text: i.text, level: i.level }))
}

export function cleanItems(items: EditItem[], withLevel = false): { text: string; level?: Item['level'] }[] {
  return items
    .map((i) => ({ ...i, text: i.text.trim() }))
    .filter((i) => i.text.length > 0)
    .map((i) => (withLevel ? { text: i.text, level: i.level ?? 'decides' } : { text: i.text }))
}

const LEVELS: Item['level'][] = ['decides', 'consents', 'consulted', 'informed']

export function ItemsEditor({
  label,
  hint,
  items,
  onChange,
  withLevel = false,
  placeholder,
}: Readonly<{ label: string; hint?: string; items: EditItem[]; onChange: (v: EditItem[]) => void; withLevel?: boolean; placeholder?: string }>) {
  const { t } = useT()
  const update = (idx: number, patch: Partial<EditItem>) => onChange(items.map((it, i) => (i === idx ? { ...it, ...patch } : it)))
  return (
    <fieldset className="grid gap-2">
      <legend className="mb-1 text-sm font-medium">{label}</legend>
      {hint && <p className="-mt-1 text-xs text-muted-foreground">{hint}</p>}
      {items.map((it, idx) => (
        <div key={idx} className="flex items-center gap-2">
          <Input
            value={it.text}
            maxLength={600}
            placeholder={placeholder}
            aria-label={`${label} ${idx + 1}`}
            onChange={(e) => update(idx, { text: e.target.value })}
          />
          {withLevel && (
            <Select value={it.level ?? 'decides'} onValueChange={(v) => update(idx, { level: v as Item['level'] })}>
              <SelectTrigger className="w-32 shrink-0" aria-label={t('Authority level')}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {LEVELS.map((l) => (
                  <SelectItem key={l} value={l as string}>
                    {t(l as string)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          <Button type="button" variant="ghost" size="icon" aria-label={t('Remove')} onClick={() => onChange(items.filter((_, i) => i !== idx))}>
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      ))}
      <Button type="button" variant="outline" size="sm" className="w-fit" onClick={() => onChange([...items, { text: '', level: 'decides' }])}>
        <Plus className="mr-1 h-4 w-4" />
        {t('Add')}
      </Button>
    </fieldset>
  )
}
