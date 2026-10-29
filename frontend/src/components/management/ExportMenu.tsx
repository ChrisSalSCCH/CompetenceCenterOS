import { useState } from 'react'
import { Download } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { useT } from '@/lib/i18n'
import { EXPORT_LABEL, EXPORT_SETS, downloadExport, type ExportFormat, type ExportSet } from '@/lib/management'

export function ExportMenu({ sets = EXPORT_SETS }: Readonly<{ sets?: readonly ExportSet[] }>) {
  const { t } = useT()
  const [busy, setBusy] = useState(false)

  const run = async (set: ExportSet, format: ExportFormat) => {
    setBusy(true)
    try {
      await downloadExport(set, format)
      toast.success(t('Export created'))
    } catch {
      // The API client already showed the error.
    } finally {
      setBusy(false)
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" disabled={busy}><Download className="mr-1 h-4 w-4" aria-hidden />{t('Export')}</Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel>{t('Exports follow your permissions')}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {sets.map((s) => (
          <div key={s} className="flex items-center justify-between gap-2 px-2 py-1 text-sm">
            <span>{t(EXPORT_LABEL[s])}</span>
            <span className="flex gap-1">
              <DropdownMenuItem className="h-6 px-2 text-xs" onSelect={() => void run(s, 'csv')}>CSV</DropdownMenuItem>
              <DropdownMenuItem className="h-6 px-2 text-xs" onSelect={() => void run(s, 'xlsx')}>XLSX</DropdownMenuItem>
            </span>
          </div>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
