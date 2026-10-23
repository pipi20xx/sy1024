// frontend_new/src/api/collections.ts

import { api } from './client';

export interface CollectionItem {
    id: string;
    name: string;
}

export interface Collection {
  name: string;
  collection_name?: string; // Backend field
  overview: string;
  items?: string[]; // Deprecated: legacy flat list
  movies?: CollectionItem[];
  series?: CollectionItem[];
  movie_count?: number;
  series_count?: number;
  poster_path?: string;
  backdrop_path?: string;
  filename: string;
}

export async function getCollections(): Promise<Collection[]> {
  const response = await api.get<{ collections: Collection[] }>('/api/emby-collections');
  return response.collections.map(c => ({
      ...c,
      name: c.collection_name || c.name // Ensure name is populated
  }));
}

export async function scanCollections(): Promise<{ message: string; success: boolean }> {
  return api.post('/api/emby-collections/scan', {});
}

export async function getCollectionDetails(filename: string): Promise<Collection> {
  return api.get<Collection>(`/api/emby-collections/${filename}`);
}

export async function createCollection(data: Partial<Collection> & { tmdb_collection_id?: string }): Promise<{ message: string; filename: string }> {
  // Backend expects separate movies and series arrays
  const payload = {
      collection_name: data.collection_name || data.name,
      overview: data.overview,
      movies: data.movies || [],
      series: data.series || [],
      tmdb_collection_id: data.tmdb_collection_id || ""
  };
  return api.post('/api/emby-collections', payload);
}

export async function updateCollection(originalFilename: string, data: Partial<Collection> & { tmdb_collection_id?: string }): Promise<{ message: string; filename: string }> {
  const payload = {
      collection_name: data.collection_name || data.name,
      overview: data.overview,
      movies: data.movies || [],
      series: data.series || [],
      tmdb_collection_id: data.tmdb_collection_id || ""
  };
  return api.put(`/api/emby-collections/${originalFilename}`, payload);
}

export async function deleteCollection(filename: string): Promise<{ message: string }> {
  return api.delete(`/api/emby-collections/${filename}`);
}

export async function applyCollectionToEmby(filename: string, onProgress?: (msg: string) => void): Promise<any> {
    return new Promise((resolve, reject) => {
        const accessToken = localStorage.getItem('access_token');
        const url = `/api/emby-collections/apply-single/${filename}${accessToken ? `?auth_token=${encodeURIComponent(accessToken)}` : ''}`;
        const eventSource = new EventSource(url);
        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (onProgress && data.message) {
                onProgress(data.message);
            }
            if (data.status === 'finished' || data.status === 'completed' || data.status === 'error') {
                eventSource.close();
                if (data.status === 'error') reject(data.message);
                else resolve(data);
            }
        };
        eventSource.onerror = (err) => {
            eventSource.close();
            reject(err);
        };
    });
}

export function applyAllCollectionsToEmby(): EventSource {
    const accessToken = localStorage.getItem('access_token');
    const url = `/api/emby-collections/apply-all-to-emby${accessToken ? `?auth_token=${encodeURIComponent(accessToken)}` : ''}`;
    return new EventSource(url);
}

export async function applyAllCollectionsToEmbyBg(): Promise<{ message: string; success: boolean }> {
    return api.post('/api/emby-collections/apply-all-to-emby-bg', {});
}

export async function importAllCollectionsFromEmby(overwriteJson: boolean, overwriteImages: boolean): Promise<any> {
    // Changed to POST for background task
    return api.post('/api/emby-collections/import-all-from-emby', { 
        overwrite_json: overwriteJson, 
        overwrite_images: overwriteImages 
    });
}

export async function importCollectionFromEmby(collectionName: string, overwriteJson: boolean, overwriteImages: boolean): Promise<any> {
    return api.post('/api/emby-collections/import-from-emby', { collection_name: collectionName, overwrite_json: overwriteJson, overwrite_images: overwriteImages });
}

export async function uploadCollectionImage(filename: string, imageType: 'poster' | 'backdrop' | 'logo', file: File): Promise<{ message: string; success: boolean }> {
    const formData = new FormData();
    formData.append('file', file);
    
    const headers: Record<string, string> = {};
    const token = localStorage.getItem('access_token');
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    
    const response = await fetch(`/api/emby-collections/${filename}/images?image_type=${imageType}`, {
        method: 'POST',
        body: formData,
        headers,
    });
    
    const result = await response.json();
    if (!response.ok) {
        throw new Error(result.detail || '上传失败');
    }
    return result;
}

export async function importCollectionZip(file: File): Promise<{ message: string; success: boolean }> {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/api/collections/import_zip', formData);
}
