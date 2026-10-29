import { PageHeader, PlannedNotice } from '@/components/kit'
import { useT } from '@/lib/i18n'

const COPY = {
  opportunities: { title: 'Opportunities', hint: 'Pipeline with stages, values and forecast' },
  quotes: { title: 'Quotes', hint: 'Quotes with line items, versions and approvals' },
  contracts: { title: 'NDAs & Contracts', hint: 'NDAs and contracts with validity dates and reminders' },
} as const

export default function CrmPlanned({ module }: Readonly<{ module: keyof typeof COPY }>) {
  const { t } = useT()
  const c = COPY[module]
  return (
    <>
      <PageHeader title={t(c.title)} subtitle={t('Coming in a later phase')} />
      <div className="max-w-xl space-y-3">
        <PlannedNotice>{t(c.hint)}. {t('Opportunities, quotes and contracts are not part of this version yet. The data model is prepared for them.')}</PlannedNotice>
      </div>
    </>
  )
}
