// frontend_new/src/api/details.ts

import { api } from './client';
import { ItemDetails, ItemType, EpisodeOrder, EpisodeGroup, ExternalIdsData } from '../types';

export async function getItemDetails(itemType: ItemType, itemId: string, viewMode: string = 'standard'): Promise<ItemDetails> {
  return api.get<ItemDetails>(`/api/items/${itemType}/${itemId}/details`, { params: { view_mode: viewMode } });
}

export async function updateItemMetadata(itemType: ItemType, itemId: string, data: any): Promise<any> {
  return api.put<any>(`/api/items/${itemType}/${itemId}`, data);
}

export async function copyToOverride(itemType: ItemType, itemId: string): Promise<any> {
  return api.post<any>(`/api/items/${itemType}/${itemId}/copy-to-override`, {});
}

export async function refreshItemCache(itemType: ItemType, itemId: string): Promise<any> {
  return api.post<any>(`/api/items/${itemType}/${itemId}/refresh-cache`, {});
}

export async function deleteOverride(itemType: ItemType, itemId: string): Promise<any> {
  return api.delete<any>(`/api/items/${itemType}/${itemId}/override`);
}

export async function deleteCache(itemType: ItemType, itemId: string): Promise<any> {
  return api.delete<any>(`/api/items/${itemType}/${itemId}/cache`);
}

export async function updateSeasonMetadata(seriesId: string, seasonNumber: number, data: any): Promise<any> {
  return api.put<any>(`/api/tv/${seriesId}/seasons/${seasonNumber}`, data);
}

export async function updateEpisodeMetadata(seriesId: string, seasonNumber: number, episodeNumber: number, data: any): Promise<any> {
  return api.put<any>(`/api/tv/${seriesId}/episodes/${seasonNumber}/${episodeNumber}`, data);
}

export async function deleteItemImages(itemType: ItemType, itemId: string): Promise<any> {
  return api.delete<any>(`/api/items/${itemType}/${itemId}/override/images`);
}

export async function deletePatchesFolder(itemType: ItemType, itemId: string): Promise<any> {
  return api.delete<any>(`/api/items/${itemType}/${itemId}/override/patches`);
}

export async function deleteItemMetadata(itemType: ItemType, itemId: string, mode: 'all' | 'main_only' = 'all'): Promise<any> {
  return api.delete<any>(`/api/items/${itemType}/${itemId}/override/metadata`, { params: { mode } });
}

export async function deleteItemTags(itemType: ItemType, itemId: string): Promise<any> {
  return api.delete<any>(`/api/tags/item/${itemType}/${itemId}/all`);
}

export async function getEpisodeOrder(seriesId: string): Promise<EpisodeOrder> {
    return api.get<EpisodeOrder>(`/api/tv/${seriesId}/episodeorder`);
}

export async function updateEpisodeOrder(seriesId: string, data: EpisodeOrder): Promise<any> {
    return api.put<any>(`/api/tv/${seriesId}/episodeorder`, data);
}

export async function deleteEpisodeOrderFile(seriesId: string): Promise<any> {
  return api.delete<any>(`/api/tv/${seriesId}/episodeorder`);
}

export async function getEpisodeGroup(seriesId: string): Promise<EpisodeGroup> {
    return api.get<EpisodeGroup>(`/api/tv/${seriesId}/episodegroup`);
}

export async function updateEpisodeGroup(seriesId: string, data: EpisodeGroup): Promise<any> {
    return api.put<any>(`/api/tv/${seriesId}/episodegroup`, data);
}

export async function deleteEpisodeGroupFile(seriesId: string): Promise<any> {
    return api.delete<any>(`/api/tv/${seriesId}/episodegroup`);
}

export async function getEmbyWebLink(itemType: ItemType, itemId: string): Promise<{ url: string }> {
  return api.get<{ url: string }>(`/api/items/${itemType}/${itemId}/emby-weblink`);
}

export async function refreshInEmby(itemType: ItemType, itemId: string): Promise<{ message: string }> {
  return api.post<{ message: string }>(`/api/items/${itemType}/${itemId}/emby-refresh`, {});
}

export async function updateMetadataFromEmby(
  itemType: ItemType, 
  itemId: string, 
  fields: string[] = [], 
  updateChildren: boolean = false
): Promise<{ message: string; success: boolean; updated_details?: any }> {
  return api.post(`/api/items/${itemType}/${itemId}/emby-update-metadata`, {
    fields_to_update: fields,
    update_children: updateChildren
  });
}

