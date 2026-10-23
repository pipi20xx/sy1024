<script setup lang="ts">
import { ref, watch, computed, defineAsyncComponent } from 'vue'
import { useRoute } from 'vue-router'
import { useTheme } from 'vuetify'
import { useThemeStore, useSystemStore, useAiStore } from '@/stores'
import { useGlassWallpaper } from '@/glass'
import { applyStoredThemeCustomizerAppearance, useThemeCustomizer } from '@/composables/useThemeCustomizer'
import {
  isChromiumFixedShellBackplateBrowser,
  provideGlassFixedShellBackplate,
  shouldUseGlassFixedShellBackplate,
  type GlassFixedShellBackplateLayer,
  DEFAULT_GLASS_WALLPAPER_TONE_PROFILE,
  loadGlassWallpaperTone,
  type GlassWallpaperToneProfile,
} from '@/glass'
import { createLoginBackgroundLayers, prepareLoginBackgroundLayer, activateLoginBackgroundLayer, settleLoginBackgroundLayers, type LoginBackgroundLayer } from '@/utils/loginPresentation'

const theme = useTheme()
const themeStore = useThemeStore()
const systemStore = useSystemStore()
const aiStore = useAiStore()
const route = useRoute()
const { settings: themeCustomizerSettings } = useThemeCustomizer()

// 玻璃光学层（异步加载，避免首屏阻塞）
const GlassOpticalLayer = defineAsyncComponent(() => import('@/glass/components/GlassOpticalLayer.vue'))

// 玻璃壁纸与光学设置
const glass = useGlassWallpaper()

// 登录状态 — sytmdb 用 localStorage token，路由变化时同步（登录/登出后立即生效）
const isLoggedIn = ref(false)
function syncLoginState() {
  isLoggedIn.value = Boolean(localStorage.getItem('access_token'))
}
syncLoginState()
watch(() => route.fullPath, syncLoginState)

// 壁纸背景层状态
const backgroundLayers = ref<LoginBackgroundLayer[]>(createLoginBackgroundLayers())
const backgroundToneProfiles = ref<Record<string, GlassWallpaperToneProfile>>({})
const backgroundDisplayImages = ref<Record<string, string>>({})
const backgroundCorsReady = ref<Record<string, boolean>>({})
const isBackgroundCrossfading = ref(false)
const backgroundCrossfadeStartedAt = ref(0)
const BACKGROUND_CROSSFADE_DURATION_MS = 1500

// 同步深色/浅色主题（Vuetify 内部）
function applyTheme(isDark: boolean) {
  const themeName = isDark ? 'dark' : 'light'
  if (typeof theme.change === 'function') {
    theme.change(themeName)
  } else {
    // Vuetify 3 回退方式
    theme.global.name.value = themeName
  }
}

// 在 <html> 上同步 dark/light class —— 给 CSS 变量用
function applyDarkClass(isDark: boolean) {
  const html = document.documentElement
  html.classList.toggle('glass-dark', isDark)
  html.classList.toggle('glass-light', !isDark)
}

// 同步玻璃主题 class 到 <html>（主题标识统一只挂 html，body 不再重复）
// data-theme 属性仅供 usePagePresentationMotion 等 TS 逻辑读取，CSS 一律用 glass-theme-xxx class
function applyGlassTheme(glassTheme: string) {
  const html = document.documentElement
  html.classList.remove('glass-theme-acg', 'glass-theme-liquid', 'glass-theme-classic')
  html.classList.add(`glass-theme-${glassTheme}`)

  if (glassTheme === 'acg') {
    html.setAttribute('data-theme', 'glass')
    // 应用玻璃定制外观设置
    applyStoredThemeCustomizerAppearance()
  } else if (glassTheme === 'liquid') {
    html.setAttribute('data-theme', 'transparent')
  } else {
    // classic
    html.removeAttribute('data-theme')
  }
}

applyTheme(themeStore.isDarkMode)
applyDarkClass(themeStore.isDarkMode)
applyGlassTheme(themeStore.glassTheme)

