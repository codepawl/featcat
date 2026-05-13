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
