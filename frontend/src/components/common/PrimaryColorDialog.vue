<script setup lang="ts">
/**
 * PrimaryColorDialog — 主题色切换对话框
 *
 * 参考 GlassSettingsDialog 的结构，提供 12 种预设主题色选择。
 * 主题色不分白天/夜晚模式，切换后立即生效并持久化。
 */
import { ref, computed, watch } from 'vue'
import { useThemeCustomizer, themeCustomizerPrimaryColors } from '@/composables/useThemeCustomizer'
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
const { settings, setPrimaryColor } = useThemeCustomizer()

// 当前选中的颜色（实时响应）
const currentPrimaryColor = computed(() => settings.value.primaryColor)

// 色盘开关 — 是否显示自定义颜色输入
const showCustomPicker = ref(false)
const customColor = ref(settings.value.primaryColor)

watch(
  () => props.modelValue,
  (value) => {
    if (value) {
      customColor.value = settings.value.primaryColor
      showCustomPicker.value = false
    }
  },
  { immediate: true },
)

const visible = computed({
  get: () => props.modelValue,
  set: (value) => {
    emit('update:modelValue', value)
    if (!value) emit('close')
  },
})

/** 选择预设颜色 — 立即应用并持久化 */
function selectColor(color: string) {
  setPrimaryColor(color)
  customColor.value = color
}

/** 应用自定义颜色 */
function applyCustomColor() {
  if (/^#[\da-f]{6}$/i.test(customColor.value)) {
    selectColor(customColor.value)
  }
}

/** 判断颜色是否深色，用于决定文字颜色 */
function isLightColor(hex: string): boolean {
  if (!/^#[\da-f]{6}$/i.test(hex)) return false
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  // 相对亮度公式
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
  return luminance > 0.6
}
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
        <VIcon icon="mdi-palette" class="me-2" />
        主题色
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
        <!-- 预设颜色网格 -->
        <section>
          <h3 class="appearance-dialog__label">预设颜色</h3>
          <div class="primary-color-dialog__grid">
            <button
              v-for="color in themeCustomizerPrimaryColors"
              :key="color.value"
              type="button"
              class="primary-color-dialog__swatch"
              :class="{ 'primary-color-dialog__swatch--active': currentPrimaryColor.toLowerCase() === color.value.toLowerCase() }"
              :style="{
                backgroundColor: color.value,
                color: isLightColor(color.value) ? '#333' : '#fff',
              }"
              :title="color.name"
              @click="selectColor(color.value)"
            >
              <VIcon
                v-if="currentPrimaryColor.toLowerCase() === color.value.toLowerCase()"
                icon="mdi-check"
                size="18"
              />
            </button>
          </div>
          <p class="appearance-dialog__hint">
            点击颜色块即可切换主题色。主题色不会因深色/浅色模式切换而改变。
          </p>
        </section>

        <!-- 自定义颜色 -->
        <section>
          <div class="primary-color-dialog__custom-header">
            <h3 class="appearance-dialog__label">自定义颜色</h3>
            <VBtn
              variant="text"
              size="small"
              :prepend-icon="showCustomPicker ? 'mdi-chevron-up' : 'mdi-chevron-down'"
              @click="showCustomPicker = !showCustomPicker"
            >
              {{ showCustomPicker ? '收起' : '展开' }}
            </VBtn>
          </div>
          <div v-if="showCustomPicker" class="primary-color-dialog__custom">
            <input
              v-model="customColor"
              type="color"
              class="primary-color-dialog__color-input"
              @input="applyCustomColor"
            />
            <VTextField
              v-model="customColor"
              label="HE 颜色值"
              variant="outlined"
              density="compact"
              hide-details
              class="primary-color-dialog__color-text"
              @blur="applyCustomColor"
              @keyup.enter="applyCustomColor"
            />
            <div
              class="primary-color-dialog__preview"
              :style="{ backgroundColor: customColor }"
            />
          </div>
        </section>

        <!-- 当前选中预览 -->
        <section class="appearance-dialog__current">
          <div class="primary-color-dialog__current-swatch" :style="{ backgroundColor: currentPrimaryColor }" />
          <div class="appearance-dialog__current-info">
            <span class="appearance-dialog__current-label">当前主题色</span>
            <span class="appearance-dialog__current-value">{{ currentPrimaryColor.toUpperCase() }}</span>
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
/* 骨架样式统一管理在 styles/appearance-dialogs.css；
   此处保留主色对话框独有规则与共享类的差异覆盖 */
.primary-color-dialog__grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 10px;
}

.primary-color-dialog__swatch {
  display: flex;
  align-items: center;
  justify-content: center;
  block-size: 44px;
  inline-size: 100%;
  border: 2px solid transparent;
  border-radius: 12px;
  cursor: pointer;
  outline: none;
  padding: 0;
  transition: transform 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;

  &:hover {
    transform: scale(1.08);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  }

  &--active {
    border-color: rgba(var(--v-theme-on-surface), 0.8);
    box-shadow: 0 0 0 3px rgba(var(--v-theme-surface), 0.6), 0 4px 12px rgba(0, 0, 0, 0.2);
  }
}

.primary-color-dialog__custom-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;

  .appearance-dialog__label {
    margin-block-end: 0;
  }
}

.primary-color-dialog__custom {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-block-start: 12px;
}

.primary-color-dialog__color-input {
  block-size: 40px;
  inline-size: 40px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 8px;
  cursor: pointer;
  padding: 2px;
  background: transparent;

  &::-webkit-color-swatch-wrapper {
    padding: 0;
  }

  &::-webkit-color-swatch {
    border: none;
    border-radius: 6px;
  }
}

.primary-color-dialog__color-text {
  flex: 1;
}

.primary-color-dialog__preview {
  block-size: 40px;
  inline-size: 40px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 8px;
}

.primary-color-dialog__current-swatch {
  block-size: 36px;
  inline-size: 36px;
  border-radius: 10px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
}

/* 当前值展示的是 hex 色值，用 on-surface 而非全局的 primary 强调色 */
.appearance-dialog__current-value {
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.9rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
</style>
