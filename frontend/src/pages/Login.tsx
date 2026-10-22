import { useEffect, useState, type FormEvent } from 'react'
import { ArrowRight, Loader2 } from 'lucide-react'
import { useAuth } from '@/contexts/AuthContext'
import api, { setTokens } from '@/lib/api'
import { useT } from '@/lib/i18n'
import { setLang, usePrefs } from '@/lib/prefs'
import { Avatar, Pill } from '@/components/kit'
import { LogoMark } from '@/components/AppShell'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

interface DemoUser {
  email: string
  display_name: string
  job_title: string | null
  access_level: string
  avatar_color: string
}

export default function Login() {
  const { t } = useT()
  const { lang } = usePrefs()
  const { signIn, refresh } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [demo, setDemo] = useState<DemoUser[]>([])

  useEffect(() => {
    api
      .get<{ enabled: boolean; users: DemoUser[] }>('/auth/demo-users')
      .then((r) => setDemo(r.data.users))
      .catch(() => setDemo([]))
  }, [])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    const res = await signIn(email.trim(), password)
    if (res.error) setError(res.error)
    setBusy(false)
  }

  const demoLogin = async (address: string) => {
    setBusy(true)
    setError(null)
    try {
      const res = await api.post<{ access_token: string; refresh_token: string }>('/auth/demo-login', { email: address })
      setTokens(res.data.access_token, res.data.refresh_token)
      await refresh()
    } catch {
      setError(t('Demo login is not available.'))
    }
    setBusy(false)
  }

  const featured = demo.filter((d) => ['anna.berger', 'markus.huber', 'lena.fischer', 'eva.lang'].some((p) => d.email.startsWith(p)))

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      <section className="relative hidden overflow-hidden bg-sidebar p-12 text-sidebar-foreground lg:flex lg:flex-col lg:justify-between">
        <svg className="pointer-events-none absolute -right-24 -top-24 h-[34rem] w-[34rem] opacity-30" viewBox="0 0 400 400" aria-hidden>
          <circle cx="200" cy="200" r="190" fill="none" stroke="hsl(16 63% 52%)" strokeWidth="1.5" />
          <circle cx="150" cy="170" r="90" fill="hsl(16 63% 52% / 0.18)" stroke="hsl(16 63% 52%)" />
          <circle cx="262" cy="230" r="70" fill="hsl(160 52% 40% / 0.2)" stroke="hsl(160 52% 40%)" />
          <circle cx="230" cy="120" r="36" fill="hsl(40 82% 50% / 0.2)" stroke="hsl(40 82% 50%)" />
        </svg>
        <div className="reveal flex items-center gap-3">
          <LogoMark className="h-10 w-10" />
          <span className="font-display text-3xl font-semibold">CircleOS</span>
        </div>
        <div className="relative max-w-xl">
          <h1 className="reveal font-display text-5xl font-medium leading-[1.05] text-sidebar-foreground" style={{ ['--i' as string]: 1 }}>
            {t('The operating system for self-organizing organizations.')}
          </h1>
          <ul className="mt-8 space-y-3 text-base text-sidebar-foreground/80">
            {[
              'People hold roles.',
              'Roles carry responsibilities.',
              'Decisions follow explicit authority.',
              'Work creates organizational progress.',
            ].map((line, i) => (
              <li key={line} className="reveal flex items-center gap-3" style={{ ['--i' as string]: i + 3 }}>
                <span className="font-mono-label text-sidebar-primary">0{i + 1}</span>
                {t(line)}
              </li>
            ))}
          </ul>
        </div>
        <p className="text-xs text-sidebar-foreground/50">{t('Holacracy, Sociocracy and custom governance models - configurable, never hardcoded.')}</p>
      </section>

      <section className="flex items-center justify-center p-6 md:p-12">
        <div className="pop-in w-full max-w-md">
          <div className="mb-8 flex items-center justify-between">
            <h2 className="font-display text-3xl font-semibold">{t('Sign in')}</h2>
            <Button variant="ghost" size="sm" onClick={() => setLang(lang === 'en' ? 'de' : 'en')}>{lang === 'en' ? 'Deutsch' : 'English'}</Button>
          </div>
          <form onSubmit={submit} className="grid gap-4">
            <div className="grid gap-1.5">
              <Label htmlFor="email">{t('Email')}</Label>
              <Input id="email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="password">{t('Password')}</Label>
              <Input id="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
            </div>
            {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
            <Button type="submit" disabled={busy} className="h-11">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : t('Sign in')}
            </Button>
          </form>

          {demo.length > 0 && (
            <div className="mt-8">
              <div className="mb-3 flex items-center gap-2">
                <span className="font-mono-label text-muted-foreground">{t('Explore the demo as')}</span>
                <Pill tone="ochre">{t('Demonstration data')}</Pill>
              </div>
              <div className="grid gap-2">
                {featured.map((d) => (
                  <button
                    key={d.email}
                    type="button"
                    disabled={busy}
                    onClick={() => demoLogin(d.email)}
                    className="paper-card interactive flex items-center gap-3 p-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <Avatar name={d.display_name} color={d.avatar_color} size={36} />
                    <span className="flex-1">
                      <span className="block text-sm font-medium">{d.display_name}</span>
                      <span className="block text-xs text-muted-foreground">{d.job_title}</span>
                    </span>
                    {d.access_level === 'org_admin' && <Pill tone="primary">{t('Administrator')}</Pill>}
                    {d.access_level === 'observer' && <Pill>{t('Observer')}</Pill>}
                    <ArrowRight className="h-4 w-4 text-muted-foreground" />
                  </button>
                ))}
              </div>
              <p className="mt-3 text-xs text-muted-foreground">{t('All 12 demo accounts use the same password:')} <code className="font-mono">Demo-Circle-2025!</code></p>
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
