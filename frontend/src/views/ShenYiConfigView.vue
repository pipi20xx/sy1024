<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { shenyiApi, type ConfigData } from '@/api/shenyi'
defineOptions({ name: 'ShenYiConfigView' })
import { useSettingsStore } from '@/stores'
import { useNotification } from '@/composables'

const settingsStore = useSettingsStore()
const { notify } = useNotification()

const isLoading = ref(false)
const isSaving = ref(false)
const isLoggedIn = ref(false)
const sessionToken = ref('')
const userId = ref('')

// 当前选中的插件页面
const currentPageId = ref('63c322:Settings')
const currentPageName = ref('神医助手')

// 配置数据
const configData = ref<ConfigData>({})
const originalJsonConfig = ref('')
const editableJsonConfig = ref('')
const editableObject = ref<Record<string, any>>({})

// 敏感字段的显示/隐藏状态
const showSecretFields = ref<Record<string, boolean>>({})

// 编辑模式 Tab
const editMode = ref<'visual' | 'json'>('visual')

// 插件页面列表
const pluginPages = [
  { id: '63c322:Settings', name: '神医助手' },
  { id: '63c322:MediaInfoExtractPageView', name: '媒体信息提取' },
  { id: '63c322:MetadataEnhancePageView', name: '元数据增强' },
  { id: '63c322:IntroSkipPageView', name: '片头片尾探测' },
  { id: '63c322:ExperienceEnhancePageView', name: '体验增强' },
]

// 可视化字段配置
interface MultiSelectOption {
  title: string
  value: string
}

interface VisualField {
  key: string           // 唯一标识，用于 v-for key 和 showSecretFields
  path: string          // 嵌套路径，如 "AboutOptions.GitHubToken"，支持点号分隔
  label: string
  type: 'string' | 'boolean' | 'secret' | 'url' | 'multiselect'
  default: string | boolean
  description: string
  options?: MultiSelectOption[]  // multiselect 类型的可选项
}

const visualFieldsConfig: Record<string, VisualField[]> = {
  '63c322:Settings': [
    {
      key: 'GitHubToken',
      path: 'AboutOptions.GitHubToken',
      label: 'GitHub Token',
      type: 'secret',
      default: '',
      description: '用于解决 GitHub API 限流 (Forbidden) 问题，填入 GitHub Personal Access Token 即可解除更新检测限制',
    },
    {
      key: 'GitHubProxy',
      path: 'AboutOptions.GitHubProxy',
      label: 'GitHub 代理',
      type: 'url',
      default: '',
      description: '用于解决无法直连 GitHub 的网络问题，填入代理地址（如 https://mirror.ghproxy.com）。有代理则不建议设置此项',
    },
  ],
  '63c322:MetadataEnhancePageView': [
    {
      key: 'PreferTraditionalChinese',
      path: 'PreferTraditionalChinese',
      label: '优先繁体中文',
      type: 'boolean',
      default: false,
      description: '[PRO]若要优先繁中且启用简转繁，设置此项为true，重启Emby生效。默认值为false',
    },
    {
      key: 'ClearTagline',
      path: 'ClearTagline',
      label: '清除标语/宣传语',
      type: 'boolean',
      default: false,
      description: '默认屏蔽刮削标语/宣传语，如有需要可手工修改配置文件。重启Emby生效。默认值为false',
    },
    {
      key: 'MetadataCacheOptionalImageTypes',
      path: 'MetadataBuildOptions.MetadataCacheOptionalImageTypes',
      label: '可选图片类型',
      type: 'multiselect',
      default: '',
      description: '只要提供了主海报poster，此处选中的图片类型将不再请求TMDB图像API刮削，减少不必要的API请求',
      options: [
        { title: 'Logo', value: 'Logo' },
        { title: 'Backdrop (背景图)', value: 'Backdrop' },
        { title: 'Art (艺术图)', value: 'Art' },
        { title: 'Disc (光盘图)', value: 'Disc' },
        { title: 'Thumb (缩略图)', value: 'Thumb' },
      ],
    },
  ],
}

