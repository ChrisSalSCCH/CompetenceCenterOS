import { useEffect, useMemo, useState, type CSSProperties } from 'react'
import './network.css'

export type NetworkVariant = 'hero' | 'compact'

interface Pt {
  x: number
  y: number
}

interface LayerSpec {
  key: 'far' | 'mid' | 'near'
  seed: number
  cols: number
  rows: number
  jitter: number
  radius: number
  edgeWidth: number
  edgeOpacity: number
  nodeOpacity: number
  accentShare: number
  wanderers: number
  pulses: number
  travelers: number
  halos: number
}

interface VariantSpec {
  width: number
  height: number
  bleed: number
  layers: LayerSpec[]
}

interface Wander {
  dx: number
  dy: number
  dur: number
  begin: number
}

interface Timing {
  dur: number
  delay: number
}

interface LayerModel {
  spec: LayerSpec
  nodes: Pt[]
  edges: [number, number][]
  wander: Map<number, Wander>
  accents: number[]
  halos: Map<number, Timing>
  pulses: Map<number, Timing>
  travelers: Map<number, Timing>
}

const GREEN = '#01F000'

const SPECS: Record<NetworkVariant, VariantSpec> = {
  hero: {
    width: 1000,
    height: 800,
    bleed: 60,
    layers: [
      { key: 'far', seed: 11, cols: 13, rows: 10, jitter: 0.85, radius: 1.1, edgeWidth: 0.5, edgeOpacity: 0.12, nodeOpacity: 0.35, accentShare: 0, wanderers: 0, pulses: 6, travelers: 0, halos: 0 },
      { key: 'mid', seed: 23, cols: 9, rows: 7, jitter: 0.8, radius: 1.6, edgeWidth: 0.6, edgeOpacity: 0.2, nodeOpacity: 0.55, accentShare: 0.1, wanderers: 3, pulses: 8, travelers: 4, halos: 3 },
      { key: 'near', seed: 37, cols: 6, rows: 5, jitter: 0.7, radius: 2.2, edgeWidth: 0.8, edgeOpacity: 0.3, nodeOpacity: 0.8, accentShare: 0.14, wanderers: 4, pulses: 6, travelers: 4, halos: 4 },
    ],
  },
  compact: {
    width: 800,
    height: 200,
    bleed: 30,
    layers: [
      { key: 'mid', seed: 5, cols: 14, rows: 4, jitter: 0.8, radius: 1.4, edgeWidth: 0.6, edgeOpacity: 0.22, nodeOpacity: 0.55, accentShare: 0.08, wanderers: 0, pulses: 0, travelers: 0, halos: 0 },
      { key: 'near', seed: 9, cols: 8, rows: 3, jitter: 0.7, radius: 2, edgeWidth: 0.8, edgeOpacity: 0.32, nodeOpacity: 0.8, accentShare: 0.12, wanderers: 0, pulses: 0, travelers: 0, halos: 0 },
    ],
  },
}

/** Small deterministic PRNG so the graphic looks the same on every load. */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function pick<T>(items: T[], count: number, rand: () => number): T[] {
  const copy = [...items]
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1))
    ;[copy[i], copy[j]] = [copy[j], copy[i]]
  }
  return copy.slice(0, count)
}

function timing(rand: () => number, minDur: number, spanDur: number, maxDelay: number): Timing {
  return { dur: minDur + rand() * spanDur, delay: -rand() * maxDelay }
}

