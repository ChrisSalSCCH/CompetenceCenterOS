import { useEffect, useState } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { useSession } from '@/contexts/SessionContext'
import { useAct } from '@/lib/hooks'
import { useT } from '@/lib/i18n'

const PREFS: [string, string][] = [
  ['governance', 'Governance updates'],
  ['tasks', 'Tasks'],
  ['meetings', 'Meetings'],
  ['tensions', 'Tensions'],
]

export function ProfileDialog({ open, onOpenChange }: Readonly<{ open: boolean; onOpenChange: (v: boolean) => void }>) {
  const { t } = useT()
  const { session } = useSession()
  const act = useAct()
  const [name, setName] = useState('')
  const [title, setTitle] = useState('')
  const [skills, setSkills] = useState('')
  const [availability, setAvailability] = useState('')
  const [prefs, setPrefs] = useState<Record<string, boolean>>({})

  useEffect(() => {
    if (open && session) {
      setName(session.user.name)
      setTitle(session.user.job_title ?? '')
      setSkills((session.user.skills ?? []).join(', '))
      setAvailability(session.user.availability ?? '')
      setPrefs(session.user.notification_prefs ?? {})
    }
  }, [open, session])

  const save = async () => {
    const res = await act('patch', '/me/profile', {
      display_name: name.trim() || undefined,
      job_title: title.trim() || null,
      availability: availability.trim() || null,
      skills: skills.split(',').map((s) => s.trim()).filter(Boolean),
      notification_prefs: prefs,
    })
    if (res) onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="font-display text-xl">{t('My profile & notifications')}</DialogTitle>
          <DialogDescription>{t('Skills and availability help colleagues find the right person.')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="pf-name">{t('Name')}</Label>
            <Input id="pf-name" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="pf-title">{t('Job title')}</Label>
            <Input id="pf-title" value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="pf-skills">{t('Skills (comma separated, optional)')}</Label>
            <Input id="pf-skills" value={skills} onChange={(e) => setSkills(e.target.value)} />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="pf-av">{t('Availability (optional)')}</Label>
            <Input id="pf-av" value={availability} maxLength={120} onChange={(e) => setAvailability(e.target.value)} />
          </div>
          <fieldset className="grid gap-2 rounded-lg border p-3">
            <legend className="px-1 text-xs font-medium text-muted-foreground">{t('Notify me about')}</legend>
            {PREFS.map(([key, label]) => (
              <div key={key} className="flex items-center justify-between">
                <Label htmlFor={`pref-${key}`}>{t(label)}</Label>
                <Switch id={`pref-${key}`} checked={prefs[key] !== false} onCheckedChange={(v) => setPrefs({ ...prefs, [key]: v })} />
              </div>
            ))}
          </fieldset>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t('Cancel')}</Button>
          <Button onClick={save}>{t('Save')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
