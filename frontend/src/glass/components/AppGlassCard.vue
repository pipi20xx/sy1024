<script setup lang="ts">
/**
 * AppGlassCard — 通用 Liquid Glass 风格卡片
 *
 * Props:
 *  - title: 卡片标题 (可选)
 *  - subtitle: 副标题 (可选)
 *  - icon: 标题图标 (可选)
 *  - fillHeight: 是否撑满高度 (默认 true)
 *
 * Slots:
 *  - default: 卡片主体内容
 *  - actions: 底部操作区
 */
defineOptions({ name: 'AppGlassCard' })

withDefaults(defineProps<{
  title?: string
  subtitle?: string
  icon?: string
  fillHeight?: boolean
}>(), {
  title: '',
  subtitle: '',
  icon: '',
  fillHeight: true,
})
</script>

<template>
  <v-card class="glass-card" :class="fillHeight ? 'fill-height' : ''">
    <v-card-text v-if="title || $slots.header" class="pb-0">
      <div class="d-flex align-start justify-space-between">
        <div class="flex-grow-1 mr-2">
          <div v-if="title" class="d-flex align-center ga-2 mb-1">
            <v-icon v-if="icon" size="18" class="flex-shrink-0">{{ icon }}</v-icon>
            <span class="text-subtitle-2 font-weight-bold text-truncate">{{ title }}</span>
          </div>
          <div v-if="subtitle" class="text-caption text-medium-emphasis">{{ subtitle }}</div>
        </div>
        <slot name="header-actions" />
      </div>
      <slot name="header" />
    </v-card-text>

    <v-card-text :class="title ? 'pt-0 pb-2' : 'pa-0'">
      <slot />
    </v-card-text>

    <template v-if="$slots.actions">
      <v-divider />
      <v-card-actions class="pa-2">
        <slot name="actions" />
      </v-card-actions>
    </template>
  </v-card>
</template>
