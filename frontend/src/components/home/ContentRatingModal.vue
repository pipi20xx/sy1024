<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { api } from '@/api/client'
import { useNotification } from '@/composables'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [boolean] }>()

const { notify } = useNotification()

const isVisible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const loading = ref(false)
const saving = ref(false)
const activeTab = ref('movies_jp')

const files = ref<Record<string, string>>({
  movies_jp: '',
  movies_us: '',
  tv_jp: '',
  tv_us: '',
})

const tabConfig = [
  { value: 'movies_jp', title: '电影 - 日本 (JP)' },
  { value: 'movies_us', title: '电影 - 美国 (US)' },
  { value: 'tv_jp', title: '剧集 - 日本 (JP)' },
  { value: 'tv_us', title: '剧集 - 美国 (US)' },
]

watch(() => props.modelValue, (newVal) => {
  if (newVal) fetchData()
})

async function fetchData() {
  loading.value = true
  try {
    const data = await api.get<Record<string, string>>('/api/system/rating-files')
    // 如果返回空对象，给默认空格式
    for (const key of Object.keys(files.value)) {
      const val = data[key] || '{}'
      files.value[key] = val === '{}' ? '{\n\n}' : val
    }
  } catch (e: any) {
    notify('加载失败', e.message, 'error')
  } finally {
    loading.value = false
  }
}

async function handleSave() {
  // 验证 JSON 格式
  for (const [key, val] of Object.entries(files.value)) {
    try {
      JSON.parse(val || '{}')
    } catch {
      const tabLabel = tabConfig.find(t => t.value === key)?.title || key
      notify('JSON 格式错误', `${tabLabel} 的内容不是有效的 JSON`, 'error')
      activeTab.value = key
      return
    }
  }

  saving.value = true
  try {
    await api.post('/api/system/rating-files', files.value)
    notify('保存成功', '重启服务后生效', 'success')
    isVisible.value = false
  } catch (e: any) {
    notify('保存失败', e.message, 'error')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <v-dialog v-model="isVisible" max-width="800" scrollable>
    <v-card rounded="xl">
      <!-- 标题栏 -->
      <v-card-title class="d-flex align-center">
        <v-icon icon="mdi shield-star" class="mr-2" />
        内容分级管理
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="isVisible = false" />
      </v-card-title>
      <v-divider />

      <!-- Tab 导航栏 — 在卡片内容区外面，固定不被挤走 -->
      <template v-if="!loading">
        <v-tabs v-model="activeTab" density="compact" show-arrows>
          <v-tab v-for="tab in tabConfig" :key="tab.value" :value="tab.value">{{ tab.title }}</v-tab>
        </v-tabs>
        <v-divider />
      </template>

      <!-- 内容区 -->
      <v-card-text class="pt-4">
        <v-alert type="info" variant="tonal" density="compact" class="mb-4">
          在此处编辑分级映射 JSON 文件。修改完成后点击保存，重启服务后生效。
        </v-alert>

        <div v-if="loading" class="text-center pa-8">
          <v-progress-circular indeterminate color="primary" />
        </div>

        <template v-else>
          <v-window v-model="activeTab">
            <v-window-item v-for="tab in tabConfig" :key="tab.value" :value="tab.value">
              <v-textarea v-model="files[tab.value]" variant="outlined" density="compact"
                placeholder='{ "G": "JP-G", ... }'
                auto-grow rows="10" class="font-mono" hide-details />
            </v-window-item>
          </v-window>
        </template>
      </v-card-text>

      <v-divider />
      <v-card-actions class="pa-4">
        <v-spacer />
        <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="isVisible = false">取消</v-btn>
        <v-btn color="primary" variant="tonal" :loading="saving" prepend-icon="mdi-content-save" @click="handleSave">
          保存
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
