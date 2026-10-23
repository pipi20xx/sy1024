/**
 * 壁纸管理 API
 *
 * 对应后端 /api/appearance/wallpaper/* 端点。
 */

import { api } from './client'

// ── 类型定义 ──────────────────────────────────────────────

export type WallpaperSourceType = 'api' | 'upload' | 'url'

export interface WallpaperApiSource {
  id: string
  name: string
  url: string
  category: 'acg' | 'general'
  orientation: 'landscape' | 'portrait' | 'any'
  is_random: boolean
}

export interface WallpaperConfig {
  source_type: WallpaperSourceType
  api_source_id: string
  custom_url: string
  upload_filename: string
  cache_ttl: number
}

export interface WallpaperUpload {
  filename: string
  size: number
}

// ── API 调用 ──────────────────────────────────────────────

export const appearanceApi = {
  /** 获取可用的壁纸 API 源列表 */
  getSources: () =>
    api.get<{ sources: WallpaperApiSource[] }>('/api/appearance/wallpaper/sources'),

  /** 获取当前壁纸配置 */
  getConfig: () =>
    api.get<WallpaperConfig>('/api/appearance/wallpaper/config'),

  /** 更新壁纸配置 */
  updateConfig: (config: Partial<WallpaperConfig>) =>
    api.put<{ success: boolean; config: WallpaperConfig }>('/api/appearance/wallpaper/config', config),

  /** 列出所有已上传的壁纸图片 */
  listUploads: async (): Promise<WallpaperUpload[]> => {
    const res = await api.get<WallpaperUpload[] | { images?: WallpaperUpload[] }>('/api/appearance/wallpaper/uploads')
    if (Array.isArray(res)) return res
    return res.images ?? []
  },

  /** 上传壁纸图片 */
  upload: (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return api.post<{ success: boolean; filename: string }>('/api/appearance/wallpaper/upload', formData)
  },

  /** 删除已上传的壁纸图片 */
  deleteUpload: (filename: string) =>
    api.delete<{ success: boolean }>(`/api/appearance/wallpaper/uploads/${encodeURIComponent(filename)}`),

  /** 构建壁纸代理 URL（不传 url 时后端自动从配置读取壁纸源） */
  buildProxyUrl: (sourceUrl?: string, isRandom?: boolean): string => {
    if (!sourceUrl) {
      if (isRandom) {
        return `/api/appearance/wallpaper_proxy?_ts=${Date.now()}`
      }
      return '/api/appearance/wallpaper_proxy'
    }
    const encoded = encodeURIComponent(sourceUrl)
    if (isRandom) {
      return `/api/appearance/wallpaper_proxy?url=${encoded}&_ts=${Date.now()}`
    }
    return `/api/appearance/wallpaper_proxy?url=${encoded}`
  },
}
