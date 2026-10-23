import { api } from './client';

export interface SpecifyScrapeRequest {
  emby_item_id: string;
  new_tmdb_id: string;
}

export interface LastEmbyIdResponse {
  emby_item_id: string;
}

export interface LastEmbyIdRequest {
    emby_item_id: string;
}

export const embyApi = {
  async specifyScrape(payload: SpecifyScrapeRequest) {
    const response = await api.post('/api/emby/specify-scrape', payload);
    return response;
  },

  async getLastEmbyId() {
    const response = await api.get<LastEmbyIdResponse>('/api/config/last-emby-id');
    return response;
  },

  async saveLastEmbyId(payload: LastEmbyIdRequest) {
      const response = await api.post('/api/config/last-emby-id', payload);
      return response;
  }
};
