import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router'
import { ChevronRight, History, Maximize2, Minimize2, Pencil, Plus, Search, Trash2, UnfoldVertical } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { CircleMap, OrgList, OrgTree, type Selection } from '@/components/OrgViews'
import { CircleFormDialog, RoleFormDialog, useSubmitFeedback } from '@/components/StructureForms'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Avatar, ErrorBlock, ItemList, LoadingBlock, ModePill, PageHeader, Pill } from '@/components/kit'
import { useSession } from '@/contexts/SessionContext'
import { useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import { effectiveMode, pathTo } from '@/lib/structure'
import type { Structure, SubmitResult } from '@/lib/types'

type ViewMode = 'map' | 'tree' | 'list'

export default function Organization() {
  const { t } = useT()
  const { session, isObserver, canGovern } = useSession()
  const act = useAct()
  const feedback = useSubmitFeedback()
  const [view, setView] = useState<ViewMode>('map')
  const [filter, setFilter] = useState('')
  const [asOf, setAsOf] = useState('')
  const [edit, setEdit] = useState(false)
  const [selected, setSelected] = useState<Selection | null>(null)
  const [focusId, setFocusId] = useState<string | null>(null)
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const [fullscreen, setFullscreen] = useState(false)
  const wrap = useRef<HTMLDivElement>(null)
  const [circleDlg, setCircleDlg] = useState<{ open: boolean; circleId?: string; parentId?: string }>({ open: false })
  const [roleDlg, setRoleDlg] = useState<{ open: boolean; roleId?: string; circleId?: string }>({ open: false })

  const { data, isLoading, error } = useGet<Structure>('/structure', { as_of: asOf ? `${asOf}T23:59:59Z` : undefined })

  useEffect(() => {
    const onChange = () => setFullscreen(Boolean(document.fullscreenElement))
    document.addEventListener('fullscreenchange', onChange)
    return () => document.removeEventListener('fullscreenchange', onChange)
  }, [])

  const historical = Boolean(asOf)
  const canEdit = !isObserver && !historical
  const circles = data?.circles ?? []
  const roles = data?.roles ?? []
  const selCircle = selected?.kind === 'circle' ? circles.find((c) => c.id === selected.id) : undefined
  const selRole = selected?.kind === 'role' ? roles.find((r) => r.id === selected.id) : undefined
  const crumbs = useMemo(() => (focusId ? pathTo(circles, focusId) : circles.filter((c) => !c.parent_id)), [circles, focusId])

  const toggle = (id: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const toggleFullscreen = async () => {
    if (document.fullscreenElement) await document.exitFullscreen()
    else await wrap.current?.requestFullscreen()
  }

  const remove = async (kind: 'circle' | 'role', id: string) => {
    const res = await act<SubmitResult>('delete', `/${kind === 'circle' ? 'circles' : 'roles'}/${id}`)
    if (feedback(res)) setSelected(null)
  }

  const viewProps = { data: { circles, roles }, selected, onSelect: setSelected, filter, collapsed, onToggle: toggle }

  return (
    <>
      <PageHeader
        eyebrow={session?.organization.name}
        title={t('Organization')}
        subtitle={t('Navigate from the whole organization down to a single role. Click a circle to zoom in; click it again to zoom out.')}
        actions={
          <>
            {canEdit && (
              <div className="flex items-center gap-2 rounded-full border bg-card px-3 py-1.5">
                <Pencil className="h-4 w-4 text-muted-foreground" aria-hidden />
                <Label htmlFor="edit-mode" className="text-sm">{t('Edit mode')}</Label>
                <Switch id="edit-mode" checked={edit} onCheckedChange={setEdit} />
              </div>
            )}
          </>
        }
      />

      <div ref={wrap} className="reveal bg-background/0 data-[fs=true]:overflow-auto data-[fs=true]:bg-background data-[fs=true]:p-4" data-fs={fullscreen} style={{ ['--i' as string]: 1 }}>
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Tabs value={view} onValueChange={(v) => setView(v as ViewMode)}>
            <TabsList>
              <TabsTrigger value="map">{t('Map')}</TabsTrigger>
              <TabsTrigger value="tree">{t('Tree')}</TabsTrigger>
              <TabsTrigger value="list">{t('List')}</TabsTrigger>
            </TabsList>
          </Tabs>
          <div className="relative min-w-[200px] flex-1 md:max-w-sm">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input className="pl-9" value={filter} onChange={(e) => setFilter(e.target.value)} placeholder={t('Filter circles, roles, responsibilities, people')} aria-label={t('Filter')} />
          </div>
          <div className="flex items-center gap-1.5 rounded-lg border bg-card px-2 py-1">
            <History className="h-4 w-4 text-muted-foreground" aria-hidden />
            <Label htmlFor="as-of" className="text-xs text-muted-foreground">{t('View as of')}</Label>
            <input id="as-of" type="date" value={asOf} max={new Date().toISOString().slice(0, 10)} onChange={(e) => setAsOf(e.target.value)} className="bg-transparent text-sm focus:outline-none" />
            {asOf && <Button variant="ghost" size="sm" className="h-6 px-2" onClick={() => setAsOf('')}>{t('Today')}</Button>}
          </div>
          <div className="ml-auto flex items-center gap-1">
            <Button variant="outline" size="sm" onClick={() => setCollapsed(new Set(circles.map((c) => c.id)))}><UnfoldVertical className="mr-1 h-4 w-4" />{t('Collapse all')}</Button>
            <Button variant="outline" size="sm" onClick={() => setCollapsed(new Set())}>{t('Expand all')}</Button>
            <Button variant="outline" size="icon" aria-label={t('Fullscreen')} onClick={toggleFullscreen}>{fullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}</Button>
          </div>
        </div>

        {historical && (
          <div className="mb-3 flex items-center gap-2 rounded-lg border border-[hsl(var(--ochre)/0.4)] bg-[hsl(var(--ochre)/0.1)] px-3 py-2 text-sm">
            <History className="h-4 w-4" aria-hidden />
            {t('Historical view: structure as it was on')} <strong>{asOf}</strong>. {t('Role holders are not versioned, and editing is disabled.')}
          </div>
        )}

        <nav aria-label={t('Breadcrumb')} className="mb-2 flex flex-wrap items-center gap-1 text-sm">
          <button type="button" className="rounded px-1 text-muted-foreground hover:text-foreground" onClick={() => setFocusId(null)}>{t('All')}</button>
          {focusId && crumbs.map((c) => (
            <span key={c.id} className="flex items-center gap-1">
              <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
              <button type="button" className="rounded px-1 font-medium hover:text-primary" onClick={() => setFocusId(c.id)}>{c.name}</button>
            </span>
          ))}
        </nav>

        {isLoading && <LoadingBlock rows={5} />}
        {error && <ErrorBlock message={error.message} />}
        {data && (
          <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
            <div className={fullscreen ? 'h-[82vh]' : 'h-[66vh] min-h-[460px]'}>
              {view === 'map' && <CircleMap {...viewProps} focusId={focusId} onFocus={setFocusId} />}
              {view === 'tree' && <OrgTree {...viewProps} />}
              {view === 'list' && <div className="h-full overflow-auto"><OrgList {...viewProps} /></div>}
            </div>

            <aside className="paper-card h-fit max-h-[66vh] overflow-y-auto p-4" aria-live="polite">
              {!selCircle && !selRole && (
                <div className="text-sm text-muted-foreground">
                  <p className="font-display text-lg text-foreground">{t('Select a circle or role')}</p>
                  <p className="mt-1">{t('Details appear here. Roles with a dashed outline have no assigned person.')}</p>
                  {canEdit && edit && circles.length > 0 && (
                    <Button className="mt-4" size="sm" onClick={() => setCircleDlg({ open: true, parentId: circles.find((c) => !c.parent_id)?.id })}><Plus className="mr-1 h-4 w-4" />{t('New circle')}</Button>
                  )}
                </div>
              )}
              {selCircle && (
                <div className="space-y-3 pop-in">
                  <div>
                    <div className="font-mono-label text-muted-foreground">{t('Circle')}</div>
                    <h3 className="font-display text-2xl font-semibold">{selCircle.name}</h3>
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      <ModePill mode={effectiveMode(circles, selCircle.id, session?.organization.default_governance_mode ?? 'consent')} />
                      <Pill>{roles.filter((r) => r.circle_id === selCircle.id).length} {t('roles')}</Pill>
                      <Pill>{circles.filter((c) => c.parent_id === selCircle.id).length} {t('subcircles')}</Pill>
                    </div>
                  </div>
                  <p className="text-sm">{selCircle.purpose}</p>
                  <div>
                    <div className="font-mono-label mb-1 text-muted-foreground">{t('Accountabilities')}</div>
                    <ItemList items={selCircle.accountabilities.slice(0, 4)} empty={t('None defined')} />
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button asChild size="sm"><Link to={`/organization/circles/${selCircle.id}`}>{t('Open circle')}</Link></Button>
                    <Button size="sm" variant="outline" onClick={() => toggle(selCircle.id)}>{collapsed.has(selCircle.id) ? t('Expand') : t('Collapse')}</Button>
                  </div>
                  {canEdit && edit && (
                    <div className="flex flex-wrap gap-2 border-t pt-3">
                      <Button size="sm" variant="secondary" onClick={() => setCircleDlg({ open: true, circleId: selCircle.id })}><Pencil className="mr-1 h-4 w-4" />{t('Edit')}</Button>
                      <Button size="sm" variant="secondary" onClick={() => setCircleDlg({ open: true, parentId: selCircle.id })}><Plus className="mr-1 h-4 w-4" />{t('Subcircle')}</Button>
                      <Button size="sm" variant="secondary" onClick={() => setRoleDlg({ open: true, circleId: selCircle.id })}><Plus className="mr-1 h-4 w-4" />{t('Role')}</Button>
                      {selCircle.parent_id && (
                        <ConfirmDialog
                          trigger={<Button size="sm" variant="ghost" className="text-destructive"><Trash2 className="mr-1 h-4 w-4" />{t('Remove')}</Button>}
                          title={t('Remove this circle?')}
                          description={t('Only empty circles can be removed. Depending on the governance workflow this creates a proposal.')}
                          onConfirm={() => remove('circle', selCircle.id)}
                        />
                      )}
                    </div>
                  )}
                  {canEdit && !edit && canGovern(selCircle.id) && <p className="text-xs text-muted-foreground">{t('You hold governance authority here. Switch on Edit mode to change the structure.')}</p>}
                </div>
              )}
              {selRole && (
                <div className="space-y-3 pop-in">
                  <div>
                    <div className="font-mono-label text-muted-foreground">{t('Role')} · {circles.find((c) => c.id === selRole.circle_id)?.name}</div>
                    <h3 className="font-display text-2xl font-semibold">{selRole.name}</h3>
                  </div>
                  <p className="text-sm">{selRole.purpose}</p>
                  <div className="space-y-1.5">
                    <div className="font-mono-label text-muted-foreground">{t('Role holders')}</div>
                    {selRole.holders.length === 0 && <Pill tone="ochre">{t('unfilled')}</Pill>}
                    {selRole.holders.map((h) => (
                      <Link key={h.assignment_id} to={`/people/${h.user_id}`} className="flex items-center gap-2 text-sm hover:text-primary">
                        <Avatar name={h.name} color={h.avatar_color} size={24} />
                        {h.name}{h.focus && <span className="text-xs text-muted-foreground">· {h.focus}</span>}
                      </Link>
                    ))}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button asChild size="sm"><Link to={`/organization/roles/${selRole.id}`}>{t('Open role')}</Link></Button>
                  </div>
                  {canEdit && edit && (
                    <div className="flex flex-wrap gap-2 border-t pt-3">
                      <Button size="sm" variant="secondary" onClick={() => setRoleDlg({ open: true, roleId: selRole.id })}><Pencil className="mr-1 h-4 w-4" />{t('Edit')}</Button>
                      <ConfirmDialog
                        trigger={<Button size="sm" variant="ghost" className="text-destructive"><Trash2 className="mr-1 h-4 w-4" />{t('Remove')}</Button>}
                        title={t('Remove this role?')}
                        description={t('Assignments end. Depending on the governance workflow this creates a proposal.')}
                        onConfirm={() => remove('role', selRole.id)}
                      />
                    </div>
                  )}
                </div>
              )}
            </aside>
          </div>
        )}
      </div>

      <CircleFormDialog open={circleDlg.open} onOpenChange={(v) => setCircleDlg((s) => ({ ...s, open: v }))} circles={circles} circle={circles.find((c) => c.id === circleDlg.circleId)} parentId={circleDlg.parentId} />
      <RoleFormDialog open={roleDlg.open} onOpenChange={(v) => setRoleDlg((s) => ({ ...s, open: v }))} circles={circles} role={roles.find((r) => r.id === roleDlg.roleId)} circleId={roleDlg.circleId} />
    </>
  )
}
