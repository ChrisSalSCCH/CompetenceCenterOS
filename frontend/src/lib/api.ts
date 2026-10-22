import axios, { type AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'

// VITE_API_URL is set automatically by the workspace runner.
// Value: /api  |  Fallback: empty string.
//
// IMPORTANT: Because baseURL is "/api", all calls via the `api` instance
// must use BARE paths — e.g. api.get("/tasks"), NOT api.get("/api/tasks").
// Using "/api/tasks" would produce the request path /api/api/tasks (WRONG).
const API_BASE_URL = import.meta.env.VITE_API_URL || ''

/**
 * Standard error shape returned by the backend's global exception handler.
 *
 * Backend wraps every HTTPException + Pydantic ValidationError into:
 *   { error: { code, message, field, details } }
 *
 * Code is UPPER_SNAKE_CASE and entity-prefixed (CUSTOMER_NOT_FOUND,
 * CUSTOMER_DUPLICATE_EMAIL). Use `code` for i18n lookup and `field` for
 * form error highlighting.
 */
export interface ApiErrorShape {
  code: string
  message: string
  field?: string | null
  details?: Record<string, unknown>
}

export class ApiError extends Error {
  readonly code: string
  readonly field: string | null
  readonly status: number
  readonly requestId: string | null
  readonly details: Record<string, unknown>

  constructor(
    status: number,
    shape: ApiErrorShape,
    requestId: string | null = null,
  ) {
    super(shape.message || shape.code || `HTTP ${status}`)
    this.name = 'ApiError'
    this.code = shape.code
    this.field = shape.field ?? null
    this.status = status
    this.requestId = requestId
    this.details = shape.details ?? {}
  }

  /** Convenience: does this error match a specific business code? */
  is(code: string): boolean {
    return this.code === code
  }
}

/**
 * Optional toast-like sink so consumers can display errors without
 * importing a toast library here. Set via `setApiErrorReporter(fn)`;
 * left unset by default so the template has no hard dep on sonner /
 * react-hot-toast / etc.
 */
type ErrorReporter = (err: ApiError) => void
let _reporter: ErrorReporter | null = null

export function setApiErrorReporter(fn: ErrorReporter | null): void {
  _reporter = fn
}

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// ---------------------------------------------------------------------------
// Session tokens (JWT access + refresh). The data itself lives in the database;
// only the credentials of the current browser session are kept here.
// ---------------------------------------------------------------------------
const ACCESS_KEY = 'circleos.access'
const REFRESH_KEY = 'circleos.refresh'

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_KEY)
}

export function setTokens(access: string, refresh: string): void {
  localStorage.setItem(ACCESS_KEY, access)
  localStorage.setItem(REFRESH_KEY, refresh)
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
}

let refreshing: Promise<string | null> | null = null

async function refreshAccessToken(): Promise<string | null> {
  const refresh = localStorage.getItem(REFRESH_KEY)
  if (!refresh) return null
  try {
    const res = await axios.post<{ access_token: string; refresh_token: string }>(
      `${API_BASE_URL}/auth/refresh`,
      { refresh_token: refresh },
    )
    setTokens(res.data.access_token, res.data.refresh_token)
    return res.data.access_token
  } catch {
    clearTokens()
    return null
  }
}

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = getAccessToken()
  if (token && config.headers && !config.headers.get('Authorization')) {
    config.headers.set('Authorization', `Bearer ${token}`)
  }
  return config
})

// Request interceptor — attach a fresh X-Request-ID for end-to-end tracing.
api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  if (config.headers && !config.headers.get('X-Request-ID')) {
    // 16-char hex id; collision-resistant enough for per-request tracing.
    const id =
      typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID().replace(/-/g, '').slice(0, 16)
        : Math.random().toString(16).slice(2, 18).padEnd(16, '0')
    config.headers.set('X-Request-ID', id)
  }
  return config
})

// Response interceptor — parse the standard error envelope into a typed
// ApiError, forward it to the optional reporter, and re-reject so the
// caller can still handle it with try/catch.
api.interceptors.response.use(
  (response: AxiosResponse) => response,
  async (error: AxiosError) => {
    const original = error.config as (InternalAxiosRequestConfig & { _retried?: boolean }) | undefined
    if (
      error.response?.status === 401 &&
      original &&
      !original._retried &&
      !(original.url ?? '').includes('/auth/')
    ) {
      original._retried = true
      refreshing = refreshing ?? refreshAccessToken()
      const token = await refreshing
      refreshing = null
      if (token) {
        original.headers.set('Authorization', `Bearer ${token}`)
        return api.request(original)
      }
      window.dispatchEvent(new Event('circleos:signed-out'))
    }
    if (error.response) {
      const status = error.response.status
      const data = error.response.data as { error?: ApiErrorShape } | undefined
      const requestId =
        (error.response.headers['x-request-id'] as string | undefined) ??
        (error.config?.headers?.get?.('X-Request-ID') as string | undefined) ??
        null

      const shape: ApiErrorShape =
        data?.error ?? {
          code: `HTTP_${status}`,
          message:
            (error.response.data as { detail?: string; message?: string } | undefined)
              ?.detail ??
            (error.response.data as { detail?: string; message?: string } | undefined)
              ?.message ??
            error.message,
        }

      const apiErr = new ApiError(status, shape, requestId)
      if (_reporter) {
        try {
          _reporter(apiErr)
        } catch (e) {
          // Never let a reporter failure mask the original error.
          console.error('[api] error reporter threw:', e)
        }
      }
      return Promise.reject(apiErr)
    }

    if (error.request) {
      const apiErr = new ApiError(
        0,
        { code: 'NETWORK_ERROR', message: 'No response from server' },
      )
      if (_reporter) {
        try {
          _reporter(apiErr)
        } catch {
          /* ignore */
        }
      }
      return Promise.reject(apiErr)
    }

    return Promise.reject(error)
  },
)

// ---------------------------------------------------------------------------
// Paginated response shape (matches backend PaginatedResponse model)
// ---------------------------------------------------------------------------

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  size: number
  pages: number
}

// Generic CRUD helpers.
// `endpoint` is a BARE path — "/tasks", "/customers", etc.
// The axios baseURL (/api) is prepended automatically.
// WRONG: getAll("/api/tasks")  →  GET /api/api/tasks
// RIGHT: getAll("/tasks")      →  GET /api/tasks

export async function getAll<T>(endpoint: string, params?: Record<string, unknown>): Promise<T[]> {
  const response = await api.get<T[] | { items: T[] }>(endpoint, { params })
  return Array.isArray(response.data) ? response.data : response.data.items
}

export async function getPaginated<T>(endpoint: string, params?: Record<string, unknown>): Promise<PaginatedResponse<T>> {
  const response = await api.get<PaginatedResponse<T>>(endpoint, { params })
  return response.data
}

export async function getOne<T>(endpoint: string, id: string): Promise<T> {
  const response = await api.get<T>(`${endpoint}/${id}`)
  return response.data
}

export async function create<T>(endpoint: string, data: Partial<T>): Promise<T> {
  const response = await api.post<T>(endpoint, data)
  return response.data
}

export async function update<T>(endpoint: string, id: string, data: Partial<T>): Promise<T> {
  const response = await api.put<T>(`${endpoint}/${id}`, data)
  return response.data
}

export async function remove(endpoint: string, id: string): Promise<void> {
  await api.delete(`${endpoint}/${id}`)
}

export default api
