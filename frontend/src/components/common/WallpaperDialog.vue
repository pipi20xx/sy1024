<script setup lang="ts">
/**
 * WallpaperDialog — 壁纸管理对话框
 *
 * 三个 TAB：
 * 1. 在线壁纸：API 随机源 + 自定义 URL（后端后台自动预取，打开秒加载）
 * 2. 上传壁纸：手动上传的图片
 * 3. 历史壁纸：系统自动收录的历史使用图
 *
 * 配置保存到后端配置文件的 wallpaper 字段，持久化且跨设备同步。
 */
import { computed, ref, watch } from 'vue'
import { appearanceApi, type WallpaperConfig, type WallpaperApiSource, type WallpaperUpload, type WallpaperHistory, type WallpaperDisplayMode } from '@/api/appearance'
import { useGlassWallpaper } from '@/glass'
import { useDisplay } from 'vuetify'
import {
  persistPartialThemeCustomizerSettings,
  useThemeCustomizer,
  type ThemeCustomizerGlassWallpaperBrightnessMode,
} from '@/composables/useThemeCustomizer'

const props = withDefaults(
  defineProps<{
    modelValue?: boolean
  }>(),
  {
    modelValue: true,
  },
)

const emit = defineEmits<{
  (event: 'close'): void
  (event: 'update:modelValue', value: boolean): void
  (event: 'changed'): void
}>()

type WallpaperTab = 'online' | 'upload' | 'history'

const display = useDisplay()
const glass = useGlassWallpaper()
const { settings } = useThemeCustomizer()

// ── 壁纸亮度 ──────────────────────────────────────────────

const WALLPAPER_BRIGHTNESS_MIN = 0.2
const WALLPAPER_BRIGHTNESS_MAX = 1.5

const brightnessMode = ref<ThemeCustomizerGlassWallpaperBrightnessMode>(settings.value.glassWallpaperBrightnessMode)
const brightnessValue = ref(settings.value.glassWallpaperBrightness)

watch(
  () => props.modelValue,
  (value) => {
    if (value) {
      brightnessMode.value = settings.value.glassWallpaperBrightnessMode
      brightnessValue.value = settings.value.glassWallpaperBrightness
    }
  },
  { immediate: true },
)

function toggleBrightnessMode() {
  const next: ThemeCustomizerGlassWallpaperBrightnessMode = brightnessMode.value === 'manual' ? 'auto' : 'manual'
  brightnessMode.value = next
  persistPartialThemeCustomizerSettings({ glassWallpaperBrightnessMode: next })
}

function updateBrightness(value: unknown) {
  const num = Array.isArray(value) ? value[0] : value
  brightnessValue.value = Math.min(WALLPAPER_BRIGHTNESS_MAX, Math.max(WALLPAPER_BRIGHTNESS_MIN, Number(num) || 0.86))
  persistPartialThemeCustomizerSettings({
    glassWallpaperBrightnessMode: 'manual',
    glassWallpaperBrightness: brightnessValue.value,
  })
  brightnessMode.value = 'manual'
}

const visible = computed({
  get: () => props.modelValue,
  set: (value) => {
    emit('update:modelValue', value)
    if (!value) emit('close')
  },
})

// ── 状态 ──────────────────────────────────────────────────

const loading = ref(false)
const saving = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const config = ref<WallpaperConfig | null>(null)
const sources = ref<WallpaperApiSource[]>([])
const uploads = ref<WallpaperUpload[]>([])
const history = ref<WallpaperHistory[]>([])
const uploadProgress = ref(false)
const customUrlInput = ref('')

// 当前浏览的 TAB：只决定弹窗里展示哪个面板，切换 TAB 不改变已应用的壁纸
const activeTab = ref<WallpaperTab>('online')

function tabFromSourceType(sourceType: WallpaperConfig['source_type']): WallpaperTab {
  if (sourceType === 'api' || sourceType === 'url') return 'online'
  if (sourceType === 'history') return 'history'
  return 'upload'
}

// 后台自动换图间隔预设
const refreshIntervalPresets = [
  { label: '30 秒', value: 30, hint: '自动换图推荐' },
  { label: '5 分钟', value: 300, hint: '中等频率' },
  { label: '1 小时', value: 3600, hint: '低频率' },
  { label: '24 小时', value: 86400, hint: '极少换图' },
  { label: '不下载', value: 0, hint: '停止后台下载' },
]

