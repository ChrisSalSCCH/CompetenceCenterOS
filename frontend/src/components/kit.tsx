import { type ReactNode } from 'react'
import { AlertTriangle, Inbox, Info, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useT } from '@/lib/i18n'
import { initials } from '@/lib/hooks'
import type { GovMode } from '@/lib/types'
import { Skeleton } from '@/components/ui/skeleton'

export type Tone = 'neutral' | 'primary' | 'forest' | 'ochre' | 'danger' | 'ink'

const TONES: Record<Tone, string> = {
  neutral: 'bg-muted text-muted-foreground border-border',
  primary: 'bg-primary/10 text-primary border-primary/30',
  forest: 'bg-[hsl(var(--forest)/0.12)] text-[hsl(var(--forest))] border-[hsl(var(--forest)/0.3)]',
  ochre: 'bg-[hsl(var(--ochre)/0.14)] text-[hsl(var(--ochre))] border-[hsl(var(--ochre)/0.35)]',
  danger: 'bg-destructive/10 text-destructive border-destructive/30',
  ink: 'bg-foreground text-background border-foreground',
}

export function Pill({ tone = 'neutral', children, className }: Readonly<{ tone?: Tone; children: ReactNode; className?: string }>) {
  return (
    <span className={cn('inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium leading-4 whitespace-nowrap', TONES[tone], className)}>
      {children}
    </span>
  )
}

const STATUS_TONE: Record<string, Tone> = {
  todo: 'neutral', doing: 'ochre', blocked: 'danger', done: 'forest',
  planned: 'neutral', active: 'primary', on_hold: 'ochre', cancelled: 'neutral',
  open: 'primary', processing: 'ochre', resolved: 'forest', dropped: 'neutral',
  draft: 'neutral', submitted: 'primary', clarifying: 'ochre', reactions: 'ochre', objections: 'danger', integration: 'ochre',
  accepted: 'forest', rejected: 'danger', withdrawn: 'neutral',
  scheduled: 'primary', in_progress: 'ochre', completed: 'forest',
}

export function StatusPill({ status }: Readonly<{ status: string }>) {
  const { t } = useT()
  return <Pill tone={STATUS_TONE[status] ?? 'neutral'}>{t(status.replaceAll('_', ' '))}</Pill>
}

export function PriorityPill({ priority }: Readonly<{ priority: string }>) {
  const { t } = useT()
  const tones: Record<string, Tone> = { high: 'danger', medium: 'ochre' }
  return <Pill tone={tones[priority] ?? 'neutral'}>{t(priority)}</Pill>
}

const MODE_LABEL: Record<GovMode, string> = {
  direct: 'Direct change',
  approval: 'Approval',
  consent: 'Consent',
  holacracy: 'Structured (Holacracy)',
}

export function ModePill({ mode }: Readonly<{ mode: GovMode }>) {
  const { t } = useT()
  return <Pill tone="ink">{t(MODE_LABEL[mode])}</Pill>
}

export function PlannedPill() {
  const { t } = useT()
  return <Pill tone="ochre">{t('Planned')}</Pill>
}

export function Avatar({ name, color = '#C2512D', size = 28 }: Readonly<{ name: string | null | undefined; color?: string; size?: number }>) {
  return (
    <span
      className="inline-flex shrink-0 items-center justify-center rounded-full font-semibold text-white ring-2 ring-card"
      style={{ background: color, width: size, height: size, fontSize: size * 0.38 }}
      title={name ?? ''}
    >
      {initials(name)}
    </span>
  )
}

