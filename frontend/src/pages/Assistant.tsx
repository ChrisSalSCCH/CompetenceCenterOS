import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { AlertTriangle, ArrowUp, CheckCircle2, Lightbulb, Loader2, Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageHeader, Pill, PlannedNotice, Section } from '@/components/kit'
import { useSession } from '@/contexts/SessionContext'
import api from '@/lib/api'
import { useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'

interface Suggestion {
  name: string
  purpose: string
  accountabilities: string[]
  domains: string[]
  parent_circle_id: string | null
  parent_circle_name: string | null
  overlaps: { role_id: string; role_name: string; circle_name: string; matching: string[] }[]
  generated_by: 'template' | 'llm'
}

interface Answer {
  intent: string
  answer: string
  facts: string[]
  recommendations: string[]
  references: { type: string; id: string; label: string; link: string }[]
  uncertainty: string | null
  suggestion: Suggestion | null
  mode: 'deterministic' | 'llm'
  llm_error?: string
  lang: string
}

interface Turn {
  question: string
  answer?: Answer
  error?: string
}

const EXAMPLES = [
  'Who is responsible for customer acquisition?',
  'Who decides whether we accept a new customer project?',
  'Which roles are responsible for personnel development?',
  'What responsibilities overlap?',
  'Which roles currently have no assigned person?',
  'What changed in the organization last month?',
  'Which governance proposals are awaiting a decision?',
  'Which tasks are overdue in my circles?',
  'Suggest a role that coordinates innovation activities across multiple circles.',
]

function AnswerCard({ a, question }: Readonly<{ a: Answer; question: string }>) {
  const { t } = useT()
  const navigate = useNavigate()
  const s = a.suggestion
  const createDraft = () => {
    if (!s?.parent_circle_id) return
    navigate('/governance/proposals/new', {
      state: {
        draft: {
          circle_id: s.parent_circle_id,
          title: `Create role ${s.name}`,
          description: s.purpose,
          reason: question,
          proposal_type: 'create_role',
          ai_generated: true,
          changes: [{ op: 'create_role', data: { circle_id: s.parent_circle_id, name: s.name, purpose: s.purpose, accountabilities: s.accountabilities.map((x) => ({ text: x })), domains: s.domains.map((x) => ({ text: x })), authorities: [] } }],
        },
      },
    })
  }
  return (
    <div className="paper-card pop-in space-y-4 p-5">
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone={a.mode === 'llm' ? 'primary' : 'neutral'}>{a.mode === 'llm' ? t('Language model + records') : t('Deterministic - from records')}</Pill>
        {a.llm_error && <Pill tone="ochre">{a.llm_error}</Pill>}
      </div>
      <p className="whitespace-pre-line font-display text-xl leading-snug">{a.answer}</p>

      {a.facts.length > 0 && (
        <div>
          <div className="font-mono-label mb-2 flex items-center gap-1 text-[hsl(var(--forest))]"><CheckCircle2 className="h-3.5 w-3.5" />{t('Verified facts from your records')}</div>
          <ul className="space-y-1.5">{a.facts.map((f) => <li key={f} className="rounded-lg bg-[hsl(var(--forest)/0.07)] px-3 py-2 text-sm">{f}</li>)}</ul>
        </div>
      )}

      {s && (
        <div className="rounded-xl border border-dashed border-[hsl(var(--ochre)/0.6)] bg-[hsl(var(--ochre)/0.07)] p-4">
          <div className="font-mono-label mb-1 text-[hsl(var(--ochre))]">{t('Suggested role (draft, not applied)')}</div>
          <h3 className="font-display text-2xl font-semibold">{s.name}</h3>
          <p className="mt-1 text-sm">{s.purpose}</p>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <div><div className="font-mono-label mb-1 text-muted-foreground">{t('Accountabilities')}</div><ul className="list-disc pl-4 text-sm">{s.accountabilities.map((x) => <li key={x}>{x}</li>)}</ul></div>
            <div><div className="font-mono-label mb-1 text-muted-foreground">{t('Domains')}</div><ul className="list-disc pl-4 text-sm">{s.domains.map((x) => <li key={x}>{x}</li>)}</ul></div>
          </div>
          <div className="mt-3 text-sm"><span className="font-mono-label text-muted-foreground">{t('Suggested parent circle')}: </span>{s.parent_circle_name}</div>
          {s.overlaps.length > 0 && (
            <div className="mt-3">
              <div className="font-mono-label mb-1 text-muted-foreground">{t('Potential overlaps with existing roles')}</div>
              <ul className="space-y-1 text-sm">{s.overlaps.map((o) => <li key={o.role_id}><Link className="font-medium text-primary hover:underline" to={`/organization/roles/${o.role_id}`}>{o.role_name}</Link> ({o.circle_name}){o.matching[0] && <span className="text-xs text-muted-foreground"> – {o.matching[0]}</span>}</li>)}</ul>
            </div>
          )}
          <Button className="mt-4" onClick={createDraft} disabled={!s.parent_circle_id}>{t('Open as governance proposal draft')}</Button>
          <p className="mt-2 text-xs text-muted-foreground">{s.generated_by === 'llm' ? t('Generated by the configured language model.') : t('Generated from templates and your wording.')} {t('The assistant never changes governance records by itself.')}</p>
        </div>
      )}

      {a.recommendations.length > 0 && (
        <div>
          <div className="font-mono-label mb-2 flex items-center gap-1 text-primary"><Lightbulb className="h-3.5 w-3.5" />{t('Recommendation')}</div>
          <ul className="space-y-1.5">{a.recommendations.map((f) => <li key={f} className="rounded-lg bg-primary/5 px-3 py-2 text-sm italic">{f}</li>)}</ul>
        </div>
      )}

      {a.uncertainty && (
        <div role="note" className="flex gap-2 rounded-lg border border-[hsl(var(--ochre)/0.5)] bg-[hsl(var(--ochre)/0.1)] p-3 text-sm">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[hsl(var(--ochre))]" aria-hidden />
          <div><span className="font-semibold">{t('Uncertainty')}: </span>{a.uncertainty}</div>
        </div>
      )}

      {a.references.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="font-mono-label text-muted-foreground">{t('References')}</span>
          {a.references.map((r) => <Link key={`${r.type}-${r.id}`} to={r.link} className="rounded-full border bg-card px-2.5 py-0.5 text-xs hover:border-primary hover:text-primary">{r.label}</Link>)}
        </div>
      )}
    </div>
  )
}

