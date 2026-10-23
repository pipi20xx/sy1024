<script setup lang="ts">
import { onMounted, ref, watch, computed } from 'vue'
import { useSettingsStore, useAiStore, useSystemStore } from '@/stores'
defineOptions({ name: 'SettingsView' })
import { setup2faApi, enable2faApi, disable2faApi, changePasswordApi, getUserInfoApi } from '@/api/auth'
import { testEmbyConnection, embyLogin, getFileWatcherStatus, type FileWatcherStatus } from '@/api/system'
import { restoreBackup, saveAllSettings } from '@/api/settings'
import { getSessionsApi, revokeSessionApi, revokeAllOtherSessionsApi, updateSessionsExpiryApi, type SessionInfo } from '@/api/session'
import { testTranslationApi } from '@/api/ai'
import { useNotification, useConfirm } from '@/composables'
import PasswordInput from '@/components/common/PasswordInput.vue'
import PathBrowserDialog from '@/components/common/PathBrowserDialog.vue'

const settingsStore = useSettingsStore()
const aiStore = useAiStore()
const systemStore = useSystemStore()
const { notify } = useNotification()
const { confirm } = useConfirm()

const activeTab = ref('general')
const formSettings = ref<Record<string, any>>({})

// 浏览偏好（纯前端，存 localStorage）
const openDetailInNewTab = ref(localStorage.getItem('open_detail_in_new_tab') === 'true')
function toggleOpenDetailInNewTab(v: boolean | null) {
  const val = !!v
  openDetailInNewTab.value = val
  localStorage.setItem('open_detail_in_new_tab', String(val))
}

// 2FA
const show2faDialog = ref(false)
const twoFactorSetup = ref<{ secret: string; qr_code: string } | null>(null)
const twoFactorCode = ref('')
const is2faEnabled = ref(false)

// 密码
const showPasswordDialog = ref(false)
const passwordForm = ref({ current: '', new: '', confirm: '' })

// 用户信息
const userInfo = ref<{ username: string; is_otp_enabled: boolean } | null>(null)

// Emby 测试
const isTestingEmby = ref(false)

// Emby 登录
const isLoggingInEmby = ref(false)

// 会话管理
const sessions = ref<SessionInfo[]>([])
const isLoadingSessions = ref(false)

// 永久登录
const permanentLoginEnabled = ref(false)
const permanentLoginLoading = ref(false)

// 实时文件监控
const fileWatcherStatus = ref<FileWatcherStatus | null>(null)

// AI 测试台
const testInput = ref('小手指向陽・高校1年生。特技は、気持ちよくさせすぎちゃう超絶マッサージ！！')
const testResult = ref('')
const isTestingAi = ref(false)

// 备份创建
const showBackupModal = ref(false)
const backupConfig = ref({ mode: 'snapshot' as 'snapshot' | 'zip', includeOverride: true, includeCollections: true })

// 恢复备份
const showRestoreDialog = ref(false)
const restoreFilename = ref('')
const restoreMode = ref<'merge_add' | 'overwrite' | 'clean_restore'>('merge_add')

// 路径浏览器
const showPathBrowser = ref(false)
const pathBrowserTitle = ref('')
const pathBrowserField = ref('')
const pathBrowserCurrent = ref('')

function openPathBrowser(field: string, label: string) {
  pathBrowserField.value = field
  pathBrowserTitle.value = label
  pathBrowserCurrent.value = formSettings.value[field] || '/'
  showPathBrowser.value = true
}

function handlePathSelect(path: string) {
  formSettings.value[pathBrowserField.value] = path
}

onMounted(async () => {
  await settingsStore.loadSettings()
  formSettings.value = { ...settingsStore.settings }
  aiStore.loadConfig()
  settingsStore.loadBackups()
  loadUserInfo()
  loadPermanentLoginSetting()
  loadFileWatcherStatus()
})

watch(() => settingsStore.settings, (val) => {
  formSettings.value = { ...val }
}, { deep: true })

async function loadUserInfo() {
  try {
    userInfo.value = await getUserInfoApi()
    is2faEnabled.value = userInfo.value.is_otp_enabled
  } catch { /* ignore */ }
}

async function handleSaveSettings() {
  const success = await settingsStore.saveSettings(formSettings.value as any)
  if (success) {
    notify('设置已保存', '', 'success')
    await loadFileWatcherStatus()
  }
  else notify('保存失败', '', 'error')
}

async function handleTestEmby() {
  if (!formSettings.value.emby_server_url || !formSettings.value.emby_api_key) {
    notify('提示', '请先填写 Emby 服务器地址和 API 密钥', 'warning')
    return
  }
  isTestingEmby.value = true
  try {
    const result = await testEmbyConnection({
      emby_server_url: formSettings.value.emby_server_url,
      emby_api_key: formSettings.value.emby_api_key,
      emby_user_id: formSettings.value.emby_user_id,
    })
    if (result.success) notify('连接成功', result.message, 'success')
    else notify('连接失败', result.message, 'error')
  } catch (e: any) {
    notify('测试失败', e.message, 'error')
  } finally {
    isTestingEmby.value = false
  }
}

async function handleEmbyLogin() {
  if (!formSettings.value.emby_username || !formSettings.value.emby_password) {
    notify('提示', '请输入用户名和密码', 'warning')
    return
  }
  isLoggingInEmby.value = true
  try {
    const result = await embyLogin({
      username: formSettings.value.emby_username,
      password: formSettings.value.emby_password,
    })
    if (result.success) {
      formSettings.value.emby_user_id = result.data.user_id
      notify('登录成功', '已获取会话令牌', 'success')
      await handleSaveSettings()
    }
  } catch (e: any) {
    notify('登录失败', e.response?.data?.detail || e.message, 'error')
  } finally {
    isLoggingInEmby.value = false
  }
}

// Webhook URL
const webhookUrl = computed(() => {
  if (!formSettings.value.emby_webhook_enabled) return 'Webhook 功能未启用，请勾选并保存设置。'
  const token = formSettings.value.webhook_secret_token
  if (token) return `${window.location.origin}/api/webhook/emby/${token}`
  return '请输入一个安全密钥...'
})

async function copyWebhookUrl() {
  if (!webhookUrl.value.startsWith('http')) {
    notify('提示', '没有可复制的有效 URL', 'warning')
    return
  }
  try {
    await navigator.clipboard.writeText(webhookUrl.value)
    notify('已复制到剪贴板', '', 'success')
  } catch {
    notify('复制失败', '', 'error')
  }
}

// 备份
async function handleCreateBackup() {
  const success = await settingsStore.createNewBackup(
    backupConfig.value.mode, backupConfig.value.includeOverride, backupConfig.value.includeCollections,
  )
  if (success) {
    notify('备份已创建', '', 'success')
    showBackupModal.value = false
  } else notify('备份创建失败', '', 'error')
}

async function handleRestoreBackup() {
  const ok = await confirm({
    title: '恢复备份',
    content: `确定要恢复备份 ${restoreFilename.value} 吗？当前数据可能会被覆盖。`,
    confirmColor: 'warning',
  })
  if (!ok) return
  try {
    await restoreBackup(restoreFilename.value, restoreMode.value)
    notify('恢复成功', '', 'success')
    showRestoreDialog.value = false
  } catch (e: any) {
    notify('恢复失败', e.message, 'error')
  }
}

async function handleDeleteBackup(filename: string) {
  const ok = await confirm({
    title: '删除备份',
    content: `确认删除备份 ${filename}？此操作不可恢复。`,
    confirmColor: 'error',
  })
  if (!ok) return
  const success = await settingsStore.deleteOneBackup(filename)
  if (success) notify('备份已删除', '', 'success')
  else notify('删除失败', '', 'error')
}

// 2FA
async function handleSetup2fa() {
  try {
    twoFactorSetup.value = await setup2faApi()
    show2faDialog.value = true
  } catch (e: any) {
    notify('获取二维码失败', e.message, 'error')
  }
}

async function handleEnable2fa() {
  try {
    await enable2faApi(twoFactorCode.value)
    notify('2FA 已启用', '', 'success')
    show2faDialog.value = false
    twoFactorSetup.value = null
    twoFactorCode.value = ''
    await loadUserInfo()
  } catch (e: any) {
    notify('启用失败', e.message, 'error')
  }
}