const currentRefreshInterval = computed(() => config.value?.refresh_interval ?? 60)
const currentRefreshIntervalLabel = computed(
  () => refreshIntervalPresets.find(p => p.value === currentRefreshInterval.value)?.label ?? `${currentRefreshInterval.value} 秒`,
)

// 图库轮播间隔预设（更细档位）
const rotationIntervalPresets = [
  { label: '10 秒', value: 10, hint: '快速轮播' },
  { label: '30 秒', value: 30, hint: '较快' },
  { label: '1 分钟', value: 60, hint: '常规' },
  { label: '5 分钟', value: 300, hint: '中等' },
  { label: '15 分钟', value: 900, hint: '较慢' },
  { label: '30 分钟', value: 1800, hint: '慢速' },
  { label: '1 小时', value: 3600, hint: '低频率' },
  { label: '6 小时', value: 21600, hint: '很少' },
  { label: '24 小时', value: 86400, hint: '极少' },
]

const currentRotationInterval = computed(() => config.value?.rotation_interval ?? 60)

// ── 数据加载 ──────────────────────────────────────────────

async function loadAll() {
  loading.value = true
  try {
    const [configRes, sourcesRes, uploadsRes, historyRes] = await Promise.all([
      appearanceApi.getConfig(),
      appearanceApi.getSources(),
      appearanceApi.listUploads(),
      appearanceApi.listHistory(),
    ])
    config.value = configRes
    sources.value = sourcesRes.sources
    uploads.value = uploadsRes
    history.value = historyRes
    customUrlInput.value = configRes.custom_url || ''
    activeTab.value = tabFromSourceType(configRes.source_type)
  } catch (e) {
    console.error('加载壁纸配置失败', e)
  } finally {
    loading.value = false
  }
}

async function reloadUploads() {
  try {
    uploads.value = await appearanceApi.listUploads()
  } catch {
    // ignore
  }
}

async function reloadHistory() {
  try {
    history.value = await appearanceApi.listHistory()
  } catch {
    // ignore
  }
}

// ── 操作 ──────────────────────────────────────────────────

function selectTab(tab: WallpaperTab) {
  activeTab.value = tab
}

async function selectApiSource(sourceId: string) {
  if (!config.value || saving.value) return
  config.value.api_source_id = sourceId
  config.value.source_type = 'api'
  await saveConfig()
}

async function selectUpload(filename: string) {
  if (!config.value || saving.value) return
  config.value.upload_filename = filename
  config.value.source_type = 'upload'
  await saveConfig()
}

async function selectHistory(filename: string) {
  if (!config.value || saving.value) return
  config.value.history_filename = filename
  config.value.source_type = 'history'
  await saveConfig()
}

async function applyCustomUrl() {
  if (!config.value || saving.value) return
  const url = customUrlInput.value.trim()
  if (!url) return
  config.value.custom_url = url
  config.value.source_type = 'url'
  await saveConfig()
}

async function selectRefreshInterval(interval: number) {
  if (!config.value || saving.value) return
  config.value.refresh_interval = interval
  await saveConfig()
}

async function selectDisplayMode(mode: WallpaperDisplayMode) {
  if (!config.value || saving.value) return
  config.value.display_mode = mode
  await saveConfig()
}

async function selectRotationInterval(interval: number) {
  if (!config.value || saving.value) return
  config.value.rotation_interval = interval
  await saveConfig()
}

async function toggleRotationScope(pool: 'history' | 'uploads', value: boolean) {
  if (!config.value || saving.value) return
  if (!value) {
    // 至少保留一个轮播范围，避免「两个都不选」的无效状态
    const other = pool === 'history' ? config.value.rotation_include_uploads : config.value.rotation_include_history
    if (!other) return
  }
  if (pool === 'history') config.value.rotation_include_history = value
  else config.value.rotation_include_uploads = value
  await saveConfig()
}

async function saveConfig() {
  if (!config.value) return
  saving.value = true
  try {
    const res = await appearanceApi.updateConfig(config.value)
    config.value = res.config
    // 递增全局刷新信号，触发 App.vue 重新加载壁纸
    glass.wallpaperRefreshSignal.value++
    emit('changed')
  } catch (e) {
    console.error('保存壁纸配置失败', e)
  } finally {
    saving.value = false
  }
}

