export interface ColumnInfo {
  name: string
  dtype: string
  semantic_type: 'categorical' | 'numeric' | 'datetime' | 'text'
  null_percentage: number
  unique_count: number
  numeric_stats?: { min: number; max: number; mean: number }
  top_values?: string[]
  sample_values: (string | number)[]
}

export interface DataFrameSchema {
  filename: string
  rows: number
  columns: number
  column_names: string[]
  numeric_columns: string[]
  date_columns: string[]
  categorical_columns: string[]
  column_info: ColumnInfo[]
}

export interface UploadResponse {
  session_id: string
  files_processed: string[]
  schema_summary: Record<string, DataFrameSchema>
  suggested_questions: string[]
}

export interface ArtifactContent {
  type: 'html'
  content: string
}

export interface QueryResponse {
  output_type: 'metric' | 'text' | 'table' | 'chart' | 'dashboard' | 'followup'
  render_mode: 'chat' | 'artifact'
  sql_query: string | string[] | null
  chat_message: string
  artifact: ArtifactContent | null
  insight: string
  execution_result?: unknown
  execution_error?: string | null
}

export interface Message {
  role: 'user' | 'assistant'
  content: string | QueryResponse
  timestamp: string
}

export interface ArtifactPanelRef {
  openArtifact: (content: string, title: string) => void
  close: () => void
}
