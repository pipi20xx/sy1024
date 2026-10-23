import { apiFetch } from './client'

// ==================== 配置接口 ====================

export interface BangumiConfig {
  enabled: boolean
  interval_days: number
  hour: number
  minute: number
  github_token?: string
  current_version?: string
  sync_config?: BangumiSyncConfig
}

export interface BangumiSyncConfig {
  item_types: string[]
  write_to_genres: boolean
  write_to_tags: boolean
  is_merge_mode: boolean
  is_preview: boolean
  allowed_tags: string[]
  allowed_tags_str?: string
  access_token?: string
}

export async function getBangumiConfigApi(): Promise<BangumiConfig> {
  return apiFetch('/api/bangumi/config')
}

export async function saveBangumiConfigApi(config: Partial<BangumiConfig>): Promise<void> {
  return apiFetch('/api/bangumi/config', {
    method: 'POST',
    body: config as any,
  })
}

// ==================== bangumi-data 映射表同步 ====================

export interface BangumiDataVersion {
  version: string
}

export async function getBangumiDataVersionApi(): Promise<BangumiDataVersion> {
  return apiFetch('/api/bangumi-data-sync/version')
}

/**
 * 启动 bangumi-data 映射表同步 (SSE 流)
 * GitHub Token 由后端从系统设置中读取，前端无需传递。
 * @returns EventSource 实例
 */
export function startBangumiDataSyncSSE(): EventSource {
  return new EventSource('/api/bangumi-data-sync/sync')
}
