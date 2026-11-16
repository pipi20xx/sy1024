/**
 * 壁纸管理 API
 *
 * 对应后端 /api/appearance/wallpaper/* 端点。
 */

import { api } from './client'

// ── 类型定义 ──────────────────────────────────────────────

export type WallpaperSourceType = 'api' | 'url' | 'upload' | 'history'

export type WallpaperDisplayMode = 'latest' | 'rotation'

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
  history_filename: string
  /** 后台自动下载新图的间隔（秒），与显示模式无关 */
  refresh_interval: number
  /** 显示方式：latest 跟随最新 | rotation 图库轮播 */
  display_mode: WallpaperDisplayMode
  /** 图库轮播间隔（秒），仅 display_mode=rotation 时使用 */
  rotation_interval: number
  /** 轮播范围：包含历史图库 */
  rotation_include_history: boolean
  /** 轮播范围：包含上传壁纸 */
  rotation_include_uploads: boolean
}

export interface WallpaperUpload {
  filename: string
  size: number
  created_at?: number
}

export interface WallpaperHistory {
  filename: string
  size: number
  created_at: number
  source_type: string
  source_id: string
  source_url: string
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

  /** 列出手动上传的壁纸图片 */
  listUploads: async (): Promise<WallpaperUpload[]> => {
    const res = await api.get<WallpaperUpload[] | { images?: WallpaperUpload[] }>('/api/appearance/wallpaper/uploads')
    if (Array.isArray(res)) return res
    return res.images ?? []
  },

  /** 列出自动收录的历史壁纸图片 */
  listHistory: async (): Promise<WallpaperHistory[]> => {
    const res = await api.get<WallpaperHistory[] | { history?: WallpaperHistory[] }>('/api/appearance/wallpaper/history')
    if (Array.isArray(res)) return res
    return res.history ?? []
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

  /** 删除历史壁纸图片 */
  deleteHistory: (filename: string) =>
    api.delete<{ success: boolean }>(`/api/appearance/wallpaper/history/${encodeURIComponent(filename)}`),

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
