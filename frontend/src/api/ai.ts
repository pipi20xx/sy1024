import { api } from './client'

export interface AiConfig {
  enabled: boolean
  include_item_context: boolean
  provider: string
  base_url: string
  api_key: string
  model: string
  temperature: number
  prompts: {
    movie_title: string
    series_title: string
    season_title: string
    movie_overview: string
    series_overview: string
    season_overview: string
    episode_title: string
    episode_overview: string
    cast_name: string
    cast_character: string
    crew_name: string
    crew_job: string
    actor_name: string
  }
}

export const getAiConfigApi = () => {
  return api.get<AiConfig>('/api/ai/config')
}

export const updateAiConfigApi = (config: Partial<AiConfig>) => {
  return api.post('/api/ai/config', config)
}

export const getAiPresetsApi = () => {
  return api.get<Record<string, { name: string; description: string; prompts: any }>>('/api/ai/presets')
}

export const testTranslationApi = (text: string, context: string = 'movie_overview', extra_info?: any) => {
  return api.post<{ original: string; translated: string }>('/api/ai/test-translation', { text, context, extra_info })
}

export const batchTranslationApi = (texts: string[], context: string, extra_info?: any) => {
  return api.post<{ results: string[] }>('/api/ai/batch-translate', { texts, context, extra_info })
}

export const aiChatApi = (messages: { role: string; content: string }[]) => {
  return api.post<{ response: string }>('/api/ai/chat', messages)
}
