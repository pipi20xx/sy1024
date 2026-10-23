// frontend_new/src/api/images.ts

import { api } from './client';
import { ItemType, Image, WebImage } from '../types';

/**
 * 获取指定项目可用的图片列表
 * @param itemType 项目类型
 * @param itemId 项目 ID
 * @param imageTypes 可选，筛选图片类型 (e.g., ['poster', 'backdrop'])
 * @param sources 可选，筛选图片来源 (e.g., ['tmdb', 'fanart'])
 */
export async function getWebImages(
  itemType: ItemType,
  itemId: string,
  imageTypes?: string[],
  sources?: string[]
): Promise<WebImage[]> {
  return api.get<WebImage[]>(`/api/items/${itemType}/${itemId}/web-images`, {
    params: {
      image_types: imageTypes?.join(','), // 后端期望逗号分隔的字符串
      sources: sources?.join(',')
    },
  });
}

/**
 * 保存选定的图片到本地缓存
 * @param itemType 项目类型
 * @param itemId 项目 ID
 * @param imagesToSave 图片 URL 列表
 * @param behavior 保存行为: 'overwrite' | 'skip'
 */
export async function saveWebImages(
  itemType: ItemType,
  itemId: string,
  imagesToSave: { url: string; label: string }[],
  behavior: 'overwrite' | 'skip' = 'overwrite'
): Promise<{ message: string; success: boolean; updated_details: any }> {
  return api.post(
    `/api/items/${itemType}/${itemId}/web-images`,
    imagesToSave,
    {
        params: { behavior }
    }
  );
}

/**
 * 获取指定季度的网络图片
 * @param seriesId 剧集 ID
 * @param seasonNumber 季号
 * @param imageTypes 可选，筛选图片类型
 * @param sources 可选，筛选图片来源
 */
export async function getSeasonWebImages(
  seriesId: string,
  seasonNumber: number,
  imageTypes?: string[],
  sources?: string[]
): Promise<WebImage[]> {
  return api.get<WebImage[]>(`/api/tv/${seriesId}/seasons/${seasonNumber}/web-images`, {
    params: {
      image_types: imageTypes?.join(','),
      sources: sources?.join(',')
    },
  });
}

/**
 * 保存选定的季度图片到本地缓存
 */
export async function saveSeasonWebImages(
  seriesId: string,
  seasonNumber: number,
  imagesToSave: { url: string; label: string }[],
  behavior: 'overwrite' | 'skip' = 'overwrite'
): Promise<{ message: string; success: boolean; updated_details: any }> {
  return api.post(
    `/api/tv/${seriesId}/seasons/${seasonNumber}/web-images`,
    imagesToSave,
    { params: { behavior } }
  );
}

/**
 * 获取指定集的网络图片
 * @param seriesId 剧集 ID
 * @param seasonNumber 季号
 * @param episodeNumber 集号
 * @param imageTypes 可选，筛选图片类型
 * @param sources 可选，筛选图片来源
 */
export async function getEpisodeWebImages(
  seriesId: string,
  seasonNumber: number,
  episodeNumber: number,
  imageTypes?: string[],
  sources?: string[]
): Promise<WebImage[]> {
  return api.get<WebImage[]>(`/api/tv/${seriesId}/episodes/${seasonNumber}/${episodeNumber}/web-images`, {
    params: {
      image_types: imageTypes?.join(','),
      sources: sources?.join(',')
    },
  });
}

/**
 * 保存选定的集图片到本地缓存
 */
export async function saveEpisodeWebImages(
  seriesId: string,
  seasonNumber: number,
  episodeNumber: number,
  imagesToSave: { url: string; label: string }[],
  behavior: 'overwrite' | 'skip' = 'overwrite'
): Promise<{ message: string; success: boolean; updated_details: any }> {
  return api.post(
    `/api/tv/${seriesId}/episodes/${seasonNumber}/${episodeNumber}/web-images`,
    imagesToSave,
    { params: { behavior } }
  );
}

/**
 * 触发从 Emby 下载图片
 * @param itemType 项目类型
 * @param itemId 项目 ID
 */
export async function downloadImagesFromEmby(
  itemType: ItemType,
  itemId: string
): Promise<{ message: string; success: boolean }> {
  return api.post(`/api/items/${itemType}/${itemId}/emby-download-images`, {});
}

// ── 视频截图相关 ──

export interface PreviewGenerateResult {
  success: boolean
  message: string
  images: string[]
  session_id: string | null
}

/**
 * 通过 TMDB ID 生成 Emby 视频截图
 * 自动查找 Emby Item ID，使用 ffmpeg 截取视频画面
 */
export async function generatePreviewsByTmdb(
  itemType: ItemType,
  tmdbId: string,
  options?: {
    count?: number;
    start_pct?: number;
    end_pct?: number;
    season_number?: number;
    episode_number?: number;
  }
): Promise<PreviewGenerateResult> {
  return api.post<PreviewGenerateResult>('/api/previews/generate-by-tmdb', {
    item_type: itemType,
    tmdb_id: tmdbId,
    count: options?.count ?? 12,
    start_pct: options?.start_pct ?? 10,
    end_pct: options?.end_pct ?? 90,
    season_number: options?.season_number,
    episode_number: options?.episode_number,
  });
}

/**
 * 将选中的截图保存到覆盖缓存目录
 * 剧集模式（传入 seasonNumber + episodeNumber）时按集级别命名保存
 */
export async function savePreviewToOverride(
  itemType: ItemType,
  tmdbId: string,
  imageUrl: string,
  imageType: string = 'poster',
  seasonNumber?: number,
  episodeNumber?: number,
): Promise<{ success: boolean; message: string }> {
  return api.post('/api/previews/save-to-override', {
    item_type: itemType,
    tmdb_id: tmdbId,
    image_url: imageUrl,
    image_type: imageType,
    season_number: seasonNumber,
    episode_number: episodeNumber,
  });
}
