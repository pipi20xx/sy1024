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
