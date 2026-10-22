import { useState } from 'react'
import { LineChart, Line, ResponsiveContainer, YAxis } from 'recharts'
import { CornerDownRight, Plus, Target } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { EmptyState, ErrorBlock, LoadingBlock, PageHeader, Pill, ProgressBar, Section } from '@/components/kit'
import { useSession } from '@/contexts/SessionContext'
import { useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import type { Structure } from '@/lib/types'

interface KeyResult { id: string; title: string; unit: string; start_value: number; target_value: number; current_value: number; progress: number }
interface Objective { id: string; circle_id: string; circle_name: string; role_id: string | null; role_name: string | null; parent_id: string | null; title: string; period: string; progress: number; own_progress: number | null; key_results: KeyResult[]; project_count: number }
interface Metric { id: string; circle_id: string; circle_name: string; role_name: string | null; name: string; unit: string; direction: 'up' | 'down'; target_value: number; current_value: number; period: string; progress: number; readings: { value: number; recorded_at: string }[] }
interface GoalsData { objectives: Objective[]; metrics: Metric[] }

const NONE = 'none'

function KrRow({ kr, editable }: Readonly<{ kr: KeyResult; editable: boolean }>) {
  const { t } = useT()
  const act = useAct()
  const [value, setValue] = useState(String(kr.current_value))
  return (
    <li className="grid gap-1 py-2">
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <span>{kr.title}</span>
        <span className="flex items-center gap-2">
          <span className="font-mono text-xs text-muted-foreground">{kr.start_value} → {kr.target_value} {kr.unit}</span>
          {editable && (
            <>
              <Input className="h-7 w-20 text-right font-mono text-xs" type="number" value={value} onChange={(e) => setValue(e.target.value)} aria-label={`${t('Current value')}: ${kr.title}`} />
              <Button size="sm" variant="outline" className="h-7" disabled={Number(value) === Number(kr.current_value) || value === ''} onClick={() => act('patch', `/key-results/${kr.id}`, { current_value: Number(value) })}>{t('Check in')}</Button>
            </>
          )}
        </span>
      </div>
      <ProgressBar value={kr.progress} tone="forest" />
    </li>
  )
}

function ObjectiveNode({ o, all, depth, editable, onAddKr }: Readonly<{ o: Objective; all: Objective[]; depth: number; editable: boolean; onAddKr: (id: string) => void }>) {
  const { t } = useT()
  const children = all.filter((c) => c.parent_id === o.id)
  return (
    <div style={{ marginLeft: depth * 18 }} className="mt-3">
      <div className="paper-card p-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <div className="flex items-center gap-2">{depth > 0 && <CornerDownRight className="h-4 w-4 text-muted-foreground" aria-label={t('contributes to the objective above')} />}<h3 className="font-display text-lg font-semibold leading-tight">{o.title}</h3></div>
            <div className="mt-1 flex flex-wrap gap-1.5"><Pill>{o.circle_name}</Pill>{o.role_name && <Pill tone="forest">{o.role_name}</Pill>}{o.period && <Pill>{o.period}</Pill>}{o.project_count > 0 && <Pill tone="primary">{o.project_count} {t('projects')}</Pill>}</div>
          </div>
          <div className="w-40"><ProgressBar value={o.progress} /></div>
        </div>
        <ul className="mt-2 divide-y">{o.key_results.map((kr) => <KrRow key={kr.id} kr={kr} editable={editable} />)}</ul>
        {editable && <Button size="sm" variant="ghost" className="mt-2" onClick={() => onAddKr(o.id)}><Plus className="mr-1 h-4 w-4" />{t('Key result')}</Button>}
      </div>
      {children.map((c) => <ObjectiveNode key={c.id} o={c} all={all} depth={depth + 1} editable={editable} onAddKr={onAddKr} />)}
    </div>
  )
}

function MetricCard({ m, editable }: Readonly<{ m: Metric; editable: boolean }>) {
  const { t } = useT()
  const act = useAct()
  const [value, setValue] = useState('')
  const series = m.readings.map((r, i) => ({ i, v: Number(r.value) }))
  const good = m.progress >= 0.9
  return (
    <div className="paper-card p-4">
      <div className="flex items-start justify-between gap-2">
        <div><h3 className="font-display text-base font-semibold leading-tight">{m.name}</h3><div className="text-xs text-muted-foreground">{m.circle_name}{m.role_name ? ` · ${m.role_name}` : ''} · {t(m.period)}</div></div>
        <Pill tone={good ? 'forest' : 'ochre'}>{m.direction === 'up' ? '↑' : '↓'} {t('target')} {m.target_value}{m.unit}</Pill>
      </div>
      <div className="mt-2 flex items-end justify-between">
        <div className="font-display text-3xl font-semibold">{m.current_value}<span className="ml-1 text-sm text-muted-foreground">{m.unit}</span></div>
        <div className="h-12 w-32" aria-hidden>
          <ResponsiveContainer width="100%" height="100%"><LineChart data={series}><YAxis hide domain={['dataMin', 'dataMax']} /><Line type="monotone" dataKey="v" stroke="hsl(var(--primary))" strokeWidth={2} dot={false} /></LineChart></ResponsiveContainer>
        </div>
      </div>
      <div className="mt-2"><ProgressBar value={m.progress} tone={good ? 'forest' : 'ochre'} /></div>
      {editable && (
        <div className="mt-3 flex gap-2">
          <Input className="h-8" type="number" value={value} onChange={(e) => setValue(e.target.value)} placeholder={t('New value')} aria-label={`${t('New value')}: ${m.name}`} />
          <Button size="sm" variant="outline" disabled={value === ''} onClick={async () => { if (await act('post', `/metrics/${m.id}/readings`, { value: Number(value) })) setValue('') }}>{t('Report')}</Button>
        </div>
      )}
    </div>
  )
}

export default function Goals() {
  const { t } = useT()
  const act = useAct()
  const { isObserver } = useSession()
  const [circle, setCircle] = useState(NONE)
  const { data, isLoading, error } = useGet<GoalsData>('/goals', { circle_id: circle === NONE ? undefined : circle })
  const { data: structure } = useGet<Structure>('/structure')
  const [objDlg, setObjDlg] = useState(false)
  const [metricDlg, setMetricDlg] = useState(false)
  const [krFor, setKrFor] = useState<string | null>(null)
  const [obj, setObj] = useState({ title: '', circle_id: '', role_id: '', parent_id: '', period: '' })
  const [kr, setKr] = useState({ title: '', unit: '', start: '0', target: '100' })
  const [met, setMet] = useState({ name: '', circle_id: '', role_id: '', unit: '', direction: 'up', target: '100', current: '0', period: 'monthly' })

  const objectives = data?.objectives ?? []
  const roots = objectives.filter((o) => !o.parent_id || !objectives.some((p) => p.id === o.parent_id))
  const editable = !isObserver
  const rolesOf = (cid: string) => (structure?.roles ?? []).filter((r) => r.circle_id === cid)

  const saveObjective = async () => {
    const res = await act('post', '/objectives', { ...obj, role_id: obj.role_id || null, parent_id: obj.parent_id || null })
    if (res) { setObjDlg(false); setObj({ title: '', circle_id: '', role_id: '', parent_id: '', period: '' }) }
  }
  const saveKr = async () => {
    const res = await act('post', `/objectives/${krFor}/key-results`, { title: kr.title, unit: kr.unit, start_value: Number(kr.start), target_value: Number(kr.target), current_value: Number(kr.start) })
    if (res) { setKrFor(null); setKr({ title: '', unit: '', start: '0', target: '100' }) }
  }
  const saveMetric = async () => {
    const res = await act('post', '/metrics', { name: met.name, circle_id: met.circle_id, role_id: met.role_id || null, unit: met.unit, direction: met.direction, target_value: Number(met.target), current_value: Number(met.current), period: met.period })
    if (res) { setMetricDlg(false); setMet({ name: '', circle_id: '', role_id: '', unit: '', direction: 'up', target: '100', current: '0', period: 'monthly' }) }
  }

  return (
    <>
      <PageHeader title={t('Goals & Metrics')} subtitle={t('See how role and circle goals contribute to higher organizational objectives.')} actions={
        <Select value={circle} onValueChange={setCircle}>
          <SelectTrigger className="w-52" aria-label={t('Circle')}><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value={NONE}>{t('All circles')}</SelectItem>{(structure?.circles ?? []).map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent>
        </Select>
      } />
      {isLoading && <LoadingBlock />}
      {error && <ErrorBlock message={error.message} />}
      <Tabs defaultValue="objectives" className="space-y-4">
        <TabsList><TabsTrigger value="objectives">{t('Objectives & key results')}</TabsTrigger><TabsTrigger value="kpis">{t('KPIs')}</TabsTrigger></TabsList>
        <TabsContent value="objectives">
          <Section title={t('Objective tree')} action={editable ? <Button size="sm" onClick={() => setObjDlg(true)}><Plus className="mr-1 h-4 w-4" />{t('New objective')}</Button> : undefined}>
            {data && objectives.length === 0 && <EmptyState title={t('No objectives yet')} />}
            {roots.map((o) => <ObjectiveNode key={o.id} o={o} all={objectives} depth={0} editable={editable} onAddKr={setKrFor} />)}
          </Section>
        </TabsContent>
        <TabsContent value="kpis">
          <div className="mb-3 flex justify-end">{editable && <Button size="sm" onClick={() => setMetricDlg(true)}><Target className="mr-1 h-4 w-4" />{t('New KPI')}</Button>}</div>
          {data && data.metrics.length === 0 && <EmptyState title={t('No KPIs yet')} />}
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{data?.metrics.map((m) => <MetricCard key={m.id} m={m} editable={editable} />)}</div>
        </TabsContent>
      </Tabs>

      <Dialog open={objDlg} onOpenChange={setObjDlg}>
        <DialogContent>
          <DialogHeader><DialogTitle className="font-display text-xl">{t('New objective')}</DialogTitle><DialogDescription>{t('Link it to a higher objective to show its contribution.')}</DialogDescription></DialogHeader>
          <div className="grid gap-3">
            <div className="grid gap-1.5"><Label htmlFor="ob-t">{t('Title')}</Label><Input id="ob-t" value={obj.title} maxLength={200} onChange={(e) => setObj({ ...obj, title: e.target.value })} /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-1.5"><Label>{t('Circle')}</Label><Select value={obj.circle_id} onValueChange={(v) => setObj({ ...obj, circle_id: v, role_id: '' })}><SelectTrigger aria-label={t('Circle')}><SelectValue placeholder={t('Choose a circle.')} /></SelectTrigger><SelectContent>{(structure?.circles ?? []).map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent></Select></div>
              <div className="grid gap-1.5"><Label>{t('Role (optional)')}</Label><Select value={obj.role_id || NONE} onValueChange={(v) => setObj({ ...obj, role_id: v === NONE ? '' : v })} disabled={!obj.circle_id}><SelectTrigger aria-label={t('Role')}><SelectValue /></SelectTrigger><SelectContent><SelectItem value={NONE}>–</SelectItem>{rolesOf(obj.circle_id).map((r) => <SelectItem key={r.id} value={r.id}>{r.name}</SelectItem>)}</SelectContent></Select></div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-1.5"><Label>{t('Contributes to')}</Label><Select value={obj.parent_id || NONE} onValueChange={(v) => setObj({ ...obj, parent_id: v === NONE ? '' : v })}><SelectTrigger aria-label={t('Contributes to')}><SelectValue /></SelectTrigger><SelectContent><SelectItem value={NONE}>–</SelectItem>{objectives.map((o) => <SelectItem key={o.id} value={o.id}>{o.title}</SelectItem>)}</SelectContent></Select></div>
              <div className="grid gap-1.5"><Label htmlFor="ob-p">{t('Period')}</Label><Input id="ob-p" value={obj.period} maxLength={30} placeholder="FY2025" onChange={(e) => setObj({ ...obj, period: e.target.value })} /></div>
            </div>
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setObjDlg(false)}>{t('Cancel')}</Button><Button onClick={saveObjective} disabled={obj.title.trim().length < 3 || !obj.circle_id}>{t('Create')}</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={krFor !== null} onOpenChange={(v) => !v && setKrFor(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle className="font-display text-xl">{t('New key result')}</DialogTitle></DialogHeader>
          <div className="grid gap-3">
            <div className="grid gap-1.5"><Label htmlFor="kr-t">{t('Title')}</Label><Input id="kr-t" value={kr.title} maxLength={200} onChange={(e) => setKr({ ...kr, title: e.target.value })} /></div>
            <div className="grid grid-cols-3 gap-3">
              <div className="grid gap-1.5"><Label htmlFor="kr-s">{t('Start')}</Label><Input id="kr-s" type="number" value={kr.start} onChange={(e) => setKr({ ...kr, start: e.target.value })} /></div>
              <div className="grid gap-1.5"><Label htmlFor="kr-g">{t('Target')}</Label><Input id="kr-g" type="number" value={kr.target} onChange={(e) => setKr({ ...kr, target: e.target.value })} /></div>
              <div className="grid gap-1.5"><Label htmlFor="kr-u">{t('Unit')}</Label><Input id="kr-u" value={kr.unit} maxLength={20} onChange={(e) => setKr({ ...kr, unit: e.target.value })} /></div>
            </div>
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setKrFor(null)}>{t('Cancel')}</Button><Button onClick={saveKr} disabled={kr.title.trim().length < 3}>{t('Create')}</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={metricDlg} onOpenChange={setMetricDlg}>
        <DialogContent>
          <DialogHeader><DialogTitle className="font-display text-xl">{t('New KPI')}</DialogTitle></DialogHeader>
          <div className="grid gap-3">
            <div className="grid gap-1.5"><Label htmlFor="mt-n">{t('Name')}</Label><Input id="mt-n" value={met.name} maxLength={160} onChange={(e) => setMet({ ...met, name: e.target.value })} /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-1.5"><Label>{t('Circle')}</Label><Select value={met.circle_id} onValueChange={(v) => setMet({ ...met, circle_id: v, role_id: '' })}><SelectTrigger aria-label={t('Circle')}><SelectValue placeholder={t('Choose a circle.')} /></SelectTrigger><SelectContent>{(structure?.circles ?? []).map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent></Select></div>
              <div className="grid gap-1.5"><Label>{t('Role (optional)')}</Label><Select value={met.role_id || NONE} onValueChange={(v) => setMet({ ...met, role_id: v === NONE ? '' : v })} disabled={!met.circle_id}><SelectTrigger aria-label={t('Role')}><SelectValue /></SelectTrigger><SelectContent><SelectItem value={NONE}>–</SelectItem>{rolesOf(met.circle_id).map((r) => <SelectItem key={r.id} value={r.id}>{r.name}</SelectItem>)}</SelectContent></Select></div>
            </div>
            <div className="grid grid-cols-4 gap-3">
              <div className="grid gap-1.5"><Label htmlFor="mt-g">{t('Target')}</Label><Input id="mt-g" type="number" value={met.target} onChange={(e) => setMet({ ...met, target: e.target.value })} /></div>
              <div className="grid gap-1.5"><Label htmlFor="mt-c">{t('Current')}</Label><Input id="mt-c" type="number" value={met.current} onChange={(e) => setMet({ ...met, current: e.target.value })} /></div>
              <div className="grid gap-1.5"><Label htmlFor="mt-u">{t('Unit')}</Label><Input id="mt-u" value={met.unit} maxLength={20} onChange={(e) => setMet({ ...met, unit: e.target.value })} /></div>
              <div className="grid gap-1.5"><Label>{t('Better')}</Label><Select value={met.direction} onValueChange={(v) => setMet({ ...met, direction: v })}><SelectTrigger aria-label={t('Better')}><SelectValue /></SelectTrigger><SelectContent><SelectItem value="up">{t('higher')}</SelectItem><SelectItem value="down">{t('lower')}</SelectItem></SelectContent></Select></div>
            </div>
            <div className="grid gap-1.5"><Label>{t('Reporting period')}</Label><Select value={met.period} onValueChange={(v) => setMet({ ...met, period: v })}><SelectTrigger aria-label={t('Reporting period')}><SelectValue /></SelectTrigger><SelectContent>{['weekly', 'monthly', 'quarterly', 'yearly'].map((p) => <SelectItem key={p} value={p}>{t(p)}</SelectItem>)}</SelectContent></Select></div>
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setMetricDlg(false)}>{t('Cancel')}</Button><Button onClick={saveMetric} disabled={met.name.trim().length < 2 || !met.circle_id}>{t('Create')}</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
