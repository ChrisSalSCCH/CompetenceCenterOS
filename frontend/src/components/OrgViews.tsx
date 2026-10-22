import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent as RPointerEvent } from 'react'
import { hierarchy, pack, tree } from 'd3-hierarchy'
import { ChevronDown, ChevronRight, Minus, Plus, ZoomOut } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Avatar, Pill } from '@/components/kit'
import { useT } from '@/lib/i18n'
import { matchesFilter, roleSearchFields } from '@/lib/structure'
import type { CircleNode, RoleNode } from '@/lib/types'

export interface OrgData {
  circles: CircleNode[]
  roles: RoleNode[]
}

export interface Selection {
  kind: 'circle' | 'role'
  id: string
}

interface Datum {
  id: string
  name: string
  kind: 'circle' | 'role'
  filled: boolean
  value?: number
  children?: Datum[]
  holders: string[]
  searchText: string
}

function leafValue(childCount: number, isCollapsed: boolean): number {
  if (childCount > 0) return 0
  return isCollapsed ? 3 : 1.5
}

function nodeFill(isCircle: boolean, filled: boolean, circleAlpha: number): string {
  if (isCircle) return `hsl(var(--primary) / ${circleAlpha})`
  return filled ? 'hsl(var(--forest) / 0.2)' : 'hsl(var(--card))'
}

function nodeStroke(isCircle: boolean, filled: boolean, selected: boolean): string {
  if (selected) return 'hsl(var(--foreground))'
  if (isCircle) return 'hsl(var(--primary) / 0.55)'
  return filled ? 'hsl(var(--forest))' : 'hsl(var(--ochre))'
}

function buildTree(data: OrgData, collapsed: Set<string>, withRoles: boolean): Datum | null {
  const roots = data.circles.filter((c) => c.parent_id === null)
  const make = (c: CircleNode): Datum => {
    const isCollapsed = collapsed.has(c.id)
    const subs = isCollapsed ? [] : data.circles.filter((x) => x.parent_id === c.id).map(make)
    const roles: Datum[] =
      isCollapsed || !withRoles
        ? []
        : data.roles
            .filter((r) => r.circle_id === c.id)
            .map((r) => ({ id: r.id, name: r.name, kind: 'role' as const, filled: r.holders.length > 0, value: 1, holders: r.holders.map((h) => h.name), searchText: roleSearchFields(r).join(' ') }))
    const children = [...subs, ...roles]
    return {
      id: c.id, name: c.name, kind: 'circle', filled: true, holders: [],
      searchText: [c.name, c.purpose, ...c.accountabilities.map((a) => a.text), ...c.domains.map((d) => d.text)].join(' '),
      children: children.length > 0 ? children : undefined,
      value: leafValue(children.length, isCollapsed),
    }
  }
  if (roots.length === 0) return null
  if (roots.length === 1) return make(roots[0])
  return { id: 'virtual', name: 'Organization', kind: 'circle', filled: true, holders: [], searchText: '', children: roots.map(make) }
}

function matchedIds(root: Datum, filter: string): Set<string> | null {
  if (!filter.trim()) return null
  const hit = new Set<string>()
  const walk = (d: Datum, ancestors: string[]) => {
    const own = matchesFilter(filter, d.name, d.searchText)
    if (own) {
      hit.add(d.id)
      ancestors.forEach((a) => hit.add(a))
    }
    d.children?.forEach((c) => walk(c, [...ancestors, d.id]))
  }
  walk(root, [])
  return hit
}

function clip(text: string, maxChars: number): string {
  if (maxChars < 4) return ''
  return text.length > maxChars ? `${text.slice(0, Math.max(1, maxChars - 1))}…` : text
}

interface ViewProps {
  data: OrgData
  selected: Selection | null
  onSelect: (s: Selection) => void
  filter: string
  collapsed: Set<string>
  onToggle: (circleId: string) => void
}