function buildLayer(spec: LayerSpec, vs: VariantSpec, animated: boolean): LayerModel {
  const rand = mulberry32(spec.seed)
  const { width, height, bleed } = vs
  const cw = (width + 2 * bleed) / spec.cols
  const ch = (height + 2 * bleed) / spec.rows

  const nodes: Pt[] = []
  for (let j = 0; j < spec.rows; j++) {
    for (let i = 0; i < spec.cols; i++) {
      const stagger = j % 2 === 0 ? 0 : 0.5
      nodes.push({
        x: -bleed + (i + 0.5 + stagger + (rand() - 0.5) * spec.jitter) * cw,
        y: -bleed + (j + 0.5 + (rand() - 0.5) * spec.jitter) * ch,
      })
    }
  }

  // Each node links to its nearest neighbours; a few links are dropped so the mesh stays organic.
  const maxDist = Math.max(cw, ch) * 1.7
  const seen = new Set<string>()
  const edges: [number, number][] = []
  nodes.forEach((p, a) => {
    const near = nodes
      .map((q, b) => ({ b, d: Math.hypot(p.x - q.x, p.y - q.y) }))
      .filter((o) => o.b !== a && o.d < maxDist)
      .sort((m, n) => m.d - n.d)
      .slice(0, 3)
    for (const o of near) {
      const key = a < o.b ? `${a}-${o.b}` : `${o.b}-${a}`
      if (seen.has(key) || rand() < 0.1) continue
      seen.add(key)
      edges.push([a, o.b])
    }
  })

  const visible = (p: Pt) => p.x > 20 && p.x < width - 20 && p.y > 20 && p.y < height - 20
  const visibleNodes = nodes.map((_, i) => i).filter((i) => visible(nodes[i]))
  const accents = pick(visibleNodes, Math.round(visibleNodes.length * spec.accentShare), rand)

  const wander = new Map<number, Wander>()
  const halos = new Map<number, Timing>()
  const pulses = new Map<number, Timing>()
  const travelers = new Map<number, Timing>()
  if (animated) {
    for (const i of pick(visibleNodes, spec.wanderers, rand)) {
      wander.set(i, { dx: (rand() - 0.5) * 36, dy: (rand() - 0.5) * 36, dur: 16 + rand() * 14, begin: -rand() * 20 })
    }
    for (const i of pick(accents.filter((n) => !wander.has(n)), spec.halos, rand)) halos.set(i, timing(rand, 5, 3, 8))
    const steady = edges
      .map((e, i) => ({ e, i }))
      .filter(({ e }) => !wander.has(e[0]) && !wander.has(e[1]) && visible(nodes[e[0]]) && visible(nodes[e[1]]))
    for (const { i } of pick(steady, spec.pulses, rand)) pulses.set(i, timing(rand, 6, 5, 10))
    const long = steady.filter(({ e, i }) => Math.hypot(nodes[e[0]].x - nodes[e[1]].x, nodes[e[0]].y - nodes[e[1]].y) > 50 && !pulses.has(i))
    for (const { i } of pick(long, spec.travelers, rand)) travelers.set(i, timing(rand, 10, 8, 14))
  }
  return { spec, nodes, edges, wander, accents, halos, pulses, travelers }
}

function usePrefersReducedMotion(): boolean {
  const query = '(prefers-reduced-motion: reduce)'
  const supported = typeof window !== 'undefined' && typeof window.matchMedia === 'function'
  const [reduced, setReduced] = useState(() => (supported ? window.matchMedia(query).matches : false))
  useEffect(() => {
    if (!supported) return undefined
    const mq = window.matchMedia(query)
    const onChange = () => setReduced(mq.matches)
    mq.addEventListener?.('change', onChange)
    return () => mq.removeEventListener?.('change', onChange)
  }, [supported])
  return reduced
}

const f1 = (n: number): string => n.toFixed(1)

function Move({ attr, base, w }: Readonly<{ attr: 'x1' | 'y1' | 'x2' | 'y2' | 'cx' | 'cy'; base: number; w: { delta: number; dur: number; begin: number } }>) {
  return (
    <animate
      attributeName={attr}
      values={`${f1(base)};${f1(base + w.delta)};${f1(base)}`}
      dur={`${f1(w.dur)}s`}
      begin={`${f1(w.begin)}s`}
      repeatCount="indefinite"
      calcMode="spline"
      keyTimes="0;0.5;1"
      keySplines="0.45 0 0.55 1;0.45 0 0.55 1"
    />
  )
}

function timingStyle(t: Timing): CSSProperties {
  return { ['--dur' as string]: `${f1(t.dur)}s`, ['--delay' as string]: `${f1(t.delay)}s` }
}