// 主题 = 风格 + 写死的明暗，整体切换
watch(() => themeStore.theme, () => {
  applyTheme(themeStore.isDarkMode)
  applyDarkClass(themeStore.isDarkMode)
  applyGlassTheme(themeStore.glassTheme)
})

// ── 主题色同步 ──
// CSS 变量由 useThemeCustomizer.applyThemeCustomizerRootSettings 写入 :root，
// 这里同步 Vuetify JS 侧的 theme 对象，确保 JS 逻辑（如 useTheme().current.value.colors.primary）也能读到最新值。
watch(() => themeCustomizerSettings.value.primaryColor, (primaryColor) => {
  theme.themes.value.light.colors.primary = primaryColor
  theme.themes.value.dark.colors.primary = primaryColor
}, { immediate: true })

// ── 壁纸背景层管理 ──────────────────────────────────────────

const isGlassTheme = computed(() => themeStore.glassTheme === 'acg')
const isBackdropTheme = computed(() => isGlassTheme.value || themeStore.glassTheme === 'liquid')
const shouldUseGlassBackgroundTreatment = computed(
  () => isGlassTheme.value && isLoggedIn.value,
)
const shouldLoadBackgroundImages = computed(
  () => isLoggedIn.value && isBackdropTheme.value,
)
const renderedBackgroundLayers = computed(() => backgroundLayers.value)
const activeBackgroundImage = computed(() => glass.wallpaperUrl.value)
const isBackgroundCrossfadingNow = computed(() => isBackgroundCrossfading.value)

/** 玻璃壁纸与 tone/WebGL 使用同一图片请求模式，避免 CSS 再创建无 Origin 的缓存变体。 */
function getBackgroundDisplayUrl(layer: LoginBackgroundLayer): string {
  // WebGL 使用的代理 URL 已经通过 CORS 代理，可以直接用于 CSS 背景
  return layer.url
}

/** 当 CORS 图片已就绪时使用 <img> 元素，否则用 CSS background-image。 */
function getBackgroundLayerImageSource(layer: LoginBackgroundLayer): string {
  return backgroundCorsReady.value[layer.url] ? getBackgroundDisplayUrl(layer) : ''
}

function getBackgroundLayerCrossOrigin(layer: LoginBackgroundLayer): 'anonymous' | undefined {
  return backgroundCorsReady.value[layer.url] ? 'anonymous' : undefined
}

// 壁纸层样式
function getBackgroundLayerStyle(layer: LoginBackgroundLayer) {
  const profile = backgroundToneProfiles.value[layer.url] ?? DEFAULT_GLASS_WALLPAPER_TONE_PROFILE
  const settings = glass.effectiveGlassSettings.value
  const displayUrl = getBackgroundDisplayUrl(layer)
  const usesCorsImageElement = Boolean(getBackgroundLayerImageSource(layer))

  let brightness: number
  if (settings.glassWallpaperBrightnessMode === 'manual') {
    brightness = settings.glassWallpaperBrightness
  } else {
    const materialExposure = settings.glassAppearance === 'frosted' ? 0.82 : settings.glassAppearance === 'tinted' ? 0.85 : 0.86
    brightness = materialExposure * profile.exposure
  }

  return {
    'backgroundImage': !usesCorsImageElement && displayUrl ? `url(${displayUrl})` : undefined,
    '--glass-wallpaper-brightness': String(brightness),
  }
}

/** 预加载壁纸：完成 CORS 可读性检查和 tone 分析，并同步到 DOM 层和 WebGL 层。 */
async function preloadWallpaperCandidate(proxyUrl: string) {
  if (!proxyUrl) return false

  try {
    const tone = await loadGlassWallpaperTone(proxyUrl)
    backgroundToneProfiles.value = {
      ...backgroundToneProfiles.value,
      [proxyUrl]: tone.profile,
    }
    if (tone.corsReady) {
      backgroundDisplayImages.value = {
        ...backgroundDisplayImages.value,
        [proxyUrl]: proxyUrl,
      }
      backgroundCorsReady.value = {
        ...backgroundCorsReady.value,
        [proxyUrl]: true,
      }
      return true
    }
    // CORS 不可读时仍然用 CSS background 显示
    backgroundDisplayImages.value = {
      ...backgroundDisplayImages.value,
      [proxyUrl]: proxyUrl,
    }
    backgroundCorsReady.value = {
      ...backgroundCorsReady.value,
      [proxyUrl]: false,
    }
    return false
  } catch {
    return false
  }
}

