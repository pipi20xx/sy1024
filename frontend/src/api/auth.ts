import { api } from './client'

export interface LoginParams {
  username: string
  password: string
  otp_code?: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  username: string
  status: string
  require_otp?: boolean
}

export const loginApi = (data: LoginParams) => {
  return api.post<TokenResponse>('/api/auth/login', data)
}

export const setup2faApi = () => {
  return api.get<{ secret: string; qr_code: string }>('/api/auth/2fa/setup')
}

export const enable2faApi = (code: string) => {
  return api.post('/api/auth/2fa/enable', null, { params: { code } })
}

export const disable2faApi = () => {
  return api.post('/api/auth/2fa/disable', null)
}

export const changePasswordApi = (data: any) => {
  return api.post('/api/auth/password', data)
}

export const getUserInfoApi = () => {
  return api.get<{ username: string; is_otp_enabled: boolean; last_login: string }>('/api/auth/me')
}
