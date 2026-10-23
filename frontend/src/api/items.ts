import { api } from './client'
import type { ItemSummary, ItemType, PaginatedResponse } from '@/types'

interface GetItemsParams {
  item_type: ItemType
  search_term?: string
  source?: 'primary' | 'override'
  poster_status?: 'yes' | 'no'
  genres?: string[]
  year?: string
  month?: string
  sort_by?: string
  page?: number
  limit?: number
}

export async function getItems(params: GetItemsParams): Promise<PaginatedResponse<ItemSummary>> {
  const { item_type, ...queryParams } = params
  const requestParams: any = { ...queryParams, genre: queryParams.genres }
  if (queryParams.month != null) requestParams.month = queryParams.month
  return api.get<PaginatedResponse<ItemSummary>>(`/api/items/${item_type}`, { params: requestParams })
}

export async function getGenres(itemType: ItemType): Promise<string[]> {
  return api.get<string[]>(`/api/genres/${itemType}`)
}

export async function getYears(itemType: ItemType): Promise<string[]> {
  return api.get<string[]>(`/api/years/${itemType}`)
}

export async function saveFullDetails(itemType: string, itemId: string, data: any): Promise<boolean> {
  const res = await api.post<any>(`/api/items/${itemType}/${itemId}/full-save`, data)
  return res.success
}

export async function getTvAggregatedCredits(seriesId: string): Promise<any> {
  return api.get<any>(`/api/tv/${seriesId}/aggregated-credits`)
}
