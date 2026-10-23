import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getAllSettings, saveAllSettings, getBackups, createBackup, restoreBackup, deleteBackup, browsePath } from '@/api/settings'
import type { AppSettings, BackupItem } from '@/api/settings'

export const useSettingsStore = defineStore('settings', () => {
  const settings = ref<AppSettings>({} as AppSettings)
  const backups = ref<BackupItem[]>([])
  const isLoading = ref(false)
  const isBackupLoading = ref(false)

  async function loadSettings() {
    isLoading.value = true
    try { settings.value = await getAllSettings() }
    catch (err) { console.error('Failed to load settings:', err) }
    finally { isLoading.value = false }
  }

  async function saveSettings(newSettings: AppSettings) {
    isLoading.value = true
    try { await saveAllSettings(newSettings); await loadSettings(); return true }
    catch (err) { console.error('Failed to save settings:', err); return false }
    finally { isLoading.value = false }
  }

  async function loadBackups() {
    isBackupLoading.value = true
    try { backups.value = await getBackups() }
    catch (err) { console.error('Failed to load backups:', err) }
    finally { isBackupLoading.value = false }
  }

  async function createNewBackup(mode: 'snapshot' | 'zip', includeOverride: boolean, includeCollections: boolean) {
    isBackupLoading.value = true
    try { await createBackup(mode, includeOverride, includeCollections); await loadBackups(); return true }
    catch (err) { console.error('Failed to create backup:', err); return false }
    finally { isBackupLoading.value = false }
  }

  async function restoreFromBackup(filename: string, mode: 'merge_add' | 'overwrite' | 'clean_restore') {
    isBackupLoading.value = true
    try { await restoreBackup(filename, mode); return true }
    catch (err) { console.error('Failed to restore backup:', err); return false }
    finally { isBackupLoading.value = false }
  }

  async function deleteOneBackup(filename: string) {
    isBackupLoading.value = true
    try { await deleteBackup(filename); await loadBackups(); return true }
    catch (err) { console.error('Failed to delete backup:', err); return false }
    finally { isBackupLoading.value = false }
  }

  async function browseServerPath(path: string) {
    return await browsePath(path)
  }

  return {
    settings, backups, isLoading, isBackupLoading,
    loadSettings, saveSettings, loadBackups, createNewBackup,
    restoreFromBackup, deleteOneBackup, browseServerPath,
  }
})
