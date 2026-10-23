<script setup lang="ts">
import { ref, watch } from 'vue'
import { browsePath } from '@/api/settings'
import { useNotification } from '@/composables'

const props = defineProps<{
  modelValue: boolean
  title?: string
  currentPath?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [boolean]
  select: [string]
}>()

const { notify } = useNotification()

interface DirItem {
  name: string
  type: string
  path: string
}

const directories = ref<DirItem[]>([])
const isLoading = ref(false)
const selectedPath = ref('')
const manualPath = ref('')

const breadcrumbs = ref<{ name: string; path: string }[]>([])

watch(() => props.modelValue, (open) => {
  if (open) {
    const startPath = props.currentPath || '/'
    selectedPath.value = props.currentPath || ''
    manualPath.value = props.currentPath || ''
    loadDirectory(startPath)
  }
})

async function loadDirectory(path: string) {
  if (!path) path = '/'
  isLoading.value = true
  try {
    const items = await browsePath(path)
    directories.value = items
    manualPath.value = path
    updateBreadcrumbs(path)
  } catch (e: any) {
    notify('浏览失败', e.message || '无法读取路径', 'error')
    directories.value = []
  } finally {
    isLoading.value = false
  }
}

function updateBreadcrumbs(path: string) {
  const parts = path.split('/').filter(Boolean)
  breadcrumbs.value = [{ name: '根目录', path: '/' }]
  let acc = ''
  for (const part of parts) {
    acc += '/' + part
    breadcrumbs.value.push({ name: part, path: acc })
  }
}

function navigateTo(path: string) {
  loadDirectory(path)
}

function selectDir(item: DirItem) {
  selectedPath.value = item.path
  manualPath.value = item.path
}

function handleConfirm() {
  const finalPath = manualPath.value || selectedPath.value
  if (!finalPath) {
    notify('提示', '请选择或输入一个路径', 'warning')
    return
  }
  emit('select', finalPath)
  emit('update:modelValue', false)
}

function handleClose() {
  emit('update:modelValue', false)
}

async function handleManualNav() {
  if (manualPath.value) {
    await loadDirectory(manualPath.value)
    selectedPath.value = manualPath.value
  }
}
</script>

<template>
  <v-dialog :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)" max-width="700" scrollable>
    <v-card rounded="xl">
      <v-card-title class="d-flex align-center pa-4">
        <v-icon icon="mdi-folder-search" class="mr-2" />
        {{ title || '选择路径' }}
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="handleClose" />
      </v-card-title>

      <v-divider />

      <!-- 面包屑 + 路径输入 -->
      <div class="pa-4 pb-0">
        <div class="d-flex align-center flex-wrap ga-1 mb-3">
          <template v-for="(crumb, i) in breadcrumbs" :key="i">
            <v-btn
              size="x-small"
              variant="text"
              density="compact"
              class="text-caption px-1"
              @click="navigateTo(crumb.path)"
            >
              {{ crumb.name }}
            </v-btn>
            <v-icon v-if="i < breadcrumbs.length - 1" size="x-small" class="text-disabled">mdi-chevron-right</v-icon>
          </template>
        </div>

        <v-text-field
          v-model="manualPath"
          placeholder="输入路径..."
          density="compact"
          variant="outlined"
          prepend-inner-icon="mdi-folder"
          clearable
          @keyup.enter="handleManualNav"
        >
          <template #append-inner>
            <v-btn size="x-small" variant="tonal" color="primary" @click="handleManualNav" :loading="isLoading">前往</v-btn>
          </template>
        </v-text-field>
      </div>

      <!-- 目录列表 -->
      <v-card-text class="scroll-y-400 pt-0">
        <v-progress-circular v-if="isLoading" indeterminate color="primary" size="32" class="d-block mx-auto mt-8" />

        <v-list v-else-if="directories.length" density="compact" class="pa-0">
          <v-list-item
            v-for="item in directories"
            :key="item.path"
            @click="selectDir(item)"
            @dblclick="navigateTo(item.path)"
            :class="{ 'bg-primary-lighten-5': selectedPath === item.path }"
            rounded="xl"
            class="mb-1"
          >
            <template #prepend>
              <v-icon color="amber-darken-2">mdi-folder</v-icon>
            </template>
            <v-list-item-title class="text-body-2 font-weight-medium">{{ item.name }}</v-list-item-title>
            <v-list-item-subtitle class="text-caption">{{ item.path }}</v-list-item-subtitle>
            <template #append>
              <v-icon v-if="selectedPath === item.path" color="primary" size="small">mdi-check-circle</v-icon>
            </template>
          </v-list-item>
        </v-list>

        <div v-else class="text-center text-medium-emphasis pa-8">
          <v-icon size="48" color="grey-lighten-1" class="mb-2">mdi-folder-off</v-icon>
          <p>此目录下没有子文件夹</p>
        </div>
      </v-card-text>

      <v-divider />
      <v-card-actions class="pa-4">
        <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="handleClose">取消</v-btn>
        <v-spacer />
        <v-btn color="primary" variant="tonal" prepend-icon="mdi-check" :disabled="!selectedPath && !manualPath" @click="handleConfirm">确定选择</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