export function CircleMap({ data, selected, onSelect, filter, collapsed, focusId, onFocus }: Readonly<ViewProps & { focusId: string | null; onFocus: (id: string | null) => void }>) {
  const { t } = useT()
  const wrap = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState(800)
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const drag = useRef<{ x: number; y: number } | null>(null)

  const root = useMemo(() => buildTree(data, collapsed, true), [data, collapsed])
  const nodes = useMemo(() => {
    if (!root) return []
    const h = hierarchy(root).sum((d) => d.value ?? 0)
    pack<Datum>().size([1000, 1000]).padding(12)(h)
    return h.descendants()
  }, [root])
  const hits = useMemo(() => (root ? matchedIds(root, filter) : null), [root, filter])
  const focus = nodes.find((n) => n.data.id === focusId) ?? nodes[0]

  const target = useMemo(() => {
    if (!focus) return { x: 500, y: 500, w: 1000 }
    const w = (focus.r * 2.12) / zoom
    return { x: focus.x + pan.x, y: focus.y + pan.y, w }
  }, [focus, zoom, pan])
  const [view, setView] = useState(target)
  const viewRef = useRef(view)
  viewRef.current = view

  useEffect(() => {
    let raf = 0
    const step = () => {
      const v = viewRef.current
      const k = 0.2
      const next = { x: v.x + (target.x - v.x) * k, y: v.y + (target.y - v.y) * k, w: v.w + (target.w - v.w) * k }
      const done = Math.abs(next.x - target.x) < 0.05 && Math.abs(next.y - target.y) < 0.05 && Math.abs(next.w - target.w) < 0.05
      setView(done ? target : next)
      if (!done) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [target])

  useEffect(() => {
    setZoom(1)
    setPan({ x: 0, y: 0 })
  }, [focusId])

  useEffect(() => {
    const el = wrap.current
    if (!el) return
    const measure = () => setSize(Math.min(el.clientWidth, el.clientHeight) || 600)
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    measure()
    return () => ro.disconnect()
  }, [])

  const unit = view.w / Math.max(size, 1) // viewBox units per screen pixel
  const onWheel = (e: React.WheelEvent) => setZoom((z) => Math.max(0.6, Math.min(6, z * (e.deltaY < 0 ? 1.15 : 0.87))))
  const onDown = (e: RPointerEvent<SVGSVGElement>) => {
    drag.current = { x: e.clientX, y: e.clientY }
  }
  const onMove = (e: RPointerEvent<SVGSVGElement>) => {
    if (!drag.current) return
    const dx = (e.clientX - drag.current.x) * unit
    const dy = (e.clientY - drag.current.y) * unit
    drag.current = { x: e.clientX, y: e.clientY }
    setPan((p) => ({ x: p.x - dx, y: p.y - dy }))
  }
  const onKey = (e: KeyboardEvent, fn: () => void) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      fn()
    }
  }

  const activate = (n: (typeof nodes)[number]) => {
    onSelect({ kind: n.data.kind, id: n.data.id })
    if (n.data.kind === 'circle') {
      if (n.data.id === focus?.data.id) onFocus(n.parent?.data.id ?? null)
      else onFocus(n.data.id)
    } else if (n.parent) {
      onFocus(n.parent.data.id)
    }
  }

  if (!root) return <p className="p-6 text-sm text-muted-foreground">{t('No circles yet.')}</p>

  return (
    <div ref={wrap} className="relative h-full min-h-[440px] w-full overflow-hidden rounded-xl bg-card/60">
      <svg
        className="h-full w-full touch-none select-none"
        viewBox={`${view.x - view.w / 2} ${view.y - view.w / 2} ${view.w} ${view.w}`}
        preserveAspectRatio="xMidYMid meet"
        role="group"
        aria-label={t('Organization map')}
        onWheel={onWheel}
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={() => (drag.current = null)}
        onPointerLeave={() => (drag.current = null)}
      >
        {nodes.map((n) => {
          const d = n.data
          const sr = n.r / unit // radius in screen pixels
          if (sr < 3) return null
          const dim = hits !== null && !hits.has(d.id)
          const isSel = selected?.id === d.id
          const isCircle = d.kind === 'circle'
          const depthAlpha = Math.min(0.06 + n.depth * 0.05, 0.22)
          const fill = nodeFill(isCircle, d.filled, depthAlpha)
          const stroke = nodeStroke(isCircle, d.filled, false)
          const fs = (isCircle ? 14 : 11.5) * unit
          const showLabel = isCircle ? sr > 46 : sr > 24
          const interactive = n.parent?.data.id === focus?.data.id || d.id === focus?.data.id
          const maxChars = Math.floor((n.r * 1.7) / (fs * 0.56))
          return (
            <g key={d.id} opacity={dim ? 0.22 : 1}>
              <circle
                className="map-circle"
                cx={n.x} cy={n.y} r={n.r}
                fill={fill}
                stroke={isSel ? 'hsl(var(--foreground))' : stroke}
                strokeWidth={(isSel ? 3 : 1.6) * unit}
                strokeDasharray={!isCircle && !d.filled ? `${5 * unit} ${4 * unit}` : undefined}
                role="button"
                tabIndex={interactive ? 0 : -1}
                aria-label={`${isCircle ? t('Circle') : t('Role')}: ${d.name}`}
                onClick={(e) => {
                  e.stopPropagation()
                  activate(n)
                }}
                onKeyDown={(e) => onKey(e, () => activate(n))}
              />
              {showLabel && (
                <text
                  x={n.x}
                  y={isCircle && n.children ? n.y - n.r + fs * 1.45 : n.y + fs * 0.35}
                  textAnchor="middle"
                  fontSize={fs}
                  fontWeight={isCircle ? 600 : 500}
                  fill="hsl(var(--foreground))"
                  stroke="hsl(var(--card))"
                  strokeWidth={fs * 0.28}
                  paintOrder="stroke"
                  pointerEvents="none"
                  fontFamily={isCircle ? 'var(--font-display)' : 'var(--font-body)'}
                >
                  {clip(d.name, maxChars)}
                </text>
              )}
              {!isCircle && sr > 52 && d.holders.length > 0 && (
                <text x={n.x} y={n.y + fs * 1.8} textAnchor="middle" fontSize={fs * 0.8} fill="hsl(var(--muted-foreground))" pointerEvents="none">
                  {clip(d.holders.join(', '), maxChars)}
                </text>
              )}
            </g>
          )
        })}
      </svg>
      <div className="absolute bottom-3 right-3 flex flex-col gap-1 rounded-lg border bg-card p-1 shadow">
        <Button size="icon" variant="ghost" className="h-8 w-8" aria-label={t('Zoom in')} onClick={() => setZoom((z) => Math.min(6, z * 1.3))}><Plus className="h-4 w-4" /></Button>
        <Button size="icon" variant="ghost" className="h-8 w-8" aria-label={t('Zoom out')} onClick={() => setZoom((z) => Math.max(0.6, z / 1.3))}><Minus className="h-4 w-4" /></Button>
        <Button size="icon" variant="ghost" className="h-8 w-8" aria-label={t('Reset view')} onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); onFocus(null) }}><ZoomOut className="h-4 w-4" /></Button>
      </div>
      <div className="pointer-events-none absolute bottom-3 left-3 flex items-center gap-3 rounded-lg border bg-card/90 px-3 py-1.5 text-[11px] text-muted-foreground">
        <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-full border border-[hsl(var(--forest))] bg-[hsl(var(--forest)/0.25)]" />{t('Filled role')}</span>
        <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-full border border-dashed border-[hsl(var(--ochre))]" />{t('Unfilled role')}</span>
      </div>
    </div>
  )
}

