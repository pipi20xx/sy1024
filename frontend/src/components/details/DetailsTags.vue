<script setup lang="ts">
import { ref, computed } from 'vue'
import { useDetailsStore } from '@/stores'
import { useNotification, useConfirm } from '@/composables'

const store = useDetailsStore()
const { notify } = useNotification()
const { confirm } = useConfirm()

const tags = computed(() => store.itemDetails?.tags || [])

// 规则标签生成弹框
const showRuleDialog = ref(false)
const ruleMode = ref<'merge' | 'overwrite'>('merge')

// BGM 标签生成弹框
const showBgmDialog = ref(false)
const bgmMode = ref<'merge' | 'overwrite'>('merge')
const bgmUseWhitelist = ref(false)

function openRuleDialog() {
  ruleMode.value = 'merge'
  showRuleDialog.value = true
}

async function handleGenerateTags() {
  showRuleDialog.value = false
  const success = await store.generateTags(ruleMode.value)
  if (success) notify('标签生成成功', '', 'success')
  else notify('生成失败，请检查标签规则配置', '', 'error')
}

function openBgmDialog() {
  bgmMode.value = 'merge'
  bgmUseWhitelist.value = false
  showBgmDialog.value = true
}

async function handleGenerateTagsFromBgm() {
  showBgmDialog.value = false
  const success = await store.generateTagsFromBgm(bgmMode.value, bgmUseWhitelist.value)
  if (success) notify('BGM 标签生成成功', '', 'success')
  else notify('生成失败，请检查是否已关联 Bangumi ID', '', 'error')
}

async function handleDeleteTags() {
  const ok = await confirm({
    title: '删除标签文件',
    content: '将删除 Override 目录下的 tags.json。此操作不可恢复！',
    confirmColor: 'error',
  })
  if (!ok) return
  const success = await store.deleteTags()
  if (success) notify('标签已删除', '', 'success')
  else notify('删除失败', '', 'error')
}
</script>

<template>
  <v-container fluid>
    <div class="d-flex flex-wrap ga-2 mb-4">
      <v-btn size="small" variant="tonal" color="primary" @click="openRuleDialog" :loading="store.isLoading" prepend-icon="mdi-tag-plus">自动生成标签</v-btn>
      <v-btn size="small" variant="tonal" color="info" @click="openBgmDialog" :loading="store.isLoading" prepend-icon="mdi-tag-heart">从 BGM 生成标签</v-btn>
      <v-btn size="small" variant="tonal" color="error" @click="handleDeleteTags" :loading="store.isLoading" prepend-icon="mdi-delete">删除标签文件</v-btn>
    </div>

    <v-sheet v-if="tags.length" class="pa-4" rounded border>
      <div class="d-flex flex-wrap ga-2">
        <v-chip v-for="tag in tags" :key="tag" size="small" variant="tonal" label prepend-icon="mdi-tag">{{ tag }}</v-chip>
      </div>
    </v-sheet>

    <v-alert v-else type="info" variant="tonal" class="text-center">
      <v-icon size="48" class="mb-2">mdi-tag-off-outline</v-icon>
      <div>暂无标签</div>
      <div class="text-caption">点击"自动生成标签"根据规则生成，或"从 BGM 生成标签"从 Bangumi 获取</div>
    </v-alert>

    <!-- 规则标签生成对话框 -->
    <v-dialog v-model="showRuleDialog" max-width="420" scrollable>
      <v-card rounded="xl">
        <v-card-title class="d-flex align-center">
          <v-icon icon="mdi-tag-plus" class="mr-2" />
          自动生成标签
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="showRuleDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <p class="text-body-2 text-medium-emphasis mb-4">根据元数据（国家、类型、年份等）和标签规则自动生成标签</p>

          <div class="text-subtitle-2 font-weight-bold mb-2">写入模式</div>
          <v-radio-group v-model="ruleMode" density="compact">
            <v-radio label="合并 - 保留已有标签，追加新标签" value="merge" />
            <v-radio label="覆盖 - 替换所有标签" value="overwrite" />
          </v-radio-group>
        </v-card-text>
        <v-divider />
        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="showRuleDialog = false">取消</v-btn>
          <v-btn color="primary" variant="tonal" prepend-icon="mdi-check" :loading="store.isLoading" @click="handleGenerateTags">开始生成</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- BGM 标签生成对话框 -->
    <v-dialog v-model="showBgmDialog" max-width="420" scrollable>
      <v-card rounded="xl">
        <v-card-title class="d-flex align-center">
          <v-icon icon="mdi-tag-heart" class="mr-2" />
          从 BGM 生成标签
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="showBgmDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <p class="text-body-2 text-medium-emphasis mb-4">从已关联的 Bangumi 条目获取标签并写入 tags.json</p>

          <div class="text-subtitle-2 font-weight-bold mb-2">写入模式</div>
          <v-radio-group v-model="bgmMode" density="compact">
            <v-radio label="合并 - 保留已有标签，追加新标签" value="merge" />
            <v-radio label="覆盖 - 替换所有标签" value="overwrite" />
          </v-radio-group>

          <v-divider class="my-3" />

          <v-checkbox v-model="bgmUseWhitelist" label="使用全局标签白名单过滤" density="compact" hide-details />
          <p class="text-caption text-medium-emphasis ml-8">仅保留白名单中的标签，白名单在 Bangumi 同步配置中管理</p>
        </v-card-text>
        <v-divider />
        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="showBgmDialog = false">取消</v-btn>
          <v-btn color="info" variant="tonal" prepend-icon="mdi-check" :loading="store.isLoading" @click="handleGenerateTagsFromBgm">开始生成</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>