export function PageHeader({ title, subtitle, actions, eyebrow }: Readonly<{ title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; eyebrow?: ReactNode }>) {
  return (
    <div className="reveal mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && <div className="font-mono-label mb-1 text-muted-foreground">{eyebrow}</div>}
        <h1 className="font-display text-3xl font-semibold tracking-tight md:text-4xl">{title}</h1>
        {subtitle && <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

export function Section({ title, action, children, className, index = 0 }: Readonly<{ title?: ReactNode; action?: ReactNode; children: ReactNode; className?: string; index?: number }>) {
  return (
    <section className={cn('paper-card reveal p-4 md:p-5', className)} style={{ ['--i' as string]: index }}>
      {(title || action) && (
        <div className="mb-3 flex items-center justify-between gap-2">
          {title && <h2 className="font-display text-lg font-semibold tracking-tight md:text-xl">{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  )
}

export function EmptyState({ title, hint, action }: Readonly<{ title: string; hint?: string; action?: ReactNode }>) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border px-4 py-8 text-center">
      <Inbox className="h-6 w-6 text-muted-foreground" aria-hidden />
      <p className="text-sm font-medium">{title}</p>
      {hint && <p className="max-w-sm text-xs text-muted-foreground">{hint}</p>}
      {action}
    </div>
  )
}

export function LoadingBlock({ rows = 4 }: Readonly<{ rows?: number }>) {
  return (
    <div className="space-y-3" aria-busy="true">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-14 w-full rounded-xl" />
      ))}
    </div>
  )
}

export function ErrorBlock({ message }: Readonly<{ message?: string }>) {
  const { t } = useT()
  return (
    <div role="alert" className="flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm">
      <AlertTriangle className="mt-0.5 h-4 w-4 text-destructive" aria-hidden />
      <div>
        <p className="font-medium">{t('Something went wrong')}</p>
        <p className="text-muted-foreground">{message ?? t('Please try again.')}</p>
      </div>
    </div>
  )
}

export function PlannedNotice({ children }: Readonly<{ children: ReactNode }>) {
  const { t } = useT()
  return (
    <div className="flex items-start gap-2 rounded-xl border border-dashed border-[hsl(var(--ochre)/0.5)] bg-[hsl(var(--ochre)/0.07)] p-3 text-sm">
      <Sparkles className="mt-0.5 h-4 w-4 text-[hsl(var(--ochre))]" aria-hidden />
      <div>
        <span className="font-semibold">{t('Planned')}: </span>
        {children}
      </div>
    </div>
  )
}

export function InfoNotice({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <div role="note" className="flex items-start gap-2 rounded-xl border bg-muted/40 p-3 text-sm">
      <Info className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
      <div>{children}</div>
    </div>
  )
}

export function ProgressBar({ value, tone = 'primary' }: Readonly<{ value: number; tone?: 'primary' | 'forest' | 'ochre' }>) {
  const pct = Math.max(0, Math.min(100, Math.round(value * 100)))
  const colors = { primary: 'bg-primary', forest: 'bg-[hsl(var(--forest))]', ochre: 'bg-[hsl(var(--ochre))]' }
  const color = colors[tone]
  return (
    <div className="flex items-center gap-2" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
        <div className={cn('h-full rounded-full transition-all duration-700', color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-9 text-right font-mono text-[11px] text-muted-foreground">{pct}%</span>
    </div>
  )
}

export function Stat({ label, value, tone, hint }: Readonly<{ label: string; value: ReactNode; tone?: Tone; hint?: string }>) {
  return (
    <div className="paper-card p-3">
      <div className="font-mono-label text-muted-foreground">{label}</div>
      <div className={cn('mt-1 font-display text-3xl font-semibold', tone === 'danger' && 'text-destructive', tone === 'primary' && 'text-primary')}>{value}</div>
      {hint && <div className="text-xs text-muted-foreground">{hint}</div>}
    </div>
  )
}

export function ItemList({ items, empty }: Readonly<{ items: { text: string; detail?: string | null; level?: string | null }[]; empty: string }>) {
  if (items.length === 0) return <p className="text-sm italic text-muted-foreground">{empty}</p>
  return (
    <ul className="space-y-1.5">
      {items.map((it) => (
        <li key={it.text} className="flex gap-2 text-sm leading-snug">
          <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" aria-hidden />
          <span>
            {it.text}
            {it.level && <Pill className="ml-2" tone="forest">{it.level}</Pill>}
            {it.detail && <span className="block text-xs text-muted-foreground">{it.detail}</span>}
          </span>
        </li>
      ))}
    </ul>
  )
}
