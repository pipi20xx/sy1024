// 媒体类型
export type ItemType = 'tmdb-movies2' | 'tmdb-tv'

// 媒体图片类型
export interface Image {
  label: string
  url: string
  name: string
}

// 网络图片类型 (用于WebImageSelector)
export interface WebImage {
  type: string
  full_url: string
  preview_url: string
  source: string
  info: string
  lang: string
  name?: string
  label?: string
}

// 列表页显示的媒体项目摘要信息
export interface ItemSummary {
  id: string
  type: ItemType
  source: 'primary' | 'override'
  name: string
  title?: string
  year: number
  full_date?: string
  poster_path?: string
  genres: string[]
  folder_id: string
  json_path: string
  has_episode_group?: boolean
  in_library?: boolean
  has_bgm_mapping?: boolean
}

// 详情页显示的媒体项目完整信息
// 后端详情API返回: id, type, source, full_metadata, images, seasons, tags, override_*
// 注意：name/title/year/overview 等字段在 full_metadata 中，不在顶层
export interface ItemDetails {
  id: string
  type: ItemType
  source: 'primary' | 'override'
  full_metadata: any
  images: Image[]
  seasons?: SeasonDetails[]
  tags?: string[]
  override_cache_exists: boolean
  primary_cache_configured?: boolean
  override_cache_configured?: boolean
  override_episodegroup_exists?: boolean
  override_episodeorder_exists?: boolean
  override_externalids_exists?: boolean
  override_patches_exists?: boolean
  poster_path?: string // 列表API中存在
  name?: string // 列表API中存在
  title?: string // 列表API中存在
  year?: number // 列表API中存在
  full_date?: string
  genres?: string[]
  folder_id?: string
  json_path?: string
  has_episode_group?: boolean
  has_bgm_mapping?: boolean
}

// 电视剧季的详情
// 后端返回: metadata, season_number, poster_path, episodes, source, is_episodegroup
// 注意: name/overview/air_date 在 metadata 中
export interface SeasonDetails {
  metadata: any
  season_number: number
  poster_path?: string
  episodes?: EpisodeDetails[]
  source?: 'primary' | 'override'
  is_episodegroup?: boolean
  // 以下字段来自 metadata 的便捷访问（可选，部分场景下后端可能填充）
  name?: string
  overview?: string
  air_date?: string
}

// 电视剧集的详情
// 后端返回: metadata, episode_number, thumb_path, source, custom_*_number
// 注意: name/air_date 在 metadata 中
export interface EpisodeDetails {
  metadata: any
  episode_number: number
  season_number?: number
  thumb_path?: string
  source?: 'primary' | 'override'
  custom_season_number?: number
  custom_episode_number?: number
  // 以下字段来自 metadata 的便捷访问
  name?: string
  air_date?: string
}

// 特别篇插入 (Episode Order) 相关接口
export interface EpisodeOrderEntry {
  episode_number: number
  sort_season_number: number
  sort_episode_number: number
}

export interface EpisodeOrder {
  description: string
  seasons: {
    season_number: number
    episodes: EpisodeOrderEntry[]
  }[]
}

// 剧集组 (Episode Group) 相关接口
export interface EpisodeGroupEpisode {
  episode_number: number
  season_number: number
  order: number
}

export interface EpisodeGroupGroup {
  name: string
  order: number
  overview?: string
  air_date?: string
  episodes: EpisodeGroupEpisode[]
}

export interface EpisodeGroup {
  description: string
  groups: EpisodeGroupGroup[]
}

// 自定义外部ID (External IDs) 相关接口
export interface ExternalIds {
  imdb_id?: string
  tvdb_id?: number
  douban_id?: number
  bgm_id?: string
}

export interface SeasonExternalIds {
  season_number: number
  external_ids: ExternalIds
}

export interface ExternalIdsData {
  external_ids: ExternalIds
  seasons?: SeasonExternalIds[]
}

// 分页响应结构
export interface PaginatedResponse<T> {
  items: T[]
  total_items: number
  total_pages: number
  current_page: number
  has_more: boolean
}
