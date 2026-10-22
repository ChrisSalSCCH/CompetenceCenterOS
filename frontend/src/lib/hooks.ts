import { useCallback } from 'react'
import { useQuery, useQueryClient, type UseQueryResult } from '@tanstack/react-query'
import api, { ApiError } from '@/lib/api'

type Params = Record<string, string | number | boolean | undefined | null>

/** GET helper: `useGet<Circle[]>('/circles')`. Disabled when url is null. */
export function useGet<T>(url: string | null, params?: Params): UseQueryResult<T, ApiError> {
  return useQuery<T, ApiError>({
    queryKey: [url, params ?? {}],
    enabled: url !== null,
    queryFn: async () => {
      const clean: Params = {}
      for (const [k, v] of Object.entries(params ?? {})) {
        if (v !== undefined && v !== null && v !== '') clean[k] = v
      }
      const res = await api.get<T>(url as string, { params: clean })
      return res.data
    },
  })
}

type Method = 'post' | 'patch' | 'put' | 'delete'

/**
 * Mutation helper. Returns the response data, or null when the request failed
 * (the error was already shown as a toast). Successful calls refresh all queries.
 */
export function useAct() {
  const qc = useQueryClient()
  return useCallback(
    async <T = unknown>(method: Method, url: string, body?: unknown): Promise<T | null> => {
      try {
        const res = await api.request<T>({ method, url, data: body })
        await qc.invalidateQueries()
        return res.data
      } catch {
        return null
      }
    },
    [qc],
  )
}

export function fmtDate(value: string | null | undefined, lang = 'en'): string {
  if (!value) return '–'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleDateString(lang === 'de' ? 'de-AT' : 'en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
}

export function fmtDateTime(value: string | null | undefined, lang = 'en'): string {
  if (!value) return '–'
  const d = new Date(value)
  return d.toLocaleString(lang === 'de' ? 'de-AT' : 'en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}

export function initials(name: string | null | undefined): string {
  if (!name) return '?'
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? '')
    .join('')
}
