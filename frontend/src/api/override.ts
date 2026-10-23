import { api } from './client';

export interface TmdbManualGenerateOptions {
  source?: 'tmdb' | 'bangumi';
  source_item_type: 'movie' | 'tv' | 'season' | 'episode';
  target_item_type?: 'movie' | 'tv';
  source_tmdb_id: string;
  target_tmdb_id: string;
  lang?: string;
  source_season?: number;
  target_season?: number;
  source_episode?: number;
  target_episode?: number;
  selected_episodes?: number[];
  overwrite?: boolean;
  recursive?: boolean;
  trigger_emby_refresh?: boolean;
}

export async function manualGenerateTmdb(options: TmdbManualGenerateOptions): Promise<any> {
  return api.post<any>('/api/tmdb/manual-generate', options);
}

export async function getBangumiPreview(subjectId: number): Promise<{ title: string; episodes: any[] }> {
  return api.get<any>(`/api/tmdb/bangumi-preview/${subjectId}`);
}
