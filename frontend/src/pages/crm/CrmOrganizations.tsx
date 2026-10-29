import { useState } from 'react'
import { Link } from 'react-router'
import { Plus, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { OrgFormDialog } from '@/components/crm/OrgFormDialog'
import { EmptyState, ErrorBlock, LoadingBlock, PageHeader, Pill, Section } from '@/components/kit'
import { useSession } from '@/contexts/SessionContext'
import { fmtDate, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import { CRM_RELATIONS } from '@/lib/portfolio'
import type { CrmOrgRow } from '@/lib/portfolio-types'

const ANY = 'any'

export default function CrmOrganizations() {
  const { t, lang } = useT()
  const { isObserver } = useSession()
  const [search, setSearch] = useState('')
  const [relation, setRelation] = useState(ANY)
  const [creating, setCreating] = useState(false)
  const { data, isLoading, error } = useGet<CrmOrgRow[]>('/crm/organizations', { search: search.trim() || undefined, relation: relation === ANY ? undefined : relation })

  return (
    <>
      <PageHeader title={t('Companies')} actions={!isObserver && <Button onClick={() => setCreating(true)}><Plus className="mr-1 h-4 w-4" aria-hidden />{t('New organization')}</Button>} />
      <Section className="mb-4">
        <div className="flex flex-wrap gap-3">
          <div className="relative min-w-64 flex-1 md:max-w-md">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
            <Input className="pl-9" value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t('Search name, city, VAT ID ...')} aria-label={t('Search')} />
          </div>
          <Select value={relation} onValueChange={setRelation}>
            <SelectTrigger className="w-52" aria-label={t('Relationship')}><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value={ANY}>{t('Relationship')}: {t('Any')}</SelectItem>
              {CRM_RELATIONS.map((r) => <SelectItem key={r} value={r}>{t(r.replaceAll('_', ' '))}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </Section>
      {isLoading && <LoadingBlock />}
      {error && <ErrorBlock message={error.message} />}
      {data && data.length === 0 && <EmptyState title={t('Nothing found.')} />}
      {data && data.length > 0 && (
        <Section className="overflow-x-auto p-0 md:p-0">
          <Table>
            <TableHeader>
              <TableRow><TableHead>{t('Name')}</TableHead><TableHead>{t('Relationship')}</TableHead><TableHead>{t('Industry')}</TableHead><TableHead>{t('Owner')}</TableHead><TableHead>{t('Projects')}</TableHead><TableHead>{t('Contacts')}</TableHead><TableHead>{t('Last activity')}</TableHead></TableRow>
            </TableHeader>
            <TableBody>
              {data.map((o) => (
                <TableRow key={o.id}>
                  <TableCell>
                    <Link to={`/crm/organizations/${o.id}`} className="font-display text-base font-semibold hover:text-primary">{o.name}</Link>
                    <div className="text-xs text-muted-foreground">{[o.city, o.country].filter(Boolean).join(', ')}{o.parent_name && ` · ${o.parent_name}`}{o.status === 'inactive' && ` · ${t('inactive')}`}</div>
                  </TableCell>
                  <TableCell><div className="flex flex-wrap gap-1">{o.relation_types.map((r) => <Pill key={r} tone={r === 'customer' ? 'ink' : 'neutral'}>{t(r.replaceAll('_', ' '))}</Pill>)}</div></TableCell>
                  <TableCell className="text-sm">{o.industry ?? '–'}</TableCell>
                  <TableCell className="text-sm">{o.owner_name ?? '–'}</TableCell>
                  <TableCell className="text-sm">{o.project_count}</TableCell>
                  <TableCell className="text-sm">{o.contact_count}</TableCell>
                  <TableCell className="whitespace-nowrap text-xs text-muted-foreground">{fmtDate(o.last_activity_at, lang)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Section>
      )}
      <OrgFormDialog org={null} open={creating} onOpenChange={setCreating} />
    </>
  )
}