function Layer({ model }: Readonly<{ model: LayerModel }>) {
  const { spec, nodes, edges, wander, accents, halos, pulses, travelers } = model
  const accentSet = new Set(accents)
  const calm = nodes.map((_, i) => i).filter((i) => !wander.has(i) && !accentSet.has(i))
  const endpoint = (index: number, a: 1 | 2) => {
    const w = wander.get(index)
    if (!w) return null
    const p = nodes[index]
    return (
      <>
        <Move attr={a === 1 ? 'x1' : 'x2'} base={p.x} w={{ delta: w.dx, dur: w.dur, begin: w.begin }} />
        <Move attr={a === 1 ? 'y1' : 'y2'} base={p.y} w={{ delta: w.dy, dur: w.dur, begin: w.begin }} />
      </>
    )
  }

  return (
    <g className={`kn-layer kn-layer-${spec.key}`}>
      <g stroke="#ffffff" strokeOpacity={spec.edgeOpacity} strokeWidth={spec.edgeWidth} strokeLinecap="round">
        {edges.map(([a, b]) => (
          <line key={`${a}-${b}`} x1={f1(nodes[a].x)} y1={f1(nodes[a].y)} x2={f1(nodes[b].x)} y2={f1(nodes[b].y)}>
            {endpoint(a, 1)}
            {endpoint(b, 2)}
          </line>
        ))}
      </g>

      {[...pulses].map(([i, t]) => (
        <line key={`p${i}`} className="kn-pulse" style={timingStyle(t)} stroke={GREEN} strokeWidth={spec.edgeWidth * 1.5} strokeLinecap="round" x1={f1(nodes[edges[i][0]].x)} y1={f1(nodes[edges[i][0]].y)} x2={f1(nodes[edges[i][1]].x)} y2={f1(nodes[edges[i][1]].y)} />
      ))}
      {[...travelers].map(([i, t]) => (
        <line key={`t${i}`} className="kn-travel" style={timingStyle(t)} pathLength={100} stroke={GREEN} strokeWidth={spec.edgeWidth * 2} strokeLinecap="round" x1={f1(nodes[edges[i][0]].x)} y1={f1(nodes[edges[i][0]].y)} x2={f1(nodes[edges[i][1]].x)} y2={f1(nodes[edges[i][1]].y)} />
      ))}

      <g fill="#ffffff" fillOpacity={spec.nodeOpacity}>
        {calm.map((i) => <circle key={i} cx={f1(nodes[i].x)} cy={f1(nodes[i].y)} r={spec.radius} />)}
        {[...wander].map(([i, w]) => (
          <circle key={`w${i}`} cx={f1(nodes[i].x)} cy={f1(nodes[i].y)} r={spec.radius}>
            <Move attr="cx" base={nodes[i].x} w={{ delta: w.dx, dur: w.dur, begin: w.begin }} />
            <Move attr="cy" base={nodes[i].y} w={{ delta: w.dy, dur: w.dur, begin: w.begin }} />
          </circle>
        ))}
      </g>

      {[...halos].map(([i, t]) => (
        <circle key={`h${i}`} className="kn-halo" style={timingStyle(t)} cx={f1(nodes[i].x)} cy={f1(nodes[i].y)} r={spec.radius * 1.2} fill="none" stroke={GREEN} strokeWidth={0.8} />
      ))}
      <g fill={GREEN}>
        {accents.map((i) => <circle key={`a${i}`} cx={f1(nodes[i].x)} cy={f1(nodes[i].y)} r={spec.radius * 1.2} />)}
      </g>
    </g>
  )
}

/**
 * Original SVG network of fine nodes and links, drawn in the SCCH petrol-and-green language.
 * No SCCH master artwork exists in the project assets, so the graphic is generated.
 */
export function NetworkGraphic({ variant, className }: Readonly<{ variant: NetworkVariant; className?: string }>) {
  const reduced = usePrefersReducedMotion()
  const animated = variant === 'hero' && !reduced
  const vs = SPECS[variant]
  const models = useMemo(() => vs.layers.map((l) => buildLayer(l, vs, animated)), [vs, animated])

  return (
    <div className={`${variant === 'hero' ? 'kn-hero ' : ''}${className ?? ''}`} aria-hidden>
      <svg
        className={variant === 'compact' ? 'kn-net kn-static' : 'kn-net'}
        viewBox={`0 0 ${vs.width} ${vs.height}`}
        preserveAspectRatio="xMidYMid slice"
        focusable="false"
      >
        {models.map((m) => <Layer key={m.spec.key} model={m} />)}
      </svg>
    </div>
  )
}
