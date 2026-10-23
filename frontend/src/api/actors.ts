import { api } from './client';

export interface ActorItem {
  id: number;
  tmdb_id: number;
  name: string;
  original_name: string;
  duplicate_tmdb_id: string;
  profile_path?: string;
  metadata?: any;
}

export interface ActorResponse {
  items: ActorItem[];
  total: number;
  page: number;
  page_size: number;
}

export async function getActors(params: { search?: string; duplicate_type?: string; page?: number; page_size?: number }): Promise<ActorResponse> {
  return api.get('/api/actors', { params });
}

export async function deleteActor(actorId: number): Promise<{ message: string }> {
  return api.delete(`/api/actors/${actorId}`);
}

export async function updateActor(actorId: number, data: Partial<ActorItem>): Promise<ActorItem> {
  return api.put(`/api/actors/${actorId}`, data);
}

export async function deleteAllActors(): Promise<{ message: string }> {
  return api.delete('/api/actors');
}

export async function importActorsFromOverride(): Promise<{ message: string }> {
  return api.post('/api/actors/import-from-override', {});
}

export async function importActorsFromOverrideBg(): Promise<{ message: string; success: boolean }> {
  return api.post('/api/actors/import-from-override-bg', {});
}

export async function updateActorsOverride(): Promise<{ message: string; success: boolean }> {
  return api.post('/api/actors/update-override', {});
}

export async function getMergePreview(type: string): Promise<any[]> {
  return api.get('/api/actors/merge/preview', { params: { type } });
}

export async function executeMerge(plan: any[]): Promise<{ message: string }> {
  return api.post('/api/actors/merge/execute', plan);
}

export async function updateActorsFromTmdb(actorIds: number[]): Promise<{ message: string; success_count: number; fail_count: number }> {
  return api.post('/api/actors/update-from-tmdb', actorIds);
}

export async function updateAllActorsFromTmdb(): Promise<{ message: string; success: boolean }> {
  return api.post('/api/actors/update-all-from-tmdb', {});
}

export async function getActorDetail(actorId: number): Promise<ActorItem> {
  return api.get(`/api/actors/${actorId}`);
}

export async function refreshActorFromTmdb(actorId: number): Promise<ActorItem> {
  return api.post(`/api/actors/${actorId}/refresh-from-tmdb`, {});
}

export async function getActorByTmdbId(tmdbId: number): Promise<ActorItem> {
  return api.get(`/api/actors/tmdb/${tmdbId}`);
}

export async function createOrGetActorByTmdbId(tmdbId: number): Promise<ActorItem> {
  return api.post(`/api/actors/tmdb/${tmdbId}`, {});
}
