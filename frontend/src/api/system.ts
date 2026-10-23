import { api } from './client'

export interface ScanStatus {
  status: 'idle' | 'scanning' | 'completed' | 'error'
  total: number
  current: number
  message: string
}

export async function triggerScan(): Promise<{ message: string }> {
  return api.post('/api/scan', {})
}

export async function getScanStatus(): Promise<ScanStatus> {
  return api.get<ScanStatus>('/api/scan/status')
}

export async function importOverrideZip(file: File): Promise<{ message: string; success: boolean }> {
  const formData = new FormData()
  formData.append('file', file)
  return api.post('/api/backups/import_zip', formData)
}

export interface EmbyTestResult {
  success: boolean
  message: string
}

export async function testEmbyConnection(params: {
  emby_server_url: string
  emby_api_key: string
  emby_user_id: string
}): Promise<EmbyTestResult> {
  return api.post('/api/system/test-emby', params)
}

export interface EmbyLoginRequest {
  username: string
  password: string
}

export interface EmbyLoginResult {
  success: boolean
  data: {
    session_token: string
    user_id: string
  }
  message: string
}

export async function embyLogin(params: EmbyLoginRequest): Promise<EmbyLoginResult> {
  return api.post('/api/system/emby-login', params)
}

export async function checkUpdate(force = false): Promise<any> {
  return api.get('/api/system/check-update', { params: { force } })
}

export interface FileWatcherStatus {
  enabled: boolean
  watched_paths: string[]
}

export async function getFileWatcherStatus(): Promise<FileWatcherStatus> {
  return api.get<FileWatcherStatus>('/api/system/file-watcher/status')
}