async function handleUpload(event: Event) {
  const input = event.target as HTMLInputElement
  if (!input.files || input.files.length === 0) return
  const file = input.files[0]
  uploadProgress.value = true
  try {
    await appearanceApi.upload(file)
    await reloadUploads()
  } catch (e) {
    console.error('上传壁纸失败', e)
  } finally {
    uploadProgress.value = false
    input.value = ''
  }
}

async function deleteUpload(filename: string) {
  try {
    await appearanceApi.deleteUpload(filename)
    await reloadUploads()
    // 如果当前选中的被删除了，清除引用
    if (config.value?.upload_filename === filename) {
      config.value.upload_filename = ''
    }
  } catch (e) {
    console.error('删除壁纸失败', e)
  }
}

async function deleteHistory(filename: string) {
  try {
    await appearanceApi.deleteHistory(filename)
    await reloadHistory()
    if (config.value?.history_filename === filename) {
      config.value.history_filename = ''
    }
  } catch (e) {
    console.error('删除历史壁纸失败', e)
  }
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(ts: number): string {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  const date = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
  const time = `${pad(d.getHours())}:${pad(d.getMinutes())}`
  if (d.toDateString() === now.toDateString()) return `今天 ${time}`
  return `${date} ${time}`
}

// ── 生命周期 ──────────────────────────────────────────────

watch(
  () => props.modelValue,
  (value) => {
    if (value) {
      void loadAll()
    }
  },
  { immediate: true },
)
</script>

<template>
  <VDialog
    v-model="visible"
    width="100%"
    max-width="34rem"
    scrollable
    :fullscreen="display.smAndDown.value"
  >
    <VCard>
      <VCardTitle class="d-flex align-center pa-4">
        <VIcon icon="mdi-wallpaper" class="me-2" />
        壁纸管理
        <VSpacer />
        <VBtn
          icon
          variant="text"
          size="small"
          aria-label="关闭"
          @click.stop="visible = false"
        >
          <VIcon icon="mdi-close" />
        </VBtn>
      </VCardTitle>
      <VDivider />

      <VCardText class="appearance-dialog__body">
        <div v-if="loading" class="wallpaper-dialog__loading">
          <VProgressCircular indeterminate color="primary" size="32" />
        </div>

        <template v-else-if="config">
          <!-- TAB 选择 -->
          <section>
            <h3 class="appearance-dialog__label">壁纸来源</h3>
            <VBtnToggle
              :model-value="activeTab"
              mandatory
              color="primary"
              variant="text"
              class="wallpaper-dialog__source-type option-btn-group"
              @update:model-value="selectTab"
            >
              <VBtn value="online" class="wallpaper-dialog__source-type-option">
                <VIcon start size="18">mdi-web</VIcon>
                在线壁纸
              </VBtn>
              <VBtn value="upload" class="wallpaper-dialog__source-type-option">
                <VIcon start size="18">mdi-upload</VIcon>
                上传壁纸
              </VBtn>
              <VBtn value="history" class="wallpaper-dialog__source-type-option">
                <VIcon start size="18">mdi-history</VIcon>
                历史壁纸
              </VBtn>
            </VBtnToggle>
          </section>

          <!-- 在线壁纸：自定义 URL + API 随机源 -->
          <template v-if="activeTab === 'online'">
            <section>
              <h3 class="appearance-dialog__label">自定义 URL</h3>
              <VTextField
                v-model="customUrlInput"
                placeholder="https://example.com/wallpaper.jpg"
                variant="outlined"
                density="compact"
                hide-details
                class="wallpaper-dialog__url-input"
              />
              <VBtn
                variant="tonal"
                color="primary"
                size="small"
                class="mt-2"
                prepend-icon="mdi-check"
                :loading="saving"
                @click="applyCustomUrl"
              >
                应用
              </VBtn>
              <p class="appearance-dialog__hint">
                输入固定图片 URL（直链），应用后立即切换为自定义 URL 壁纸。
              </p>
            </section>

            <section>
              <h3 class="appearance-dialog__label">API 随机源</h3>
              <div class="wallpaper-dialog__source-grid">
                <button
                  v-for="source in sources"
                  :key="source.id"
                  type="button"
                  class="wallpaper-dialog__source-card"
                  :class="{ 'wallpaper-dialog__source-card--active': config.source_type === 'api' && config.api_source_id === source.id }"
                  @click="selectApiSource(source.id)"
                >
                  <div class="wallpaper-dialog__source-info">
                    <span class="wallpaper-dialog__source-name">{{ source.name }}</span>
                    <span class="wallpaper-dialog__source-meta">
                      {{ source.category === 'acg' ? 'ACG' : '综合' }} ·
                      {{ source.orientation === 'landscape' ? '横屏' : source.orientation === 'portrait' ? '竖屏' : '任意' }}
                    </span>
                  </div>
                  <VIcon
                    v-if="config.source_type === 'api' && config.api_source_id === source.id"
                    icon="mdi-check-circle"
                    color="primary"
                    size="20"
                  />
                </button>
              </div>
            </section>

            <!-- 下载新图间隔（后端预取节奏，与显示模式无关） -->
            <section>
              <h3 class="appearance-dialog__label">下载新图间隔</h3>
              <div class="wallpaper-dialog__cache-grid">
                <button
                  v-for="preset in refreshIntervalPresets"
                  :key="preset.value"
                  type="button"
                  class="wallpaper-dialog__cache-option"
                  :class="{ 'wallpaper-dialog__cache-option--active': currentRefreshInterval === preset.value }"
                  @click="selectRefreshInterval(preset.value)"
                >
                  <span class="wallpaper-dialog__cache-label">{{ preset.label }}</span>
                  <span class="wallpaper-dialog__cache-hint">{{ preset.hint }}</span>
                </button>
              </div>
              <p class="appearance-dialog__hint">
                后端按此间隔在后台下载新图到历史图库，打开页面即时加载，不再阻塞等待。
              </p>
            </section>

            <!-- 显示方式（仅 API 随机源） -->
            <section v-if="config.source_type === 'api'">
              <h3 class="appearance-dialog__label">显示方式</h3>
              <VBtnToggle
                :model-value="config.display_mode"
                mandatory
                color="primary"
                variant="outlined"
                density="comfortable"
                class="wallpaper-dialog__display-mode"
                @update:model-value="selectDisplayMode"
              >
                <VBtn value="latest">
                  <VIcon start size="16">mdi-image-filter-hdr</VIcon>
                  跟随最新
                </VBtn>
                <VBtn value="rotation">
                  <VIcon start size="16">mdi-shuffle</VIcon>
                  图库轮播
                </VBtn>
              </VBtnToggle>
              <p class="appearance-dialog__hint">
                跟随最新：一直显示历史最新一张；图库轮播：仅在历史图库内随机切换。
              </p>
            </section>

            <!-- 轮播范围 -->
            <section v-if="config.source_type === 'api' && config.display_mode === 'rotation'">
              <h3 class="appearance-dialog__label">轮播范围</h3>
              <div class="wallpaper-dialog__rotation-scope">
                <VSwitch
                  :model-value="config.rotation_include_history"
                  color="primary"
                  density="compact"
                  hide-details
                  label="历史图库"
                  @update:model-value="(value) => toggleRotationScope('history', Boolean(value))"
                />
                <VSwitch
                  :model-value="config.rotation_include_uploads"
                  color="primary"
                  density="compact"
                  hide-details
                  label="上传壁纸"
                  @update:model-value="(value) => toggleRotationScope('uploads', Boolean(value))"
                />
              </div>
              <p class="appearance-dialog__hint">
                全开 = 两个都勾；半开 = 只勾一个。至少保留一个参与轮播。
              </p>
            </section>

            <!-- 图库轮播间隔 -->
            <section v-if="config.source_type === 'api' && config.display_mode === 'rotation'">
              <h3 class="appearance-dialog__label">轮播间隔</h3>
              <div class="wallpaper-dialog__cache-grid">
                <button
                  v-for="preset in rotationIntervalPresets"
                  :key="preset.value"
                  type="button"
                  class="wallpaper-dialog__cache-option"
                  :class="{ 'wallpaper-dialog__cache-option--active': currentRotationInterval === preset.value }"
                  @click="selectRotationInterval(preset.value)"
                >
                  <span class="wallpaper-dialog__cache-label">{{ preset.label }}</span>
                  <span class="wallpaper-dialog__cache-hint">{{ preset.hint }}</span>
                </button>
              </div>
              <p class="appearance-dialog__hint">
                与「下载新图间隔」无关，仅在历史图库内随机轮播。
              </p>
            </section>
          </template>

          <!-- 上传壁纸 -->
          <section v-if="activeTab === 'upload'">
            <div class="wallpaper-dialog__upload-header">
              <h3 class="appearance-dialog__label">已上传壁纸</h3>
              <VBtn
                variant="tonal"
                color="primary"
                size="small"
                prepend-icon="mdi-upload"
                :loading="uploadProgress"
                @click="fileInput?.click()"
              >
                上传
              </VBtn>
              <input
                ref="fileInput"
                type="file"
                accept="image/jpeg,image/png,image/webp,image/gif,image/bmp"
                class="wallpaper-dialog__file-input"
                @change="handleUpload"
              />
            </div>

            <div v-if="uploads.length === 0" class="wallpaper-dialog__empty">
              <VIcon icon="mdi-image-off" size="32" class="mb-2" />
              <span>暂无上传的壁纸</span>
            </div>

            <div v-else class="wallpaper-dialog__upload-grid">
              <div
                v-for="item in uploads"
                :key="item.filename"
                class="wallpaper-dialog__upload-item"
                :class="{ 'wallpaper-dialog__upload-item--active': config?.upload_filename === item.filename }"
              >
                <img
                  :src="`/api/appearance/wallpaper/uploads/${item.filename}`"
                  class="wallpaper-dialog__upload-thumb"
                  loading="lazy"
                  @click="selectUpload(item.filename)"
                />
                <div class="wallpaper-dialog__upload-meta">
                  <span class="wallpaper-dialog__upload-size">{{ formatSize(item.size) }}</span>
                  <div class="wallpaper-dialog__upload-actions">
                    <VIcon
                      v-if="config?.upload_filename === item.filename"
                      icon="mdi-check-circle"
                      color="primary"
                      size="18"
                    />
                    <VBtn
                      icon="mdi-delete"
                      size="x-small"
                      variant="text"
                      color="error"
                      @click.stop="deleteUpload(item.filename)"
                    />
                  </div>
                </div>
              </div>
            </div>
          </section>

          <!-- 历史壁纸 -->
          <section v-if="activeTab === 'history'">
            <div class="wallpaper-dialog__upload-header">
              <h3 class="appearance-dialog__label">历史壁纸</h3>
              <span class="wallpaper-dialog__history-count">共 {{ history.length }} 张</span>
            </div>

            <div v-if="history.length === 0" class="wallpaper-dialog__empty">
              <VIcon icon="mdi-image-off" size="32" class="mb-2" />
              <span>暂无历史壁纸</span>
            </div>

            <div v-else class="wallpaper-dialog__upload-grid">
              <div
                v-for="item in history"
                :key="item.filename"
                class="wallpaper-dialog__upload-item"
                :class="{ 'wallpaper-dialog__upload-item--active': config?.history_filename === item.filename }"
              >
                <img
                  :src="`/api/appearance/wallpaper/uploads/${item.filename}`"
                  class="wallpaper-dialog__upload-thumb"
                  loading="lazy"
                  @click="selectHistory(item.filename)"
                />
                <div class="wallpaper-dialog__upload-meta">
                  <span class="wallpaper-dialog__upload-size">{{ formatDate(item.created_at) }}</span>
                  <div class="wallpaper-dialog__upload-actions">
                    <VIcon
                      v-if="config?.history_filename === item.filename"
                      icon="mdi-check-circle"
                      color="primary"
                      size="18"
                    />
                    <VBtn
                      icon="mdi-delete"
                      size="x-small"
                      variant="text"
                      color="error"
                      @click.stop="deleteHistory(item.filename)"
                    />
                  </div>
                </div>
              </div>
            </div>
          </section>

          <!-- 壁纸亮度 -->
          <section>
            <div class="appearance-dialog__slider-header">
              <h3 class="appearance-dialog__label">壁纸亮度</h3>
              <VBtn
                variant="text"
                size="x-small"
                :color="brightnessMode === 'manual' ? 'primary' : 'default'"
                @click="toggleBrightnessMode"
              >
                {{ brightnessMode === 'manual' ? '手动' : '自动' }}
              </VBtn>
            </div>
            <VSlider
              v-if="brightnessMode === 'manual'"
              :model-value="brightnessValue"
              aria-label="壁纸亮度"
              :min="WALLPAPER_BRIGHTNESS_MIN"
              :max="WALLPAPER_BRIGHTNESS_MAX"
              :step="0.01"
              color="primary"
              density="comfortable"
              hide-details
              thumb-label
              @update:model-value="updateBrightness"
            />
            <p class="appearance-dialog__hint">
              自动模式下根据壁纸明暗自动计算亮度；手动模式可自行调节。
            </p>
          </section>
        </template>
      </VCardText>

      <VDivider />
      <VCardActions class="appearance-dialog__actions justify-center">
        <VBtn
          variant="tonal"
          color="primary"
          prepend-icon="mdi-check"
          @click="visible = false"
        >
          完成
        </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style scoped lang="scss">
/* 骨架样式统一管理在 styles/appearance-dialogs.css，此处保留壁纸对话框独有规则 */
.wallpaper-dialog__loading {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 0;
}

.appearance-dialog__slider-header {
  /* 此对话框滑块头间距为 16px,覆盖全局默认 12px */
  gap: 16px;
}

.wallpaper-dialog__source-type {
  width: 100%;

  :deep(.v-btn-group) {
    width: 100%;
  }
}

.wallpaper-dialog__source-type-option {
  /* 边框/圆角/阴影复位由全局 .option-btn-group 统一提供 */
  flex: 1;
  min-inline-size: 0;
}

.wallpaper-dialog__display-mode {
  width: 100%;

  .v-btn {
    flex: 1;
  }
}

.wallpaper-dialog__rotation-scope {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
}

.wallpaper-dialog__source-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
}