const pageDescriptions: Record<string, string> = {
  '63c322:Settings': '因GitHub API有限流阈值，如频繁遇到Forbidden更新错误或其他网络错误，可手工配置插件目录中的配置文件。GitHubToken用于解决更新检测遇到Forbidden的问题，GitHubProxy用于解决一般网络问题，有代理则不建议设置。',
  '63c322:MediaInfoExtractPageView': '默认不对ts/m2ts做视频截图，因为网盘场景可能会扫很久并失败。如有需要可手工修改插件目录的配置文件中的"ImageCaptureExcludeMediaContainers"配置项来启用并重启Emby生效。',
  '63c322:MetadataEnhancePageView': '比如某些电影没有Logo和Backdrop图片，TMDB也没有，默认行为仍会请求TMDB图像API刮削缺失的图片。如果希望避免这种请求，可在配置文件中设置"MetadataCacheOptionalImageTypes": "Logo,Backdrop"，意味着只要提供了主海报poster，就不会产生图像API请求。',
}

const currentVisualFields = computed(() => {
  return visualFieldsConfig[currentPageId.value] || []
})

// ── 嵌套路径工具 ──
// 根据点号路径读取嵌套对象值，如 "AboutOptions.GitHubToken"
function getNestedValue(obj: any, path: string): any {
  return path.split('.').reduce((o, k) => o?.[k], obj)
}

// 根据点号路径设置嵌套对象值，自动创建中间对象
function setNestedValue(obj: any, path: string, value: any): void {
  const keys = path.split('.')
  let target = obj
  for (let i = 0; i < keys.length - 1; i++) {
    const k = keys[i]
    if (target[k] === undefined || typeof target[k] !== 'object') {
      target[k] = {}
    }
    target = target[k]
  }
  target[keys[keys.length - 1]] = value
}

const embyConfigured = computed(() => {
  return !!(settingsStore.settings.emby_username && settingsStore.settings.emby_password)
})

// 登录
async function loginWithCredentials() {
  const settings = settingsStore.settings
  if (!settings.emby_username || !settings.emby_password) {
    notify('未配置 Emby 账号', '请先在系统设置中配置 Emby 账号信息', 'warning')
    return
  }

  isLoading.value = true
  try {
    const result = await shenyiApi.login({
      username: settings.emby_username,
      password: settings.emby_password,
    })

    if (result.success && result.data?.session_token) {
      sessionToken.value = result.data.session_token
      userId.value = result.data.user_id || ''
      isLoggedIn.value = true
      notify('登录成功', '已通过 Emby 账号获取会话令牌', 'success')
      await loadConfig()
    } else {
      notify('登录失败', result.message || '未知错误', 'error')
    }
  } catch (e: any) {
    notify('登录失败', e.message, 'error')
  } finally {
    isLoading.value = false
  }
}

// 加载配置
async function loadConfig() {
  if (!sessionToken.value) return
  isLoading.value = true
  try {
    const result = await shenyiApi.getConfig(sessionToken.value, currentPageId.value)
    if (result.success && result.data) {
      configData.value = result.data

      const editObjectContainer = result.data.EditObjectContainer || {}
      originalJsonConfig.value = JSON.stringify(editObjectContainer, null, 2)

      const objectData = editObjectContainer.Object || {}
      if (Array.isArray(objectData)) {
        editableObject.value = objectData[0] || {}
      } else {
        editableObject.value = objectData
      }

      editableJsonConfig.value = JSON.stringify(editableObject.value, null, 2)
    }
  } catch (e: any) {
    notify('加载配置失败', e.message, 'error')
  } finally {
    isLoading.value = false
  }
}