async function handleDisable2fa() {
  const ok = await confirm({ title: '禁用双重验证', content: '确认禁用双重验证？', confirmColor: 'error' })
  if (!ok) return
  try {
    await disable2faApi()
    notify('2FA 已禁用', '', 'success')
    await loadUserInfo()
  } catch (e: any) {
    notify('禁用失败', e.message, 'error')
  }
}

// 密码
async function handleChangePassword() {
  if (!passwordForm.value.current || !passwordForm.value.new || passwordForm.value.new !== passwordForm.value.confirm) {
    notify('提示', '请检查密码输入', 'warning')
    return
  }
  try {
    await changePasswordApi({ current_password: passwordForm.value.current, new_password: passwordForm.value.new })
    notify('密码已修改', '', 'success')
    showPasswordDialog.value = false
    passwordForm.value = { current: '', new: '', confirm: '' }
  } catch (e: any) {
    notify('修改失败', e.message, 'error')
  }
}

// AI
async function handleSaveAiConfig() {
  try {
    await aiStore.saveConfig()
    notify('AI 配置已保存', '', 'success')
  } catch (e: any) {
    notify('保存失败', e.message, 'error')
  }
}

watch(activeTab, (val) => {
  if (val === 'sessions') loadSessions()
})

// 会话管理
async function loadSessions() {
  isLoadingSessions.value = true
  try { sessions.value = await getSessionsApi() }
  catch (e: any) { notify('加载会话失败', e.message, 'error') }
  finally { isLoadingSessions.value = false }
}

async function handleRevokeSession(sessionId: string) {
  try {
    await revokeSessionApi(sessionId)
    notify('已踢出该设备', '', 'success')
    await loadSessions()
  } catch (e: any) { notify('踢出失败', e.message, 'error') }
}

async function handleRevokeAllSessions() {
  const ok = await confirm({ title: '踢出所有其他设备', content: '确认踢出除当前会话外的所有设备？', confirmColor: 'error' })
  if (!ok) return
  try {
    const res = await revokeAllOtherSessionsApi()
    notify('已踢出所有其他设备', res.message, 'success')
    await loadSessions()
  } catch (e: any) { notify('踢出失败', e.message, 'error') }
}

function formatExpiresIn(hours: number) {
  if (hours < 1) return `${Math.round(hours * 60)}分钟`
  return `${hours}小时`
}

function formatUserAgent(ua: string) {
  if (!ua) return '未知'
  return ua.length > 50 ? ua.substring(0, 50) + '...' : ua
}

