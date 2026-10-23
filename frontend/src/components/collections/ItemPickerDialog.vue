<script setup lang="ts">
import { ref, watch } from 'vue'
import { useItemStore } from '@/stores'
import type { ItemSummary, ItemType } from '@/types'

export interface SelectedItem {
  id: string
  name: string
  type: ItemType
}

const props = defineProps<{
  modelValue: boolean
  initialSelectedItems?: SelectedItem[]
}>()

const emit = defineEmits<{
  'update:modelValue': [boolean]
  confirm: [SelectedItem[]]
}>()

const itemStore = useItemStore()
const searchQuery = ref('')
const searchType = ref<ItemType>('tmdb-tv')
const selectedMap = ref<Map<string, SelectedItem>>(new Map())

watch(() => props.modelValue, (newVal) => {
  if (newVal) {
    // 初始化已选
    selectedMap.value.clear()
    props.initialSelectedItems?.forEach(item => {
      selectedMap.value.set(String(item.id), item)
    })
    searchQuery.value = ''
    // 加载数据
    itemStore.searchTerm = ''
    itemStore.setCurrentItemType(searchType.value)
  }
})

async function handleSearch() {
  itemStore.searchTerm = searchQuery.value
  await itemStore.loadItems(searchType.value, 1)
}

function switchType(type: ItemType) {
  searchType.value = type
  itemStore.setCurrentItemType(type)
}

function toggleSelection(item: ItemSummary) {
  const idStr = String(item.id)
  if (selectedMap.value.has(idStr)) {
    selectedMap.value.delete(idStr)
  } else {
    selectedMap.value.set(idStr, {
      id: idStr,
      name: item.name,
      type: item.type,
    })
  }
}

function isSelected(id: string | number) {
  return selectedMap.value.has(String(id))
}

function handleConfirm() {
  emit('confirm', Array.from(selectedMap.value.values()))
  emit('update:modelValue', false)
}

function handleClose() {
  emit('update:modelValue', false)
}
</script>

<template>
  <v-dialog :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)" max-width="800" scrollable>
    <v-card rounded="xl">
      <v-card-title class="d-flex align-center pa-4">
        <v-icon icon="mdi-selection" class="mr-2" />
        选择媒体项目
        <v-chip size="small" variant="tonal" label class="ml-3">已选: {{ selectedMap.size }}</v-chip>
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="handleClose" />
      </v-card-title>

      <v-divider />

      <!-- 搜索控制 -->
      <div class="pa-4 pb-0">
        <v-btn-toggle v-model="searchType" mandatory density="compact" variant="outlined" class="mb-3" @update:model-value="switchType">
          <v-btn value="tmdb-tv" size="small">
            <v-icon start size="16">mdi-television</v-icon>
            电视剧
          </v-btn>
          <v-btn value="tmdb-movies2" size="small">
            <v-icon start size="16">mdi-movie</v-icon>
            电影
          </v-btn>
        </v-btn-toggle>

        <v-text-field
          v-model="searchQuery"
          placeholder="搜索名称..."
          density="compact"
          variant="outlined"
          prepend-inner-icon="mdi-magnify"
          clearable
          @keyup.enter="handleSearch"
        >
          <template #append-inner>
            <v-btn size="x-small" variant="tonal" color="primary" @click="handleSearch" :loading="itemStore.isLoading">搜索</v-btn>
          </template>
        </v-text-field>
      </div>

      <!-- 列表 -->
      <v-card-text class="scroll-y-500 pt-0">
        <v-progress-circular v-if="itemStore.isLoading && !itemStore.items.length" indeterminate color="primary" size="32" class="d-block mx-auto mt-8" />

        <v-list v-else-if="itemStore.items.length" density="compact" class="pa-0">
          <v-list-item
            v-for="item in itemStore.items"
            :key="item.id"
            @click="toggleSelection(item)"
            :class="{ 'bg-primary-lighten-5': isSelected(item.id) }"
            rounded="xl"
            class="mb-1"
          >
            <template #prepend>
              <v-checkbox :model-value="isSelected(item.id)" @click.stop @update:model-value="toggleSelection(item)" hide-details density="compact" class="mr-2" />
              <v-img
                v-if="item.poster_path"
                :src="item.poster_path"
                width="36"
                height="54"
                cover
                rounded="sm"
                class="mr-3 flex-shrink-0"
              >
                <template #error>
                  <div class="d-flex align-center justify-center fill-height bg-surface-variant">
                    <v-icon size="14" color="grey-lighten-1">mdi-image-off</v-icon>
                  </div>
                </template>
              </v-img>
              <v-sheet v-else width="36" height="54" rounded="sm" class="d-flex align-center justify-center bg-surface-variant mr-3 flex-shrink-0">
                <v-icon size="14" color="grey-lighten-1">mdi-image-off</v-icon>
              </v-sheet>
            </template>
            <v-list-item-title class="text-body-2 font-weight-medium">{{ item.name }}</v-list-item-title>
            <v-list-item-subtitle class="text-caption">{{ item.year }} · ID: {{ item.id }} · {{ item.type === 'tmdb-movies2' ? '电影' : '剧集' }}</v-list-item-subtitle>
          </v-list-item>
        </v-list>

        <div v-else class="text-center text-medium-emphasis pa-8">
          <v-icon size="48" color="grey-lighten-1" class="mb-2">mdi-magnify</v-icon>
          <p>未找到结果，请尝试搜索</p>
        </div>
      </v-card-text>

      <v-divider />
      <v-card-actions class="pa-4">
        <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="handleClose">取消</v-btn>
        <v-spacer />
        <v-btn color="primary" variant="tonal" @click="handleConfirm">
          确定选择 ({{ selectedMap.size }})
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
