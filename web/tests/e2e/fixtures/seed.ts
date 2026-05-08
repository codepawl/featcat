import { BACKEND_URL, FIXTURES_PARQUET_DIR } from './constants'
import type { BulkScanResponse, FeatureGroupRow, FeatureRow, PaginatedFeatures } from './types'

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BACKEND_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`API ${init?.method ?? 'GET'} ${path} → ${res.status}: ${body}`)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export async function listFeatures(): Promise<FeatureRow[]> {
  const raw = await api<FeatureRow[] | PaginatedFeatures>('/api/features')
  return Array.isArray(raw) ? raw : raw.items
}

export async function listGroups(): Promise<FeatureGroupRow[]> {
  return api<FeatureGroupRow[]>('/api/groups')
}

export async function ensureSeeded(): Promise<void> {
  const features = await listFeatures()
  if (features.length > 0) return

  const result = await api<BulkScanResponse>('/api/scan-bulk', {
    method: 'POST',
    body: JSON.stringify({
      path: FIXTURES_PARQUET_DIR,
      recursive: false,
      owner: 'e2e',
      tags: ['e2e'],
      dry_run: false,
    }),
  })

  if (result.registered_features === 0) {
    throw new Error(
      `Seed failed: scan-bulk found ${result.found} files but registered 0 features. ` +
        `Fixture path: ${FIXTURES_PARQUET_DIR}\n` +
        `Details: ${JSON.stringify(result.details, null, 2)}`,
    )
  }
}

export async function clearWriteState(): Promise<void> {
  const groups = await listGroups()
  await Promise.all(
    groups.map((g) =>
      fetch(`${BACKEND_URL}/api/groups/${encodeURIComponent(g.name)}`, { method: 'DELETE' }),
    ),
  )
}

export async function createGroup(input: {
  name: string
  description?: string
  project?: string
  owner?: string
}): Promise<FeatureGroupRow> {
  return api<FeatureGroupRow>('/api/groups', {
    method: 'POST',
    body: JSON.stringify({
      description: '',
      project: '',
      owner: '',
      ...input,
    }),
  })
}

export async function addMembers(groupName: string, featureSpecs: string[]): Promise<void> {
  await api(`/api/groups/${encodeURIComponent(groupName)}/members`, {
    method: 'POST',
    body: JSON.stringify({ feature_specs: featureSpecs }),
  })
}