export function OrgTree({ data, selected, onSelect, filter, collapsed, onToggle }: Readonly<ViewProps>) {
  const { t } = useT()
  const root = useMemo(() => buildTree(data, collapsed, true), [data, collapsed])
  const layout = useMemo(() => {
    if (!root) return null
    const h = hierarchy(root)
    tree<Datum>().nodeSize([34, 250])(h)
    const all = h.descendants()
    const xs = all.map((n) => n.x ?? 0)
    const ys = all.map((n) => n.y ?? 0)
    return { all, links: h.links(), minX: Math.min(...xs), maxX: Math.max(...xs), maxY: Math.max(...ys) }
  }, [root])
  const hits = useMemo(() => (root ? matchedIds(root, filter) : null), [root, filter])
  if (!layout) return <p className="p-6 text-sm text-muted-foreground">{t('No circles yet.')}</p>
  const height = layout.maxX - layout.minX + 60
  const width = layout.maxY + 270
  return (
    <div className="h-full min-h-[440px] overflow-auto rounded-xl bg-card/60 p-2">
      <svg width={width} height={height} role="group" aria-label={t('Organization tree')}>
        <g transform={`translate(20 ${30 - layout.minX})`}>
          {layout.links.map((l) => {
            const sx = l.source.y ?? 0, sy = l.source.x ?? 0, tx = l.target.y ?? 0, ty = l.target.x ?? 0
            const mx = (sx + tx) / 2
            return <path key={`${l.source.data.id}-${l.target.data.id}`} d={`M${sx + 200},${sy}C${mx + 100},${sy} ${mx + 100},${ty} ${tx},${ty}`} fill="none" stroke="hsl(var(--border))" strokeWidth={1.5} />
          })}
          {layout.all.map((n) => {
            const d = n.data
            const isCircle = d.kind === 'circle'
            const dim = hits !== null && !hits.has(d.id)
            const isSel = selected?.id === d.id
            const collapsedNode = isCircle && collapsed.has(d.id)
            return (
              <g key={d.id} transform={`translate(${n.y ?? 0} ${(n.x ?? 0) - 13})`} opacity={dim ? 0.25 : 1}>
                <rect
                  width={200} height={26} rx={13}
                  fill={nodeFill(isCircle, d.filled, 0.12)}
                  stroke={nodeStroke(isCircle, d.filled, isSel)}
                  strokeWidth={isSel ? 2.5 : 1.3}
                  strokeDasharray={!isCircle && !d.filled ? '4 3' : undefined}
                  className="cursor-pointer"
                  role="button"
                  tabIndex={0}
                  aria-label={`${isCircle ? t('Circle') : t('Role')}: ${d.name}`}
                  onClick={() => onSelect({ kind: d.kind, id: d.id })}
                  onKeyDown={(e) => { if (e.key === 'Enter') onSelect({ kind: d.kind, id: d.id }) }}
                />
                <text x={12} y={17} fontSize={12.5} fontWeight={isCircle ? 600 : 500} fill="hsl(var(--foreground))" pointerEvents="none">{clip(d.name, 26)}</text>
                {isCircle && d.id !== 'virtual' && (
                  <g className="cursor-pointer" onClick={() => onToggle(d.id)} role="button" tabIndex={0} aria-label={collapsedNode ? t('Expand') : t('Collapse')} onKeyDown={(e) => { if (e.key === 'Enter') onToggle(d.id) }}>
                    <circle cx={186} cy={13} r={8} fill="hsl(var(--card))" stroke="hsl(var(--primary))" />
                    <text x={186} y={17} fontSize={12} textAnchor="middle" fill="hsl(var(--primary))" pointerEvents="none">{collapsedNode ? '+' : '−'}</text>
                  </g>
                )}
              </g>
            )
          })}
        </g>
      </svg>
    </div>
  )
}

