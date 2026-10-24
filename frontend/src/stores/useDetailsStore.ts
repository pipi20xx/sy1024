import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  getItemDetails, updateItemMetadata, refreshItemCache,
  updateSeasonMetadata, updateEpisodeMetadata, copyToOverride,
  deleteOverride, deleteCache, deleteItemImages, deletePatchesFolder, deleteItemMetadata,
  deleteItemTags, deleteEpisodeOrderFile, deleteEpisodeGroupFile,
  deleteExternalIdsFile, getEmbyWebLink, refreshInEmby,
  updateMetadataFromEmby, lockItemName, generateItemTags,
  deleteSeasonMetadata, deleteEpisodeMetadata, updatePatchName,
  updateMetadataFromBangumi,
} from '@/api/details'
import { getWebImages, saveWebImages, downloadImagesFromEmby, getSeasonWebImages, saveSeasonWebImages, getEpisodeWebImages, saveEpisodeWebImages, generatePreviewsByTmdb, savePreviewToOverride } from '@/api/images'
import { saveFullDetails } from '@/api/items'
import type { ItemDetails, ItemType, WebImage } from '@/types'

export const useDetailsStore = defineStore('details', () => {
  const isVisible = ref(false)
  const isLoading = ref(false)
  const itemDetails = ref<ItemDetails | null>(null)
  const currentItemType = ref<ItemType>('tmdb-movies2')
  const currentItemId = ref('')
  const currentViewMode = ref('standard')
  const embyWebLink = ref('')
  const webImages = ref<WebImage[]>([])
  const isImagesLoading = ref(false)

  // 图片 cache-buster 版本号：仅在发生写操作（保存/删除/下载图片等）后递增，
  // 同一会话内的普通加载/静默刷新复用同一 URL，让浏览器缓存生效。
  // 之前每次 loadDetails 都用 Date.now()，详情页一刷新所有海报/剧照/集缩略图
  // 全部重新下载（长剧一次就是几百个重复请求）。
  // sessionBase 保证整页刷新后仍能拿到磁盘上更新过的图片。
  const sessionBase = Date.now()
  let imageVersion = 0

  function applyImageCacheBuster(data: ItemDetails) {
    const bust = `v=${sessionBase}-${imageVersion}`

    if (data.images) {
      data.images.forEach((img) => {
        if (img.url?.startsWith('/media-content')) img.url = `${img.url}?${bust}`
      })
    }
    if (data.poster_path?.startsWith('/media-content')) data.poster_path = `${data.poster_path}?${bust}`
    if (data.seasons) {
      data.seasons.forEach((season) => {
        if (season.poster_path?.startsWith('/media-content')) season.poster_path = `${season.poster_path}?${bust}`
        season.episodes?.forEach((ep) => {
          if (ep.thumb_path?.startsWith('/media-content')) ep.thumb_path = `${ep.thumb_path}?${bust}`
        })
      })
    }
  }

  // 季/集网络图片状态
  const seasonWebImages = ref<WebImage[]>([])
  const episodeWebImages = ref<WebImage[]>([])
  const isSeasonImagesLoading = ref(false)
  const isEpisodeImagesLoading = ref(false)
  // 静默刷新标志：保存图片等操作后刷新数据时不触发 isLoading，
  // 避免整个详情页被 v-if="store.isLoading" 销毁导致子组件状态丢失
  const isSilentRefreshing = ref(false)

  async function openModal(itemType: ItemType, itemId: string) {
    currentItemType.value = itemType
    currentItemId.value = itemId
    currentViewMode.value = 'standard'
    isVisible.value = true
    embyWebLink.value = ''

    await loadDetails()

    if (itemType === 'tmdb-tv' && itemDetails.value?.override_episodegroup_exists) {
      currentViewMode.value = 'episodegroup'
      await loadDetails()
    }

    fetchEmbyLink()
  }

  // 页面模式：不需要弹框，直接加载数据
  async function openPage(itemType: ItemType, itemId: string) {
    currentItemType.value = itemType
    currentItemId.value = itemId
    currentViewMode.value = 'standard'
    isVisible.value = false  // 页面模式不需要弹框
    embyWebLink.value = ''

    await loadDetails()

    if (itemType === 'tmdb-tv' && itemDetails.value?.override_episodegroup_exists) {
      currentViewMode.value = 'episodegroup'
      await loadDetails()
    }

    fetchEmbyLink()
  }

  function closeModal() {
    isVisible.value = false
    itemDetails.value = null
    webImages.value = []
    currentViewMode.value = 'standard'
  }

  async function loadDetails(silent: boolean = false) {
    if (!silent) isLoading.value = true
    else isSilentRefreshing.value = true
    try {
      const data = await getItemDetails(currentItemType.value, currentItemId.value, currentViewMode.value)
      applyImageCacheBuster(data)
      itemDetails.value = data
    } catch (err) {
      console.error('Failed to load details:', err)
    } finally {
      isLoading.value = false
      isSilentRefreshing.value = false
    }
  }

  // 写操作后的刷新：先递增图片版本号，让本次加载拿到新的图片 URL
  async function loadDetailsAfterChange(silent: boolean = false) {
    imageVersion++
    await loadDetails(silent)
  }

  async function toggleViewMode() {
    currentViewMode.value = currentViewMode.value === 'standard' ? 'episodegroup' : 'standard'
    await loadDetails()
  }

  async function refreshCache() {
    isLoading.value = true
    try {
      await refreshItemCache(currentItemType.value, currentItemId.value)
      await loadDetailsAfterChange()
    } catch (err) { console.error(err) } finally { isLoading.value = false }
  }

  async function saveMetadata(newData: any) {
    isLoading.value = true
    try {
      await updateItemMetadata(currentItemType.value, currentItemId.value, newData)
      await loadDetailsAfterChange()
      return true
    } catch (err) { console.error(err); return false } finally { isLoading.value = false }
  }

  async function saveSeasonMetadata(seasonNumber: number, newData: any) {
    isLoading.value = true
    try {
      await updateSeasonMetadata(currentItemId.value, seasonNumber, newData)
      await loadDetailsAfterChange()
      return true
    } catch (err) { console.error(err); return false } finally { isLoading.value = false }
  }

  async function saveEpisodeMetadata(seasonNumber: number, episodeNumber: number, newData: any) {
    isLoading.value = true
    try {
      await updateEpisodeMetadata(currentItemId.value, seasonNumber, episodeNumber, newData)
      await loadDetailsAfterChange()
      return true
    } catch (err) { console.error(err); return false } finally { isLoading.value = false }
  }

  async function loadWebImages(imageTypes?: string[], sources?: string[]) {
    if (!currentItemId.value || !currentItemType.value) return
    isImagesLoading.value = true
    try { webImages.value = await getWebImages(currentItemType.value, currentItemId.value, imageTypes, sources) }
    catch (err) { console.error(err); webImages.value = [] }
    finally { isImagesLoading.value = false }
  }

  async function saveSelectedWebImages(imagesToSave: { url: string; label: string }[], behavior: 'overwrite' | 'skip' = 'overwrite') {
    isImagesLoading.value = true
    try {
      const result = await saveWebImages(currentItemType.value, currentItemId.value, imagesToSave, behavior)
      if (result.success) { await loadDetailsAfterChange(true); return true }
      return false
    } catch (err) { console.error(err); return false } finally { isImagesLoading.value = false }
  }

  async function loadSeasonWebImages(seasonNumber: number, imageTypes?: string[], sources?: string[]) {
    if (!currentItemId.value) return
    isSeasonImagesLoading.value = true
    try { seasonWebImages.value = await getSeasonWebImages(currentItemId.value, seasonNumber, imageTypes, sources) }
    catch (err) { console.error(err); seasonWebImages.value = [] }
    finally { isSeasonImagesLoading.value = false }
  }

  async function saveSelectedSeasonWebImages(seasonNumber: number, imagesToSave: { url: string; label: string }[], behavior: 'overwrite' | 'skip' = 'overwrite') {
    isSeasonImagesLoading.value = true
    try {
      const result = await saveSeasonWebImages(currentItemId.value, seasonNumber, imagesToSave, behavior)
      if (result.success) { await loadDetailsAfterChange(true); return true }
      return false
    } catch (err) { console.error(err); return false } finally { isSeasonImagesLoading.value = false }
  }

  async function loadEpisodeWebImages(seasonNumber: number, episodeNumber: number, imageTypes?: string[], sources?: string[]) {
    if (!currentItemId.value) return
    isEpisodeImagesLoading.value = true
    try { episodeWebImages.value = await getEpisodeWebImages(currentItemId.value, seasonNumber, episodeNumber, imageTypes, sources) }
    catch (err) { console.error(err); episodeWebImages.value = [] }
    finally { isEpisodeImagesLoading.value = false }
  }

  async function saveSelectedEpisodeWebImages(seasonNumber: number, episodeNumber: number, imagesToSave: { url: string; label: string }[], behavior: 'overwrite' | 'skip' = 'overwrite') {
    isEpisodeImagesLoading.value = true
    try {
      const result = await saveEpisodeWebImages(currentItemId.value, seasonNumber, episodeNumber, imagesToSave, behavior)
      if (result.success) { await loadDetailsAfterChange(true); return true }
      return false
    } catch (err) { console.error(err); return false } finally { isEpisodeImagesLoading.value = false }
  }

  async function downloadFromEmby() {
    isImagesLoading.value = true
    try {
      const result = await downloadImagesFromEmby(currentItemType.value, currentItemId.value)
      if (result.success) { await loadDetailsAfterChange(); return true }
      return false
    } catch (err) { console.error(err); return false } finally { isImagesLoading.value = false }
  }

  // 视频截图相关
  const previewImages = ref<string[]>([])
  const isPreviewLoading = ref(false)

  async function generatePreviews(seasonNumber?: number, episodeNumber?: number) {
    isPreviewLoading.value = true
    previewImages.value = []
    try {
      const result = await generatePreviewsByTmdb(currentItemType.value, currentItemId.value, {
        season_number: seasonNumber,
        episode_number: episodeNumber,
      })
      if (result.success) {
        previewImages.value = result.images
      }
      return result
    } catch (err) { console.error(err); return { success: false, message: String(err), images: [], session_id: null } }
    finally { isPreviewLoading.value = false }
  }

  async function savePreviewImage(imageUrl: string, imageType: string = 'poster', seasonNumber?: number, episodeNumber?: number) {
    isImagesLoading.value = true
    try {
      const result = await savePreviewToOverride(currentItemType.value, currentItemId.value, imageUrl, imageType, seasonNumber, episodeNumber)
      if (result.success) { await loadDetailsAfterChange(true); return true }
      return false
    } catch (err) { console.error(err); return false } finally { isImagesLoading.value = false }
  }

  function clearPreviews() {
    previewImages.value = []
  }

  async function copyItemToOverride() {
    isLoading.value = true
    try { await copyToOverride(currentItemType.value, currentItemId.value); await loadDetailsAfterChange(); return true }
    catch (e) { console.error(e); return false } finally { isLoading.value = false }
  }

  async function deleteImages() {
    isLoading.value = true
    try { await deleteItemImages(currentItemType.value, currentItemId.value); await loadDetailsAfterChange(); return true }
    catch (e) { console.error(e); return false } finally { isLoading.value = false }
  }

  async function deletePatches() {
    isLoading.value = true
    try { await deletePatchesFolder(currentItemType.value, currentItemId.value); await loadDetailsAfterChange(); return true }
    catch (e) { console.error(e); return false } finally { isLoading.value = false }
  }

  async function deleteMetadata(mode: 'all' | 'main_only') {
    isLoading.value = true
    try { await deleteItemMetadata(currentItemType.value, currentItemId.value, mode); await loadDetailsAfterChange(); return true }
    catch (e) { console.error(e); return false } finally { isLoading.value = false }
  }

  async function deleteTags() {
    isLoading.value = true
    try { await deleteItemTags(currentItemType.value, currentItemId.value); await loadDetailsAfterChange(); return true }
    catch (e) { console.error(e); return false } finally { isLoading.value = false }
  }

  async function deleteEpisodeOrder() {
    isLoading.value = true
    try { await deleteEpisodeOrderFile(currentItemId.value); await loadDetailsAfterChange(); return true }
    catch (e) { console.error(e); return false } finally { isLoading.value = false }
  }

  async function deleteEpisodeGroup() {
    isLoading.value = true
    try { await deleteEpisodeGroupFile(currentItemId.value); await loadDetailsAfterChange(); return true }
    catch (e) { console.error(e); return false } finally { isLoading.value = false }
  }

  async function deleteExternalIds() {
    isLoading.value = true
    try { await deleteExternalIdsFile(currentItemType.value, currentItemId.value); await loadDetailsAfterChange(); return true }
    catch (e) { console.error(e); return false } finally { isLoading.value = false }
  }

  async function deleteSelectedFiles(targets: string[]) {
    isLoading.value = true
    try {
      for (const target of targets) {
        if (target === 'metadata') await deleteItemMetadata(currentItemType.value, currentItemId.value, 'all')
        else if (target === 'tags') await deleteItemTags(currentItemType.value, currentItemId.value)
        else if (target === 'external_ids') await deleteExternalIdsFile(currentItemType.value, currentItemId.value)
        else if (target === 'episode_order') await deleteEpisodeOrderFile(currentItemId.value)
        else if (target === 'episode_group') await deleteEpisodeGroupFile(currentItemId.value)
      }
      await loadDetailsAfterChange()
      return true
    }
    catch (e) { console.error(e); return false } finally { isLoading.value = false }
  }

  async function deleteOverrideFolder() {
    isLoading.value = true
    try { await deleteOverride(currentItemType.value, currentItemId.value); await loadDetailsAfterChange(); return true }
    catch (e) { console.error(e); return false } finally { isLoading.value = false }
  }

  async function deleteCacheFolder() {
    isLoading.value = true
    try { await deleteCache(currentItemType.value, currentItemId.value); await loadDetailsAfterChange(); return true }
    catch (e) { console.error(e); return false } finally { isLoading.value = false }
  }

  async function deleteSeason(seasonNumber: number, includeEpisodes: boolean) {
    isLoading.value = true
    try { await deleteSeasonMetadata(currentItemId.value, seasonNumber, includeEpisodes); await loadDetailsAfterChange(); return true }
    catch (e) { console.error(e); return false } finally { isLoading.value = false }
  }

  async function deleteEpisode(seasonNumber: number, episodeNumber: number) {
    isLoading.value = true
    try { await deleteEpisodeMetadata(currentItemId.value, seasonNumber, episodeNumber); await loadDetailsAfterChange(); return true }
    catch (e) { console.error(e); return false } finally { isLoading.value = false }
  }

  async function fetchEmbyLink() {
    try { const res = await getEmbyWebLink(currentItemType.value, currentItemId.value); embyWebLink.value = res.url }
    catch (e) { console.warn('Failed to get Emby link', e) }
  }

  async function triggerEmbyRefresh() {
    isLoading.value = true
    try { await refreshInEmby(currentItemType.value, currentItemId.value); return true }
    catch (e) { console.error(e); return false } finally { isLoading.value = false }
  }

  async function triggerEmbyMetadataUpdate(fields: string[] = [], updateChildren = false) {
    isLoading.value = true
    try { await updateMetadataFromEmby(currentItemType.value, currentItemId.value, fields, updateChildren); await loadDetailsAfterChange(); return true }
    catch (e) { console.error(e); return false } finally { isLoading.value = false }
  }

  async function lockName() {
    isLoading.value = true
    try { await lockItemName(currentItemType.value, currentItemId.value); await loadDetailsAfterChange(); return true }
    catch (e) { console.error(e); return false } finally { isLoading.value = false }
  }

  async function updatePatchNameField(name: string) {
    isLoading.value = true
    try { await updatePatchName(currentItemType.value, currentItemId.value, name); await loadDetailsAfterChange(); return true }
    catch (e) { console.error(e); return false } finally { isLoading.value = false }
  }

  async function generateTags(mode: 'merge' | 'overwrite') {
    isLoading.value = true
    try { await generateItemTags(currentItemType.value, currentItemId.value, mode); await loadDetailsAfterChange(); return true }
    catch (e) { console.error(e); return false } finally { isLoading.value = false }
  }

  async function generateTagsFromBgm(mode: 'merge' | 'overwrite' = 'merge', useWhitelist: boolean = false) {
    isLoading.value = true
    try {
      await updateMetadataFromBangumi(currentItemType.value, currentItemId.value, undefined, ['tags'], false, useWhitelist, mode)
      await loadDetailsAfterChange(); return true
    }
    catch (e) { console.error(e); return false } finally { isLoading.value = false }
  }

  async function saveAllChanges() {
    if (!itemDetails.value) return false
    isLoading.value = true
    try { await saveFullDetails(currentItemType.value, currentItemId.value, itemDetails.value); await loadDetailsAfterChange(); return true }
    catch (e) { console.error('Full save failed:', e); return false } finally { isLoading.value = false }
  }

  return {
    isVisible, isLoading, isSilentRefreshing, itemDetails, currentItemType, currentItemId, currentViewMode,
    embyWebLink, webImages, isImagesLoading,
    seasonWebImages, episodeWebImages, isSeasonImagesLoading, isEpisodeImagesLoading,
    previewImages, isPreviewLoading,
    openModal, openPage, closeModal, loadDetails, toggleViewMode, refreshCache,
    saveMetadata, saveSeasonMetadata, saveEpisodeMetadata,
    loadWebImages, saveSelectedWebImages, downloadFromEmby,
    generatePreviews, savePreviewImage, clearPreviews,
    loadSeasonWebImages, saveSelectedSeasonWebImages,
    loadEpisodeWebImages, saveSelectedEpisodeWebImages,
    copyItemToOverride, deleteImages, deletePatches, deleteMetadata, deleteTags,
    deleteEpisodeOrder, deleteEpisodeGroup, deleteExternalIds,
    deleteSelectedFiles,
    deleteOverrideFolder, deleteCacheFolder, deleteSeason, deleteEpisode,
    fetchEmbyLink, triggerEmbyRefresh, triggerEmbyMetadataUpdate,
    lockName, generateTags, generateTagsFromBgm, saveAllChanges, updatePatchNameField,
  }
})
