<script setup lang="ts">
/**
 * BorderRadiusDialog — 圆角切换对话框
 *
 * 参考 PrimaryColorDialog 的结构，提供 5 种圆角预设。
 * 切换后立即生效并持久化，不受白天/夜晚模式影响。
 */
import { computed, ref, watch } from 'vue'
import { useThemeCustomizer, type ThemeCustomizerRadius } from '@/composables/useThemeCustomizer'
import { useDisplay } from 'vuetify'

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
}>()

const display = useDisplay()
const { settings, setRadius } = useThemeCustomizer()

const currentRadius = computed(() => settings.value.radius)

const visible = computed({
  get: () => props.modelValue,
  set: (value) => {
    emit('update:modelValue', value)
    if (!value) emit('close')
  },
})

interface RadiusOption {
  value: ThemeCustomizerRadius
  label: string
  hint: string
  icon: string
  /** 预览方块的圆角 px */
  previewRadius: string
}

const radiusOptions: RadiusOption[] = [
  { value: 'none', label: '无圆角', hint: '所有组件直角', icon: 'mdi-square-outline', previewRadius: '0px' },
  { value: 'small', label: '小圆角', hint: '4-8px 轻微圆角', icon: 'mdi-square-rounded-outline', previewRadius: '6px' },
  { value: 'default', label: '默认', hint: '保持各主题原生圆角', icon: 'mdi-square-rounded', previewRadius: '16px' },
  { value: 'large', label: '大圆角', hint: '20-28px 明显圆角', icon: 'mdi-square-rounded', previewRadius: '24px' },
  { value: 'extra', label: '更大圆角', hint: '28-36px 夸张圆角', icon: 'mdi-circle-outline', previewRadius: '32px' },
]

/** 用于自定义滑块的映射（0=none, 1=small, 2=default, 3=large, 4=extra） */
const radiusSliderValue = ref(2)

watch(
  () => props.modelValue,
  (value) => {
    if (value) {
      const idx = radiusOptions.findIndex(o => o.value === currentRadius.value)
      radiusSliderValue.value = idx >= 0 ? idx : 2
    }
  },
  { immediate: true },
)

function selectRadius(value: ThemeCustomizerRadius) {
  setRadius(value)
  const idx = radiusOptions.findIndex(o => o.value === value)
  if (idx >= 0) radiusSliderValue.value = idx
}

function onSliderChange(value: number) {
  const option = radiusOptions[value]
  if (option) selectRadius(option.value)
}

const currentOption = computed(() => radiusOptions.find(o => o.value === currentRadius.value) ?? radiusOptions[2])
</script>

<template>
  <VDialog
    v-model="visible"
    width="100%"
    max-width="32rem"
    scrollable
    :fullscreen="display.smAndDown.value"
  >
    <VCard>
      <VCardTitle class="d-flex align-center pa-4">
        <VIcon icon="mdi-border-radius" class="me-2" />
        圆角
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
        <!-- 预设选项 -->
        <section>
          <h3 class="appearance-dialog__label">圆角样式</h3>
          <div class="appearance-dialog__grid">
            <button
              v-for="option in radiusOptions"
              :key="option.value"
              type="button"
              class="appearance-dialog__option"
              :class="{ 'appearance-dialog__option--active': currentRadius === option.value }"
              @click="selectRadius(option.value)"
            >
              <div
                class="appearance-dialog__preview"
                :style="{ borderRadius: option.previewRadius }"
              >
                <VIcon :icon="option.icon" size="20" />
              </div>
              <span class="appearance-dialog__option-label">{{ option.label }}</span>
            </button>
          </div>
          <p class="appearance-dialog__hint">
            点击预设即可切换圆角。圆角设置不会因深色/浅色模式切换而改变。
          </p>
        </section>

        <!-- 滑块调整 -->
        <section>
          <div class="appearance-dialog__slider-header">
            <h3 class="appearance-dialog__label">快速调整</h3>
            <span class="appearance-dialog__current-value">{{ currentOption.label }}</span>
          </div>
          <div class="appearance-dialog__slider-wrapper">
            <VSlider
              v-model="radiusSliderValue"
              :min="0"
              :max="4"
              :step="1"
              color="primary"
              show-ticks
              thumb-label
              @update:model-value="onSliderChange"
            >
              <template #thumb-label="{ modelValue }">
                {{ radiusOptions[modelValue]?.label ?? '' }}
              </template>
            </VSlider>
          </div>
          <div class="appearance-dialog__tick-labels">
            <span
              v-for="option in radiusOptions"
              :key="option.value"
              class="appearance-dialog__tick-label"
            >{{ option.label }}</span>
          </div>
        </section>

        <!-- 当前选中预览 -->
        <section class="appearance-dialog__current">
          <div
            class="appearance-dialog__current-preview"
            :style="{ borderRadius: currentOption.previewRadius }"
          />
          <div class="appearance-dialog__current-info">
            <span class="appearance-dialog__current-label">当前圆角</span>
            <span class="appearance-dialog__current-text">{{ currentOption.label }}</span>
            <span class="appearance-dialog__current-hint">{{ currentOption.hint }}</span>
          </div>
        </section>
      </VCardText>

      <VDivider />
      <VCardActions class="appearance-dialog__actions justify-center">
        <VBtn
          :slim="false"
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
/* 骨架样式统一管理在 styles/appearance-dialogs.css，此处只保留圆角预览的差异部分 */
.appearance-dialog__preview {
  border: 1.5px solid rgba(var(--v-theme-on-surface), 0.2);
  transition: border-radius 0.2s ease;
}

.appearance-dialog__current-preview {
  border: 2px solid rgba(var(--v-theme-on-surface), 0.15);
  transition: border-radius 0.2s ease;
}
</style>
