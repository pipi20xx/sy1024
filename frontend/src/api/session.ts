import { api } from './client'

export interface SessionInfo {
  id: number
  session_id: string
  device_name: string
  device_type: string
  ip_address: string
  user_agent: string
  login_time: string
  last_activity: string
  expires_at: string
  is_current: boolean
  expires_in_hours: number
}

export interface RevokeResponse {
  message: string
}

export const getSessionsApi = () => {
  return api.get<SessionInfo[]>('/api/auth/sessions')
}

export const revokeSessionApi = (sessionId: string) => {
  return api.delete<RevokeResponse>(`/api/auth/sessions/${sessionId}`)
}

export const revokeAllOtherSessionsApi = () => {
  return api.delete<RevokeResponse>('/api/auth/sessions')
}

export const updateSessionsExpiryApi = () => {
  return api.post<RevokeResponse>('/api/auth/sessions/update-expiry', {})
}
