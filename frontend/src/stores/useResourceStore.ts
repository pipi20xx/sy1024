import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getResources, saveResources, uploadAttachment } from '@/api/resources'
import type { ResourceItem, ItemType } from '@/types'

export const useResourceStore = defineStore('resource', () => {
  const resources = ref<ResourceItem[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  async function loadResources(itemType: ItemType, itemId: string) {
    isLoading.value = true; error.value = null
    try { resources.value = await getResources(itemType, itemId) }
    catch (err: any) { error.value = err.message || '加载资源失败' }
    finally { isLoading.value = false }
  }

  async function save(itemType: ItemType, itemId: string, newResources: ResourceItem[]) {
    isLoading.value = true
    try { await saveResources(itemType, itemId, newResources); resources.value = newResources; return true }
    catch (err: any) { error.value = err.message || '保存资源失败'; return false }
    finally { isLoading.value = false }
  }

  async function uploadFile(itemType: ItemType, itemId: string, file: File) {
    return await uploadAttachment(itemType, itemId, file)
  }

  function clear() { resources.value = []; error.value = null }

  return { resources, isLoading, error, loadResources, save, uploadFile, clear }
})
