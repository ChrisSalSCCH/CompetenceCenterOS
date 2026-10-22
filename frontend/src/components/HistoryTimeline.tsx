import { useState } from 'react'
import { Link } from 'react-router'
import { ChevronDown, ChevronUp, GitCommitVertical } from 'lucide-react'
import { Pill } from '@/components/kit'
import { fmtDateTime } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import type { HistoryEntry } from '@/lib/types'

interface FieldDiff {
  field: string
  removed: string[]
  added: string[]
}

const OP_TONE = { create: 'forest', update: 'primary', delete: 'danger' } as const
const SOURCE_LABEL = { proposal: 'via proposal', seed: 'initial setup', direct: 'direct change' } as const
const LIST_FIELDS = ['accountabilities', 'domains', 'policies', 'authorities']
const SCALAR_FIELDS = ['name', 'purpose', 'description', 'governance_mode', 'allow_multiple', 'can_govern', 'parent_id', 'circle_id']

function texts(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.map((v) => (typeof v === 'object' && v !== null ? String((v as { text?: unknown }).text ?? '') : String(v)))
}

export function diffSnapshots(before: Record<string, unknown> | null, after: Record<string, unknown> | null): FieldDiff[] {
  const out: FieldDiff[] = []
  for (const f of SCALAR_FIELDS) {
    const b = before?.[f]
    const a = after?.[f]
    if (JSON.stringify(b) !== JSON.stringify(a)) {
      out.push({ field: f, removed: b === undefined || b === null || b === '' ? [] : [String(b)], added: a === undefined || a === null || a === '' ? [] : [String(a)] })
    }
  }
  for (const f of LIST_FIELDS) {
    const b = texts(before?.[f])
    const a = texts(after?.[f])
    const removed = b.filter((x) => !a.includes(x))
    const added = a.filter((x) => !b.includes(x))
    if (removed.length > 0 || added.length > 0) out.push({ field: f, removed, added })
  }
  return out
}

export function HistoryTimeline({ entries, showEntity = false }: Readonly<{ entries: HistoryEntry[]; showEntity?: boolean }>) {
  const { t, lang } = useT()
  const [open, setOpen] = useState<string | null>(null)
  if (entries.length === 0) return <p className="text-sm text-muted-foreground">{t('No recorded changes.')}</p>
  return (
    <ol className="relative space-y-4 border-l border-border pl-5">
      {entries.map((e) => {
        const diffs = diffSnapshots(e.before_state, e.after_state)
        const isOpen = open === e.id
        return (
          <li key={e.id} className="relative">
            <GitCommitVertical className="absolute -left-[31px] top-0.5 h-5 w-5 rounded-full bg-background text-primary" aria-hidden />
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium">{e.summary}</span>
              <Pill tone={OP_TONE[e.op]}>{t(e.op)}</Pill>
              <Pill>{t(SOURCE_LABEL[e.source])}</Pill>
            </div>
            <div className="text-xs text-muted-foreground">
              {fmtDateTime(e.created_at, lang)} · {t('proposed/changed by')} {e.actor_name ?? '?'}
              {e.decided_by_name && <> · {t('decided by')} {e.decided_by_name}</>}
              {showEntity && <> · {e.entity_type}</>}
            </div>
            {e.reason && <p className="mt-1 text-sm italic text-muted-foreground">“{e.reason}”</p>}
            {e.proposal_id && <Link to={`/governance/proposals/${e.proposal_id}`} className="text-xs text-primary hover:underline">{e.proposal_title}</Link>}
            {diffs.length > 0 && e.op !== 'create' && (
              <div className="mt-1">
                <button type="button" className="flex items-center gap-1 text-xs font-medium text-primary" onClick={() => setOpen(isOpen ? null : e.id)} aria-expanded={isOpen}>
                  {isOpen ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                  {t('What changed?')}
                </button>
                {isOpen && (
                  <div className="pop-in mt-2 space-y-2 rounded-lg border bg-muted/40 p-3 text-sm">
                    {diffs.map((d) => (
                      <div key={d.field}>
                        <div className="font-mono-label text-muted-foreground">{d.field.replaceAll('_', ' ')}</div>
                        {d.removed.map((r) => <div key={`r-${r}`} className="text-destructive line-through decoration-destructive/40">− {r}</div>)}
                        {d.added.map((a) => <div key={`a-${a}`} className="text-[hsl(var(--forest))]">+ {a}</div>)}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </li>
        )
      })}
    </ol>
  )
}
