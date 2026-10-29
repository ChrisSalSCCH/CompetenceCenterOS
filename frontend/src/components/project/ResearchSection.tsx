import { useState } from 'react'
import { ExternalLink, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState, Pill, Section, type Tone } from '@/components/kit'
import { fmtDate, useAct } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import type { ProjectDetailData, ProjectResult, WorkPackage } from '@/lib/portfolio-types'

const WP_STATUS: WorkPackage['status'][] = ['planned', 'active', 'done']
const RESULT_STATUS: ProjectResult['status'][] = ['planned', 'achieved', 'partial', 'missed']
const RESULT_KINDS: ProjectResult['kind'][] = ['deliverable', 'kpi', 'publication', 'prototype', 'other']
const RESULT_TONE: Record<ProjectResult['status'], Tone> = { planned: 'neutral', achieved: 'forest', partial: 'ochre', missed: 'danger' }

export function ResearchSection({ p }: Readonly<{ p: ProjectDetailData }>) {
  const { t, lang } = useT()
  const act = useAct()
  const base = `/portfolio/${p.id}`
  const [wp, setWp] = useState({ code: '', title: '' })
  const [res, setRes] = useState({ title: '', kind: 'deliverable' as ProjectResult['kind'], planned: '', shown: '', unit: '' })

  const addWp = async () => {
    const ok = await act('post', `${base}/work-packages`, { code: wp.code.trim(), title: wp.title.trim() })
    if (ok) setWp({ code: '', title: '' })
  }
  const addResult = async () => {
    const ok = await act('post', `${base}/results`, {
      title: res.title.trim(), kind: res.kind, planned_value: res.planned.trim() || null, demonstrated_value: res.shown.trim() || null, unit: res.unit.trim() || null,
      status: res.shown.trim() ? 'achieved' : 'planned',
    })
    if (ok) setRes({ title: '', kind: 'deliverable', planned: '', shown: '', unit: '' })
  }

  return (
    <div className="space-y-4">
      <Section title={t('Work packages')}>
        {p.work_packages.length === 0 && <EmptyState title={t('Work packages')} />}
        <ul className="divide-y">
          {p.work_packages.map((w) => (
            <li key={w.id} className="flex flex-wrap items-center gap-2 py-2">
              <span className="w-12 font-mono text-xs text-muted-foreground">{w.code}</span>
              <span className="min-w-40 flex-1 text-sm font-medium">{w.title}</span>
              <span className="text-xs text-muted-foreground">{fmtDate(w.start_date, lang)} – {fmtDate(w.end_date, lang)}</span>
              {p.can_manage ? (
                <Select value={w.status} onValueChange={(v) => act('patch', `${base}/work-packages/${w.id}`, { status: v })}>
                  <SelectTrigger className="h-8 w-32" aria-label={t('Status')}><SelectValue /></SelectTrigger>
                  <SelectContent>{WP_STATUS.map((s) => <SelectItem key={s} value={s}>{t(s)}</SelectItem>)}</SelectContent>
                </Select>
              ) : <Pill>{t(w.status)}</Pill>}
              {p.can_manage && (
                <ConfirmDialog
                  trigger={<Button variant="ghost" size="icon" aria-label={t('Remove')}><Trash2 className="h-4 w-4" /></Button>}
                  title={t('Remove')} description={w.title} onConfirm={() => act('delete', `${base}/work-packages/${w.id}`)}
                />
              )}
            </li>
          ))}
        </ul>
        {p.can_manage && (
          <div className="mt-3 flex flex-wrap gap-2">
            <Input className="w-24" value={wp.code} maxLength={20} placeholder={t('Code')} aria-label={t('Code')} onChange={(e) => setWp({ ...wp, code: e.target.value })} />
            <Input className="min-w-48 flex-1" value={wp.title} maxLength={200} placeholder={t('Title')} aria-label={t('Title')} onChange={(e) => setWp({ ...wp, title: e.target.value })} />
            <Button onClick={addWp} disabled={!wp.title.trim()}>{t('Add work package')}</Button>
          </div>
        )}
      </Section>

      <Section title={t('Planned vs. demonstrated')} className="overflow-x-auto">
        {p.results.length === 0 && <EmptyState title={t('Results')} />}
        {p.results.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow><TableHead>{t('Results')}</TableHead><TableHead>{t('Planned')}</TableHead><TableHead>{t('Demonstrated')}</TableHead><TableHead>{t('Status')}</TableHead><TableHead className="w-10" /></TableRow>
            </TableHeader>
            <TableBody>
              {p.results.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="text-sm"><span className="font-medium">{r.title}</span><div className="text-xs text-muted-foreground">{t(r.kind)}</div></TableCell>
                  <TableCell className="text-sm">{r.planned_value ?? '–'} {r.unit}</TableCell>
                  <TableCell className="text-sm">
                    {r.demonstrated_value ?? '–'} {r.unit}
                    {r.evidence_url && <a href={r.evidence_url} target="_blank" rel="noreferrer noopener" className="ml-1 inline-flex align-middle text-primary" aria-label={t('Evidence link')}><ExternalLink className="h-3 w-3" /></a>}
                  </TableCell>
                  <TableCell>
                    {p.can_manage ? (
                      <Select value={r.status} onValueChange={(v) => act('patch', `${base}/results/${r.id}`, { status: v })}>
                        <SelectTrigger className="h-8 w-32" aria-label={t('Status')}><SelectValue /></SelectTrigger>
                        <SelectContent>{RESULT_STATUS.map((s) => <SelectItem key={s} value={s}>{t(s)}</SelectItem>)}</SelectContent>
                      </Select>
                    ) : <Pill tone={RESULT_TONE[r.status]}>{t(r.status)}</Pill>}
                  </TableCell>
                  <TableCell>
                    {p.can_manage && (
                      <ConfirmDialog
                        trigger={<Button variant="ghost" size="icon" aria-label={t('Remove')}><Trash2 className="h-4 w-4" /></Button>}
                        title={t('Remove')} description={r.title} onConfirm={() => act('delete', `${base}/results/${r.id}`)}
                      />
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        {p.can_manage && (
          <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_9rem_6rem_6rem_5rem_auto]">
            <Input value={res.title} maxLength={200} placeholder={t('Title')} aria-label={t('Title')} onChange={(e) => setRes({ ...res, title: e.target.value })} />
            <Select value={res.kind} onValueChange={(v) => setRes({ ...res, kind: v as ProjectResult['kind'] })}>
              <SelectTrigger aria-label={t('Kind')}><SelectValue /></SelectTrigger>
              <SelectContent>{RESULT_KINDS.map((k) => <SelectItem key={k} value={k}>{t(k)}</SelectItem>)}</SelectContent>
            </Select>
            <Input value={res.planned} maxLength={200} placeholder={t('Planned')} aria-label={t('Planned')} onChange={(e) => setRes({ ...res, planned: e.target.value })} />
            <Input value={res.shown} maxLength={200} placeholder={t('Demonstrated')} aria-label={t('Demonstrated')} onChange={(e) => setRes({ ...res, shown: e.target.value })} />
            <Input value={res.unit} maxLength={30} placeholder={t('Unit')} aria-label={t('Unit')} onChange={(e) => setRes({ ...res, unit: e.target.value })} />
            <Button onClick={addResult} disabled={!res.title.trim()}>{t('Add result')}</Button>
          </div>
        )}
      </Section>
    </div>
  )
}