function formatTime(time: string) {
  if (!time) return '未知'
  return new Date(time).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

// 永久登录
async function loadPermanentLoginSetting() {
  try {
    permanentLoginEnabled.value = settingsStore.settings.permanent_login_enabled || false
  } catch (e) { console.error(e) }
}

async function handleTogglePermanentLogin(value: boolean) {
  permanentLoginLoading.value = true
  try {
    const newSettings = { ...settingsStore.settings, permanent_login_enabled: value }
    await saveAllSettings(newSettings)
    await settingsStore.loadSettings()
    await updateSessionsExpiryApi()
    notify(value ? '已开启永久登录' : '已切换为24小时过期', '', 'success')
  } catch (e: any) {
    notify('设置失败', e.response?.data?.detail || e.message, 'error')
    permanentLoginEnabled.value = !value
  } finally { permanentLoginLoading.value = false }
}

// 实时文件监控
async function loadFileWatcherStatus() {
  try {
    fileWatcherStatus.value = await getFileWatcherStatus()
  } catch { /* ignore */ }
}

// AI 测试台
async function handleTestAi(context: string) {
  if (!aiStore.config.enabled) {
    notify('提示', '请先开启 AI 服务并保存配置', 'warning')
    return
  }
  isTestingAi.value = true
  testResult.value = ''
  try {
    const res = await testTranslationApi(testInput.value, context)
    testResult.value = res.translated
    notify('测试完成', '', 'success')
  } catch (e: any) { notify('测试失败', e.message, 'error') }
  finally { isTestingAi.value = false }
}

// TMDB Mock URL
const mockApiUrl = computed(() => `${window.location.origin}/tmdb-mock/3/`)

// TMDB 支持的图片语言（供「回退图片语言」下拉选择；null 代表无语言标记的图片）
const TMDB_IMAGE_LANGUAGE_OPTIONS = [
  { title: 'zh-CN 简体中文', value: 'zh-CN' },
  { title: 'zh-TW 繁体中文', value: 'zh-TW' },
  { title: 'zh 中文', value: 'zh' },
  { title: 'en 英语', value: 'en' },
  { title: 'ja 日语', value: 'ja' },
  { title: 'ko 韩语', value: 'ko' },
  { title: 'de 德语', value: 'de' },
  { title: 'fr 法语', value: 'fr' },
  { title: 'es 西班牙语', value: 'es' },
  { title: 'pt 葡萄牙语', value: 'pt' },
  { title: 'pt-BR 巴西葡萄牙语', value: 'pt-BR' },
  { title: 'it 意大利语', value: 'it' },
  { title: 'ru 俄语', value: 'ru' },
  { title: 'uk 乌克兰语', value: 'uk' },
  { title: 'pl 波兰语', value: 'pl' },
  { title: 'cs 捷克语', value: 'cs' },
  { title: 'sk 斯洛伐克语', value: 'sk' },
  { title: 'hu 匈牙利语', value: 'hu' },
  { title: 'ro 罗马尼亚语', value: 'ro' },
  { title: 'bg 保加利亚语', value: 'bg' },
  { title: 'el 希腊语', value: 'el' },
  { title: 'hr 克罗地亚语', value: 'hr' },
  { title: 'nl 荷兰语', value: 'nl' },
  { title: 'sv 瑞典语', value: 'sv' },
  { title: 'nb 挪威语', value: 'nb' },
  { title: 'da 丹麦语', value: 'da' },
  { title: 'fi 芬兰语', value: 'fi' },
  { title: 'tr 土耳其语', value: 'tr' },
  { title: 'ar 阿拉伯语', value: 'ar' },
  { title: 'he 希伯来语', value: 'he' },
  { title: 'hi 印地语', value: 'hi' },
  { title: 'th 泰语', value: 'th' },
  { title: 'vi 越南语', value: 'vi' },
  { title: 'id 印尼语', value: 'id' },
  { title: 'ms 马来语', value: 'ms' },
  { title: 'null 无语言标记', value: 'null' },
]

// 「回退图片语言」：配置里是逗号分隔字符串，下拉多选需要数组
const imageLanguageSelection = computed<string[]>({
  get: () => String(formSettings.value.tmdb_image_languages ?? '')
    .split(',')
    .map((s: string) => s.trim())
    .filter(Boolean),
  set: (vals) => {
    formSettings.value.tmdb_image_languages = (vals ?? []).join(',')
  },
})
</script>

<template>
  <v-container fluid class="pa-6">
    <div class="d-flex flex-wrap align-center mb-6 ga-3">
      <div class="flex-grow-1">
        <h1 class="text-h5 font-weight-bold">系统设置</h1>
        <p class="text-caption text-medium-emphasis mt-1">配置应用参数、API密钥、自动化与备份管理</p>
      </div>
      <div class="d-flex ga-2 flex-wrap">
        <v-btn class="glass-btn-accent" variant="tonal" prepend-icon="mdi-content-save" :loading="settingsStore.isLoading" @click="handleSaveSettings">保存所有设置</v-btn>
      </div>
    </div>

    <v-tabs v-model="activeTab" density="comfortable" color="primary">
      <v-tab value="general" prepend-icon="mdi-cog-outline">通用设置</v-tab>
      <v-tab value="network" prepend-icon="mdi-network-outline">网络代理</v-tab>
      <v-tab value="automation" prepend-icon="mdi-robot-outline">自动化</v-tab>
      <v-tab value="tmdb_mock" prepend-icon="mdi-api">TMDB 模拟器</v-tab>
      <v-tab value="ai" prepend-icon="mdi-robot-happy-outline">AI 实验室</v-tab>
      <v-tab value="security" prepend-icon="mdi-shield-lock-outline">安全设置</v-tab>
      <v-tab value="sessions" prepend-icon="mdi-devices">会话管理</v-tab>
      <v-tab value="backup" prepend-icon="mdi-backup-restore">备份管理</v-tab>
    </v-tabs>

    <v-divider />

    <v-window v-model="activeTab" class="mt-4">
      <!-- ========== 通用设置 ========== -->
      <v-window-item value="general">
        <v-form @submit.prevent="handleSaveSettings">
          <!-- 核心路径 -->
          <v-card variant="outlined" rounded="xl" class="mb-4">
            <v-card-title class="d-flex align-center text-subtitle-2 font-weight-bold pa-4 pb-0">
              <v-icon start size="small">mdi-folder-outline</v-icon>核心路径配置
            </v-card-title>
            <v-card-text>
              <v-row density="compact">
                <v-col cols="12" sm="6">
                  <v-text-field v-model="formSettings.primary_cache_path" label="主缓存路径 (Primary)" density="compact" variant="outlined" prepend-inner-icon="mdi-folder-multiple" hint="选择cache文件夹，此路径为只读。" persistent-hint>
                    <template #append-inner>
                      <v-btn size="x-small" variant="text" icon="mdi-folder-search" density="comfortable" @click="openPathBrowser('primary_cache_path', '选择主缓存路径')" />
                    </template>
                  </v-text-field>
                </v-col>
                <v-col cols="12" sm="6">
                  <v-text-field v-model="formSettings.override_cache_path" label="覆盖缓存路径 (Override)" density="compact" variant="outlined" prepend-inner-icon="mdi-folder-edit" hint="选择override文件夹，此路径为读写。" persistent-hint>
                    <template #append-inner>
                      <v-btn size="x-small" variant="text" icon="mdi-folder-search" density="comfortable" @click="openPathBrowser('override_cache_path', '选择覆盖缓存路径')" />
                    </template>
                  </v-text-field>
                </v-col>
                <v-col cols="12" sm="6">
                  <v-text-field v-model="formSettings.emby_collections_path" label="合集路径 (Collections)" density="compact" variant="outlined" prepend-inner-icon="mdi-folder-star" hint="用于存放自定义合集的 .json 文件。" persistent-hint>
                    <template #append-inner>
                      <v-btn size="x-small" variant="text" icon="mdi-folder-search" density="comfortable" @click="openPathBrowser('emby_collections_path', '选择合集路径')" />
                    </template>
                  </v-text-field>
                </v-col>
                <v-col cols="12" sm="6">
                  <v-text-field v-model="formSettings.backup_path" label="备份路径 (Backups)" density="compact" variant="outlined" prepend-inner-icon="mdi-folder-zip" hint="用于存放应用的快照或压缩包备份文件。" persistent-hint>
                    <template #append-inner>
                      <v-btn size="x-small" variant="text" icon="mdi-folder-search" density="comfortable" @click="openPathBrowser('backup_path', '选择备份路径')" />
                    </template>
                  </v-text-field>
                </v-col>
                <v-col cols="12" sm="6">
                  <v-text-field v-model="formSettings.resource_info_path" label="资源信息路径 (Resource Info)" density="compact" variant="outlined" prepend-inner-icon="mdi-folder-information" hint="用于存放媒体的外部资源链接信息 .json 文件。" persistent-hint>
                    <template #append-inner>
                      <v-btn size="x-small" variant="text" icon="mdi-folder-search" density="comfortable" @click="openPathBrowser('resource_info_path', '选择资源信息路径')" />
                    </template>
                  </v-text-field>
                </v-col>
              </v-row>
            </v-card-text>
          </v-card>

          <!-- 实时文件监控 -->
          <v-card variant="outlined" rounded="xl" class="mb-4">
            <v-card-title class="d-flex align-center text-subtitle-2 font-weight-bold pa-4 pb-0">
              <v-icon start size="small">mdi-file-sync</v-icon>实时文件监控
            </v-card-title>
            <v-card-text>
              <v-switch
                v-model="formSettings.file_watcher_enabled"
                color="primary"
                hide-details
                inset
                label="启用实时文件监控"
              />
              <div class="text-caption text-medium-emphasis ml-12 mb-3">
                开启后将自动监控 Primary 和 Override 缓存目录中的 JSON 文件变化，
                检测到变更时自动重新扫描对应项目并更新数据库缓存，无需手动触发全量扫描。
              </div>
              <div v-if="fileWatcherStatus?.enabled" class="d-flex align-center">
                <v-chip size="x-small" color="success" variant="tonal" label>
                  <v-icon size="x-small" start>mdi-circle-medium</v-icon>运行中
                </v-chip>
                <span class="text-caption text-medium-emphasis ml-2">
                  监控目录: {{ fileWatcherStatus?.watched_paths?.join(', ') || '-' }}
                </span>
              </div>
              <div v-else-if="fileWatcherStatus && !fileWatcherStatus.enabled" class="d-flex align-center">
                <v-chip size="x-small" color="default" variant="tonal" label>已停止</v-chip>
              </div>

              <v-divider v-if="formSettings.file_watcher_enabled" class="my-3" />

              <template v-if="formSettings.file_watcher_enabled">
                <v-switch
                  v-model="formSettings.file_watcher_auto_lock_name"
                  color="primary"
                  hide-details
                  inset
                  label="自动锁定名称"
                />
                <div class="text-caption text-medium-emphasis ml-12">
                  文件变动时自动锁定项目名称。仅对未锁定的项目生效，已锁定的不会被覆盖。
                </div>

                <v-divider class="my-3" />

                <div class="text-subtitle-2 font-weight-bold mb-2">监控轮询间隔</div>
                <v-slider
                  :model-value="formSettings.file_watcher_poll_interval ?? 5"
                  @update:model-value="formSettings.file_watcher_poll_interval = $event"
                  :min="1"
                  :max="30"
                  :step="1"
                  color="primary"
                  show-ticks
                  thumb-label
                  class="mb-1"
                />
                <div class="text-caption text-medium-emphasis">
                  每 {{ formSettings.file_watcher_poll_interval ?? 5 }} 秒扫描一次缓存目录。值越大 CPU 占用越低，但文件变更检测的响应会变慢。建议 5~10 秒。
                </div>
              </template>
            </v-card-text>
          </v-card>

          <!-- 首页入库状态显示 -->
          <v-card variant="outlined" rounded="xl" class="mb-4">
            <v-card-title class="d-flex align-center text-subtitle-2 font-weight-bold pa-4 pb-0">
              <v-icon start size="small">mdi-check-decagram</v-icon>首页入库状态显示
            </v-card-title>
            <v-card-text>
              <v-switch
                v-model="formSettings.show_library_status"
                color="primary"
                hide-details
                inset
                label="在首页卡片右上角显示 Emby 入库状态"
              />
              <div class="text-caption text-medium-emphasis ml-12">
                开启后，首页的电影和剧集卡片右上角将显示绿色「已入库」或红色「未入库」角标。
                需要先配置好 Emby 服务器连接。数据来自 Emby 全库扫描缓存（3 分钟有效期），开销很小。
              </div>
            </v-card-text>
          </v-card>

          <!-- 首页 BGM 映射状态显示 -->
          <v-card variant="outlined" rounded="xl" class="mb-4">
            <v-card-title class="d-flex align-center text-subtitle-2 font-weight-bold pa-4 pb-0">
              <v-icon start size="small">mdi-link-variant</v-icon>首页 BGM 映射状态显示
            </v-card-title>
            <v-card-text>
              <v-switch
                v-model="formSettings.show_bgm_mapping_status"
                color="primary"
                hide-details
                inset
                label="在首页卡片左下角显示 Bangumi 映射状态"
              />
              <div class="text-caption text-medium-emphasis ml-12">
                开启后，首页的电影和剧集卡片左下角将显示粉色「BGM」或「无BGM」角标，
                表示该 TMDB 条目是否已有 Bangumi 关联映射。数据来自本地 bangumi-data 映射表，开销极小。
              </div>
            </v-card-text>
          </v-card>

          <!-- 浏览偏好 -->
          <v-card variant="outlined" rounded="xl" class="mb-4">
            <v-card-title class="d-flex align-center text-subtitle-2 font-weight-bold pa-4 pb-0">
              <v-icon start size="small">mdi-tab-plus</v-icon>浏览偏好
            </v-card-title>
            <v-card-text>
              <v-switch
                :model-value="openDetailInNewTab"
                color="primary"
                hide-details
                inset
                label="在新标签页打开详情页"
                @update:model-value="toggleOpenDetailInNewTab"
              />
              <div class="text-caption text-medium-emphasis ml-12">
                开启后，点击首页或合集页的媒体卡片时，会在浏览器新标签页中打开详情页。
                这样在详情页中进行下载图片等操作后返回时，原页面的滚动位置不会丢失。
              </div>
            </v-card-text>
          </v-card>

          <!-- 第三方服务 API Key -->
          <v-card variant="outlined" rounded="xl" class="mb-4">
            <v-card-title class="d-flex align-center text-subtitle-2 font-weight-bold pa-4 pb-0">
              <v-icon start size="small">mdi-key-chain</v-icon>第三方服务 API Key
            </v-card-title>
            <v-card-text>
              <!-- Emby 账号登录 -->
              <div class="text-caption text-medium-emphasis font-weight-bold mb-3">
                <v-icon size="x-small" start>mdi-account-key</v-icon>Emby 账号登录
              </div>
              <v-row density="compact" class="mb-2">
                <v-col cols="12" sm="6">
                  <v-text-field v-model="formSettings.emby_username" label="用户名" density="compact" variant="outlined" prepend-inner-icon="mdi-account" />
                </v-col>
                <v-col cols="12" sm="6">
                  <PasswordInput v-model="formSettings.emby_password" label="密码" density="compact" variant="outlined" prepend-inner-icon="mdi-lock" />
                </v-col>
              </v-row>
              <div class="d-flex ga-2 mb-4 flex-wrap">
                <v-btn variant="tonal" color="primary" :loading="isLoggingInEmby" @click="handleEmbyLogin" prepend-icon="mdi-login">登录获取令牌</v-btn>
                <v-btn variant="tonal" color="success" :loading="isTestingEmby" @click="handleTestEmby" prepend-icon="mdi-connection">测试连接</v-btn>
              </div>
              <v-alert v-if="formSettings.emby_user_id" type="success" variant="tonal" density="compact" class="mb-4">
                已登录用户ID: {{ formSettings.emby_user_id }} · 使用此账号可访问神医配置等功能
              </v-alert>

              <v-divider class="mb-4" />

              <!-- API 密钥配置 -->
              <div class="text-caption text-medium-emphasis font-weight-bold mb-3">
                <v-icon size="x-small" start>mdi-key-variant</v-icon>API 密钥配置
              </div>
              <v-row density="compact">
                <v-col cols="12" sm="6">
                  <v-text-field v-model="formSettings.emby_server_url" label="Emby Host" density="compact" variant="outlined" placeholder="http://192.168.x.x:8096" prepend-inner-icon="mdi-server" hint="Emby服务器的访问地址" persistent-hint />
                </v-col>
                <v-col cols="12" sm="6">
                  <PasswordInput v-model="formSettings.emby_api_key" label="Emby API Key" density="compact" variant="outlined" prepend-inner-icon="mdi-key" hint="Emby服务器的 API 密钥" persistent-hint />
                </v-col>
                <v-col cols="12" sm="6">
                  <PasswordInput v-model="formSettings.emby_user_id" label="Emby User ID" density="compact" variant="outlined" prepend-inner-icon="mdi-account-circle" hint="userId=后面的内容即可，用于元数据同步等功能" persistent-hint />
                </v-col>
                <v-col cols="12" sm="6">
                  <PasswordInput v-model="formSettings.tmdb_api_key" label="TMDB API Key" density="compact" variant="outlined" prepend-inner-icon="mdi-movie-search" hint="用于从 The Movie Database 获取元数据和图片" persistent-hint />
                  <v-select
                    v-model="formSettings.tmdb_preferred_language"
                    :items="[{ title: '简体中文 (zh-CN)', value: 'zh-CN' }, { title: '繁体中文 (zh-TW)', value: 'zh-TW' }, { title: '英语 (en)', value: 'en' }, { title: '日语 (ja)', value: 'ja' }, { title: '韩语 (ko)', value: 'ko' }]"
                    label="首选元数据语言"
                    density="compact"
                    variant="outlined"
                    hint="TMDB 模拟器收到不带 language 参数的请求时，使用此语言向 TMDB 官方回退。本地 Override 命中不受影响"
                    persistent-hint
                  />
                </v-col>
                <v-col cols="12" sm="6">
                  <PasswordInput v-model="formSettings.fanart_api_key" label="Fanart.tv API Key" density="compact" variant="outlined" prepend-inner-icon="mdi-image-search" placeholder="用于下载高清艺术图" hint="用于从 Fanart.tv 下载高清艺术图" persistent-hint />
                </v-col>
                <v-col cols="12" sm="6">
                  <PasswordInput v-model="formSettings.github_token" label="GitHub Token" density="compact" variant="outlined" prepend-inner-icon="mdi-github" hint="用于 bangumi-data 映射表同步（可选，提高 API 速率限制）" persistent-hint />
                </v-col>
                <v-col cols="12" sm="6">
                  <PasswordInput v-model="formSettings.bangumi_access_token" label="Bangumi Access Token" density="compact" variant="outlined" prepend-inner-icon="mdi-account-key" hint="用于 Bangumi API 调用（可选）" persistent-hint />
                </v-col>
              </v-row>
            </v-card-text>
          </v-card>

          <div class="d-flex justify-end">
            <v-btn type="submit" color="primary" variant="tonal" :loading="settingsStore.isLoading" prepend-icon="mdi-content-save">保存设置</v-btn>
          </div>
        </v-form>
      </v-window-item>

      <!-- ========== 网络代理 ========== -->
      <v-window-item value="network">
        <v-form @submit.prevent="handleSaveSettings">
          <v-card variant="outlined" rounded="xl" class="mb-4">
            <v-card-title class="d-flex align-center text-subtitle-2 font-weight-bold pa-4 pb-0">
              <v-icon start size="small">mdi-ip-network</v-icon>HTTP 代理配置
            </v-card-title>
            <v-card-text>
              <v-switch v-model="formSettings.network.enable_global" color="primary" hide-details inset label="启用全局代理" class="mb-4" />

              <template v-if="formSettings.network?.enable_global">
                <v-row density="compact" class="mb-4">
                  <v-col cols="12" sm="8">
                    <v-text-field v-model="formSettings.network.proxy_url" label="代理地址" density="compact" variant="outlined" placeholder="http://127.0.0.1:7890" prepend-inner-icon="mdi-lan-connect" hint="仅支持 HTTP/HTTPS 代理。格式：http://ip:port" persistent-hint />
                  </v-col>
                </v-row>

                <div class="text-caption text-medium-emphasis font-weight-bold mb-3">
                  <v-icon size="x-small" start>mdi-swap-horizontal</v-icon>代理目标 (分流控制)
                </div>
                <v-row density="compact">
                  <v-col cols="12" sm="6" md="4">
                    <v-switch v-model="formSettings.network.proxy_targets.tmdb" color="primary" hide-details label="TMDB · 元数据与图片搜索" density="compact" />
                  </v-col>
                  <v-col cols="12" sm="6" md="4">
                    <v-switch v-model="formSettings.network.proxy_targets.bangumi" color="primary" hide-details label="Bangumi · 离线包下载与API" density="compact" />
                  </v-col>
                  <v-col cols="12" sm="6" md="4">
                    <v-switch v-model="formSettings.network.proxy_targets.fanart" color="primary" hide-details label="Fanart.tv · 高清图下载" density="compact" />
                  </v-col>
                  <v-col cols="12" sm="6" md="4">
                    <v-switch v-model="formSettings.network.proxy_targets.emby" color="primary" hide-details label="Emby · 通常不建议开启" density="compact" />
                  </v-col>
                  <v-col cols="12" sm="6" md="4">
                    <v-switch v-model="formSettings.network.proxy_targets.ai" color="primary" hide-details label="AI 服务 · OpenAI/Claude 等" density="compact" />
                  </v-col>
                </v-row>
              </template>
            </v-card-text>
          </v-card>

          <div class="d-flex justify-end">
            <v-btn type="submit" color="primary" variant="tonal" :loading="settingsStore.isLoading" prepend-icon="mdi-content-save">保存设置</v-btn>
          </div>
        </v-form>
      </v-window-item>

      <!-- ========== 自动化 (Webhook & 备份) ========== -->
      <v-window-item value="automation">
        <v-form @submit.prevent="handleSaveSettings">
          <!-- Emby Webhook -->
          <v-card variant="outlined" rounded="xl" class="mb-4">
            <v-card-title class="d-flex align-center text-subtitle-2 font-weight-bold pa-4 pb-0">
              <v-icon start size="small">mdi-webhook</v-icon>Emby Webhook 自动化
            </v-card-title>
            <v-card-text>
              <v-switch v-model="formSettings.emby_webhook_enabled" color="primary" hide-details inset label="启用 Webhook" class="mb-4" />

              <template v-if="formSettings.emby_webhook_enabled">
                <v-row density="compact" class="mb-4">
                  <v-col cols="12" sm="6">
                    <PasswordInput v-model="formSettings.webhook_secret_token" label="安全密钥 (Token)" density="compact" variant="outlined" placeholder="自定义一个复杂的字符串" prepend-inner-icon="mdi-shield-key" />
                  </v-col>
                  <v-col cols="12" sm="6">
                    <v-text-field :model-value="webhookUrl" label="Webhook URL" density="compact" variant="outlined" readonly append-inner-icon="mdi-content-copy" @click:append-inner="copyWebhookUrl" />
                  </v-col>
                </v-row>

                <div class="text-caption text-medium-emphasis font-weight-bold mb-3">响应动作</div>
                <v-row density="compact">
                  <v-col cols="12" sm="6">
                    <v-switch v-model="formSettings.webhook_action_collection_sync_enabled" color="primary" hide-details label="响应合集变更" density="compact" />
                    <div class="text-caption text-medium-emphasis ml-12 mb-2">WEBHOOK通知需勾选 <strong>合集项目已添加</strong> <strong>合集项目已移除</strong> 才能生效，当 Emby 合集变化时，自动更新合集 JSON 文件和合集图片。</div>
                  </v-col>
                  <v-col cols="12" sm="6">
                    <v-switch v-model="formSettings.webhook_action_script_enabled" color="primary" hide-details label="响应自定义脚本" density="compact" />
                    <div class="text-caption text-medium-emphasis ml-12 mb-2">
                      <a href="https://greasyfork.org/zh-CN/scripts/551727" target="_blank" class="link-unstyled">Emby-TMDB-Trakt-IMDB-Douban-Bangumi 辅助脚本</a>
                      <br><a href="/static/EMBYCSS插件版.js" download class="link-unstyled">下载 EMBYCSS 插件版.js</a>
                    </div>
                  </v-col>
                  <v-col cols="12" sm="6">
                    <v-switch v-model="formSettings.webhook_action_image_update_enabled" color="primary" hide-details label="响应图片更新" density="compact" />
                    <div class="text-caption text-medium-emphasis ml-12 mb-2">WEBHOOK通知需勾选 <strong>媒体图像更新</strong>，当 Emby 中的媒体图片（海报、封面等）更新时触发，自动更新覆盖缓存的图片。</div>
                  </v-col>
                  <v-col cols="12" sm="6">
                    <v-switch v-model="formSettings.webhook_action_metadata_update_enabled" color="primary" hide-details label="响应元数据更新" density="compact" />
                    <div class="text-caption text-medium-emphasis ml-12 mb-2">WEBHOOK通知需勾选 <strong>媒体元数据更新</strong>，当 Emby 元数据更新时，自动更新 Override 里面的 JSON 文件。</div>
                  </v-col>
                  <v-col cols="12" sm="6">
                    <v-switch v-model="formSettings.webhook_action_storage_query_enabled" color="primary" hide-details label="响应存储查询" density="compact" />
                    <div class="text-caption text-medium-emphasis ml-12 mb-2">允许 EMBYCSS 辅助脚本通过 Webhook 查询本地存储信息（元数据、季度集统计等），用于在 Emby 界面中显示本地覆盖状态。</div>
                  </v-col>
                </v-row>

                <v-alert type="info" variant="tonal" density="compact" class="mt-4">
                  启用后，请将上方生成的完整 URL 复制并粘贴到 Emby 服务器 → 通知 → 添加 Webhooks，请求类型选择 JSON。
                  通知里面选择神医助手，勾选 <strong>合集项目已添加</strong> <strong>合集项目已移除</strong> <strong>媒体图像更新</strong> <strong>媒体元数据更新</strong>。
                  <br><br>
                  支持的字段：<br>
                  <strong>剧集</strong>：名称(title), 原始名称(original_title), 概述(overview), 类型(genres), 首播日期(air_date), 评分(vote_average), 完结日期(end_date), 标签(tags)。<br>
                  <strong>季</strong>：季名称(season_name), 季概述(season_overview), 季首播日期(season_air_date)。<br>
                  <strong>集</strong>：集名称(episode_name), 集概述(episode_overview), 集首播日期(episode_air_date)。<br>
                  <strong>电影</strong>：名称(title), 原始名称(original_title), 概述(overview), 类型(genres), 上映日期(air_date), 评分(vote_average), 标签(tags)。
                </v-alert>
              </template>
            </v-card-text>
          </v-card>

          <!-- 自动备份设置 -->
          <v-card variant="outlined" rounded="xl" class="mb-4">
            <v-card-title class="d-flex align-center text-subtitle-2 font-weight-bold pa-4 pb-0">
              <v-icon start size="small">mdi-timer-outline</v-icon>自动备份设置
            </v-card-title>
            <v-card-text>
              <v-switch v-model="formSettings.auto_backup_enabled" color="primary" hide-details inset label="启用自动备份" class="mb-4" />

              <template v-if="formSettings.auto_backup_enabled">
                <v-row density="compact" class="mb-4">
                  <v-col cols="12" sm="4">
                    <v-text-field v-model.number="formSettings.auto_backup_interval_hours" label="备份间隔 (小时)" density="compact" variant="outlined" type="number" min="1" />
                  </v-col>
                  <v-col cols="12" sm="4">
                    <v-select v-model="formSettings.auto_backup_mode" :items="[{ title: '增量快照', value: 'snapshot' }, { title: '压缩包', value: 'zip' }]" label="备份模式" density="compact" variant="outlined" />
                  </v-col>
                  <v-col cols="12" sm="4">
                    <v-text-field v-model.number="formSettings.auto_backup_max_snapshots" label="保留快照数量" density="compact" variant="outlined" type="number" min="0" />
                  </v-col>
                </v-row>
                <v-row density="compact">
                  <v-col cols="12" sm="4">
                    <v-switch v-model="formSettings.auto_backup_include_override" color="primary" hide-details label="Override 缓存" density="compact" />
                  </v-col>
                  <v-col cols="12" sm="4">
                    <v-switch v-model="formSettings.auto_backup_include_collections" color="primary" hide-details label="自定义合集" density="compact" />
                  </v-col>
                </v-row>
              </template>
            </v-card-text>
          </v-card>

          <div class="d-flex justify-end">
            <v-btn type="submit" color="primary" variant="tonal" :loading="settingsStore.isLoading" prepend-icon="mdi-content-save">保存设置</v-btn>
          </div>
        </v-form>
      </v-window-item>

            <!-- ========== TMDB 模拟器 ========== -->
      <v-window-item value="tmdb_mock">
        <v-form @submit.prevent="handleSaveSettings">
          <v-card variant="outlined" rounded="xl" class="mb-4">
            <v-card-title class="d-flex align-center text-subtitle-2 font-weight-bold pa-4 pb-0">
              <v-icon start size="small">mdi-api</v-icon>TMDB Proxy (Mock API) 配置
            </v-card-title>
            <v-card-text>
              <!-- 功能概述 -->
              <v-alert type="info" variant="tonal" density="compact" class="mb-4">
                <div class="font-weight-bold mb-1">这是什么？</div>
                本服务内置了一套 TMDB API 模拟器，相当于一个<strong>TMDB 反向代理</strong>。
                将 Emby/Jellyfin 的 TMDB 刮削地址指向本服务后，所有元数据请求和图片请求都会经过本服务转发。
                <br><br>
                与普通代理不同，本服务支持<strong>本地覆盖</strong>（手动修改的元数据和图片优先返回）和<strong>磁盘缓存</strong>（图片自动缓存，减少重复请求）。
                <br><br>
                数据组装顺序：<strong>Override 主 JSON → 远程 TMDB → <code>patches/</code></strong>（不读取主缓存）。
                <code>patches/</code> 中锁定的字段（如名称）会覆盖以上任何来源；<code>images/</code> 下的本地图片优先级最高。
              </v-alert>

              <!-- 配置指引 -->
              <v-alert type="warning" variant="tonal" density="compact" class="mb-4">
                <div class="font-weight-bold mb-1">如何配置？</div>
                在 Emby/Jellyfin 的「网络」设置或刮削器配置中，将 TMDB API 地址改为：
                <br><code>{{ mockApiUrl }}</code>
                <br>图片地址会自动跟随，无需单独配置。
              </v-alert>

              <v-divider class="mb-4" />

              <!-- 开关配置 -->
              <div class="text-caption text-medium-emphasis font-weight-bold mb-3">
                <v-icon size="x-small" start>mdi-tune</v-icon>行为配置
              </div>

              <v-switch v-model="formSettings.tmdb_proxy_fallback" color="primary" hide-details label="启用远程回退" class="mb-2" />
              <div class="text-caption text-medium-emphasis ml-12 mb-4">
                Override 中没有对应主 JSON 时，是否自动从 TMDB 官方获取（获取结果仍会叠加 patches 与本地图片）。
                <br>
                关闭后仅使用本地数据：Override 主 JSON 优先；若项目只有 patches（如仅锁定过名称），
                也会用 patch 内容兜底返回；两者都没有才返回 404。
                <br>
                注意：即使关闭，本地 <code>images/</code> 中没有的图片仍会走 TMDB 图片代理（按「图片处理机制」的三级查找）。
              </div>

              <v-switch v-model="formSettings.tmdb_episode_group_mode" color="primary" hide-details label="剧集组模式" class="mb-2" />
              <div class="text-caption text-medium-emphasis ml-12 mb-4">
                开启后，模拟器按 override 中该项目的 episodegroup.json（剧集组定义）重组季与集：
                每个分组返回为一个「虚拟季」，分组内集按 order 重新编号（虚拟集号 = order + 1），
                单集请求会先映射回 TMDB 真实的季/集号再取数据。
                注意：季/集的列表结构与编号由剧集组决定，patches 与本地图片仍可覆盖名称、简介、海报等内容。
                需要先在 Override 中放置 episodegroup.json，否则按标准季结构返回。
              </div>

              <v-select
                v-model="imageLanguageSelection"
                :items="TMDB_IMAGE_LANGUAGE_OPTIONS"
                label="回退图片语言"
                density="compact"
                variant="outlined"
                multiple
                chips
                closable-chips
                hint="首选语言图片缺失时，按选中顺序依次尝试获取。null 代表无语言标记"
                persistent-hint
                class="mb-4"
              />

              <v-divider class="mb-4" />

              <!-- 元数据语言行为 -->
              <div class="text-caption text-medium-emphasis font-weight-bold mb-3">
                <v-icon size="x-small" start>mdi-translate</v-icon>元数据语言行为
              </div>

              <v-alert type="info" variant="tonal" density="compact" class="mb-2">
                <div>
                  <strong>本地命中（Override / patches）不区分语言</strong>：一个条目在磁盘上只有一份 JSON，
                  无论请求带什么 <code>language</code> 参数，都返回这份你维护的数据。
                  <br>
                  <code>language</code> 参数只在<strong>远程回退</strong>时生效（决定向 TMDB 官方请求哪种语言的元数据）。
                  请求未携带 <code>language</code> 时，使用「通用设置 → 首选元数据语言」作为默认值。
                </div>
              </v-alert>

              <v-alert type="warning" variant="tonal" density="compact" class="mb-4">
                若某个 Emby 媒体库配置了非中文语言，本地命中仍会返回中文元数据（Override 内容）。
                如需按语言区分数据，请将对应语言的条目交给远程回退，或在 Emby 中把该库语言改为 zh-CN。
              </v-alert>

              <v-divider class="mb-4" />

              <!-- 图片处理机制 -->
              <div class="text-caption text-medium-emphasis font-weight-bold mb-3">
                <v-icon size="x-small" start>mdi-image-multiple</v-icon>图片处理机制
              </div>

              <v-alert type="success" variant="tonal" density="compact" class="mb-3">
                所有经过 <code>/t/p/</code> 端点的图片请求（无论来自前端、Emby 还是其他客户端）都会按以下顺序查找：
              </v-alert>

              <v-table density="compact" class="text-caption mb-4">
                <thead>
                  <tr>
                    <th class="text-left w-40px">#</th>
                    <th class="text-left">查找层级</th>
                    <th class="text-left">说明</th>
                    <th class="text-left w-180px">存储位置</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>①</td>
                    <td><strong>本地覆盖图</strong></td>
                    <td>优先返回 Override 目录中手动放置的 poster.jpg / fanart.jpg / clearlogo.png 等</td>
                    <td><code>{override}/{type}/{id}/images/</code></td>
                  </tr>
                  <tr>
                    <td>②</td>
                    <td><strong>图片磁盘缓存</strong></td>
                    <td>非覆盖图片首次从 TMDB 拉取后自动缓存到磁盘，后续请求直接从本地返回，不再访问 TMDB</td>
                    <td><code>{data}/tmdb_image_cache/{size}/</code></td>
                  </tr>
                  <tr>
                    <td>③</td>
                    <td><strong>远程拉取</strong></td>
                    <td>缓存未命中时，从 TMDB 官方服务器获取图片，同时写入磁盘缓存</td>
                    <td><code>image.tmdb.org</code></td>
                  </tr>
                </tbody>
              </v-table>

              <v-alert type="info" variant="tonal" density="compact" class="mb-4">
                浏览器侧也会缓存图片 24 小时（<code>Cache-Control</code>），配合磁盘缓存实现两级缓存加速。
              </v-alert>

              <v-divider class="mb-4" />

              <!-- 支持的端点 -->
              <div class="text-caption text-medium-emphasis font-weight-bold mb-3">
                <v-icon size="x-small" start>mdi-link-variant</v-icon>支持的模拟端点
              </div>

              <v-table density="compact" class="text-caption">
                <thead>
                  <tr>
                    <th class="text-left w-280px">端点</th>
                    <th class="text-left">说明</th>
                  </tr>
                </thead>
                <tbody>
                  <tr><td><code>/3/configuration</code></td><td>基础配置 — 返回模拟的图片基地址，使所有图片请求回流到本服务</td></tr>
                  <tr><td><code>/3/movie/{id}</code></td><td>电影详情 — 优先返回本地 <code>all.json</code>，可回退 TMDB</td></tr>
                  <tr><td><code>/3/tv/{id}</code></td><td>剧集详情 — 优先返回本地 <code>series.json</code>，可回退 TMDB</td></tr>
                  <tr><td><code>/3/tv/{id}/season/{n}</code></td><td>季度详情 — 优先返回本地 <code>season-{n}.json</code>，可回退 TMDB</td></tr>
                  <tr><td><code>/3/tv/{id}/season/{n}/episode/{m}</code></td><td>单集详情 — 优先返回本地 <code>season-{n}-episode-{m}.json</code>，可回退 TMDB</td></tr>
                  <tr><td><code>/3/search/{movie|tv|multi}</code></td><td>搜索代理 — 透明转发至 TMDB 官方搜索接口</td></tr>
                  <tr><td><code>/3/person/{id}</code></td><td>人物详情 — 透明转发至 TMDB 官方接口</td></tr>
                  <tr><td><code>/t/p/{size}/{path}</code></td><td>图片代理 — 按上述三层机制处理（覆盖图 → 缓存 → 远程）</td></tr>
                </tbody>
              </v-table>
            </v-card-text>
          </v-card>

          <div class="d-flex justify-end">
            <v-btn type="submit" color="primary" variant="tonal" :loading="settingsStore.isLoading" prepend-icon="mdi-content-save">保存设置</v-btn>
          </div>
        </v-form>
      </v-window-item>

      <!-- ========== AI 实验室 ========== -->
      <v-window-item value="ai">
        <v-card variant="outlined" rounded="xl">
          <v-card-text>
            <v-form @submit.prevent="handleSaveAiConfig">
              <v-switch v-model="aiStore.config.enabled" color="primary" hide-details inset label="启用 AI 翻译（标题、简介、演员名等）" class="mb-4" />

              <template v-if="aiStore.config.enabled">
                <v-switch v-model="aiStore.config.include_item_context" color="primary" hide-details inset label="智能上下文注入" class="mb-4" />
                <div class="text-caption text-medium-emphasis ml-12 mb-4">开启后翻译时将自动带上作品标题、类型等背景信息。小模型效果不佳时可关闭。</div>

                <v-divider class="mb-4" />

                <div class="text-caption text-medium-emphasis font-weight-bold mb-3">
                  <v-icon size="x-small" start>mdi-api</v-icon>连接配置
                </div>
                <v-row density="compact" class="mb-4">
                  <v-col cols="12" sm="6">
                    <v-select v-model="aiStore.config.provider" :items="[
                      { title: 'OpenAI (官方或代理)', value: 'openai' },
                      { title: 'Ollama (本地)', value: 'ollama' },
                      { title: '自定义端点', value: 'custom' },
                    ]" label="AI 提供商" density="compact" variant="outlined" />
                  </v-col>
                  <v-col cols="12" sm="6">
                    <v-text-field v-model="aiStore.config.model" label="模型名称" density="compact" variant="outlined" placeholder="gpt-4o / deepseek-chat / qwen2.5:14b" />
                  </v-col>
                  <v-col cols="12">
                    <v-text-field v-model="aiStore.config.base_url" label="Base URL" density="compact" variant="outlined" placeholder="https://api.openai.com/v1" prepend-inner-icon="mdi-link" />
                  </v-col>
                  <v-col cols="12">
                    <PasswordInput v-model="aiStore.config.api_key" label="API Key" density="compact" variant="outlined" placeholder="sk-..." prepend-inner-icon="mdi-key" />
                  </v-col>
                  <v-col cols="12" sm="6">
                    <div class="text-caption mb-1">Temperature ({{ aiStore.config.temperature }})</div>
                    <v-slider v-model="aiStore.config.temperature" :min="0" :max="1" :step="0.1" thumb-label color="primary" track-color="grey-darken-1" density="compact" />
                  </v-col>
                </v-row>

                <!-- Prompt 预设 -->
                <template v-if="Object.keys(aiStore.presets).length">
                  <div class="text-caption text-medium-emphasis font-weight-bold mb-3">
                    <v-icon size="x-small" start>mdi-text-box-edit</v-icon>Prompt 预设
                  </div>
                  <v-row density="compact" class="mb-4">
                    <v-col v-for="(preset, key) in aiStore.presets" :key="key" cols="12" sm="6" md="4">
                      <v-card variant="outlined" density="compact" class="pa-3">
                        <div class="text-subtitle-2 font-weight-bold mb-1">{{ preset.name }}</div>
                        <div class="text-caption text-medium-emphasis mb-2">{{ preset.description }}</div>
                        <v-btn size="x-small" variant="tonal" color="primary" @click="aiStore.applyPreset(key as string)">应用预设</v-btn>
                      </v-card>
                    </v-col>
                  </v-row>
                </template>

                <!-- Prompt 编辑 -->
                <div class="text-caption text-medium-emphasis font-weight-bold mb-3">
                  <v-icon size="x-small" start>mdi-translate</v-icon>翻译 Prompt 编辑
                </div>
                <v-row density="compact" class="mb-4">
                  <v-col v-for="(prompt, key) in aiStore.config.prompts" :key="key" cols="12" sm="6">
                    <v-textarea v-model="aiStore.config.prompts[key]" :label="key" density="compact" variant="outlined" rows="2" auto-grow class="mb-2">
                      <template #append>
                        <v-btn size="x-small" variant="text" icon="mdi-undo" @click="aiStore.resetPrompt(key as any)" />
                      </template>
                    </v-textarea>
                  </v-col>
                </v-row>
              </template>

              <div class="d-flex justify-end">
                <v-btn type="submit" class="glass-btn-accent" variant="tonal" prepend-icon="mdi-content-save">保存 AI 配置</v-btn>
              </div>
            </v-form>
          </v-card-text>
        </v-card>

        <!-- AI 测试台 -->
        <v-card variant="outlined" rounded="xl" class="mt-4">
          <v-card-title class="d-flex align-center text-subtitle-2 font-weight-bold pa-4 pb-0">
            <v-icon start size="small">mdi-flask-outline</v-icon>AI 测试台
          </v-card-title>
          <v-card-text>
            <v-textarea v-model="testInput" label="待翻译原文" density="compact" variant="outlined" rows="3" auto-grow class="mb-4" />
            <div class="d-flex ga-2 mb-4">
              <v-btn size="small" variant="tonal" color="primary" :loading="isTestingAi" @click="handleTestAi('series_overview')">测试剧集简介</v-btn>
              <v-btn size="small" variant="tonal" color="primary" :loading="isTestingAi" @click="handleTestAi('cast_character')">测试角色翻译</v-btn>
              <v-btn size="small" variant="tonal" color="info" :loading="isTestingAi" @click="handleTestAi('movie_title')">测试标题</v-btn>
            </div>
            <v-divider class="mb-4" />
            <div class="text-caption text-medium-emphasis font-weight-bold mb-2">翻译结果</div>
            <v-sheet v-if="testResult" class="pa-4 border rounded bg-success-darken-4">
              <div class="text-caption text-medium-emphasis mb-1">AI 译文：</div>
              <div class="text-body-2">{{ testResult }}</div>
            </v-sheet>
            <v-alert v-else type="info" variant="tonal" density="compact">点击上方按钮开始测试</v-alert>
          </v-card-text>
        </v-card>
      </v-window-item>

      <!-- ========== 安全设置 ========== -->
      <v-window-item value="security">
        <v-card variant="outlined" rounded="xl">
          <v-card-text>
            <h3 class="text-subtitle-2 font-weight-bold mb-3">
              <v-icon size="small" start>mdi-shield-check</v-icon>双重验证 (2FA)
            </h3>
            <div class="d-flex align-center mb-4">
              <v-chip :color="is2faEnabled ? 'success' : 'default'" size="small" variant="tonal" label>
                {{ is2faEnabled ? '已启用' : '未启用' }}
              </v-chip>
              <v-spacer />
              <v-btn v-if="!is2faEnabled" size="small" variant="tonal" color="primary" prepend-icon="mdi-shield-plus" @click="handleSetup2fa">启用 2FA</v-btn>
              <v-btn v-else size="small" variant="tonal" color="error" prepend-icon="mdi-shield-off" @click="handleDisable2fa">禁用 2FA</v-btn>
            </div>

            <v-divider class="my-5" />

            <h3 class="text-subtitle-2 font-weight-bold mb-3">
              <v-icon size="small" start>mdi-key-variant</v-icon>修改密码
            </h3>
            <v-btn size="small" variant="tonal" color="primary" prepend-icon="mdi-lock-reset" @click="showPasswordDialog = true">修改密码</v-btn>

            <v-divider class="my-5" />

            <h3 class="text-subtitle-2 font-weight-bold mb-3">
              <v-icon size="small" start>mdi-timer-outline</v-icon>登录过期设置
            </h3>
            <div class="d-flex align-center mb-2">
              <v-chip :color="permanentLoginEnabled ? 'success' : 'default'" size="small" variant="tonal" label>
                {{ permanentLoginEnabled ? '永久登录' : '24小时过期' }}
              </v-chip>
              <v-spacer />
              <v-switch v-model="permanentLoginEnabled" color="primary" hide-details inset :loading="permanentLoginLoading" @update:model-value="(v: boolean | null) => handleTogglePermanentLogin(!!v)">
                <template #label>
                  <span class="text-caption">{{ permanentLoginEnabled ? '永久登录' : '24小时过期' }}</span>
                </template>
              </v-switch>
            </div>
            <div class="text-caption text-medium-emphasis">{{ permanentLoginEnabled ? '登录后长期有效，无需频繁重新登录。' : '登录后24小时过期，需要定期重新登录。' }}</div>
          </v-card-text>
        </v-card>
      </v-window-item>

      <!-- ========== 会话管理 ========== -->
      <v-window-item value="sessions">
        <v-card variant="outlined" rounded="xl">
          <v-card-text>
            <div class="d-flex align-center mb-4">
              <h3 class="text-subtitle-1 font-weight-bold">会话管理</h3>
              <v-spacer />
              <v-btn size="small" variant="tonal" prepend-icon="mdi-refresh" :loading="isLoadingSessions" @click="loadSessions" class="mr-2">刷新</v-btn>
              <v-btn size="small" variant="tonal" color="error" prepend-icon="mdi-account-remove" @click="handleRevokeAllSessions">踢出所有其他设备</v-btn>
            </div>

            <v-alert v-if="!sessions.length" type="info" variant="tonal" density="compact">暂无活跃会话</v-alert>

            <v-list lines="two" density="compact">
              <v-list-item v-for="session in sessions" :key="session.session_id" :class="session.is_current ? 'bg-success-darken-4' : ''" rounded="xl" class="mb-2 border">
                <template #prepend>
                  <v-chip :color="session.is_current ? 'success' : 'default'" size="small" variant="tonal" label>
                    {{ session.is_current ? '当前' : '其他' }}
                  </v-chip>
                </template>
                <v-list-item-title class="font-weight-medium">{{ session.device_name }} / {{ session.device_type }}</v-list-item-title>
                <v-list-item-subtitle>
                  IP: {{ session.ip_address }} · UA: {{ formatUserAgent(session.user_agent) }} · {{ formatExpiresIn(session.expires_in_hours) }}后过期 · 登录时间: {{ formatTime(session.login_time) }}
                </v-list-item-subtitle>
                <template #append>
                  <v-btn v-if="!session.is_current" size="x-small" variant="tonal" color="error" icon="mdi-close" density="comfortable" @click="handleRevokeSession(session.session_id)" />
                </template>
              </v-list-item>
            </v-list>
          </v-card-text>
        </v-card>
      </v-window-item>

      <!-- ========== 备份管理 ========== -->
      <v-window-item value="backup">
        <v-card variant="outlined" rounded="xl" class="mb-4">
          <v-card-text>
            <div class="d-flex align-center justify-space-between mb-4">
              <div>
                <h3 class="text-subtitle-1 font-weight-bold">手动备份与恢复</h3>
                <p class="text-caption text-medium-emphasis">创建快照以保护你的元数据和合集配置</p>
              </div>
              <v-btn color="primary" variant="tonal" prepend-icon="mdi-plus" :loading="settingsStore.isBackupLoading" @click="showBackupModal = true">创建备份</v-btn>
            </div>

            <v-table v-if="settingsStore.backups.length" density="compact" hover>
              <thead>
                <tr>
                  <th class="text-left">文件名</th>
                  <th class="text-left">类型</th>
                  <th class="text-left">大小</th>
                  <th class="text-left">创建时间</th>
                  <th class="text-center" width="140">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="b in settingsStore.backups" :key="b.filename">
                  <td><code>{{ b.filename }}</code></td>
                  <td>{{ b.type === 'zip' ? '压缩包' : '快照' }}</td>
                  <td class="text-body-2">{{ b.size_mb || b.size }}</td>
                  <td class="text-body-2">{{ b.created_at }}</td>
                  <td class="text-center">
                    <v-btn size="x-small" variant="tonal" color="info" icon="mdi-restore" density="comfortable" class="mr-1" @click="restoreFilename = b.filename; showRestoreDialog = true" />
                    <v-btn size="x-small" variant="tonal" color="error" icon="mdi-delete" density="comfortable" @click="handleDeleteBackup(b.filename)" />
                  </td>
                </tr>
              </tbody>
            </v-table>

            <v-card v-else variant="tonal" class="pa-6 text-center">
              <v-icon size="48" color="grey-lighten-1">mdi-zip-box-outline</v-icon>
              <p class="mt-2 text-medium-emphasis">暂无备份记录</p>
              <v-btn color="primary" variant="tonal" size="small" class="mt-2" @click="showBackupModal = true">创建第一个备份</v-btn>
            </v-card>
          </v-card-text>
        </v-card>
      </v-window-item>
    </v-window>

    <!-- 2FA 对话框 -->
    <v-dialog v-model="show2faDialog" max-width="400">
      <v-card rounded="xl">
        <v-card-title class="d-flex align-center">
          <v-icon icon="mdi-shield-lock" class="mr-2" />
          启用双重验证
        </v-card-title>
        <v-divider />
        <v-card-text class="text-center">
          <v-img v-if="twoFactorSetup?.qr_code" :src="twoFactorSetup.qr_code" alt="2FA QR Code" max-width="200" class="mx-auto" />
          <p class="text-caption text-medium-emphasis mt-3">使用验证器 App 扫描二维码</p>
          <v-text-field v-model="twoFactorCode" label="输入 6 位验证码" density="compact" variant="outlined" maxlength="6" class="mt-4" />
        </v-card-text>
        <v-divider />
        <v-card-actions>
          <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="show2faDialog = false; twoFactorCode = ''">取消</v-btn>
          <v-btn color="primary" variant="tonal" prepend-icon="mdi-check" @click="handleEnable2fa">确认启用</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 修改密码对话框 -->
    <v-dialog v-model="showPasswordDialog" max-width="400">
      <v-card rounded="xl">
        <v-card-title class="d-flex align-center">
          <v-icon icon="mdi-key-variant" class="mr-2" />
          修改密码
        </v-card-title>
        <v-divider />
        <v-card-text>
          <PasswordInput v-model="passwordForm.current" label="当前密码" density="compact" variant="outlined" />
          <PasswordInput v-model="passwordForm.new" label="新密码" density="compact" variant="outlined" />
          <PasswordInput v-model="passwordForm.confirm" label="确认新密码" density="compact" variant="outlined" />
        </v-card-text>
        <v-divider />
        <v-card-actions>
          <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="showPasswordDialog = false">取消</v-btn>
          <v-btn color="primary" variant="tonal" prepend-icon="mdi-check" @click="handleChangePassword">确认修改</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 创建备份对话框 -->
    <v-dialog v-model="showBackupModal" max-width="420">
      <v-card rounded="xl">
        <v-card-title class="d-flex align-center">
          <v-icon icon="mdi-backup-restore" class="mr-2" />
          创建备份
        </v-card-title>
        <v-divider />
        <v-card-text>
          <v-select v-model="backupConfig.mode" :items="[{ title: '快照(仅元数据)', value: 'snapshot' }, { title: '完整(含图片)', value: 'zip' }]" label="备份模式" density="compact" variant="outlined" class="mb-4" />
          <v-switch v-model="backupConfig.includeOverride" color="primary" hide-details label="Override 缓存" class="mb-2" />
          <v-switch v-model="backupConfig.includeCollections" color="primary" hide-details label="自定义合集" />
        </v-card-text>
        <v-divider />
        <v-card-actions>
          <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="showBackupModal = false">取消</v-btn>
          <v-btn color="primary" variant="tonal" prepend-icon="mdi-download" :loading="settingsStore.isBackupLoading" @click="handleCreateBackup">开始备份</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 恢复备份对话框 -->
    <v-dialog v-model="showRestoreDialog" max-width="420">
      <v-card rounded="xl">
        <v-card-title class="d-flex align-center">
          <v-icon icon="mdi-restore" class="mr-2" />
          恢复备份
        </v-card-title>
        <v-divider />
        <v-card-text>
          <p class="text-body-2 mb-4">恢复备份: <code>{{ restoreFilename }}</code></p>
          <v-select v-model="restoreMode" :items="[
            { title: '合并添加 (保留现有数据)', value: 'merge_add' },
            { title: '覆盖 (替换冲突数据)', value: 'overwrite' },
            { title: '纯净恢复 (清空后恢复)', value: 'clean_restore' },
          ]" label="恢复模式" density="compact" variant="outlined" />
          <v-alert type="warning" variant="tonal" density="compact" class="mt-4">建议先创建当前状态的快照再恢复。</v-alert>
        </v-card-text>
        <v-divider />
        <v-card-actions>
          <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="showRestoreDialog = false">取消</v-btn>
          <v-btn color="warning" variant="tonal" prepend-icon="mdi-restore" @click="handleRestoreBackup">确认恢复</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 路径浏览器对话框 -->
    <PathBrowserDialog
      v-model="showPathBrowser"
      :title="pathBrowserTitle"
      :current-path="pathBrowserCurrent"
      @select="handlePathSelect"
    />
  </v-container>
</template>
