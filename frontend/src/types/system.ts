export interface ScanStatus {
  status: 'idle' | 'scanning' | 'completed' | 'error'
  total: number
  current: number
  message: string
}

export interface RatingFiles {
  movies_us: string
  movies_jp: string
  tv_us: string
  tv_jp: string
}

export interface EmbyTestResult {
  success: boolean
  message: string
}

export interface LogFile {
  filename: string
  size: number
  mtime: number
}

export interface UpdateInfo {
  current: string
  latest: string | null
  has_update: boolean
  cached: boolean
}

export interface AppSettings {
  primary_cache_path: string
  override_cache_path: string
  backup_path: string
  resource_info_path: string | null
  emby_collections_path: string | null
  emby_host: string
  emby_api_key: string
  emby_user_id: string
  tmdb_api_key: string
  tmdb_image_base_url: string
  auto_backup_enabled: boolean
  auto_backup_interval_hours: number
  auto_backup_mode: 'snapshot' | 'zip'
  auto_backup_include_override: boolean
  auto_backup_include_collections: boolean
  emby_webhook_enabled: boolean
  webhook_secret_token: string
  [key: string]: any
}

export interface BackupItem {
  filename: string
  created_at: string
  size_mb: string
  type: 'snapshot' | 'zip'
  triggered_by?: string
  timestamp?: number
  size?: number
  mode?: 'snapshot' | 'zip'
}

export interface ProgressData {
  status: string
  current: number
  total: number
  message: string
}

export interface Country {
  iso_3166_1: string
  native_name: string
}

export interface Genre {
  id: number
  name: string
}

export interface TagRule {
  id?: string
  name: string
  tag: string
  countries: string[]
  genres: number[]
  media_type: 'all' | 'movie' | 'tv'
  year: number | string | number[]
  strict_match: boolean
  negative_match: boolean
}

export interface MenuConfig {
  id: number
  key: string
  label: string
  icon?: string
  path?: string
  order: number
  is_visible: boolean
}

export interface ScheduledTask {
  id: number
  name: string
  task_type: string
  cron_expression: string
  enabled: boolean
  last_run: string | null
  next_run: string | null
  params: string
}

export interface ActorItem {
  id: number
  tmdb_id: number
  name: string
  original_name: string
  duplicate_tmdb_id: string
}

export interface ResourceItem {
  team?: string
  url?: string
  magnet?: string
  season_episode?: string
  subtitles?: string
  media?: string
  codec?: string
  resolution?: string
  remarks?: string
  attachment?: string[]
}

export interface WorkflowTask {
  type: string
  params?: Record<string, any>
  description?: string
}

export interface WorkflowRequest {
  item_type: string
  tasks: WorkflowTask[]
  interval_seconds: number
  item_ids?: string[]
  filters?: Record<string, any>
}

export interface SessionInfo {
  id: number
  session_id: string
  device_name: string
  device_type: string
  ip_address: string
  user_agent: string
  login_time: string
  last_activity: string
  expires_at: string
  is_current: boolean
  expires_in_hours: number
}
