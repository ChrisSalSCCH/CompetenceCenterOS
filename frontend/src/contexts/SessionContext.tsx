import { createContext, useContext, useEffect, useMemo, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/contexts/AuthContext'
import { useGet } from '@/lib/hooks'
import type { Session } from '@/lib/types'

interface SessionValue {
  session: Session | null
  loading: boolean
  isAdmin: boolean
  isObserver: boolean
  canGovern: (circleId: string | null | undefined) => boolean
}

const SessionContext = createContext<SessionValue | null>(null)

export function SessionProvider({ children }: Readonly<{ children: ReactNode }>) {
  const { user } = useAuth()
  const qc = useQueryClient()
  useEffect(() => {
    // Never show cached data of a previous account after signing out.
    if (!user) qc.clear()
  }, [user, qc])
  const { data, isLoading } = useGet<Session>(user ? '/session' : null)
  const value = useMemo<SessionValue>(() => {
    const governable = new Set(data?.governable_circle_ids ?? [])
    return {
      session: data ?? null,
      loading: isLoading,
      isAdmin: data?.access_level === 'org_admin',
      isObserver: data?.access_level === 'observer',
      canGovern: (id) => (id ? governable.has(id) : false),
    }
  }, [data, isLoading])
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export function useSession(): SessionValue {
  const ctx = useContext(SessionContext)
  if (!ctx) throw new Error('useSession must be used inside <SessionProvider>')
  return ctx
}
