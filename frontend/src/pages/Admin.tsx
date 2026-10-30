import { useState } from 'react'
import { Download, KeyRound, Plus, RotateCcw } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Avatar, ErrorBlock, LoadingBlock, PageHeader, PlannedNotice, Pill, Section } from '@/components/kit'
import { useSession } from '@/contexts/SessionContext'
import api from '@/lib/api'
import { fmtDateTime, useAct, useGet } from '@/lib/hooks'
import { useT } from '@/lib/i18n'
import type { AccessLevel, GovMode } from '@/lib/types'

interface AdminUser { id: string; email: string; name: string; access_level: AccessLevel; job_title: string | null; active: boolean }
interface AuditRow { id: string; action: string; summary: string; created_at: string; actor_name: string | null }
interface AiConfig { name: string; base_url: string; model: string; enabled: boolean; has_key: boolean }
interface OrgSettings { id: string; name: string; default_governance_mode: GovMode; is_demo: boolean }

const LEVELS: [AccessLevel, string][] = [['org_admin', 'Organization administrator'], ['member', 'Member'], ['observer', 'Read-only observer']]

function UsersTab() {
  const { t } = useT()
  const act = useAct()
  const { data, isLoading, error } = useGet<AdminUser[]>('/admin/users')
  const [open, setOpen] = useState(false)
  const [pwFor, setPwFor] = useState<AdminUser | null>(null)
  const [pw, setPw] = useState('')
  const [f, setF] = useState({ email: '', display_name: '', password: '', access_level: 'member', job_title: '' })
  const create = async () => {
    const res = await act('post', '/admin/users', { ...f, job_title: f.job_title || null })
    if (res) { setOpen(false); setF({ email: '', display_name: '', password: '', access_level: 'member', job_title: '' }) }
  }
  return (
    <Section title={t('Users & permissions')} action={<Button size="sm" onClick={() => setOpen(true)}><Plus className="mr-1 h-4 w-4" />{t('New user')}</Button>}>
      <p className="mb-4 text-xs text-muted-foreground">{t('Access levels are organization-wide. Governance authority comes from roles flagged with governance authority, not from the access level; holding a role never grants administrator rights.')}</p>
      {isLoading && <LoadingBlock rows={3} />}
      {error && <ErrorBlock message={error.message} />}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead><tr className="border-b text-left text-xs text-muted-foreground"><th className="py-2">{t('Name')}</th><th>{t('Access level')}</th><th>{t('Active')}</th><th /></tr></thead>
          <tbody>
            {data?.map((u) => (
              <tr key={u.id} className="border-b last:border-0">
                <td className="py-2"><span className="flex items-center gap-2"><Avatar name={u.name} size={26} /><span><span className="block font-medium">{u.name}</span><span className="block text-xs text-muted-foreground">{u.email}</span></span></span></td>
                <td>
                  <Select value={u.access_level} onValueChange={(v) => act('patch', `/admin/users/${u.id}`, { access_level: v })}>
                    <SelectTrigger className="w-56" aria-label={`${t('Access level')}: ${u.name}`}><SelectValue /></SelectTrigger>
                    <SelectContent>{LEVELS.map(([k, l]) => <SelectItem key={k} value={k}>{t(l)}</SelectItem>)}</SelectContent>
                  </Select>
                </td>
                <td><Switch checked={u.active} onCheckedChange={(v) => act('patch', `/admin/users/${u.id}`, { active: v })} aria-label={`${t('Active')}: ${u.name}`} /></td>
                <td className="text-right"><Button size="sm" variant="ghost" onClick={() => setPwFor(u)}><KeyRound className="mr-1 h-4 w-4" />{t('Password')}</Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle className="font-display text-xl">{t('New user')}</DialogTitle><DialogDescription>{t('Passwords are stored as salted hashes. Minimum 10 characters with a letter and a digit.')}</DialogDescription></DialogHeader>
          <div className="grid gap-3">
            <div className="grid gap-1.5"><Label htmlFor="u-name">{t('Name')}</Label><Input id="u-name" value={f.display_name} maxLength={120} onChange={(e) => setF({ ...f, display_name: e.target.value })} /></div>
            <div className="grid gap-1.5"><Label htmlFor="u-mail">{t('Email')}</Label><Input id="u-mail" type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></div>
            <div className="grid gap-1.5"><Label htmlFor="u-pw">{t('Initial password')}</Label><Input id="u-pw" type="password" autoComplete="new-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-1.5"><Label>{t('Access level')}</Label><Select value={f.access_level} onValueChange={(v) => setF({ ...f, access_level: v })}><SelectTrigger aria-label={t('Access level')}><SelectValue /></SelectTrigger><SelectContent>{LEVELS.map(([k, l]) => <SelectItem key={k} value={k}>{t(l)}</SelectItem>)}</SelectContent></Select></div>
              <div className="grid gap-1.5"><Label htmlFor="u-job">{t('Job title')}</Label><Input id="u-job" value={f.job_title} maxLength={120} onChange={(e) => setF({ ...f, job_title: e.target.value })} /></div>
            </div>
          </div>
          <DialogFooter><Button variant="outline" onClick={() => setOpen(false)}>{t('Cancel')}</Button><Button onClick={create} disabled={!f.email || f.display_name.length < 2 || f.password.length < 10}>{t('Create user')}</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={pwFor !== null} onOpenChange={(v) => !v && setPwFor(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle className="font-display text-xl">{t('Set a new password')}: {pwFor?.name}</DialogTitle></DialogHeader>
          <div className="grid gap-1.5"><Label htmlFor="npw">{t('New password')}</Label><Input id="npw" type="password" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} /></div>
          <DialogFooter><Button variant="outline" onClick={() => setPwFor(null)}>{t('Cancel')}</Button><Button disabled={pw.length < 10} onClick={async () => { if (await act('post', `/admin/users/${pwFor?.id}/password`, { password: pw })) { toast.success(t('Password updated.')); setPwFor(null); setPw('') } }}>{t('Save')}</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </Section>
  )
}

function GovernanceTab() {
  const { t } = useT()
  const act = useAct()
  const { data } = useGet<OrgSettings>('/admin/org')
  const [name, setName] = useState<string | null>(null)
  if (!data) return <LoadingBlock rows={2} />
  return (
    <Section title={t('Organization & governance defaults')}>
      <div className="grid max-w-xl gap-4">
        <div className="grid gap-1.5">
          <Label htmlFor="o-name">{t('Organization name')}</Label>
          <div className="flex gap-2">
            <Input id="o-name" value={name ?? data.name} maxLength={120} onChange={(e) => setName(e.target.value)} />
            <Button variant="outline" disabled={name === null || name.trim().length < 2} onClick={async () => { if (await act('patch', '/admin/org', { name })) setName(null) }}>{t('Save')}</Button>
          </div>
        </div>
        <div className="grid gap-1.5">
          <Label>{t('Default governance workflow')}</Label>
          <Select value={data.default_governance_mode} onValueChange={(v) => act('patch', '/admin/org', { default_governance_mode: v })}>
            <SelectTrigger aria-label={t('Default governance workflow')}><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="direct">{t('Direct change')}</SelectItem>
              <SelectItem value="approval">{t('Approval')}</SelectItem>
              <SelectItem value="consent">{t('Consent')}</SelectItem>
              <SelectItem value="holacracy">{t('Structured (Holacracy)')}</SelectItem>
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">{t('Circles inherit this workflow unless they define their own (circle settings). No framework is hardcoded.')}</p>
        </div>
      </div>
    </Section>
  )
}

function AiTab() {
  const { t } = useT()
  const act = useAct()
  const { data } = useGet<AiConfig>('/admin/ai')
  const [f, setF] = useState<{ name: string; base_url: string; model: string; api_key: string; enabled: boolean } | null>(null)
  const [result, setResult] = useState<string | null>(null)
  if (!data) return <LoadingBlock rows={2} />
  const form = f ?? { name: data.name || 'Custom provider', base_url: data.base_url, model: data.model, api_key: '', enabled: data.enabled }
  const save = async () => {
    const res = await act('put', '/admin/ai', { ...form, api_key: form.api_key || null })
    if (res) { setF(null); toast.success(t('AI provider saved.')) }
  }
  const test = async () => {
    try {
      const res = await api.post<{ ok: boolean; message: string }>('/admin/ai/test')
      setResult(`${res.data.ok ? 'OK' : t('Failed')}: ${res.data.message}`)
    } catch {
      setResult(t('Failed'))
    }
  }
  return (
    <div className="space-y-4">
      <Section title={t('Language model provider')}>
        <p className="mb-4 max-w-2xl text-sm text-muted-foreground">{t('Any OpenAI-compatible chat endpoint works: hosted providers or an internal on-premise service. Calls are made by the server; the key is stored encrypted and never sent to the browser. Without a provider the assistant stays fully usable with deterministic answers.')}</p>
        <div className="grid max-w-xl gap-3">
          <div className="grid gap-1.5"><Label htmlFor="ai-name">{t('Display name')}</Label><Input id="ai-name" value={form.name} maxLength={80} onChange={(e) => setF({ ...form, name: e.target.value })} /></div>
          <div className="grid gap-1.5"><Label htmlFor="ai-url">{t('API endpoint (base URL)')}</Label><Input id="ai-url" value={form.base_url} placeholder="https://api.openai.com/v1" maxLength={300} onChange={(e) => setF({ ...form, base_url: e.target.value })} /></div>
          <div className="grid gap-1.5"><Label htmlFor="ai-model">{t('Model name')}</Label><Input id="ai-model" value={form.model} maxLength={120} onChange={(e) => setF({ ...form, model: e.target.value })} /></div>
          <div className="grid gap-1.5"><Label htmlFor="ai-key">{t('API key')}</Label><Input id="ai-key" type="password" autoComplete="off" value={form.api_key} placeholder={data.has_key ? t('stored - leave empty to keep') : ''} onChange={(e) => setF({ ...form, api_key: e.target.value })} /></div>
          <label className="flex items-center gap-2 text-sm"><Switch checked={form.enabled} onCheckedChange={(v) => setF({ ...form, enabled: v })} />{t('Enable generative answers')}</label>
          <div className="flex flex-wrap items-center gap-2">
            <Button onClick={save}>{t('Save')}</Button>
            <Button variant="outline" onClick={test} disabled={!data.base_url}>{t('Test connection')}</Button>
            {data.enabled ? <Pill tone="forest">{t('active')}</Pill> : <Pill>{t('disabled')}</Pill>}
          </div>
          {result && <p role="status" className="text-sm">{result}</p>}
        </div>
      </Section>
      <PlannedNotice>{t('MCP server for external agents, AI agents that hold governed roles, and semantic search with embeddings are planned for a later phase.')}</PlannedNotice>
    </div>
  )
}

function AuditTab() {
  const { t, lang } = useT()
  const { data, isLoading } = useGet<AuditRow[]>('/admin/audit', { limit: 150 })
  return (
    <Section title={t('Audit log')}>
      {isLoading && <LoadingBlock rows={3} />}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead><tr className="border-b text-left text-xs text-muted-foreground"><th className="py-2">{t('When')}</th><th>{t('Who')}</th><th>{t('Action')}</th><th>{t('Details')}</th></tr></thead>
          <tbody>{data?.map((a) => <tr key={a.id} className="border-b last:border-0"><td className="py-1.5 pr-3 whitespace-nowrap text-xs text-muted-foreground">{fmtDateTime(a.created_at, lang)}</td><td className="pr-3">{a.actor_name ?? '–'}</td><td className="pr-3"><Pill>{a.action}</Pill></td><td>{a.summary}</td></tr>)}</tbody>
        </table>
      </div>
    </Section>
  )
}

function DataTab() {
  const { t } = useT()
  const act = useAct()
  const { session } = useSession()
  const exportData = async () => {
    try {
      const res = await api.get('/admin/export')
      const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `kernel-export-${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      toast.error(t('Export failed.'))
    }
  }
  return (
    <div className="space-y-4">
      <Section title={t('Export')}>
        <p className="mb-3 text-sm text-muted-foreground">{t('Download all data of this organization (structure, governance history, work, goals, audit log) as JSON.')}</p>
        <Button variant="outline" onClick={exportData}><Download className="mr-1 h-4 w-4" />{t('Export JSON')}</Button>
      </Section>
      <Section title={t('Backup & restore')}>
        <p className="text-sm text-muted-foreground">{t('All data lives in PostgreSQL. Back it up with pg_dump (see docs/operations.md) and restore with pg_restore into an empty database; migrations are versioned and re-run safely.')}</p>
      </Section>
      {session?.organization.is_demo && (
        <Section title={t('Demonstration data')}>
          <p className="mb-3 text-sm text-muted-foreground">{t('Reset the sample organization to its original state. All changes to this organization are lost.')}</p>
          <ConfirmDialog
            trigger={<Button variant="destructive"><RotateCcw className="mr-1 h-4 w-4" />{t('Reset demo data')}</Button>}
            title={t('Reset demonstration data?')}
            description={t('This deletes every change made in the demonstration organization and recreates the original sample content.')}
            onConfirm={async () => { if (await act('post', '/admin/reset-demo')) toast.success(t('Demonstration data reset.')) }}
          />
        </Section>
      )}
    </div>
  )
}

export default function Admin() {
  const { t } = useT()
  const { isAdmin } = useSession()
  if (!isAdmin) return <ErrorBlock message={t('Administrator permission required.')} />
  return (
    <>
      <PageHeader title={t('Administration')} subtitle={t('Users, governance defaults, AI provider, audit log and data management.')} />
      <Tabs defaultValue="users" className="space-y-4">
        <TabsList className="h-auto flex-wrap">
          <TabsTrigger value="users">{t('Users')}</TabsTrigger>
          <TabsTrigger value="governance">{t('Governance')}</TabsTrigger>
          <TabsTrigger value="ai">{t('AI provider')}</TabsTrigger>
          <TabsTrigger value="audit">{t('Audit log')}</TabsTrigger>
          <TabsTrigger value="data">{t('Data')}</TabsTrigger>
        </TabsList>
        <TabsContent value="users"><UsersTab /></TabsContent>
        <TabsContent value="governance"><GovernanceTab /></TabsContent>
        <TabsContent value="ai"><AiTab /></TabsContent>
        <TabsContent value="audit"><AuditTab /></TabsContent>
        <TabsContent value="data"><DataTab /></TabsContent>
      </Tabs>
    </>
  )
}
