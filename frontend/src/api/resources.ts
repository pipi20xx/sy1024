import { api } from './client'
import type { ItemType } from '@/types'

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

export async function getResources(itemType: ItemType, itemId: string): Promise<ResourceItem[]> {
  return api.get<ResourceItem[]>(`/api/items/${itemType}/${itemId}/resources`)
}

export async function saveResources(itemType: ItemType, itemId: string, resources: ResourceItem[]): Promise<any> {
  return api.post(`/api/items/${itemType}/${itemId}/resources`, resources)
}

export async function uploadAttachment(itemType: ItemType, itemId: string, file: File): Promise<{ filename: string }> {
  const formData = new FormData()
  formData.append('file', file)
  const response = await fetch(`/api/items/${itemType}/${itemId}/attachments`, { method: 'POST', body: formData })
  if (!response.ok) throw new Error('上传失败')
  return response.json()
}
