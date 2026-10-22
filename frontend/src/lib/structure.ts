import type { CircleNode, GovMode, RoleNode } from '@/lib/types'

export function childrenOf(circles: CircleNode[], id: string): CircleNode[] {
  return circles.filter((c) => c.parent_id === id)
}

export function descendantIds(circles: CircleNode[], id: string): Set<string> {
  const out = new Set<string>()
  const stack = [id]
  while (stack.length > 0) {
    const cur = stack.pop() as string
    for (const c of circles) {
      if (c.parent_id === cur && !out.has(c.id)) {
        out.add(c.id)
        stack.push(c.id)
      }
    }
  }
  return out
}

export function pathTo(circles: CircleNode[], id: string): CircleNode[] {
  const byId = new Map(circles.map((c) => [c.id, c]))
  const path: CircleNode[] = []
  let cur = byId.get(id)
  let guard = 0
  while (cur && guard < 50) {
    path.unshift(cur)
    cur = cur.parent_id ? byId.get(cur.parent_id) : undefined
    guard += 1
  }
  return path
}

export function effectiveMode(circles: CircleNode[], id: string, orgDefault: GovMode): GovMode {
  const path = pathTo(circles, id).reverse()
  return path.find((c) => c.governance_mode)?.governance_mode ?? orgDefault
}

export function rolesOf(roles: RoleNode[], circleId: string): RoleNode[] {
  return roles.filter((r) => r.circle_id === circleId)
}

export function matchesFilter(text: string, ...fields: (string | undefined)[]): boolean {
  const needle = text.trim().toLowerCase()
  if (!needle) return true
  return fields.some((f) => (f ?? '').toLowerCase().includes(needle))
}

export function roleSearchFields(r: RoleNode): string[] {
  return [r.name, r.purpose, ...r.accountabilities.map((a) => a.text), ...r.domains.map((d) => d.text), ...r.authorities.map((a) => a.text), ...r.holders.map((h) => h.name)]
}
