import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { Pill, Section } from '@/components/kit'
import { fmtDate, useAct } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import type { Communication, ProjectDetailData } from '@/lib/portfolio-types'

const EMPTY: Communication = {
  reference_allowed: false, allow_name: false, allow_logo: false, allow_images: false, allow_description: false, allow_results: false,
  approved_by_name: null, approved_at: null, notes: '',
}

type FlagKey = 'allow_name' | 'allow_logo' | 'allow_images' | 'allow_description' | 'allow_results'
const FLAGS: { key: FlagKey; label: string }[] = [
  { key: 'allow_name', label: 'Customer name' },
  { key: 'allow_logo', label: 'Logo' },
  { key: 'allow_images', label: 'Images' },
  { key: 'allow_description', label: 'Project description' },
  { key: 'allow_results', label: 'Results and figures' },
]

export function CommTab({ p }: Readonly<{ p: ProjectDetailData }>) {
  const { t, lang } = useT()
  const act = useAct()
  const [form, setForm] = useState<Communication>(p.communication ?? EMPTY)
  const sig = JSON.stringify(p.communication)
  useEffect(() => setForm(p.communication ?? EMPTY), [sig]) // eslint-disable-line react-hooks/exhaustive-deps
  const canEdit = p.can_manage

  const save = () => act('put', `/portfolio/${p.id}/communication`, {
    ...form,
    approved_by_name: form.approved_by_name?.trim() || null,
    approved_at: form.approved_at || null,
  })

  return (
    <Section title={t('Reference permission')}>
      <p className="mb-4 text-sm text-muted-foreground">{t('Only content that is explicitly released may be used externally.')}</p>
      <Label className="mb-4 flex items-center gap-3 text-base font-medium">
        <Switch checked={form.reference_allowed} disabled={!canEdit} onCheckedChange={(v) => setForm({ ...form, reference_allowed: v })} />
        {t('This project may be used as a reference')}
      </Label>
      {form.reference_allowed && (
        <div className="space-y-4">
          <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {FLAGS.map((f) => (
              <li key={f.key} className="flex items-center justify-between gap-2 rounded-lg border p-3">
                <Label htmlFor={`flag-${f.key}`} className="text-sm">{t(f.label)}</Label>
                {canEdit ? <Switch id={`flag-${f.key}`} checked={form[f.key]} onCheckedChange={(v) => setForm({ ...form, [f.key]: v })} /> : <Pill tone={form[f.key] ? 'forest' : 'neutral'}>{t(form[f.key] ? 'Released' : 'Not released')}</Pill>}
              </li>
            ))}
          </ul>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="grid gap-1.5"><Label htmlFor="cm-by">{t('Approved by (customer side)')}</Label><Input id="cm-by" value={form.approved_by_name ?? ''} maxLength={160} disabled={!canEdit} onChange={(e) => setForm({ ...form, approved_by_name: e.target.value })} /></div>
            <div className="grid gap-1.5"><Label htmlFor="cm-at">{t('Approved on')}</Label><Input id="cm-at" type="date" value={form.approved_at ?? ''} disabled={!canEdit} onChange={(e) => setForm({ ...form, approved_at: e.target.value })} /></div>
          </div>
          <div className="grid gap-1.5"><Label htmlFor="cm-notes">{t('Notes')}</Label><Textarea id="cm-notes" rows={2} maxLength={3000} value={form.notes} disabled={!canEdit} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></div>
          {!canEdit && form.approved_at && <p className="text-xs text-muted-foreground">{t('Approved on')} {fmtDate(form.approved_at, lang)}</p>}
        </div>
      )}
      {canEdit && <Button className="mt-4" onClick={save}>{t('Save')}</Button>}
    </Section>
  )
}
