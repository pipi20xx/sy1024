import { apiFetch, api } from './client'

export interface TmdbBgmMappingItem {
  tmdb_id: number
  tmdb_type: 'tv' | 'movie'
  season_mappings: Record<string, number[]>
}

export interface TmdbBgmMappingList {
  items: TmdbBgmMappingItem[]
  total: number
  page: number
  page_size: number
}

export interface DiffItem {
  tmdb_id: number
  tmdb_type: string
  season_number: string
  old_bgm_ids: number[]
  new_bgm_ids: number[]
  diff_type: 'new' | 'modified' | 'deleted' | 'unchanged'
}

export interface ImportDiffResponse {
  diff_items: DiffItem[]
  stats: { new: number; modified: number; deleted: number; unchanged: number }
}

export interface TmdbBgmMappingUpdate {
  tmdb_id: number
  tmdb_type: 'tv' | 'movie'
  season_mappings: Record<string, number[]>
}

export async function getMappingsApi(params?: { search?: string; tmdb_type?: string; page?: number; page_size?: number }): Promise<TmdbBgmMappingList> {
  const query = new URLSearchParams()
  if (params?.search) query.set('search', params.search)
  if (params?.tmdb_type && params.tmdb_type !== 'all') query.set('tmdb_type', params.tmdb_type)
  if (params?.page) query.set('page', String(params.page))
  if (params?.page_size) query.set('page_size', String(params.page_size))
  const qs = query.toString()
  return apiFetch(`/api/tmdb-bgm-mapping/list${qs ? '?' + qs : ''}`)
}

export async function exportMappingsApi(): Promise<TmdbBgmMappingItem[]> {
  return apiFetch('/api/tmdb-bgm-mapping/export')
}

export async function importDiffApi(importData: TmdbBgmMappingItem[]): Promise<ImportDiffResponse> {
  return apiFetch('/api/tmdb-bgm-mapping/import/diff', { method: 'POST', body: { import_data: importData } as any })
}

export async function applyImportApi(selectedDiffItems: DiffItem[]): Promise<{ status: string }> {
  return apiFetch('/api/tmdb-bgm-mapping/import/apply', { method: 'POST', body: { selected_diff_items: selectedDiffItems } as any })
}

export async function updateMappingApi(update: TmdbBgmMappingUpdate): Promise<{ status: string }> {
  return apiFetch('/api/tmdb-bgm-mapping/update', { method: 'POST', body: update as any })
}

export async function deleteMappingApi(tmdbId: number, tmdbType: string): Promise<{ status: string }> {
  return apiFetch(`/api/tmdb-bgm-mapping/delete?tmdb_id=${tmdbId}&tmdb_type=${tmdbType}`, { method: 'DELETE' })
}

export async function clearAllMappingsApi(): Promise<{ status: string }> {
  return apiFetch('/api/tmdb-bgm-mapping/clear-all', { method: 'DELETE' })
}

export interface BangumiInfo {
  id: number
  name: string
  name_cn: string
  date: string
  eps: number | null
}

export async function getBatchBangumiDetailsApi(bangumiIds: number[]): Promise<BangumiInfo[]> {
  return apiFetch('/api/bangumi/batch-details', { method: 'POST', body: bangumiIds as any })
}