// 当壁纸 URL 变化时更新背景层
watch(activeBackgroundImage, async (newUrl, oldUrl) => {
  if (!newUrl) return
  if (newUrl === oldUrl) return

  // 先预加载壁纸（CORS 检查 + tone 分析）
  await preloadWallpaperCandidate(newUrl)

  // 触发交叉淡化
  backgroundLayers.value = prepareLoginBackgroundLayer(backgroundLayers.value, newUrl)
  isBackgroundCrossfading.value = true
  backgroundCrossfadeStartedAt.value = performance.now()

  // 延迟完成交叉淡化
  window.setTimeout(() => {
    backgroundLayers.value = activateLoginBackgroundLayer(backgroundLayers.value)
    backgroundLayers.value = settleLoginBackgroundLayers(backgroundLayers.value)
    isBackgroundCrossfading.value = false
  }, BACKGROUND_CROSSFADE_DURATION_MS)
}, { immediate: true })

// 当 WallpaperDialog 保存配置后触发的全局刷新信号
watch(() => glass.wallpaperRefreshSignal.value, (signal) => {
  if (signal > 0) {
    void glass.refreshWallpaper()
  }
})

// 当登录状态变化时，确保壁纸层有正确的 URL
watch(shouldUseGlassBackgroundTreatment, (shouldUse) => {
  if (shouldUse) {
    const currentUrl = activeBackgroundImage.value
    const activeLayer = backgroundLayers.value.find(l => l.role === 'active')
    if (currentUrl && (!activeLayer || !activeLayer.url)) {
      // 壁纸层还没有 URL，直接设置
      backgroundLayers.value = backgroundLayers.value.map(layer =>
        layer.role === 'active' ? { ...layer, url: currentUrl } : layer,
      )
      // 异步预加载
      void preloadWallpaperCandidate(currentUrl)
    }
  }
})

// ── Fixed Shell Backplate ──────────────────────────────────
const needsStableFixedBackdrop = isChromiumFixedShellBackplateBrowser()
const fixedShellBackplateLayers = computed<readonly GlassFixedShellBackplateLayer[]>(() => {
  const hasWallpaper = renderedBackgroundLayers.value.some(layer => Boolean(layer.url))
  if (
    !shouldUseGlassFixedShellBackplate({
      appearance: glass.effectiveGlassSettings.value.glassAppearance,
      hasWallpaper,
      isAuthenticated: isLoggedIn.value,
      needsStableFixedBackdrop,
      quality: glass.effectiveGlassSettings.value.glassQuality,
      themeName: 'glass',
    })
  ) {
    return []
  }

  return renderedBackgroundLayers.value.map(layer => ({
    ...layer,
    crossOrigin: getBackgroundLayerCrossOrigin(layer),
    src: getBackgroundLayerImageSource(layer),
    style: getBackgroundLayerStyle(layer),
  }))
})

provideGlassFixedShellBackplate({
  layers: fixedShellBackplateLayers,
  transitionDurationMs: BACKGROUND_CROSSFADE_DURATION_MS,
})

// 登录状态变化时同步 WebSocket 连接（登录后立即连接，登出后断开）
watch(isLoggedIn, (loggedIn) => {
  if (loggedIn) {
    systemStore.connect()
    aiStore.loadConfig()
  } else {
    systemStore.disconnect()
  }
}, { immediate: true })
</script>

