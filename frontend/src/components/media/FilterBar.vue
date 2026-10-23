<script setup lang="ts">
import { computed, ref, onUnmounted } from 'vue'
import { useItemStore } from '@/stores'

const store = useItemStore()
const showFilterDialog = ref(false)

const sourceOptions = [
  { title: '所有来源', value: null },
  { title: 'Primary', value: 'primary' },
  { title: 'Override', value: 'override' },
]

const sortOptions = [
  { title: '日期降序', value: 'date_desc' },
  { title: '日期升序', value: 'date_asc' },
  { title: '名称 A-Z', value: 'name_asc' },
  { title: '名称 Z-A', value: 'name_desc' },
]

const genreOptions = computed(() => [
  { title: '所有类型', value: null },
  ...store.availableGenres.map((g: string) => ({ title: g, value: g })),
])

const yearOptions = computed(() => [
  { title: '所有年份', value: null },
  ...store.availableYears.map((y: string) => ({ title: String(y), value: y })),
])

const monthOptions = [
  { title: '月份', value: null },
  ...Array.from({ length: 12 }, (_, i) => ({ title: `${i + 1}月`, value: String(i + 1) })),
]

const posterOptions = [
  { title: '海报状态', value: null },
  { title: '有海报', value: 'yes' },
  { title: '无海报', value: 'no' },
]

let debounceTimer: ReturnType<typeof setTimeout> | null = null

function handleSearchInput(value: string) {
  store.searchTerm = value
  clearTimeout(debounceTimer!)
  debounceTimer = setTimeout(() => store.applyFilters(), 400)
}

onUnmounted(() => {
  if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null }
})

// 是否有活跃的筛选条件（不含搜索）
const hasActiveFilters = computed(() =>
  !!store.selectedGenre || !!store.selectedYear || !!store.selectedMonth ||
  !!store.selectedSource || !!store.selectedPosterStatus || store.sortBy !== 'date_desc'
)

// 活跃筛选条件数量
const activeFilterCount = computed(() => {
  let count = 0
  if (store.selectedGenre) count++
  if (store.selectedYear) count++
  if (store.selectedMonth) count++
  if (store.selectedSource) count++
  if (store.selectedPosterStatus) count++
  if (store.sortBy !== 'date_desc') count++
  return count
})

function handleApplyFilters() {
  store.applyFilters()
  showFilterDialog.value = false
}

function handleResetFilters() {
  store.resetFilters(true)
  showFilterDialog.value = false
}
</script>