.wallpaper-dialog__source-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border: 2px solid transparent;
  border-radius: 10px;
  background: rgba(var(--v-theme-on-surface), 0.03);
  cursor: pointer;
  outline: none;
  transition: border-color 0.15s ease, background 0.15s ease;

  &:hover {
    background: rgba(var(--v-theme-on-surface), 0.06);
  }

  &--active {
    border-color: rgb(var(--v-theme-primary));
    background: rgba(var(--v-theme-primary), 0.08);
  }
}

.wallpaper-dialog__source-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.wallpaper-dialog__source-name {
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.875rem;
  font-weight: 500;
}

.wallpaper-dialog__source-meta {
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.6875rem;
}

.wallpaper-dialog__url-input {
  :deep(.v-field) {
    border-radius: 8px;
  }
}

.wallpaper-dialog__upload-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;

  .appearance-dialog__label {
    margin-block-end: 0;
  }
}

.wallpaper-dialog__history-count {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
  font-size: 0.75rem;
}

.wallpaper-dialog__file-input {
  display: none;
}

.wallpaper-dialog__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 32px 0;
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.8125rem;
}

.wallpaper-dialog__upload-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 12px;
}

.wallpaper-dialog__upload-item {
  border: 2px solid transparent;
  border-radius: 10px;
  overflow: hidden;
  background: rgba(var(--v-theme-on-surface), 0.03);
  transition: border-color 0.15s ease;

  &--active {
    border-color: rgb(var(--v-theme-primary));
  }
}

.wallpaper-dialog__upload-thumb {
  width: 100%;
  height: 80px;
  object-fit: cover;
  cursor: pointer;
}

.wallpaper-dialog__upload-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 8px;
}

.wallpaper-dialog__upload-size {
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.625rem;
}

.wallpaper-dialog__upload-actions {
  display: flex;
  align-items: center;
  gap: 2px;
}

.wallpaper-dialog__cache-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
  gap: 8px;
}

.wallpaper-dialog__cache-option {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 10px 8px;
  border: 2px solid transparent;
  border-radius: 10px;
  background: rgba(var(--v-theme-on-surface), 0.03);
  cursor: pointer;
  outline: none;
  transition: border-color 0.15s ease, background 0.15s ease;

  &:hover {
    background: rgba(var(--v-theme-on-surface), 0.06);
  }

  &--active {
    border-color: rgb(var(--v-theme-primary));
    background: rgba(var(--v-theme-primary), 0.08);
  }
}

.wallpaper-dialog__cache-label {
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.8125rem;
  font-weight: 500;
}

.wallpaper-dialog__cache-hint {
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.625rem;
  text-align: center;
}
</style>