// 保存配置
async function handleSave() {
  if (!sessionToken.value) return

  // 可视化模式：editableObject 已包含完整的嵌套结构（通过 setNestedValue 修改了目标字段）
  // JSON 模式：从 editableJsonConfig 解析
  let objectData: any
  if (editMode.value === 'visual') {
    objectData = editableObject.value
  } else {
    try {
      objectData = JSON.parse(editableJsonConfig.value)
    } catch {
      notify('JSON 格式错误', '请检查 JSON 语法', 'error')
      return
    }
  }

  const configToSave = {
    PageId: currentPageId.value,
    EditObjectContainer: {
      Object: objectData,
    },
  }

  isSaving.value = true
  try {
    const result = await shenyiApi.saveConfig({
      config_data: configToSave,
      session_token: sessionToken.value,
    })
    if (result.success) {
      notify('保存成功', `${currentPageName.value}配置已保存`, 'success')
      await loadConfig()
    } else {
      notify('保存失败', result.message, 'error')
    }
  } catch (e: any) {
    notify('保存失败', e.message, 'error')
  } finally {
    isSaving.value = false
  }
}

// 切换插件页面
function handlePageChange(pageId: string) {
  const page = pluginPages.find(p => p.id === pageId)
  if (!page) return
  currentPageId.value = page.id
  currentPageName.value = page.name
  editMode.value = 'visual'
  if (isLoggedIn.value) {
    loadConfig()
  }
}

// 多选字段：从逗号分隔字符串解析为数组
function csvToArray(csv: string): string[] {
  if (!csv) return []
  return csv.split(',').map(s => s.trim()).filter(Boolean)
}

// 多选字段：从数组序列化为逗号分隔字符串
function arrayToCsv(arr: string[]): string {
  return arr.join(',')
}

// 获取多选字段的当前选中值（数组形式）
function getMultiSelectValue(path: string): string[] {
  const raw = getNestedValue(editableObject.value, path)
  if (Array.isArray(raw)) return raw
  return csvToArray(String(raw || ''))
}

// 可视化字段变更
function handleVisualFieldChange(path: string, value: any) {
  const field = currentVisualFields.value.find(f => f.path === path)
  if (field && field.type === 'boolean') {
    setNestedValue(editableObject.value, path, value === 'true' || value === true)
  } else if (field && field.type === 'multiselect') {
    // multiselect: value 是 string[]，保存为逗号分隔字符串
    setNestedValue(editableObject.value, path, arrayToCsv(value as string[]))
  } else {
    setNestedValue(editableObject.value, path, value)
  }
  updateJsonFromVisual()
}

// 从可视化编辑同步到 JSON
function updateJsonFromVisual() {
  try {
    let baseObject: any = {}
    if (originalJsonConfig.value) {
      const editObjectContainer = JSON.parse(originalJsonConfig.value)
      if (Array.isArray(editObjectContainer.Object)) {
        baseObject = editObjectContainer.Object[0] || {}
      } else {
        baseObject = editObjectContainer.Object || {}
      }
    }
    const mergedObject = { ...baseObject, ...editableObject.value }
    editableJsonConfig.value = JSON.stringify(mergedObject, null, 2)
  } catch (e) {
    console.error('JSON 解析失败:', e)
  }
}

// JSON 编辑变更 → 同步到可视化对象
function handleJsonChange() {
  try {
    const objectData = JSON.parse(editableJsonConfig.value)
    if (Array.isArray(objectData)) {
      editableObject.value = objectData[0] || {}
    } else {
      editableObject.value = objectData
    }
  } catch {
    // JSON 语法错误时不同步，等用户修好
  }
}

onMounted(async () => {
  if (!settingsStore.settings.emby_username) {
    await settingsStore.loadSettings()
  }
  if (embyConfigured.value) {
    await loginWithCredentials()
  }
})
</script>