<template>
  <div class="mb-4">
    <!-- 搜索栏 + 高级筛选按钮 -->
    <v-row align="center" density="compact">
      <!-- 搜索框 -->
      <v-col cols="12" sm="8" md="9" lg="10">
        <v-text-field
          :model-value="store.searchTerm"
          @update:model-value="handleSearchInput"
          placeholder="搜索名称..."
          prepend-inner-icon="mdi-magnify"
          clearable
          density="compact"
          variant="outlined"
          hide-details
          rounded="xl"
        />
      </v-col>

      <!-- 高级筛选按钮 -->
      <v-col cols="12" sm="4" md="3" lg="2" class="d-flex ga-2">
        <v-btn
          variant="tonal"
          :color="hasActiveFilters ? 'primary' : 'default'"
          prepend-icon="mdi-filter-variant"
          @click="showFilterDialog = true"
          :class="{ 'filter-btn-active': hasActiveFilters }"
        >
          高级筛选
          <v-badge
            v-if="activeFilterCount > 0"
            :content="activeFilterCount"
            floating
            color="primary"
            size="x-small"
            class="ml-1"
          />
        </v-btn>
        <v-btn
          v-if="hasActiveFilters"
          variant="tonal"
          size="small"
          color="grey"
          icon="mdi-filter-remove"
          @click="handleResetFilters"
        />
      </v-col>
    </v-row>

    <!-- 筛选状态标签 -->
    <div v-if="store.searchTerm || store.selectedGenre || store.selectedYear || store.selectedMonth || store.selectedSource || store.selectedPosterStatus" class="d-flex flex-wrap ga-1 mt-2">
      <v-chip v-if="store.searchTerm" size="small" closable @click:close="store.searchTerm = ''; store.applyFilters()" variant="tonal" label>
        <v-icon start size="x-small">mdi-magnify</v-icon>{{ store.searchTerm }}
      </v-chip>
      <v-chip v-if="store.selectedGenre" size="small" closable @click:close="store.selectedGenre = null; store.applyFilters()" variant="tonal" label>类型: {{ store.selectedGenre }}</v-chip>
      <v-chip v-if="store.selectedYear" size="small" closable @click:close="store.selectedYear = null; store.applyFilters()" variant="tonal" label>年份: {{ store.selectedYear }}</v-chip>
      <v-chip v-if="store.selectedMonth" size="small" closable @click:close="store.selectedMonth = null; store.applyFilters()" variant="tonal" label>{{ store.selectedMonth }}月</v-chip>
      <v-chip v-if="store.selectedSource" size="small" closable @click:close="store.selectedSource = null; store.applyFilters()" variant="tonal" label>来源: {{ store.selectedSource }}</v-chip>
      <v-chip v-if="store.selectedPosterStatus" size="small" closable @click:close="store.selectedPosterStatus = null; store.applyFilters()" variant="tonal" label>海报: {{ store.selectedPosterStatus === 'yes' ? '有' : '无' }}</v-chip>
    </div>

    <!-- 高级筛选弹框 -->
    <v-dialog v-model="showFilterDialog" max-width="560" scrollable>
      <v-card rounded="xl">
        <v-card-title class="d-flex align-center">
          <v-icon icon="mdi-filter-variant" class="mr-2" />
          高级筛选
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="showFilterDialog = false" />
        </v-card-title>
        <v-divider />

        <v-card-text class="pt-4">
          <v-row density="compact">
            <!-- 类型筛选 -->
            <v-col cols="12" sm="6">
              <v-select
                v-model="store.selectedGenre"
                :items="genreOptions"
                item-title="title"
                item-value="value"
                label="类型"
                density="compact"
                variant="outlined"
              />
            </v-col>

            <!-- 来源筛选 -->
            <v-col cols="12" sm="6">
              <v-select
                v-model="store.selectedSource"
                :items="sourceOptions"
                item-title="title"
                item-value="value"
                label="来源"
                density="compact"
                variant="outlined"
              />
            </v-col>

            <!-- 年份筛选 -->
            <v-col cols="12" sm="6">
              <v-select
                v-model="store.selectedYear"
                :items="yearOptions"
                item-title="title"
                item-value="value"
                label="年份"
                density="compact"
                variant="outlined"
              />
            </v-col>

            <!-- 月份筛选 -->
            <v-col cols="12" sm="6">
              <v-select
                v-model="store.selectedMonth"
                :items="monthOptions"
                item-title="title"
                item-value="value"
                label="月份"
                density="compact"
                variant="outlined"
              />
            </v-col>

            <!-- 海报状态 -->
            <v-col cols="12" sm="6">
              <v-select
                v-model="store.selectedPosterStatus"
                :items="posterOptions"
                item-title="title"
                item-value="value"
                label="海报状态"
                density="compact"
                variant="outlined"
              />
            </v-col>

            <!-- 排序 -->
            <v-col cols="12" sm="6">
              <v-select
                v-model="store.sortBy"
                :items="sortOptions"
                item-title="title"
                item-value="value"
                label="排序方式"
                density="compact"
                variant="outlined"
              />
            </v-col>
          </v-row>
        </v-card-text>

        <v-divider />
        <v-card-actions class="pa-4">
          <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="showFilterDialog = false">取消</v-btn>
          <v-spacer />
          <v-btn variant="tonal" color="warning" prepend-icon="mdi-filter-remove" @click="handleResetFilters">重置</v-btn>
          <v-btn color="primary" variant="tonal" prepend-icon="mdi-check" @click="handleApplyFilters">应用筛选</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>
