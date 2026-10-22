import { createContext, useContext, useEffect, useMemo, useState, ReactNode } from 'react'
import api, { getAccessToken, clearTokens, setTokens } from '@/lib/api'

// Email/password auth only. No OAuth providers, no magic-link.
// All auth goes through the app's own FastAPI backend.

export interface AppUser {
  id: string
  email: string
  display_name: string | null
  created_at: string
}

interface TokenPair {
  access_token: string
  refresh_token: string
  token_type?: string
}

interface AuthContextValue {
  user: AppUser | null
  loading: boolean
  // Whether public self-registration is enabled for this app. When false the
  // backend rejects POST /auth/signup with 403 (admin-only app) — gate your
  // Signup page/route on this so closed apps only show Login.
  publicSignupEnabled: boolean
  signIn: (email: string, password: string) => Promise<{ error?: string }>
  signUp: (email: string, password: string, displayName?: string) => Promise<{ error?: string }>
  signOut: () => Promise<void>
  refresh: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

function extractError(err: unknown): string {
  const anyErr = err as { response?: { data?: { detail?: string } }; message?: string }
  return anyErr?.response?.data?.detail || anyErr?.message || 'Unknown error'
}

export function AuthProvider({ children }: Readonly<{ children: ReactNode }>) {
  const [user, setUser] = useState<AppUser | null>(null)
  const [loading, setLoading] = useState(true)
  const [publicSignupEnabled, setPublicSignupEnabled] = useState(true)

  const fetchMe = async () => {
    try {
      const res = await api.get<AppUser>('/auth/me')
      setUser(res.data)
    } catch {
      setUser(null)
    }
  }

  useEffect(() => {
    const token = getAccessToken()
    if (!token) {
      setLoading(false)
      return
    }
    fetchMe().finally(() => setLoading(false))
  }, [])

  // Discover whether self-registration is enabled. Independent of auth state.
  // On error we leave it enabled (the common case); the backend endpoint still
  // enforces the real gate, so this only affects which pages the UI renders.
  useEffect(() => {
    api
      .get<{ public_signup_enabled: boolean }>('/auth/config')
      .then((res) => setPublicSignupEnabled(res.data.public_signup_enabled))
      .catch(() => setPublicSignupEnabled(true))
  }, [])

  const signIn: AuthContextValue['signIn'] = async (email, password) => {
    try {
      const res = await api.post<TokenPair>('/auth/login', { email, password })
      setTokens(res.data.access_token, res.data.refresh_token)
      await fetchMe()
      return {}
    } catch (err) {
      return { error: extractError(err) }
    }
  }

  const signUp: AuthContextValue['signUp'] = async (email, password, displayName) => {
    try {
      const res = await api.post<TokenPair>('/auth/signup', {
        email,
        password,
        display_name: displayName,
      })
      setTokens(res.data.access_token, res.data.refresh_token)
      await fetchMe()
      return {}
    } catch (err) {
      return { error: extractError(err) }
    }
  }

  const signOut = async () => {
    try {
      await api.post('/auth/logout')
    } catch {
      // Even if the server call fails we still clear local state.
    }
    clearTokens()
    setUser(null)
  }

  // Memoize so the Provider value identity is stable between renders (it only
  // changes when user/loading/publicSignupEnabled change). The handler closures
  // capture only stable refs (state setters, the api client), so they need not
  // be dependencies.
  const value = useMemo<AuthContextValue>(
    // eslint-disable-next-line react-hooks/exhaustive-deps
    () => ({ user, loading, publicSignupEnabled, signIn, signUp, signOut, refresh: fetchMe }),
    [user, loading, publicSignupEnabled],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
