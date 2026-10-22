import { useEffect, useState, type ReactNode } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router'
import {
  Bell, CalendarDays, Languages, LayoutDashboard, LogOut, Menu, Moon, Network, Scale, Search, Settings2, Sparkles, Sun, Target, UserCircle2, Users, KanbanSquare,
} from 'lucide-react'
import { toast } from 'sonner'
import { useAuth } from '@/contexts/AuthContext'
import { useSession } from '@/contexts/SessionContext'
import { useT } from '@/lib/i18n'
import { setLang, setTheme, usePrefs } from '@/lib/prefs'
import { useAct, useGet, fmtDateTime } from '@/lib/hooks'
import { Avatar, Pill } from '@/components/kit'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetTitle, SheetDescription } from '@/components/ui/sheet'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { SearchPalette } from '@/components/SearchPalette'
import { ProfileDialog } from '@/components/ProfileDialog'
import { cn } from '@/lib/utils'

export function LogoMark({ className }: Readonly<{ className?: string }>) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <circle cx="16" cy="16" r="14" fill="none" stroke="currentColor" strokeWidth="2" />
      <circle cx="11" cy="14" r="5" fill="hsl(16 63% 52%)" />
      <circle cx="21" cy="18" r="4" fill="currentColor" opacity="0.85" />
    </svg>
  )
}

interface NavDef {
  to: string
  label: string
  icon: typeof Network
  admin?: boolean
  end?: boolean
}

const NAV: NavDef[] = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/organization', label: 'Organization', icon: Network },
  { to: '/my-roles', label: 'My Roles', icon: UserCircle2 },
  { to: '/people', label: 'People', icon: Users },
  { to: '/governance', label: 'Governance', icon: Scale },
  { to: '/meetings', label: 'Meetings', icon: CalendarDays },
  { to: '/work', label: 'Projects & Tasks', icon: KanbanSquare },
  { to: '/goals', label: 'Goals & Metrics', icon: Target },
  { to: '/assistant', label: 'AI Assistant', icon: Sparkles },
  { to: '/admin', label: 'Administration', icon: Settings2, admin: true },
]

function NavList({ onNavigate }: Readonly<{ onNavigate?: () => void }>) {
  const { t } = useT()
  const { isAdmin } = useSession()
  return (
    <nav aria-label={t('Main navigation')} className="flex flex-col gap-0.5">
      {NAV.filter((n) => !n.admin || isAdmin).map((n) => (
        <NavLink
          key={n.to}
          to={n.to}
          end={n.end}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              'group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-sidebar-foreground/80 transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring',
              isActive && 'bg-sidebar-accent text-sidebar-accent-foreground',
            )
          }
        >
          {({ isActive }) => (
            <>
              <span className={cn('absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full bg-sidebar-primary transition-opacity', isActive ? 'opacity-100' : 'opacity-0')} />
              <n.icon className="h-4 w-4 shrink-0" aria-hidden />
              {t(n.label)}
            </>
          )}
        </NavLink>
      ))}
    </nav>
  )
}

function Brand() {
  const { session } = useSession()
  return (
    <div className="px-3">
      <div className="flex items-center gap-2 text-sidebar-foreground">
        <LogoMark className="h-8 w-8" />
        <span className="font-display text-2xl font-semibold tracking-tight">CircleOS</span>
      </div>
      <p className="mt-1 truncate text-xs text-sidebar-foreground/60">{session?.organization.name}</p>
    </div>
  )
}

interface NotificationItem {
  id: string
  title: string
  body: string
  link: string | null
  read_at: string | null
  created_at: string
}