<template>
  <v-container fluid class="pa-6">
    <div class="d-flex flex-wrap align-center mb-6 ga-3">
      <div class="flex-grow-1">
        <h1 class="text-h5 font-weight-bold">神医配置</h1>
        <p class="text-caption text-medium-emphasis mt-1">通过 API 管理神医 (Strm Assistant) 插件的配置文件</p>
      </div>
      <div class="d-flex ga-2 flex-wrap">
        <v-btn
          v-if="isLoggedIn"
          variant="tonal"
          color="primary"
          prepend-icon="mdi-refresh"
          :loading="isLoading"
          @click="loadConfig"
        >
          刷新配置
        </v-btn>
        <v-btn
          v-if="isLoggedIn"
          variant="tonal"
          color="primary"
          prepend-icon="mdi-content-save"
          :loading="isSaving"
          @click="handleSave"
        >
          保存配置
        </v-btn>
      </div>
    </div>

    <!-- 未配置 Emby 账号 -->
    <v-alert
      v-if="!embyConfigured"
      type="warning"
      variant="tonal"
      class="mb-4"
    >
      <div class="font-weight-bold mb-1">未配置 Emby 账号</div>
      神医配置需要使用 Emby 账号登录获取会话令牌。请先在
      <router-link to="/settings" class="text-primary font-weight-bold">系统设置 → 通用设置 → Emby 账号登录</router-link>
      中配置用户名和密码。
    </v-alert>

    <!-- 已配置但未登录（登录中 / 登录失败） -->
    <v-card
      v-else-if="!isLoggedIn"
      variant="outlined"
      rounded="xl"
      max-width="480"
      class="mx-auto pa-6 text-center"
    >
      <v-progress-circular v-if="isLoading" indeterminate color="primary" size="48" class="mb-4" />
      <v-icon v-else size="48" color="error" class="mb-2">mdi-alert-circle</v-icon>
      <div class="text-h6 mb-2">{{ isLoading ? '正在登录...' : '登录失败' }}</div>
      <div class="text-body-2 text-medium-emphasis mb-4">
        使用系统设置中的 Emby 账号自动登录获取会话令牌
      </div>
      <v-btn v-if="!isLoading" color="primary" variant="tonal" prepend-icon="mdi-refresh" @click="loginWithCredentials">
        重新登录
      </v-btn>
    </v-card>

    <!-- 已登录：配置界面 -->
    <template v-else>
      <!-- 登录信息 -->
      <v-alert type="success" variant="tonal" density="compact" class="mb-4">
        已通过 Emby 账号登录 · 用户ID: {{ userId }}
      </v-alert>

      <!-- 插件页面选择 -->
      <v-card variant="outlined" rounded="xl" class="mb-4">
        <v-card-text>
          <div class="text-subtitle-2 font-weight-bold mb-3">
            <v-icon start size="small">mdi-view-dashboard-outline</v-icon>插件页面
          </div>
          <v-chip-group v-model="currentPageId" column mandatory>
            <v-chip
              v-for="page in pluginPages"
              :key="page.id"
              :value="page.id"
              :variant="currentPageId === page.id ? 'flat' : 'outlined'"
              :color="currentPageId === page.id ? 'primary' : 'default'"
              filter
              @click="handlePageChange(page.id)"
            >
              {{ page.name }}
            </v-chip>
          </v-chip-group>
        </v-card-text>
      </v-card>

      <!-- 页面说明 -->
      <v-alert
        v-if="pageDescriptions[currentPageId]"
        type="info"
        variant="tonal"
        density="compact"
        class="mb-4"
      >
        {{ pageDescriptions[currentPageId] }}
      </v-alert>

      <!-- 配置编辑区域 -->
      <v-card variant="outlined" rounded="xl">
        <v-card-title class="d-flex align-center text-subtitle-2 font-weight-bold pa-4 pb-0">
          <v-icon start size="small">mdi-cog</v-icon>
          {{ currentPageName }} 配置
          <v-spacer />
          <v-btn-toggle v-model="editMode" density="compact" variant="outlined" divided mandatory>
            <v-btn value="visual" size="small" :disabled="currentVisualFields.length === 0">
              <v-icon start size="small">mdi-form-select</v-icon>
              可视化
            </v-btn>
            <v-btn value="json" size="small">
              <v-icon start size="small">mdi-code-block-braces</v-icon>
              JSON
            </v-btn>
          </v-btn-toggle>
        </v-card-title>

        <v-divider class="mt-3" />

        <v-card-text>
          <!-- 加载中 -->
          <div v-if="isLoading" class="text-center pa-6">
            <v-progress-circular indeterminate color="primary" size="40" />
            <p class="mt-2 text-medium-emphasis">加载配置中...</p>
          </div>

          <!-- 可视化编辑 -->
          <template v-else-if="editMode === 'visual'">
            <template v-if="currentVisualFields.length > 0">
              <v-row density="compact">
                <v-col
                  v-for="field in currentVisualFields"
                  :key="field.key"
                  cols="12"
                  sm="6"
                >
                  <v-card variant="outlined" density="compact" class="pa-3 h-100">
                    <div class="text-subtitle-2 font-weight-bold mb-1">{{ field.label }}</div>
                    <div class="text-caption text-medium-emphasis mb-2">{{ field.description }}</div>

                    <!-- 布尔字段 -->
                    <v-select
                      v-if="field.type === 'boolean'"
                      :model-value="getNestedValue(editableObject, field.path) ? 'true' : 'false'"
                      @update:model-value="(val: string) => handleVisualFieldChange(field.path, val)"
                      :items="[{ title: 'true (启用)', value: 'true' }, { title: 'false (关闭)', value: 'false' }]"
                      density="compact"
                      variant="outlined"
                      hide-details
                    />

                    <!-- 敏感字段（Token/密码） -->
                    <v-text-field
                      v-else-if="field.type === 'secret'"
                      :model-value="getNestedValue(editableObject, field.path) || ''"
                      @update:model-value="(val: string) => handleVisualFieldChange(field.path, val)"
                      :placeholder="getNestedValue(editableObject, field.path) ? '●●●●●●●●' : '未设置'"
                      :type="showSecretFields[field.key] ? 'text' : 'password'"
                      :append-inner-icon="showSecretFields[field.key] ? 'mdi-eye-off' : 'mdi-eye'"
                      density="compact"
                      variant="outlined"
                      hide-details
                      @click:append-inner="showSecretFields[field.key] = !showSecretFields[field.key]"
                    />

                    <!-- URL 字段 -->
                    <v-text-field
                      v-else-if="field.type === 'url'"
                      :model-value="getNestedValue(editableObject, field.path) || ''"
                      @update:model-value="(val: string) => handleVisualFieldChange(field.path, val)"
                      :placeholder="String(field.default || '')"
                      prepend-inner-icon="mdi-link-variant"
                      density="compact"
                      variant="outlined"
                      hide-details
                    />

                    <!-- 多选字段（逗号分隔字符串 → v-chip-group 多选） -->
                    <template v-else-if="field.type === 'multiselect'">
                      <v-chip-group
                        :model-value="getMultiSelectValue(field.path)"
                        @update:model-value="(val: string[]) => handleVisualFieldChange(field.path, val)"
                        column
                        multiple
                      >
                        <v-chip
                          v-for="opt in field.options"
                          :key="opt.value"
                          :value="opt.value"
                          variant="outlined"
                          size="small"
                          filter
                        >
                          {{ opt.title }}
                        </v-chip>
                      </v-chip-group>
                    </template>

                    <!-- 普通字符串字段 -->
                    <v-text-field
                      v-else
                      :model-value="getNestedValue(editableObject, field.path) || ''"
                      @update:model-value="(val: string) => handleVisualFieldChange(field.path, val)"
                      :placeholder="String(field.default || '')"
                      density="compact"
                      variant="outlined"
                      hide-details
                    />
                  </v-card>
                </v-col>
              </v-row>
            </template>

            <!-- 无可视化字段 -->
            <div v-else class="text-center pa-6">
              <v-icon size="48" color="grey-lighten-1" class="mb-2">mdi-form-textbox</v-icon>
              <p class="text-medium-emphasis">此页面暂无可视化编辑字段</p>
              <p class="text-caption text-medium-emphasis">请切换到 JSON 模式进行编辑</p>
            </div>
          </template>

          <!-- JSON 编辑 -->
          <template v-else>
            <v-textarea
              v-model="editableJsonConfig"
              auto-grow
              variant="outlined"
              rows="10"
              label="配置 JSON"
              hint="直接编辑 JSON 配置，保存后将写入神医插件配置文件"
              persistent-hint
              @update:model-value="handleJsonChange"
            />
          </template>
        </v-card-text>
      </v-card>
    </template>
  </v-container>
</template>
