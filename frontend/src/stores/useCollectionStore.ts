import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  getCollections, createCollection, updateCollection, deleteCollection as apiDeleteCollection,
  applyCollectionToEmby, importCollectionFromEmby, importAllCollectionsFromEmby,
  applyAllCollectionsToEmby, applyAllCollectionsToEmbyBg, scanCollections,
} from '@/api/collections'
import type { Collection } from '@/api/collections'

export const useCollectionStore = defineStore('collection', () => {
  const collections = ref<Collection[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  async function loadCollections() {
    isLoading.value = true; error.value = null
    try { collections.value = await getCollections() }
    catch (err: any) { error.value = err.message || '加载合集失败' }
    finally { isLoading.value = false }
  }

  async function scanLibrary() {
    isLoading.value = true
    try { await scanCollections(); await loadCollections() }
    catch (err: any) { error.value = err.message || '扫描失败' }
    finally { isLoading.value = false }
  }

  async function create(data: Partial<Collection>) {
    isLoading.value = true
    try { await createCollection(data); await loadCollections(); return true }
    catch (err) { console.error(err); return false } finally { isLoading.value = false }
  }

  async function update(originalFilename: string, data: Partial<Collection>) {
    isLoading.value = true
    try { await updateCollection(originalFilename, data); await loadCollections(); return true }
    catch (err) { console.error(err); return false } finally { isLoading.value = false }
  }

  async function remove(filename: string) {
    isLoading.value = true
    try { await apiDeleteCollection(filename); await loadCollections(); return true }
    catch (e) { console.error(e); return false } finally { isLoading.value = false }
  }

  async function syncToEmby(filename: string, onProgress?: (msg: string) => void) {
    try { await applyCollectionToEmby(filename, onProgress); return true }
    catch (e) { console.error(e); return false }
  }

  async function importFromEmby(name: string, overwriteJson: boolean, overwriteImages: boolean) {
    isLoading.value = true
    try { await importCollectionFromEmby(name, overwriteJson, overwriteImages); await loadCollections(); return true }
    finally { isLoading.value = false }
  }

  async function importAllFromEmby(overwriteJson: boolean, overwriteImages: boolean) {
    return await importAllCollectionsFromEmby(overwriteJson, overwriteImages)
  }

  function applyAllToEmby(): EventSource {
    return applyAllCollectionsToEmby()
  }

  async function applyAllToEmbyBg() {
    return await applyAllCollectionsToEmbyBg()
  }

  return {
    collections, isLoading, error,
    loadCollections, scanLibrary, create, update, remove,
    syncToEmby, importFromEmby, importAllFromEmby, applyAllToEmby, applyAllToEmbyBg,
  }
})