export function OrgList({ data, selected, onSelect, filter, collapsed, onToggle }: Readonly<ViewProps>) {
  const { t } = useT()
  const roots = data.circles.filter((c) => c.parent_id === null)
  const renderCircle = (c: CircleNode, depth: number) => {
    const roles = data.roles.filter((r) => r.circle_id === c.id)
    const subs = data.circles.filter((x) => x.parent_id === c.id)
    const open = !collapsed.has(c.id)
    const roleHit = roles.filter((r) => matchesFilter(filter, ...roleSearchFields(r)))
    const selfHit = matchesFilter(filter, c.name, c.purpose, ...c.accountabilities.map((a) => a.text))
    return (
      <li key={c.id}>
        <div className="flex items-center gap-1" style={{ paddingLeft: depth * 20 }}>
          <Button variant="ghost" size="icon" className="h-7 w-7" aria-label={open ? t('Collapse') : t('Expand')} onClick={() => onToggle(c.id)}>
            {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </Button>
          <button type="button" onClick={() => onSelect({ kind: 'circle', id: c.id })} className={`flex-1 rounded-lg px-2 py-1.5 text-left font-display text-base font-semibold transition-colors hover:bg-muted ${selected?.id === c.id ? 'bg-primary/10' : ''} ${selfHit ? '' : 'opacity-50'}`}>
            {c.name}
            <span className="ml-2 font-sans text-xs font-normal text-muted-foreground">{roles.length} {t('roles')}</span>
          </button>
        </div>
        {open && (
          <ul>
            {roleHit.map((r) => (
              <li key={r.id} style={{ paddingLeft: depth * 20 + 36 }}>
                <button type="button" onClick={() => onSelect({ kind: 'role', id: r.id })} className={`flex w-full items-center gap-2 rounded-lg px-2 py-1 text-left text-sm transition-colors hover:bg-muted ${selected?.id === r.id ? 'bg-primary/10' : ''}`}>
                  <span className="flex-1">{r.name}</span>
                  {r.holders.length === 0 ? <Pill tone="ochre">{t('unfilled')}</Pill> : <span className="flex -space-x-2">{r.holders.map((h) => <Avatar key={h.assignment_id} name={h.name} color={h.avatar_color} size={22} />)}</span>}
                </button>
              </li>
            ))}
            {subs.map((s) => renderCircle(s, depth + 1))}
          </ul>
        )}
      </li>
    )
  }
  return <ul className="space-y-1 rounded-xl bg-card/60 p-3">{roots.map((r) => renderCircle(r, 0))}</ul>
}
