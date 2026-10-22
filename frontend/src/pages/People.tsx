import { useState } from 'react'
import { Link } from 'react-router'
import { Search } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Avatar, EmptyState, ErrorBlock, LoadingBlock, PageHeader, Pill, Section } from '@/components/kit'
import { useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import { matchesFilter } from '@/lib/structure'
import type { PersonRow, Structure } from '@/lib/types'

export default function People() {
  const { t } = useT()
  const { data, isLoading, error } = useGet<PersonRow[]>('/people')
  const { data: structure } = useGet<Structure>('/structure')
  const [filter, setFilter] = useState('')
  const [circle, setCircle] = useState('')
  const people = (data ?? []).filter((p) => matchesFilter(filter, p.name, p.job_title ?? '', p.skills.join(' '), p.roles.map((r) => r.role_name).join(' ')))
  const selected = circle || structure?.circles.find((c) => !c.parent_id)?.id || ''
  const circleRoles = (structure?.roles ?? []).filter((r) => r.circle_id === selected)

  return (
    <>
      <PageHeader title={t('People')} subtitle={t('Who holds which role? Look at people, or at the roles of a circle.')} />
      <Tabs defaultValue="person" className="space-y-4">
        <TabsList>
          <TabsTrigger value="person">{t('By person')}</TabsTrigger>
          <TabsTrigger value="circle">{t('By circle')}</TabsTrigger>
        </TabsList>

        <TabsContent value="person" className="space-y-4">
          <div className="relative max-w-sm">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input className="pl-9" value={filter} onChange={(e) => setFilter(e.target.value)} placeholder={t('Search name, skill or role')} aria-label={t('Search name, skill or role')} />
          </div>
          {isLoading && <LoadingBlock />}
          {error && <ErrorBlock message={error.message} />}
          {data && people.length === 0 && <EmptyState title={t('Nobody matches your search')} />}
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {people.map((p, i) => (
              <Link key={p.id} to={`/people/${p.id}`} className="paper-card interactive reveal block p-4" style={{ ['--i' as string]: i }}>
                <div className="flex items-center gap-3">
                  <Avatar name={p.name} color={p.avatar_color} size={44} />
                  <div className="min-w-0">
                    <div className="font-display text-lg font-semibold leading-tight">{p.name}</div>
                    <div className="truncate text-xs text-muted-foreground">{p.job_title}</div>
                  </div>
                  {p.access_level === 'observer' && <Pill className="ml-auto">{t('Observer')}</Pill>}
                  {p.access_level === 'org_admin' && <Pill tone="primary" className="ml-auto">{t('Admin')}</Pill>}
                </div>
                <div className="mt-3 flex flex-wrap gap-1">
                  {p.roles.slice(0, 5).map((r) => <Pill key={r.role_id} tone="forest">{r.role_name}</Pill>)}
                  {p.roles.length === 0 && <span className="text-xs text-muted-foreground">{t('No roles')}</span>}
                </div>
                <div className="mt-3 flex gap-4 text-xs text-muted-foreground">
                  <span>{p.role_count} {t('roles')}</span><span>{p.open_tasks} {t('open tasks')}</span>{p.availability && <span>{p.availability}</span>}
                </div>
              </Link>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="circle" className="space-y-4">
          <div className="max-w-xs">
            <Select value={selected} onValueChange={setCircle}>
              <SelectTrigger aria-label={t('Circle')}><SelectValue placeholder={t('Choose a circle.')} /></SelectTrigger>
              <SelectContent>{(structure?.circles ?? []).map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <Section title={t('Who fills the roles in this circle?')}>
            {circleRoles.length === 0 ? <EmptyState title={t('This circle has no roles')} /> : (
              <ul className="divide-y">
                {circleRoles.map((r) => (
                  <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 py-3">
                    <Link to={`/organization/roles/${r.id}`} className="font-display text-base font-semibold hover:text-primary">{r.name}</Link>
                    <span className="flex flex-wrap items-center gap-2">
                      {r.holders.length === 0 && <Pill tone="ochre">{t('unfilled')}</Pill>}
                      {r.holders.map((h) => (
                        <Link key={h.assignment_id} to={`/people/${h.user_id}`} className="flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-sm hover:border-primary">
                          <Avatar name={h.name} color={h.avatar_color} size={20} />{h.name}
                        </Link>
                      ))}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Section>
        </TabsContent>
      </Tabs>
    </>
  )
}