<template>
  <div
    class="app-wrapper"
    :class="{
      'app-wrapper--background-transition': isBackgroundCrossfadingNow,
    }"
  >
    <!-- 壁纸背景层 -->
    <div
      v-if="shouldLoadBackgroundImages && shouldUseGlassBackgroundTreatment && renderedBackgroundLayers.length > 0"
      class="background-container is-glass-theme"
    >
      <div
        v-for="layer in renderedBackgroundLayers"
        :key="layer.key"
        class="background-image"
        :class="layer.role"
        :style="getBackgroundLayerStyle(layer)"
      >
        <img
          v-if="getBackgroundLayerImageSource(layer)"
          class="background-image__source"
          :crossorigin="getBackgroundLayerCrossOrigin(layer)"
          :src="getBackgroundLayerImageSource(layer)"
          alt=""
          aria-hidden="true"
          draggable="false"
        />
      </div>
    </div>
    <!-- 玻璃光学渲染层 -->
    <GlassOpticalLayer
      v-if="glass.shouldRenderGlassOpticalLayer.value"
      :appearance="glass.effectiveGlassSettings.value.glassAppearance"
      :deformation-strength="glass.opticalDeformationStrength.value"
      :dynamics-mode="glass.effectiveGlassSettings.value.glassDynamicsMode"
      :flow-strength="glass.opticalFlowStrength.value"
      :quality="glass.opticalQuality.value === 'high' ? 'high' : 'balanced'"
      :reflection-strength="glass.opticalReflectionStrength.value"
      :surface-mode="glass.opticalSurfaceMode.value"
      :transparency-strength="glass.opticalTransparencyStrength.value"
      :transmission-strength="glass.opticalTransmissionStrength.value"
      :translation-strength="glass.opticalTranslationStrength.value"
      :route-key="route.fullPath"
      :tint-color="glass.glassMaterialTintColor.value"
      :transition-duration="glass.transitionDuration"
      :transition-started-at="glass.transitionStartedAt.value"
      :wallpaper-url="glass.wallpaperUrl.value"
      :previous-wallpaper-url="glass.previousWallpaperUrl.value"
      :pending-wallpaper-url="glass.pendingWallpaperUrl.value"
      :pending-wallpaper-revision="glass.pendingWallpaperRevision.value"
      :activate-wallpaper-revision="glass.activateWallpaperRevision.value"
    />
    <!-- 页面内容 -->
    <router-view />
  </div>
</template>

<style lang="scss">
/* 全局样式 */
.app-wrapper {
  position: relative;
  inline-size: 100%;
  min-block-size: 100vh;
}

.background-container {
  position: fixed;
  z-index: 0;
  overflow: hidden;
  block-size: 100%;
  inline-size: 100%;
  inset-block-start: 0;
  inset-inline-start: 0;
}

.background-image {
  position: absolute;
  background-position: center;
  background-repeat: no-repeat;
  background-size: cover;
  block-size: 100%;
  inline-size: 100%;
  inset-block-start: 0;
  inset-inline-start: 0;
  opacity: 0;
  transition: opacity 1.5s ease;

  &::after {
    position: absolute;
    background: linear-gradient(rgba(0, 0, 0, 30%) 0%, rgba(0, 0, 0, 60%) 100%);
    block-size: 100%;
    content: '';
    inline-size: 100%;
    inset-block-start: 0;
    inset-inline-start: 0;
  }

  &.active {
    z-index: 2;
    opacity: 1;
  }

  &.previous {
    z-index: 1;
  }
}

.background-container.is-glass-theme .background-image.active,
.background-container.is-glass-theme .background-image.previous {
  filter: brightness(var(--glass-wallpaper-brightness, 0.86)) saturate(0.95) contrast(1.02);
}

.background-container.is-glass-theme .background-image.active {
  opacity: 0.94;
}

.background-container.is-glass-theme .background-image.active::after,
.background-container.is-glass-theme .background-image.previous::after {
  background:
    radial-gradient(circle at 50% 18%, transparent 24%, rgba(var(--am-dark-veil-rgb), 12%) 100%),
    linear-gradient(rgba(var(--am-dark-veil-rgb), 10%) 0%, rgba(var(--am-dark-veil-rgb), 30%) 100%);
}

.background-image__source {
  position: absolute;
  display: block;
  block-size: 100%;
  inline-size: 100%;
  inset: 0;
  object-fit: cover;
  pointer-events: none;
}
</style>
