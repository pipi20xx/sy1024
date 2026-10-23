import { defineStore } from 'pinia'
import { ref } from 'vue'
import { runWorkflow, type WorkflowTask, type WorkflowRequest } from '@/api/workflow'
import { useItemStore } from './useItemStore'

export const useWorkflowStore = defineStore('workflow', () => {
  const isLoading = ref(false)

  const availableTasks: WorkflowTask[] = [
    { type: 'tmdb_update_metadata', description: '从 TMDB 更新元数据', params: { overwrite: true } },
    { type: 'bangumi_update_metadata', description: '从 Bangumi 更新元数据', params: { force_refresh: false, use_whitelist: false, mode: 'merge', auto_match: false } },
    { type: 'copy_to_override', description: '补充到 Override' },
    { type: 'emby_download_images', description: '从 Emby 下载图片' },
    { type: 'download_web_images', description: '从网络下载图片', params: { sources: ['tmdb', 'fanart'], image_types: ['poster', 'fanart', 'logo'], behavior: 'overwrite' } },
    { type: 'emby_update_metadata', description: '从 Emby 更新元数据', params: { fields_to_update: [], update_children: false } },
    { type: 'emby_refresh', description: '在 Emby 中刷新' },
    { type: 'lock_name', description: '锁定名称' },
    { type: 'delete_all_images', description: '删除所有图片' },
    { type: 'delete_override', description: '删除 Override (慎用)' },
    { type: 'delete_override_files', description: '删除元数据文件', params: { targets: ['metadata', 'tags', 'external_ids', 'episode_order', 'episode_group'] } },
    { type: 'generate_item_tags', description: '生成自定义标签' },
    { type: 'ai_translate', description: 'AI 批量中文化', params: {
      title: true, overview: true, season_title: false, season_overview: false,
      episode_title: false, episode_overview: false, credits: false,
      include_children_credits: false,
      credits_options: { cast_name: true, cast_character: true, crew_name: false, crew_job: false },
    } },
  ]

  async function executeWorkflow(tasks: WorkflowTask[], interval: number) {
    if (tasks.length === 0) return
    isLoading.value = true

    const itemStore = useItemStore()
    const filters: any = {}
    if (itemStore.searchTerm) filters.search_term = itemStore.searchTerm
    if (itemStore.selectedSource) filters.source = itemStore.selectedSource
    if (itemStore.selectedPosterStatus) filters.poster_status = itemStore.selectedPosterStatus
    if (itemStore.selectedGenre) filters.genres = [itemStore.selectedGenre]
    if (itemStore.selectedYear) filters.year = itemStore.selectedYear
    if (itemStore.selectedMonth) filters.month = itemStore.selectedMonth

    const request: WorkflowRequest = {
      item_type: itemStore.currentItemType,
      tasks: tasks.map(({ type, params }) => ({ type, params })),
      interval_seconds: interval,
      filters,
    }

    try { await runWorkflow(request); return true }
    catch (e) { console.error(e); return false }
    finally { isLoading.value = false }
  }

  return { availableTasks, isLoading, executeWorkflow }
})
