export type FeatureStatus = 'draft' | 'reviewed' | 'certified' | 'deprecated'

export interface FeatureRow {
  id: string
  name: string
  data_source_id: string
  column_name: string
  dtype: string
  description: string
  tags: string[]
  owner: string
  stats: Record<string, unknown>
  has_doc?: boolean
  health_score?: number
  health_grade?: string
  status?: FeatureStatus
  created_at: string
  updated_at: string
}

export interface PaginatedFeatures {
  items: FeatureRow[]
  total: number
  limit: number
  offset: number
}

export interface DataSourceRow {
  id: string
  name: string
  path: string
  storage_type: string
  format: string
  description: string
  created_at: string
  updated_at: string
}

export interface FeatureGroupRow {
  id: string
  name: string
  description: string
  project: string
  owner: string
  member_count?: number
  members?: FeatureRow[]
  created_at: string
  updated_at: string
}

export interface EntityRow {
  id: string
  name: string
  primary_keys: string[]
  join_keys: string[]
  description: string
  owner: string
  source_of_truth: string
  lifecycle_status: string
  created_at: string
  updated_at: string
}

export interface EntityRelationshipJoinKeyRow {
  left_key: string
  right_key: string
}

export interface EntityRelationshipRow {
  id: string
  name: string
  left_entity: string
  right_entity: string
  relation_type: string
  join_keys: EntityRelationshipJoinKeyRow[]
  valid_from: string | null
  valid_to: string | null
  event_time: string | null
  description: string
  owner: string
  lifecycle_status: string
  created_at: string
  updated_at: string
}

export interface FeatureViewRow {
  id: string
  name: string
  entity: string
  source_name: string
  source_entity: string | null
  relationship: string | null
  aggregation: string | null
  feature_names: string[]
  description: string
  owner: string
  lifecycle_status: string
  created_at: string
  updated_at: string
}

export interface FeatureSetRow {
  id: string
  name: string
  target_entity: string
  feature_names: string[]
  rollup_rules: Record<string, string>
  use_case: string
  description: string
  owner: string
  lifecycle_status: string
  created_at: string
  updated_at: string
}

export interface BusinessMetricRow {
  id: string
  name: string
  business_metric_name: string
  business_definition: string
  metric_domain: string
  lifecycle_stage: string
  metric_group: string
  metric_level: string
  entity_grain: string
  aggregation_rule: string
  mapped_features: string[]
  owner: string
  lifecycle_status: string
  allowed_use_cases: string[]
  created_at: string
  updated_at: string
}

export interface BulkScanResponse {
  found: number
  registered_sources: number
  registered_features: number
  skipped: number
  details: Array<{ file: string; status: string; feature_count: number; error?: string }>
}

export type ChatEventType =
  | 'thinking_start'
  | 'thinking'
  | 'thinking_end'
  | 'tool_start'
  | 'tool_call'
  | 'tool_result'
  | 'token'
  | 'result'
  | 'done'
  | 'error'

export interface ChatEvent {
  type: ChatEventType
  content?: string
  id?: string
  name?: string
  tool?: string
  input?: unknown
  args?: unknown
  output?: unknown
  result?: unknown
  error?: string
  status?: string
}
