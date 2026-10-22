import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { CalendarDays, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Checkbox } from '@/components/ui/checkbox'
import { EmptyState, ErrorBlock, LoadingBlock, PageHeader, Pill, StatusPill } from '@/components/kit'
import { useSession } from '@/contexts/SessionContext'
import { fmtDateTime, useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import type { PersonRow, Structure, TensionRow } from '@/lib/types'

interface MeetingRow {
  id: string
  title: string
  meeting_type: string
  scheduled_at: string
  duration_min: number
  status: string
  circle_id: string
  circle_name: string
  facilitator_name: string | null
  participant_count: number
}

const TYPES = [
  ['tactical', 'Tactical meeting'],
  ['governance', 'Governance meeting'],
  ['general', 'General circle meeting'],
  ['custom', 'Custom meeting'],
]

function defaultStart(): string {
  const d = new Date(Date.now() + 2 * 24 * 3600 * 1000)
  d.setMinutes(0, 0, 0)
  d.setHours(10)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:00`
}

function ScheduleDialog({ open, onOpenChange, circleId }: Readonly<{ open: boolean; onOpenChange: (v: boolean) => void; circleId?: string }>) {
  const { t } = useT()
  const act = useAct()
  const navigate = useNavigate()
  const { session } = useSession()
  const { data: structure } = useGet<Structure>(open ? '/structure' : null)
  const { data: people } = useGet<PersonRow[]>(open ? '/people' : null)
  const [circle, setCircle] = useState('')
  const [type, setType] = useState('tactical')
  const [title, setTitle] = useState('')
  const [start, setStart] = useState(defaultStart())
  const [duration, setDuration] = useState(60)
  const [facilitator, setFacilitator] = useState('')
  const [picked, setPicked] = useState<string[]>([])
  const { data: tensions } = useGet<TensionRow[]>(open && circle ? '/tensions' : null, { scope: 'circle', circle_id: circle, status: 'open' })

  useEffect(() => {
    if (open) {
      setCircle(circleId ?? structure?.circles.find((c) => !c.parent_id)?.id ?? '')
      setTitle('')
      setPicked([])
      setFacilitator(session?.user.id ?? '')
    }
  }, [open, circleId, structure, session])

  const circleName = structure?.circles.find((c) => c.id === circle)?.name ?? ''
  const save = async () => {
    const label = TYPES.find((x) => x[0] === type)?.[1] ?? 'Meeting'
    const res = await act<{ id: string }>('post', '/meetings', {
      circle_id: circle,
      title: title.trim() || `${circleName} – ${t(label)}`,
      meeting_type: type,
      scheduled_at: new Date(start).toISOString(),
      duration_min: duration,
      facilitator_id: facilitator || undefined,
      tension_ids: picked,
    })
    if (res) {
      onOpenChange(false)
      navigate(`/meetings/${res.id}`)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="font-display text-xl">{t('Schedule meeting')}</DialogTitle>
          <DialogDescription>{t('Participants default to everyone holding a role in the circle. The template creates the agenda.')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5">
              <Label>{t('Circle')}</Label>
              <Select value={circle} onValueChange={setCircle}>
                <SelectTrigger aria-label={t('Circle')}><SelectValue /></SelectTrigger>
                <SelectContent>{(structure?.circles ?? []).map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="grid gap-1.5">
              <Label>{t('Type')}</Label>
              <Select value={type} onValueChange={setType}>
                <SelectTrigger aria-label={t('Type')}><SelectValue /></SelectTrigger>
                <SelectContent>{TYPES.map(([k, l]) => <SelectItem key={k} value={k}>{t(l)}</SelectItem>)}</SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid gap-1.5"><Label htmlFor="m-title">{t('Title')}</Label><Input id="m-title" value={title} maxLength={200} placeholder={`${circleName}`} onChange={(e) => setTitle(e.target.value)} /></div>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5"><Label htmlFor="m-start">{t('Start')}</Label><Input id="m-start" type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} /></div>
            <div className="grid gap-1.5"><Label htmlFor="m-dur">{t('Duration (min)')}</Label><Input id="m-dur" type="number" min={5} max={600} value={duration} onChange={(e) => setDuration(Number(e.target.value))} /></div>
          </div>
          <div className="grid gap-1.5">
            <Label>{t('Facilitator')}</Label>
            <Select value={facilitator} onValueChange={setFacilitator}>
              <SelectTrigger aria-label={t('Facilitator')}><SelectValue /></SelectTrigger>
              <SelectContent>{(people ?? []).map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          {type === 'tactical' && (tensions ?? []).length > 0 && (
            <fieldset className="grid gap-2 rounded-lg border p-3">
              <legend className="px-1 text-xs font-medium text-muted-foreground">{t('Add open tensions to the agenda')}</legend>
              {tensions?.map((x) => (
                <label key={x.id} className="flex items-center gap-2 text-sm">
                  <Checkbox checked={picked.includes(x.id)} onCheckedChange={(v) => setPicked(v ? [...picked, x.id] : picked.filter((p) => p !== x.id))} />
                  {x.title}
                </label>
              ))}
            </fieldset>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t('Cancel')}</Button>
          <Button onClick={save} disabled={!circle}>{t('Schedule')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default function Meetings() {
  const { t, lang } = useT()
  const { isObserver } = useSession()
  const [params, setParams] = useSearchParams()
  const [scope, setScope] = useState('upcoming')
  const [dialog, setDialog] = useState(false)
  const newCircle = params.get('new') ?? undefined
  const { data, isLoading, error } = useGet<MeetingRow[]>('/meetings', { scope })

  useEffect(() => {
    if (newCircle) setDialog(true)
  }, [newCircle])

  return (
    <>
      <PageHeader
        title={t('Meetings')}
        subtitle={t('Tactical, governance and general circle meetings with reusable agendas.')}
        actions={!isObserver ? <Button onClick={() => setDialog(true)}><Plus className="mr-1 h-4 w-4" />{t('Schedule meeting')}</Button> : undefined}
      />
      <Tabs value={scope} onValueChange={setScope} className="mb-4">
        <TabsList>
          <TabsTrigger value="upcoming">{t('Upcoming')}</TabsTrigger>
          <TabsTrigger value="mine">{t('My meetings')}</TabsTrigger>
          <TabsTrigger value="past">{t('Past')}</TabsTrigger>
        </TabsList>
      </Tabs>
      {isLoading && <LoadingBlock />}
      {error && <ErrorBlock message={error.message} />}
      {data && data.length === 0 && <EmptyState title={t('No meetings here')} />}
      <div className="grid gap-3 md:grid-cols-2">
        {data?.map((m, i) => (
          <Link key={m.id} to={`/meetings/${m.id}`} className="paper-card interactive reveal block p-4" style={{ ['--i' as string]: i }}>
            <div className="flex items-start justify-between gap-2">
              <div className="font-display text-lg font-semibold leading-tight">{m.title}</div>
              <StatusPill status={m.status} />
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <CalendarDays className="h-3.5 w-3.5" aria-hidden />{fmtDateTime(m.scheduled_at, lang)} · {m.duration_min} min
              <Pill>{t(m.meeting_type)}</Pill><Pill>{m.circle_name}</Pill>
            </div>
            <div className="mt-1 text-xs text-muted-foreground">{t('Facilitator')}: {m.facilitator_name ?? '–'} · {m.participant_count} {t('participants')}</div>
          </Link>
        ))}
      </div>
      <ScheduleDialog open={dialog} onOpenChange={(v) => { setDialog(v); if (!v && newCircle) setParams({}) }} circleId={newCircle} />
    </>
  )
}
