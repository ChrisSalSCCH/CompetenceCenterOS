import { useState } from 'react'
import { Link } from 'react-router'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { EmptyState, ErrorBlock, LoadingBlock, PageHeader, Pill, Section } from '@/components/kit'
import { fmtDate, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import { PROPOSAL_TONE, fmtMoney } from '@/lib/sales'
import type { ProposalRow, ProposalStatus } from '@/lib/sales-types'

const ANY = 'any'
const STATUSES: ProposalStatus[] = ['draft', 'in_approval', 'approved', 'submitted', 'accepted', 'rejected', 'withdrawn', 'expired']

export default function ProposalsList() {
  const { t, lang } = useT()
  const [status, setStatus] = useState(ANY)
  const { data, isLoading, error } = useGet<ProposalRow[]>('/commercial/proposals', { status: status === ANY ? undefined : status })
  return (
    <>
      <PageHeader title={t('Proposals')} subtitle={t('Every proposal keeps all its versions. Approved versions are locked.')} />
      <Section className="mb-4">
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger className="w-56" aria-label={t('Status')}><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>{t('Status')}: {t('Any')}</SelectItem>
            {STATUSES.map((s) => <SelectItem key={s} value={s}>{t(s.replaceAll('_', ' '))}</SelectItem>)}
          </SelectContent>
        </Select>
      </Section>
      {isLoading && <LoadingBlock />}
      {error && <ErrorBlock message={error.message} />}
      {data && data.length === 0 && <EmptyState title={t('No proposals yet')} hint={t('Create proposals from an opportunity after a Bid decision.')} />}
      {data && data.length > 0 && (
        <Section className="overflow-x-auto p-0 md:p-0">
          <Table>
            <TableHeader>
              <TableRow><TableHead>{t('Proposal')}</TableHead><TableHead>{t('Opportunity')}</TableHead><TableHead>{t('Customer')}</TableHead><TableHead>{t('Status')}</TableHead><TableHead>{t('Version')}</TableHead><TableHead className="text-right">{t('Total price')}</TableHead><TableHead>{t('Valid until')}</TableHead></TableRow>
            </TableHeader>
            <TableBody>
              {data.map((p) => (
                <TableRow key={p.id}>
                  <TableCell><Link to={`/sales/proposals/${p.id}`} className="font-display text-base font-semibold hover:text-primary">{p.title}</Link><div className="font-mono-label text-muted-foreground">{p.number}</div></TableCell>
                  <TableCell className="text-sm"><Link to={`/sales/opportunities/${p.opportunity_id}`} className="hover:text-primary">{p.opportunity_number}</Link></TableCell>
                  <TableCell className="text-sm">{p.customer_name}</TableCell>
                  <TableCell><Pill tone={PROPOSAL_TONE[p.status]}>{t(p.status.replaceAll('_', ' '))}</Pill></TableCell>
                  <TableCell className="text-sm">v{p.version_no ?? 1} / {p.version_count}</TableCell>
                  <TableCell className="whitespace-nowrap text-right text-sm">{fmtMoney(p.price_total, p.currency ?? 'EUR', lang)}</TableCell>
                  <TableCell className="text-sm">{fmtDate(p.valid_until, lang)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Section>
      )}
    </>
  )
}
