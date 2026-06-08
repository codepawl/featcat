import { execFileSync } from 'node:child_process'
import { BACKEND_URL, FIXTURES_PARQUET_DIR, TEST_DB_PATH, VENV_PYTHON } from './constants'
import type {
  BusinessMetricRow,
  BulkScanResponse,
  EntityRelationshipRow,
  EntityRow,
  FeatureGroupRow,
  FeatureRow,
  FeatureSetRow,
  FeatureViewRow,
  PaginatedFeatures,
} from './types'

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

function ensureFeatureNames(features: FeatureRow[], names: string[]): void {
  const available = new Set(features.map((feature) => feature.name))
  const missing = names.filter((name) => !available.has(name))
  if (missing.length > 0) {
    throw new Error(`Missing seeded features: ${missing.join(', ')}`)
  }
}

async function post<T>(path: string, body: unknown): Promise<T> {
  return api<T>(path, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function upsertEntity(body: EntityRow): Promise<EntityRow> {
  const { id: _id, created_at: _createdAt, updated_at: _updatedAt, ...payload } = body
  return post<EntityRow>('/api/entities', payload)
}

export async function upsertEntityRelationship(body: EntityRelationshipRow): Promise<EntityRelationshipRow> {
  const { id: _id, created_at: _createdAt, updated_at: _updatedAt, ...payload } = body
  return post<EntityRelationshipRow>('/api/entity-relationships', payload)
}

export async function upsertFeatureView(body: FeatureViewRow): Promise<FeatureViewRow> {
  const { id: _id, created_at: _createdAt, updated_at: _updatedAt, ...payload } = body
  return post<FeatureViewRow>('/api/feature-views', payload)
}

export async function upsertFeatureSet(body: FeatureSetRow): Promise<FeatureSetRow> {
  const { id: _id, created_at: _createdAt, updated_at: _updatedAt, ...payload } = body
  return post<FeatureSetRow>('/api/feature-sets', payload)
}

export async function upsertBusinessMetric(body: BusinessMetricRow): Promise<BusinessMetricRow> {
  const { id: _id, created_at: _createdAt, updated_at: _updatedAt, ...payload } = body
  return post<BusinessMetricRow>('/api/business-metrics', payload)
}

export function setFeatureLeakageRisk(name: string, leakageRisk: 'low' | 'high'): void {
  const script = `
import sqlite3
import sys

db_path, feature_name, leakage = sys.argv[1:4]
conn = sqlite3.connect(db_path)
conn.execute("UPDATE features SET leakage_risk = ? WHERE name = ?", (leakage, feature_name))
conn.commit()
conn.close()
`
  execFileSync(VENV_PYTHON, ['-c', script, TEST_DB_PATH, name, leakageRisk], { stdio: 'ignore' })
}

export async function seedRegistryCatalog(): Promise<{
  entityNames: string[]
  relationshipNames: string[]
  featureViewNames: string[]
  featureSetNames: string[]
  businessMetricNames: string[]
}> {
  await ensureSeeded()

  const features = await listFeatures()
  ensureFeatureNames(features, [
    'device_performance.cpu_usage',
    'device_performance.error_count',
    'device_performance.latency_ms',
    'user_behavior_30d.session_count',
    'user_behavior_30d.complaint_count',
    'user_behavior_30d.churn_label',
  ])

  const entities: EntityRow[] = [
    {
      id: '',
      name: 'customer',
      primary_keys: ['customer_id'],
      join_keys: ['customer_id'],
      description: 'Khách hàng cuối cùng',
      owner: 'customer-platform',
      source_of_truth: 'billing.customers',
      lifecycle_status: 'validated',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
    {
      id: '',
      name: 'contract',
      primary_keys: ['contract_id'],
      join_keys: ['customer_id'],
      description: 'Hợp đồng dịch vụ',
      owner: 'billing-platform',
      source_of_truth: 'billing.contracts',
      lifecycle_status: 'validated',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
    {
      id: '',
      name: 'device',
      primary_keys: ['device_id'],
      join_keys: ['contract_id'],
      description: 'Thiết bị mạng',
      owner: 'network-platform',
      source_of_truth: 'network.devices',
      lifecycle_status: 'validated',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
  ]

  for (const entity of entities) {
    await upsertEntity(entity)
  }

  const relationships: EntityRelationshipRow[] = [
    {
      id: '',
      name: 'customer_has_contracts',
      left_entity: 'customer',
      right_entity: 'contract',
      relation_type: 'one_to_many',
      join_keys: [{ left_key: 'customer_id', right_key: 'customer_id' }],
      valid_from: null,
      valid_to: null,
      event_time: null,
      description: 'Một khách hàng có nhiều hợp đồng',
      owner: 'billing-platform',
      lifecycle_status: 'validated',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
    {
      id: '',
      name: 'contract_has_devices',
      left_entity: 'contract',
      right_entity: 'device',
      relation_type: 'one_to_many',
      join_keys: [{ left_key: 'contract_id', right_key: 'contract_id' }],
      valid_from: null,
      valid_to: null,
      event_time: null,
      description: 'Một hợp đồng sở hữu nhiều thiết bị',
      owner: 'network-platform',
      lifecycle_status: 'validated',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
  ]

  for (const relationship of relationships) {
    await upsertEntityRelationship(relationship)
  }

  const featureViews: FeatureViewRow[] = [
    {
      id: '',
      name: 'contract_view',
      entity: 'contract',
      source_name: 'device_performance',
      source_entity: 'device',
      relationship: 'contract_has_devices',
      aggregation: 'sum',
      feature_names: [
        'device_performance.cpu_usage',
        'device_performance.error_count',
        'device_performance.latency_ms',
      ],
      description: 'Tổng hợp tín hiệu thiết bị theo hợp đồng',
      owner: 'network-platform',
      lifecycle_status: 'production',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
  ]

  for (const featureView of featureViews) {
    await upsertFeatureView(featureView)
  }

  const featureSets: FeatureSetRow[] = [
    {
      id: '',
      name: 'cust_churn_set',
      target_entity: 'customer',
      feature_names: ['device_performance.cpu_usage', 'device_performance.error_count', 'user_behavior_30d.session_count'],
      rollup_rules: {
        'device_performance.cpu_usage': 'avg(device)->customer via contract',
        'device_performance.error_count': 'sum(device)->customer via contract',
        'user_behavior_30d.session_count': 'sum(user)->customer',
      },
      use_case: 'Customer churn prediction',
      description: 'Tập feature cho mô hình churn khách hàng',
      owner: 'ml-platform',
      lifecycle_status: 'production',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
  ]

  for (const featureSet of featureSets) {
    await upsertFeatureSet(featureSet)
  }

  const businessMetrics: BusinessMetricRow[] = [
    {
      id: '',
      name: 'bad_signal_7d',
      business_metric_name: 'bad_signal_days_7d',
      business_definition: 'Số ngày có tín hiệu xấu trong 7 ngày gần nhất',
      metric_domain: 'network_quality',
      lifecycle_stage: 'consume',
      metric_group: 'signal_health',
      metric_level: 'contract',
      entity_grain: 'device_id',
      aggregation_rule: 'sum(device)->contract qua contract_has_devices',
      mapped_features: ['device_performance.error_count', 'device_performance.latency_ms'],
      owner: 'network-platform',
      lifecycle_status: 'production',
      allowed_use_cases: ['retention', 'churn'],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
    {
      id: '',
      name: 'pay_delay_30d',
      business_metric_name: 'payment_delay_count_30d',
      business_definition: 'Đếm số lần thanh toán trễ trong 30 ngày',
      metric_domain: 'billing',
      lifecycle_stage: 'manage',
      metric_group: 'payment_behavior',
      metric_level: 'customer',
      entity_grain: 'contract_id',
      aggregation_rule: 'sum(contract)->customer qua customer_has_contracts',
      mapped_features: ['user_behavior_30d.complaint_count'],
      owner: 'billing-platform',
      lifecycle_status: 'validated',
      allowed_use_cases: ['collections', 'risk'],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
    {
      id: '',
      name: 'downtime_7d',
      business_metric_name: 'downtime_minutes_7d',
      business_definition: 'Phút downtime trong 7 ngày gần nhất',
      metric_domain: 'service_ops',
      lifecycle_stage: 'manage',
      metric_group: 'availability',
      metric_level: 'mixed',
      entity_grain: 'service_id',
      aggregation_rule: 'sum(device)->service khi tổng hợp sự cố',
      mapped_features: ['device_performance.latency_ms'],
      owner: 'ops-platform',
      lifecycle_status: 'production',
      allowed_use_cases: ['ops', 'sla'],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
    {
      id: '',
      name: 'pref_channel',
      business_metric_name: 'preferred_channel',
      business_definition: 'Kênh liên hệ ưu tiên của khách hàng',
      metric_domain: 'contact',
      lifecycle_stage: 'consume',
      metric_group: 'channel_preference',
      metric_level: 'customer',
      entity_grain: 'customer_id',
      aggregation_rule: '',
      mapped_features: ['user_behavior_30d.session_count'],
      owner: 'contact-center',
      lifecycle_status: 'validated',
      allowed_use_cases: ['routing'],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
    {
      id: '',
      name: 'churn_basket',
      business_metric_name: 'churn_basket_count',
      business_definition: 'Nhóm tín hiệu liên quan rời mạng',
      metric_domain: 'customer_experience',
      lifecycle_stage: 'leave',
      metric_group: 'churn',
      metric_level: 'mixed',
      entity_grain: 'customer_id',
      aggregation_rule: 'weighted sum over customer behaviors',
      mapped_features: ['user_behavior_30d.churn_label'],
      owner: 'customer-analytics',
      lifecycle_status: 'draft',
      allowed_use_cases: ['churn_prediction'],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
  ]

  for (const metric of businessMetrics) {
    await upsertBusinessMetric(metric)
  }

  setFeatureLeakageRisk('device_performance.error_count', 'high')

  return {
    entityNames: entities.map((entity) => entity.name),
    relationshipNames: relationships.map((relationship) => relationship.name),
    featureViewNames: featureViews.map((featureView) => featureView.name),
    featureSetNames: featureSets.map((featureSet) => featureSet.name),
    businessMetricNames: businessMetrics.map((metric) => metric.name),
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