function NotificationBell() {
  const { t, lang } = useT()
  const { session } = useSession()
  const navigate = useNavigate()
  const act = useAct()
  const [open, setOpen] = useState(false)
  const { data } = useGet<NotificationItem[]>(open ? '/notifications' : null)
  const unread = session?.unread_notifications ?? 0
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" className="relative" aria-label={t('Notifications')}>
          <Bell className="h-5 w-5" />
          {unread > 0 && (
            <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-semibold text-primary-foreground">{unread}</span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[22rem] p-0">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <span className="font-display text-base font-semibold">{t('Notifications')}</span>
          <Button variant="ghost" size="sm" onClick={() => act('post', '/notifications/read-all')}>{t('Mark all as read')}</Button>
        </div>
        <div className="max-h-96 overflow-y-auto">
          {(data ?? []).length === 0 && <p className="p-6 text-center text-sm text-muted-foreground">{t('You are all caught up.')}</p>}
          {(data ?? []).map((n) => (
            <button
              key={n.id}
              type="button"
              className={cn('block w-full border-b px-4 py-3 text-left text-sm transition-colors hover:bg-muted focus-visible:bg-muted focus-visible:outline-none', !n.read_at && 'bg-primary/5')}
              onClick={async () => {
                await act('post', `/notifications/${n.id}/read`)
                setOpen(false)
                if (n.link) navigate(n.link)
              }}
            >
              <span className="flex items-start gap-2">
                {!n.read_at && <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-primary" aria-label={t('unread')} />}
                <span>
                  <span className="block font-medium">{n.title}</span>
                  <span className="text-xs text-muted-foreground">{fmtDateTime(n.created_at, lang)}</span>
                </span>
              </span>
            </button>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  )
}

function UserMenu() {
  const { t } = useT()
  const { session } = useSession()
  const { signOut } = useAuth()
  const { lang, theme } = usePrefs()
  const [profileOpen, setProfileOpen] = useState(false)
  if (!session) return null
  const levelLabel: Record<string, string> = { org_admin: 'Organization administrator', member: 'Member', observer: 'Read-only observer' }
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" className="gap-2 px-2" aria-label={t('Profile')}>
            <Avatar name={session.user.name} color={session.user.avatar_color} size={30} />
            <span className="hidden text-left text-sm leading-tight md:block">
              <span className="block font-medium">{session.user.name}</span>
              <span className="block text-[11px] text-muted-foreground">{t(levelLabel[session.access_level])}</span>
            </span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-60">
          <DropdownMenuLabel className="font-normal">
            <span className="block font-medium">{session.user.name}</span>
            <span className="block text-xs text-muted-foreground">{session.user.email}</span>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => setProfileOpen(true)}>{t('My profile & notifications')}</DropdownMenuItem>
          <DropdownMenuItem onSelect={() => setLang(lang === 'en' ? 'de' : 'en')}>
            <Languages className="mr-2 h-4 w-4" />
            {lang === 'en' ? 'Deutsch' : 'English'}
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => setTheme(theme === 'dark' ? 'light' : 'dark')}>
            {theme === 'dark' ? <Sun className="mr-2 h-4 w-4" /> : <Moon className="mr-2 h-4 w-4" />}
            {theme === 'dark' ? t('Light mode') : t('Dark mode')}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => signOut()}>
            <LogOut className="mr-2 h-4 w-4" />
            {t('Sign out')}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <ProfileDialog open={profileOpen} onOpenChange={setProfileOpen} />
    </>
  )
}

export function AppShell({ children }: Readonly<{ children?: ReactNode }>) {
  const { t } = useT()
  const { session } = useSession()
  const { signOut } = useAuth()
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setSearchOpen((v) => !v)
      }
    }
    const onSignedOut = () => {
      toast.message(t('Your session expired. Please sign in again.'))
      signOut()
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('circleos:signed-out', onSignedOut)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('circleos:signed-out', onSignedOut)
    }
  }, [signOut, t])

  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [location.pathname])

  return (
    <div className="min-h-screen lg:pl-64">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-foreground">
        {t('Skip to content')}
      </a>
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col gap-6 bg-sidebar py-5 text-sidebar-foreground lg:flex">
        <Brand />
        <div className="flex-1 overflow-y-auto px-2">
          <NavList />
        </div>
        <p className="px-5 text-[11px] leading-snug text-sidebar-foreground/50">{t('People hold roles. Roles carry responsibilities. Decisions follow explicit authority.')}</p>
      </aside>

      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent side="left" className="w-72 border-none bg-sidebar p-0 py-5 text-sidebar-foreground">
          <SheetTitle className="sr-only">{t('Main navigation')}</SheetTitle>
          <SheetDescription className="sr-only">{t('Navigate between modules')}</SheetDescription>
          <div className="flex flex-col gap-6">
            <Brand />
            <div className="px-2">
              <NavList onNavigate={() => setMobileOpen(false)} />
            </div>
          </div>
        </SheetContent>
      </Sheet>

      <header className="sticky top-0 z-20 flex h-16 items-center gap-2 border-b bg-background/85 px-3 backdrop-blur md:px-6">
        <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setMobileOpen(true)} aria-label={t('Open navigation')}>
          <Menu className="h-5 w-5" />
        </Button>
        <button
          type="button"
          onClick={() => setSearchOpen(true)}
          className="flex h-10 max-w-xl flex-1 items-center gap-2 rounded-full border bg-card px-4 text-sm text-muted-foreground shadow-sm transition-colors hover:border-primary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label={t('Search')}
        >
          <Search className="h-4 w-4" aria-hidden />
          <span className="flex-1 truncate text-left">{t('Search roles, responsibilities, people, projects...')}</span>
          <kbd className="hidden rounded border bg-muted px-1.5 font-mono text-[10px] md:inline">Ctrl K</kbd>
        </button>
        <div className="ml-auto flex items-center gap-1">
          <NotificationBell />
          <UserMenu />
        </div>
      </header>

      {session?.organization.is_demo && (
        <div className="flex flex-wrap items-center gap-2 border-b border-[hsl(var(--ochre)/0.3)] bg-[hsl(var(--ochre)/0.08)] px-4 py-1.5 text-xs md:px-6">
          <Pill tone="ochre">{t('Demonstration data')}</Pill>
          <span className="text-muted-foreground">{t('This organization is fictional sample content. You can edit it; administrators can reset it in Administration.')}</span>
        </div>
      )}

      <main id="main" className="mx-auto w-full max-w-[1400px] px-4 py-6 md:px-8 md:py-8">
        {children ?? <Outlet />}
      </main>
      <SearchPalette open={searchOpen} onOpenChange={setSearchOpen} />
    </div>
  )
}
