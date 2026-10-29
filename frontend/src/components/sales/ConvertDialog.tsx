import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ComboPicker } from '@/components/ComboPicker'
import { ErrorBlock, InfoNotice, LoadingBlock, Pill, type Tone } from '@/components/kit'
import { useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import type { PortfolioRow } from '@/lib/portfolio-types'
import type { ConvertAction, ConvertPreview, OppDetail } from '@/lib/sales-types'

const FIELD_LABEL: Record<string, string> = {
  name: 'Name', description: 'Description', category: 'Category', start_date: 'Start', due_date: 'End', effort_days: 'Effort (days)', budget_total: 'Budget', classification: 'Classification',
}
const ACTION_TONE: Record<ConvertAction, Tone> = { set: 'forest', fill: 'primary', conflict: 'ochre' }
const ACTION_LABEL: Record<ConvertAction, string> = { set: 'will be set', fill: 'fills an empty field', conflict: 'differs' }
const WARNING_LABEL: Record<string, string> = {
  no_approved_proposal: 'There is no approved proposal. Work packages and budget cannot be taken over.',
  circle_required: 'Choose the circle that will own the new project.',
  project_has_other_source: 'This project already originates from another opportunity.',
}

interface Circles {
  circles: { id: string; name: string }[]
}

function show(value: string | number | null): string {
  return value === null || value === '' ? '–' : String(value)
}

export function ConvertDialog({ opp, open, onOpenChange }: Readonly<{ opp: OppDetail; open: boolean; onOpenChange: (v: boolean) => void }>) {
  const { t } = useT()
  const act = useAct()
  const navigate = useNavigate()
  const [mode, setMode] = useState<'new' | 'existing'>('new')
  const [existing, setExisting] = useState<string[]>([])
  const [circle, setCircle] = useState('')
  const [overwrite, setOverwrite] = useState<string[]>([])
  const projectId = mode === 'existing' ? existing[0] : undefined
  const { data, isLoading, error } = useGet<ConvertPreview>(open ? `/commercial/opportunities/${opp.id}/convert-preview` : null, { project_id: projectId })
  const { data: projects } = useGet<PortfolioRow[]>(open ? '/portfolio' : null)
  const { data: structure } = useGet<Circles>(open ? '/structure' : null)

  useEffect(() => {
    if (open) {
      setMode('new')
      setExisting([])
      setCircle(opp.circle_id ?? '')
      setOverwrite([])
    }
  }, [open, opp.circle_id])

  const needsCircle = mode === 'new' && !opp.circle_id
  const missingProject = mode === 'existing' && existing.length === 0
  const canConvert = Boolean(data?.can_convert) && !missingProject && (!needsCircle || circle !== '')

  const toggle = (field: string, on: boolean) => setOverwrite((o) => (on ? [...o, field] : o.filter((x) => x !== field)))

  const run = async () => {
    const res = await act<{ project_id: string }>('post', `/commercial/opportunities/${opp.id}/convert`, {
      project_id: projectId ?? null, circle_id: needsCircle ? circle : null, overwrite_fields: overwrite,
    })
    if (!res) return
    onOpenChange(false)
    navigate(`/projects/${res.project_id}`)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="font-display text-xl">{t('Create project from opportunity')}</DialogTitle>
          <DialogDescription>{opp.number} · {opp.title}</DialogDescription>
        </DialogHeader>
        <RadioGroup value={mode} onValueChange={(v) => setMode(v as 'new' | 'existing')} className="grid gap-2 sm:grid-cols-2">
          <Label className="flex items-center gap-2 rounded-lg border p-3 font-normal"><RadioGroupItem value="new" />{t('Create a new customer project')}</Label>
          <Label className="flex items-center gap-2 rounded-lg border p-3 font-normal"><RadioGroupItem value="existing" />{t('Fill an existing project')}</Label>
        </RadioGroup>
        {mode === 'existing' && (
          <ComboPicker options={(projects ?? []).map((p) => ({ id: p.id, label: p.name, hint: p.project_no }))} value={existing} onChange={(v) => setExisting(v.slice(-1))} placeholder={t('Choose project')} />
        )}
        {needsCircle && (
          <div className="grid gap-1.5">
            <Label>{t('Circle')} *</Label>
            <Select value={circle} onValueChange={setCircle}>
              <SelectTrigger aria-label={t('Circle')}><SelectValue placeholder={t('Choose circle')} /></SelectTrigger>
              <SelectContent>{(structure?.circles ?? []).map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
        )}
        {isLoading && <LoadingBlock rows={3} />}
        {error && <ErrorBlock message={error.message} />}
        {data?.blocked_reason === 'OPPORTUNITY_NOT_WON' && <InfoNotice>{t('Only a won opportunity can be turned into a project.')}</InfoNotice>}
        {data?.blocked_reason === 'ALREADY_CONVERTED' && <InfoNotice>{t('This opportunity was already turned into a project.')}</InfoNotice>}
        {data && data.warnings.filter((w) => w !== 'circle_required').map((w) => <p key={w} className="text-xs text-[hsl(var(--ochre))]">{t(WARNING_LABEL[w] ?? w)}</p>)}
        {data && (
          <>
            <div className="overflow-x-auto rounded-lg border">
              <table className="w-full text-sm">
                <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
                  <tr><th className="p-2">{t('Field')}</th><th className="p-2">{t('Current')}</th><th className="p-2">{t('From opportunity')}</th><th className="p-2" /></tr>
                </thead>
                <tbody>
                  {data.fields.map((r) => (
                    <tr key={r.field} className="border-t">
                      <td className="p-2 font-medium">{t(FIELD_LABEL[r.field] ?? r.field)}</td>
                      <td className="p-2 text-muted-foreground">{show(r.current)}</td>
                      <td className="p-2">{show(r.new)}</td>
                      <td className="p-2">
                        {r.action === 'conflict' ? (
                          <Label className="flex items-center gap-1.5 text-xs font-normal"><Checkbox checked={overwrite.includes(r.field)} onCheckedChange={(v) => toggle(r.field, v === true)} />{t('Overwrite')}</Label>
                        ) : (
                          <Pill tone={ACTION_TONE[r.action]}>{t(ACTION_LABEL[r.action])}</Pill>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-xs text-muted-foreground">
              {t('Will be linked')}: {t('work packages')} {data.will_link.work_packages ?? 0} · {t('milestones')} {data.will_link.milestones ?? 0} · {t('catalog entries')} {data.will_link.catalog_entries ?? 0} · {t('contacts')} {data.will_link.contacts ?? 0} · {t('team')} {data.will_link.team ?? 0} · {t('contracts')} {data.will_link.contracts ?? 0}
            </p>
          </>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t('Cancel')}</Button>
          <Button onClick={run} disabled={!canConvert}>{mode === 'new' ? t('Create project') : t('Fill project')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