export default function Assistant() {
  const { t, lang } = useT()
  const { session } = useSession()
  const [params, setParams] = useSearchParams()
  const [turns, setTurns] = useState<Turn[]>([])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const asked = useRef<string | null>(null)
  const bottom = useRef<HTMLDivElement>(null)
  const { data: caps } = useGet<{ llm_configured: boolean; mcp: string; agents: string; semantic_search: string }>('/ai/capabilities')

  const ask = async (question: string) => {
    const q = question.trim()
    if (q.length < 2 || busy) return
    setBusy(true)
    setText('')
    setTurns((prev) => [...prev, { question: q }])
    try {
      const res = await api.post<Answer>('/ai/ask', { question: q, lang })
      setTurns((prev) => prev.map((x, i) => (i === prev.length - 1 ? { ...x, answer: res.data } : x)))
    } catch {
      setTurns((prev) => prev.map((x, i) => (i === prev.length - 1 ? { ...x, error: t('The assistant could not answer. Please try again.') } : x)))
    }
    setBusy(false)
  }

  useEffect(() => {
    const q = params.get('q')
    if (q && asked.current !== q) {
      asked.current = q
      setParams({}, { replace: true })
      ask(q)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params])

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [turns])

  const submit = (e: FormEvent) => {
    e.preventDefault()
    ask(text)
  }

  return (
    <>
      <PageHeader title={<span className="flex items-center gap-3"><Sparkles className="h-7 w-7 text-primary" />Circle Intelligence</span>} subtitle={t('Answers come from your actual organizational data. Facts are separated from recommendations, and ambiguity about authority is stated, never guessed.')} />

      <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
        {caps?.llm_configured ? <Pill tone="forest">{t('Language model connected')}</Pill> : <Pill tone="neutral">{t('No language model configured: deterministic answers only')}</Pill>}
        {!caps?.llm_configured && session?.access_level === 'org_admin' && <Link to="/admin" className="text-xs text-primary hover:underline">{t('Configure a provider')}</Link>}
      </div>

      {turns.length === 0 && (
        <Section title={t('Try a question')} index={1} className="mb-4">
          <div className="flex flex-wrap gap-2">
            {EXAMPLES.map((e) => <button key={e} type="button" onClick={() => ask(e)} className="rounded-full border bg-card px-3 py-1.5 text-left text-sm transition-colors hover:border-primary hover:text-primary">{e}</button>)}
          </div>
        </Section>
      )}

      <div className="space-y-5 pb-28" aria-live="polite">
        {turns.map((turn, i) => (
          <div key={i} className="space-y-3">
            <div className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-tr-sm bg-foreground px-4 py-2.5 text-sm text-background">{turn.question}</div>
            {turn.answer && <AnswerCard a={turn.answer} question={turn.question} />}
            {turn.error && <p role="alert" className="text-sm text-destructive">{turn.error}</p>}
            {!turn.answer && !turn.error && <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />{t('Looking through your organization...')}</div>}
          </div>
        ))}
        <div ref={bottom} />
      </div>

      <form onSubmit={submit} className="fixed inset-x-0 bottom-0 z-10 border-t bg-background/90 p-3 backdrop-blur lg:left-64">
        <div className="mx-auto flex max-w-3xl items-center gap-2 rounded-full border bg-card p-1.5 pl-5 shadow-lg">
          <input value={text} onChange={(e) => setText(e.target.value)} maxLength={1000} className="h-10 flex-1 bg-transparent text-sm focus:outline-none" placeholder={t('Ask anything about your organization...')} aria-label={t('Ask anything about your organization...')} />
          <Button type="submit" size="icon" className="rounded-full" disabled={busy || text.trim().length < 2} aria-label={t('Ask')}><ArrowUp className="h-4 w-4" /></Button>
        </div>
      </form>

      <div className="mt-8 space-y-2">
        <PlannedNotice>{t('MCP tool access, autonomous AI agents holding governed roles and semantic (embedding) search are planned. The interfaces are prepared, but nothing acts on its own.')}</PlannedNotice>
      </div>
    </>
  )
}