export async function lockItemName(itemType: ItemType, itemId: string): Promise<any> {
  return api.post<any>(`/api/items/${itemType}/${itemId}/lock-name`, {});
}

export async function updatePatchName(itemType: ItemType, itemId: string, name: string): Promise<any> {
  return api.put<any>(`/api/items/${itemType}/${itemId}/patch-name`, { name });
}

export async function generateItemTags(itemType: ItemType, itemId: string, mode: 'merge' | 'overwrite'): Promise<any> {
  return api.post<any>(`/api/tags/item/${itemType}/${itemId}`, { mode });
}

export interface ItemBackup {
  name: string;
  created_at: string; // timestamp or string
  size?: string;
}

export async function getItemBackups(itemType: ItemType, itemId: string): Promise<ItemBackup[]> {
  return api.get<ItemBackup[]>(`/api/items/${itemType}/${itemId}/backups`);
}

export async function createItemBackup(itemType: ItemType, itemId: string): Promise<any> {
  return api.post<any>(`/api/items/${itemType}/${itemId}/backups`, {});
}

export async function restoreItemBackup(itemType: ItemType, itemId: string, backupName: string): Promise<any> {
  return api.post<any>(`/api/items/${itemType}/${itemId}/backups/${backupName}/restore`, {});
}

export async function deleteItemBackup(itemType: ItemType, itemId: string, backupName: string): Promise<any> {
  return api.delete<any>(`/api/items/${itemType}/${itemId}/backups/${backupName}`);
}

export async function deleteSeasonMetadata(seriesId: string, seasonNumber: number, includeEpisodes: boolean): Promise<any> {
  return api.delete<any>(`/api/tv/${seriesId}/seasons/${seasonNumber}/override/metadata`, { params: { include_episodes: includeEpisodes } });
}

export async function deleteEpisodeMetadata(seriesId: string, seasonNumber: number, episodeNumber: number): Promise<any> {
  return api.delete<any>(`/api/tv/${seriesId}/episodes/${seasonNumber}/${episodeNumber}/override/metadata`);
}

export interface TmdbUpdateOptions {
  fields_to_update?: string[];
  overwrite?: boolean;
  trigger_emby_refresh?: boolean;
  update_season_episodes?: boolean;
}

export async function updateTmdbMetadata(
  itemType: 'movie' | 'tv' | 'season' | 'episode',
  tmdbId: string,
  options: TmdbUpdateOptions,
  lang: string = 'zh-CN',
  seasonNumber?: number,
  episodeNumber?: number
): Promise<any> {
  const params: any = { lang };
  if (seasonNumber !== undefined) params.season_number = seasonNumber;
  if (episodeNumber !== undefined) params.episode_number = episodeNumber;

  return api.post<any>(`/api/tmdb/${itemType}/${tmdbId}/update-metadata`, options, { params });
}

export async function getTmdbUpdateConfig(): Promise<any> {
  return api.get<any>('/api/tmdb/update-config');
}

export async function setTmdbUpdateConfig(config: any): Promise<any> {
  return api.post<any>('/api/tmdb/update-config', config);
}

export async function getBangumiRecommendation(itemType: ItemType, itemId: string): Promise<any> {
  return api.get<any>(`/api/items/${itemType}/${itemId}/bangumi-recommendation`);
}

export async function updateMetadataFromBangumi(
  itemType: ItemType, 
  itemId: string, 
  bangumiId?: number,
  fields: string[] = [], 
  forceRefresh: boolean = false,
  useWhitelist: boolean = false,
  mode: 'merge' | 'overwrite' = 'merge'
): Promise<any> {
  return api.post<any>(`/api/items/${itemType}/${itemId}/refresh-metadata-from-bangumi`, {
    bangumi_id: bangumiId,
    fields: fields,
    force_refresh: forceRefresh,
    use_whitelist: useWhitelist,
    mode: mode
  });
}

export async function getExternalIds(itemType: ItemType, itemId: string): Promise<ExternalIdsData> {
  return api.get<ExternalIdsData>(`/api/items/${itemType}/${itemId}/externalids`);
}

export async function updateExternalIds(itemType: ItemType, itemId: string, data: ExternalIdsData): Promise<any> {
  return api.put<any>(`/api/items/${itemType}/${itemId}/externalids`, data);
}

export async function deleteExternalIdsFile(itemType: ItemType, itemId: string): Promise<any> {
  return api.delete<any>(`/api/items/${itemType}/${itemId}/externalids`);
}
