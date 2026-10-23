import { api } from './client'

export interface LoginRequest {
  username: string
  password: string
}

export interface LoginResponse {
  success: boolean
  data: {
    session_token: string
    user_id: string
    user_info: any
  }
  message: string
}

export interface ConfigData {
  PageId?: string
  EditObjectContainer?: {
    Object?: any
  }
  [key: string]: any
}

export interface ConfigSaveRequest {
  config_data: ConfigData
  session_token: string
}

export interface ConfigResponse {
  success: boolean
  data: any
  message: string
}

export const shenyiApi = {
  login: async (data: LoginRequest): Promise<LoginResponse> => {
    const response = await api.post<LoginResponse>('/api/shenyi/login', data)
    return response
  },

  getConfig: async (sessionToken: string, pageId: string = '63c322:Settings'): Promise<ConfigResponse> => {
    const response = await api.get<ConfigResponse>('/api/shenyi/config', {
      params: { session_token: sessionToken, page_id: pageId }
    })
    return response
  },

  saveConfig: async (data: ConfigSaveRequest): Promise<ConfigResponse> => {
    const response = await api.post<ConfigResponse>('/api/shenyi/config', data)
    return response
  }
}