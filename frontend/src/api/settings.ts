// frontend_new/src/api/settings.ts

import { api } from './client';

export interface AppSettings {
  primary_cache_path: string;
  override_cache_path: string;
  backup_path: string;
  resource_info_path: string | null;
  emby_collections_path: string | null;
  emby_host: string;
  emby_api_key: string;
  emby_user_id: string;
  tmdb_api_key: string;
  tmdb_image_base_url: string;
  auto_backup_enabled: boolean;
  auto_backup_interval_hours: number;
  auto_backup_mode: 'snapshot' | 'zip';
  auto_backup_include_override: boolean;
  auto_backup_include_collections: boolean;
  emby_webhook_enabled: boolean;
  webhook_secret_token: string;
  // ... 其他配置项
  [key: string]: any;
}

export interface BackupItem {
  filename: string;
  created_at: string;
  size_mb: string;
  type: 'snapshot' | 'zip';
  triggered_by?: string;
  // Optional/Legacy fields
  timestamp?: number;
  size?: number;
  mode?: 'snapshot' | 'zip';
}

export async function getAllSettings(): Promise<AppSettings> {
  return api.get<AppSettings>('/api/settings/all');
}

export async function saveAllSettings(settings: AppSettings): Promise<{ message: string }> {
  return api.post('/api/settings/all', settings);
}

export async function getBackups(): Promise<BackupItem[]> {
  return api.get<BackupItem[]>('/api/backups');
}

export async function createBackup(mode: 'snapshot' | 'zip', includeOverride: boolean, includeCollections: boolean): Promise<{ message: string }> {
  return api.post('/api/backups/create', {}, {
    params: {
      mode,
      include_override: includeOverride,
      include_collections: includeCollections
    }
  });
}

export async function restoreBackup(filename: string, mode: 'merge_add' | 'overwrite' | 'clean_restore'): Promise<{ message: string }> {
  return api.post(`/api/backups/restore/${filename}`, {}, {
    params: { mode }
  });
}

export async function deleteBackup(filename: string): Promise<{ message: string }> {
  return api.delete(`/api/backups/${filename}`);
}

export async function browsePath(path: string): Promise<{name: string, type: string, path: string}[]> {
    return api.get('/api/browse_path', { params: { path } });
}

export async function getSystemLogs(): Promise<{filename: string; size: number; mtime: number}[]> {
    return api.get('/api/system/logs');
}
