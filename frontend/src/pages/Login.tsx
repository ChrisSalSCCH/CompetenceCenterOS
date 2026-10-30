import { useEffect, useState, type FormEvent } from 'react'
import { ArrowRight, Eye, EyeOff, Loader2 } from 'lucide-react'
import { useAuth } from '@/contexts/AuthContext'
import api, { setTokens } from '@/lib/api'
import { useT } from '@/lib/i18n'
import { setLang, usePrefs } from '@/lib/prefs'
import { cn } from '@/lib/utils'
import { Avatar, Pill } from '@/components/kit'
import { KernelWordmark } from '@/components/brand/KernelBrand'
import { NetworkGraphic } from '@/components/brand/NetworkGraphic'
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

interface FieldErrors {
  email?: string
  password?: string
}

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const TAGLINE = 'The operating system for your organization.'

export default function Login() {
  const { t } = useT()
  const { lang } = usePrefs()
  const { signIn, refresh } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [demo, setDemo] = useState<DemoUser[]>([])

  useEffect(() => {
    api
      .get<{ enabled: boolean; users: DemoUser[] }>('/auth/demo-users')
      .then((r) => setDemo(r.data.users))
      .catch(() => setDemo([]))
  }, [])

  const validate = (): FieldErrors => {
    const next: FieldErrors = {}
    const address = email.trim()
    if (!address) next.email = t('Enter your email address.')
    else if (!EMAIL_PATTERN.test(address)) next.email = t('Enter a valid email address.')
    if (!password) next.password = t('Enter your password.')
    return next
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    const next = validate()
    setFieldErrors(next)
    if (next.email || next.password) {
      document.getElementById(next.email ? 'email' : 'password')?.focus()
      return
    }
    setBusy(true)
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
  const invalid = 'border-destructive focus-visible:ring-destructive'

  return (
    <div className="grid min-h-screen grid-rows-[auto_1fr] md:grid-cols-2 md:grid-rows-1 lg:grid-cols-[3fr_2fr]">
      {/* Mobile header: compact, static network */}
      <header className="relative overflow-hidden bg-[#024654] text-white md:hidden">
        <NetworkGraphic variant="compact" className="absolute inset-0" />
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-r from-[#024654] via-[#024654]/70 to-transparent" />
        <div className="relative z-10 flex h-40 flex-col justify-between p-5">
          <KernelWordmark className="text-xl" markClassName="h-7 w-7" />
          <p className="max-w-[16rem] text-sm leading-snug text-white/90">{t(TAGLINE)}</p>
        </div>
      </header>

      {/* Tablet and desktop: brand experience */}
      <section className="relative hidden overflow-hidden bg-[#024654] text-white md:block" aria-label="scch/kernel">
        <NetworkGraphic variant="hero" className="absolute inset-0" />
        <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_top_right,rgba(2,70,84,0.94)_0%,rgba(2,70,84,0.6)_38%,rgba(2,70,84,0)_72%)]" />
        <div className="relative z-10 flex h-full min-h-screen flex-col justify-between p-10 lg:p-14">
          <div className="reveal">
            <KernelWordmark className="text-2xl lg:text-3xl" markClassName="h-9 w-9" />
          </div>
          <div className="max-w-xl">
            <div className="reveal mb-6 h-1 w-14 rounded-full bg-[#01F000]" style={{ ['--i' as string]: 1 }} />
            <p className="reveal text-4xl font-semibold leading-[1.05] tracking-tight lg:text-6xl" style={{ ['--i' as string]: 2 }}>{t(TAGLINE)}</p>
            <p className="reveal mt-5 max-w-md text-base text-white/85 lg:text-lg" style={{ ['--i' as string]: 3 }}>{t('Connecting people, projects, knowledge and intelligence.')}</p>
            <p className="reveal mt-10 text-xs tracking-wide text-white/70" style={{ ['--i' as string]: 4 }}>Software Competence Center Hagenberg</p>
          </div>
        </div>
      </section>

      <section className="kernel-login-form flex items-start justify-center p-6 md:items-center md:p-10 lg:p-14">
        <div className="pop-in w-full max-w-md">
          <div className="mb-8 flex items-start justify-between gap-4">
            <div>
              <h1 className="text-3xl font-semibold tracking-tight">{t('Welcome to kernel')}</h1>
              <p className="mt-1.5 text-sm text-muted-foreground">{t('Sign in with your account to continue.')}</p>
            </div>
            <Button variant="ghost" size="sm" className="shrink-0" onClick={() => setLang(lang === 'en' ? 'de' : 'en')}>{lang === 'en' ? 'Deutsch' : 'English'}</Button>
          </div>

          <form onSubmit={submit} noValidate className="grid gap-4">
            <div className="grid gap-1.5">
              <Label htmlFor="email">{t('Email')}</Label>
              <Input
                id="email"
                type="email"
                autoComplete="username"
                value={email}
                aria-invalid={fieldErrors.email ? true : undefined}
                aria-describedby={fieldErrors.email ? 'email-error' : undefined}
                className={cn('h-11', fieldErrors.email && invalid)}
                onChange={(e) => {
                  setEmail(e.target.value)
                  if (fieldErrors.email) setFieldErrors((f) => ({ ...f, email: undefined }))
                }}
              />
              {fieldErrors.email && <p id="email-error" role="alert" className="text-sm text-destructive">{fieldErrors.email}</p>}
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="password">{t('Password')}</Label>
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  value={password}
                  aria-invalid={fieldErrors.password ? true : undefined}
                  aria-describedby={fieldErrors.password ? 'password-error' : undefined}
                  className={cn('h-11 pr-11', fieldErrors.password && invalid)}
                  onChange={(e) => {
                    setPassword(e.target.value)
                    if (fieldErrors.password) setFieldErrors((f) => ({ ...f, password: undefined }))
                  }}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? t('Hide password') : t('Show password')}
                  aria-pressed={showPassword}
                  className="absolute right-1 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" aria-hidden /> : <Eye className="h-4 w-4" aria-hidden />}
                </button>
              </div>
              {fieldErrors.password && <p id="password-error" role="alert" className="text-sm text-destructive">{fieldErrors.password}</p>}
            </div>
            {error && <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">{error}</p>}
            <Button type="submit" disabled={busy} className="h-11 w-full bg-[#024654] text-white transition-colors hover:bg-[#013642] focus-visible:ring-[#024654]">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-label="..." /> : t('Sign in')}
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
                    <ArrowRight className="h-4 w-4 text-muted-foreground" aria-hidden />
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
