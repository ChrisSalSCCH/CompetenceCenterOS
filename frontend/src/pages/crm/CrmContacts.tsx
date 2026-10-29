import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { Plus, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { ContactFormDialog } from '@/components/crm/ContactFormDialog'
import { Avatar, EmptyState, ErrorBlock, LoadingBlock, PageHeader, Pill, Section } from '@/components/kit'
import { useSession } from '@/contexts/SessionContext'
import { useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import { fullName } from '@/lib/portfolio'
import type { CrmContactRow } from '@/lib/portfolio-types'
import { cn } from '@/lib/utils'

export default function CrmContacts() {
  const { t } = useT()
  const { isObserver } = useSession()
  const [params] = useSearchParams()
  const highlighted = params.get('contact')
  const [search, setSearch] = useState('')
  const [creating, setCreating] = useState(false)
  const { data, isLoading, error } = useGet<CrmContactRow[]>('/crm/contacts', { search: search.trim() || undefined })

  return (
    <>
      <PageHeader title={t('Contacts')} actions={!isObserver && <Button onClick={() => setCreating(true)}><Plus className="mr-1 h-4 w-4" aria-hidden />{t('New contact')}</Button>} />
      <Section className="mb-4">
        <div className="relative max-w-md">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input className="pl-9" value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t('Search name or e-mail ...')} aria-label={t('Search')} />
        </div>
        {isObserver && <p className="mt-2 text-xs text-muted-foreground">{t('Contact details are hidden for read-only observers.')}</p>}
      </Section>
      {isLoading && <LoadingBlock />}
      {error && <ErrorBlock message={error.message} />}
      {data && data.length === 0 && <EmptyState title={t('Nothing found.')} />}
      {data && data.length > 0 && (
        <Section className="overflow-x-auto p-0 md:p-0">
          <Table>
            <TableHeader>
              <TableRow><TableHead>{t('Name')}</TableHead><TableHead>{t('Organizations')}</TableHead><TableHead>{t('Email')}</TableHead><TableHead>{t('Phone')}</TableHead></TableRow>
            </TableHeader>
            <TableBody>
              {data.map((c) => (
                <TableRow key={c.id} className={cn(c.id === highlighted && 'bg-primary/5 ring-1 ring-primary/40')}>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Avatar name={fullName(c)} size={28} />
                      <div><div className="font-medium">{fullName(c)}</div><div className="text-xs text-muted-foreground">{c.job_title}</div></div>
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {c.orgs.map((o) => <Link key={o.id} to={`/crm/organizations/${o.id}`}><Pill tone={o.is_primary ? 'primary' : 'neutral'}>{o.name}{o.contact_role && ` · ${o.contact_role}`}</Pill></Link>)}
                    </div>
                  </TableCell>
                  <TableCell className="text-sm">{c.email ?? '–'}</TableCell>
                  <TableCell className="text-sm">{c.phone ?? '–'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Section>
      )}
      <ContactFormDialog open={creating} onOpenChange={setCreating} />
    </>
  )
}
