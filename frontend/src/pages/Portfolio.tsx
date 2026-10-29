import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { Plus, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { CatalogPicker, type PickedEntry } from '@/components/CatalogPicker'
import { ComboPicker } from '@/components/ComboPicker'
import { ProjectCreateDialog } from '@/components/project/ProjectCreateDialog'
import { EmptyState, ErrorBlock, LoadingBlock, PageHeader, Pill, Section, StatusPill } from '@/components/kit'
import { useSession } from '@/contexts/SessionContext'
import { fmtDate, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import { CATEGORIES, PHASES, classificationTone, phaseTone } from '@/lib/portfolio'
import type { CatalogEntry, Classification, CrmOrgRow, PortfolioRow } from '@/lib/portfolio-types'
import type { PersonRow } from '@/lib/types'

const ANY = 'any'

function useDebounced<T>(value: T, ms = 300): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), ms)
    return () => clearTimeout(id)
  }, [value, ms])
  return debounced
}

interface Props {
  /** Fixes the classification (Customer Projects / Internal Projects views). */
  fixed?: Classification
}

export default function Portfolio({ fixed }: Readonly<Props>) {
  const { t, lang } = useT()
  const { isObserver } = useSession()
  const [params] = useSearchParams()
  const entryParam = params.get('entry')
  const [search, setSearch] = useState('')
  const [classification, setClassification] = useState<string>(ANY)
  const [category, setCategory] = useState(ANY)
  const [phase, setPhase] = useState(ANY)
  const [manager, setManager] = useState<string[]>([])
  const [customer, setCustomer] = useState<string[]>([])
  const [tags, setTags] = useState<PickedEntry[]>([])
  const [refOnly, setRefOnly] = useState(false)
  const [creating, setCreating] = useState(false)
  const debounced = useDebounced(search)
  const { data: catalog } = useGet<CatalogEntry[]>(entryParam ? '/catalog' : null)

  // A link such as /projects?entry=<id> (from search or a project tag) pre-selects that catalog filter.
  useEffect(() => {
    const found = catalog?.find((c) => c.id === entryParam)
    if (found) setTags([{ id: found.id, name: found.name, kind: found.kind }])
  }, [catalog, entryParam])

  const query = useMemo(() => {
    const p = new URLSearchParams()
    for (const e of tags) p.append('entry_ids', e.id)
    const s = p.toString()
    return s ? `/portfolio?${s}` : '/portfolio'
  }, [tags])
  const effectiveClassification = fixed ?? (classification === ANY ? undefined : classification)
  const { data, isLoading, error } = useGet<PortfolioRow[]>(query, {
    search: debounced.trim() || undefined,
    classification: effectiveClassification,
    category: category === ANY ? undefined : category,
    phase: phase === ANY ? undefined : phase,
    manager_id: manager[0],
    crm_org_id: customer[0],
    reference_eligible: refOnly ? true : undefined,
  })
  const { data: people } = useGet<PersonRow[]>('/people')
  const { data: orgs } = useGet<CrmOrgRow[]>('/crm/organizations')

  const filtered = !!debounced || tags.length > 0 || manager.length > 0 || customer.length > 0 || refOnly || category !== ANY || phase !== ANY || (!fixed && classification !== ANY)
  const reset = () => {
    setSearch('')
    setClassification(ANY)
    setCategory(ANY)
    setPhase(ANY)
    setManager([])
    setCustomer([])
    setTags([])
    setRefOnly(false)
  }

  let title = t('Project Portfolio')
  if (fixed === 'customer') title = t('Customer Projects')
  if (fixed === 'internal') title = t('Internal Projects')

  return (
    <>
      <PageHeader
        title={title}
        subtitle={t('All projects of the organization - searchable by customer, technology, industry and research area.')}
        actions={!isObserver && <Button onClick={() => setCreating(true)}><Plus className="mr-1 h-4 w-4" aria-hidden />{t('New project')}</Button>}
      />

      <Section className="mb-4" index={1}>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <div className="relative md:col-span-2">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input className="pl-9" value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t('Search name, number, customer, technology ...')} aria-label={t('Search')} />
          </div>
          {!fixed && (
            <Select value={classification} onValueChange={setClassification}>
              <SelectTrigger aria-label={t('Classification')}><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value={ANY}>{t('Classification')}: {t('Any')}</SelectItem>
                <SelectItem value="customer">{t('Customer')}</SelectItem>
                <SelectItem value="internal">{t('Internal')}</SelectItem>
              </SelectContent>
            </Select>
          )}
          <Select value={category} onValueChange={setCategory}>
            <SelectTrigger aria-label={t('Category')}><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value={ANY}>{t('Category')}: {t('Any')}</SelectItem>
              {CATEGORIES.map((c) => <SelectItem key={c} value={c}>{t(c)}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={phase} onValueChange={setPhase}>
            <SelectTrigger aria-label={t('Phase')}><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value={ANY}>{t('Phase')}: {t('Any')}</SelectItem>
              {PHASES.map((p) => <SelectItem key={p} value={p}>{t(p)}</SelectItem>)}
            </SelectContent>
          </Select>
          <ComboPicker options={(orgs ?? []).map((o) => ({ id: o.id, label: o.name, hint: o.city }))} value={customer} onChange={(v) => setCustomer(v.slice(-1))} placeholder={`${t('Customer')}: ${t('Any')}`} ariaLabel={t('Customer')} />
          <ComboPicker options={(people ?? []).map((p) => ({ id: p.id, label: p.name, hint: p.job_title }))} value={manager} onChange={(v) => setManager(v.slice(-1))} placeholder={`${t('Manager')}: ${t('Any')}`} ariaLabel={t('Manager')} />
          <Label className="flex items-center gap-2 text-sm"><Switch checked={refOnly} onCheckedChange={setRefOnly} />{t('Reference-eligible only')}</Label>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted-foreground">{t('Technology')} / {t('Industry')} / {t('Research area')}:</span>
          <CatalogPicker value={tags} onChange={setTags} allowCreate={false} />
          {filtered && <Button variant="ghost" size="sm" onClick={reset}>{t('Reset filters')}</Button>}
        </div>
      </Section>

      {isLoading && <LoadingBlock />}
      {error && <ErrorBlock message={error.message} />}
      {data && data.length === 0 && <EmptyState title={t('No projects match your filters')} />}
      {data && data.length > 0 && (
        <Section index={2} className="overflow-x-auto p-0 md:p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('Project')}</TableHead>
                <TableHead>{t('Classification')}</TableHead>
                <TableHead>{t('Phase')}</TableHead>
                <TableHead>{t('Customers')}</TableHead>
                <TableHead>{t('Technologies')}</TableHead>
                <TableHead>{t('Manager')}</TableHead>
                <TableHead>{t('Timeline')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((p) => {
                const tech = p.entries.filter((e) => e.kind === 'technology')
                return (
                  <TableRow key={p.id} className="align-top">
                    <TableCell className="min-w-56">
                      <Link to={`/projects/${p.id}`} className="font-display text-base font-semibold hover:text-primary">{p.name}</Link>
                      <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                        {p.project_no && <span className="font-mono">{p.project_no}</span>}
                        {p.is_research && <Pill tone="forest">{t('Research project')}</Pill>}
                        {p.ai_relevant && <Pill tone="ochre">{t('AI relevant')}</Pill>}
                        {p.reference_allowed && <Pill tone="primary">{t('Reference')}</Pill>}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Pill tone={classificationTone(p.classification)}>{t(p.classification)}</Pill>
                      <div className="mt-1 text-xs text-muted-foreground">{t(p.category)}</div>
                    </TableCell>
                    <TableCell className="space-y-1">
                      <Pill tone={phaseTone(p.phase)}>{t(p.phase)}</Pill>
                      <div><StatusPill status={p.status} /></div>
                    </TableCell>
                    <TableCell className="min-w-40 text-sm">
                      {p.customers.length === 0 ? <span className="text-muted-foreground">–</span> : p.customers.map((c) => <Link key={c.id} to={`/crm/organizations/${c.id}`} className="block hover:text-primary">{c.name}</Link>)}
                    </TableCell>
                    <TableCell className="min-w-44">
                      <div className="flex flex-wrap gap-1">
                        {tech.slice(0, 4).map((e) => <Pill key={e.id}>{e.name}</Pill>)}
                        {tech.length > 4 && <Pill>+{tech.length - 4}</Pill>}
                      </div>
                    </TableCell>
                    <TableCell className="text-sm">{p.manager_name ?? '–'}</TableCell>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{fmtDate(p.start_date, lang)}<br />{fmtDate(p.due_date, lang)}</TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </Section>
      )}
      <ProjectCreateDialog open={creating} onOpenChange={setCreating} defaultClassification={fixed ?? 'customer'} />
    </>
  )
}
