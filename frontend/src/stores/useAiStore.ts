import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getAiConfigApi, updateAiConfigApi, getAiPresetsApi, type AiConfig } from '@/api/ai'

export const DEFAULT_PROMPTS = {
  movie_title: '你是一个影视翻译专家。请将以下【电影标题】翻译成中文。如果已有公认的官方中文译名，请优先使用；如果没有，请提供一个优美的译名。直接返回标题，不要解释。',
  series_title: '你是一个影视翻译专家。请将以下【剧集标题】翻译成中文。如果已有公认的官方中文译名，请优先使用；如果没有，请提供一个贴切的译名。直接返回标题，不要解释。',
  season_title: '你是一个影视翻译专家。请将以下【剧集季度标题】翻译成中文。要求：保持与主剧名风格一致，准确传达本季主题。直接返回标题，不要解释。',
  movie_overview: '你是一个专业的影视翻译专家。请将以下【电影简介】翻译成中文。要求：风格宏大且自然，符合中文表达习惯，保持剧情张力。',
  series_overview: '你是一个专业的影视翻译专家。请将以下【剧集简介】翻译成中文。要求：概述清晰，吸引人，符合中文表达习惯。',
  season_overview: '你是一个专业的影视翻译专家。请将以下【剧集季度简介】翻译成中文。要求：简洁明了地描述本季的核心剧情。',
  episode_title: '你是一个影视翻译专家。请将以下【分集标题】翻译成中文。要求：风格与整剧保持一致，准确传达本集主题。直接返回标题，不要解释。',
  episode_overview: '你是一个专业的影视翻译专家。请将以下【分集剧情简介】翻译成中文。要求：准确描述本集内容，用词精炼。',
  actor_name: '你是一个专业的影视库整理助手。请将以下【演员/制作人员名称】或【角色名】翻译成中文。如果是外文名，请提供通用的中文译名。直接返回结果，不要解释，不要标点符号。',
  cast_name: '你是一个专业的翻译助手。请将以下【演员姓名】翻译成中文。要求：遵循通用的影视译名惯例（音译），直接返回名字，不要解释。',
  cast_character: '你是一个专业的影视翻译专家。请将以下【角色名称】翻译成中文。要求：根据语境提供贴切的译名，如果该角色有公认译名请直接使用。直接返回结果。',
  crew_name: '你是一个专业的翻译助手。请将以下【制作人员姓名】翻译成中文。要求：遵循通用的影视译名惯例（音译），直接返回名字，不要解释。',
  crew_job: '你是一个影视行业术语专家。请将以下【制作职位/头衔】翻译成中文专业术语。要求：用词专业准确。直接返回翻译结果。',
}

export const useAiStore = defineStore('ai', () => {
  const config = ref<AiConfig>({
    enabled: false,
    include_item_context: true,
    provider: 'openai',
    base_url: '',
    api_key: '',
    model: 'gpt-3.5-turbo',
    temperature: 0.3,
    prompts: { ...DEFAULT_PROMPTS },
  })

  const presets = ref<Record<string, { name: string; description: string; prompts: any }>>({})

  async function loadConfig() {
    try {
      const res = await getAiConfigApi()
      config.value = { ...config.value, ...res, prompts: { ...DEFAULT_PROMPTS, ...(res.prompts || {}) } }
      try {
        const presetRes = await getAiPresetsApi()
        if (presetRes && typeof presetRes === 'object') presets.value = { ...presetRes }
      } catch (e) { console.error('Failed to load AI presets', e) }
    } catch (e) { console.error('Failed to load AI config', e) }
  }

  function applyPreset(key: string) {
    const preset = presets.value[key]
    if (preset?.prompts) config.value.prompts = { ...config.value.prompts, ...preset.prompts }
  }

  function resetPrompt(key: keyof typeof DEFAULT_PROMPTS) {
    if (config.value.prompts) config.value.prompts[key] = (DEFAULT_PROMPTS as any)[key]
  }

  async function saveConfig() {
    try { await updateAiConfigApi(config.value); return true }
    catch (e: any) { console.error('Save AI config failed:', e); throw e }
  }

  return { config, presets, loadConfig, applyPreset, resetPrompt, saveConfig }
})
