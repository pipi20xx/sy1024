import { ref, computed, watch, onMounted } from 'vue'
import { useThemeStore } from '@/composables/useThemeStore'
import { useEffectiveGlassSettings, applyStoredThemeCustomizerAppearance, themeCustomizerPrimaryColors } from '@/composables/useThemeCustomizer'
import { normalizeThemeMaterialAccent } from '../utils/glassColor'
import { loadGlassWallpaperTone, DEFAULT_GLASS_WALLPAPER_TONE_PROFILE, type GlassWallpaperToneProfile } from '../utils/glassWallpaperTone'
import { useTheme } from 'vuetify'
import { appearanceApi, type WallpaperConfig, type WallpaperApiSource } from '@/api/appearance'

/**
 * 全局壁纸刷新信号 —— 递增后触发 App.vue 中的 watch 重新加载壁纸。
 * WallpaperDialog 保存配置后递增此值，实现跨组件通信。
 */
const wallpaperRefreshSignal = ref(0)

/**
 * 已知的随机壁纸 API 域名 —— URL 不变但每次请求返回不同图片。
 * 对这类源需要添加 cache-buster 让前端缓存和浏览器 HTTP 缓存失效，
 * 否则页面刷新后永远拿到同一张图。
 */
const RANDOM_WALLPAPER_DOMAINS = new Set([
  'loliapi.com',
  'www.loliapi.com',
  'api.loliapi.com',
])

function isRandomWallpaperUrl(url: string): boolean {
  try {
    const host = new URL(url).hostname.toLowerCase()
    return RANDOM_WALLPAPER_DOMAINS.has(host)
  } catch {
    return false
  }
}

/**
 * 构建代理 URL。对随机壁纸 API 添加时间戳 cache-buster，
 * 使每次页面加载都能获取新图片。
 * 不传 sourceUrl 时，后端自动从配置读取壁纸源。
 */
function buildProxyUrl(sourceUrl?: string): string {
  if (!sourceUrl) {
    // 不传 URL 时后端自动从配置解析，随机壁纸仍需 cache-buster
    return `/api/appearance/wallpaper_proxy?_ts=${Date.now()}`
  }
  const encodedUrl = encodeURIComponent(sourceUrl)
  if (isRandomWallpaperUrl(sourceUrl)) {
    return `/api/appearance/wallpaper_proxy?url=${encodedUrl}&_ts=${Date.now()}`
  }
  return `/api/appearance/wallpaper_proxy?url=${encodedUrl}`
}

/**
 * 玻璃壁纸管理：
 *
 * 壁纸源由后端 config.json 的 wallpaper 字段统一管理：
 * - source_type="api": 从预设 API 源列表中选择（loliapi 等）
 * - source_type="url": 自定义固定 URL
 * - source_type="upload": 本地上传图片
 *
 * 前端通过 /api/appearance/wallpaper_proxy 不带 url 参数请求时，
 * 后端自动从配置读取壁纸源。
 *
 * WebGL 纹理加载需要 CORS 支持，外部壁纸通过后端代理。
 * 壁纸色调分析（tone profile）用于材质亮度调节。
 */
export function useGlassWallpaper() {
  const themeStore = useThemeStore()
  const vuetifyTheme = useTheme()
  const effectiveGlassSettings = useEffectiveGlassSettings()

  // 后端壁纸配置
  const wallpaperConfig = ref<WallpaperConfig | null>(null)
  const wallpaperSources = ref<WallpaperApiSource[]>([])

  // 判断当前壁纸源是否为随机类型（需要 cache-buster）
  const isCurrentSourceRandom = computed(() => {
    if (!wallpaperConfig.value) return true
    const cfg = wallpaperConfig.value
    if (cfg.source_type === 'api') {
      const src = wallpaperSources.value.find(s => s.id === cfg.api_source_id)
      return src?.is_random ?? true
    }
    if (cfg.source_type === 'url') {
      return isRandomWallpaperUrl(cfg.custom_url)
    }
    // upload 模式不是随机的
    return false
  })

  // WebGL 使用的壁纸 URL —— 通过后端代理
  // 初始为空，由 initDefaultWallpaper 或 refreshWallpaper 设置
  const wallpaperUrl = ref<string>('')
  const previousWallpaperUrl = ref<string>('')
  const transitionStartedAt = ref<number>(0)
  const pendingWallpaperUrl = ref<string>('')
  const pendingWallpaperRevision = ref<number>(0)
  const activateWallpaperRevision = ref<number>(0)

  // 壁纸色调 profile —— 用于材质亮度调节
  const wallpaperToneProfile = ref<GlassWallpaperToneProfile>(DEFAULT_GLASS_WALLPAPER_TONE_PROFILE)

  // 壁纸交叉淡化时长
  const TRANSITION_DURATION_MS = 1500

  // 初始化守卫
  let defaultWallpaperInitialized = false

  const isGlassTheme = computed(() => themeStore.glassTheme === 'acg')
  const shouldRenderGlassOpticalLayer = computed(
    () =>
      isGlassTheme.value &&
      effectiveGlassSettings.value.glassQuality !== 'css' &&
      Boolean(wallpaperUrl.value),
  )

  // 玻璃材质色
  const glassMaterialTintColor = computed(
    () =>
      normalizeThemeMaterialAccent(String(vuetifyTheme.current.value.colors.primary))?.hex ??
      normalizeThemeMaterialAccent(themeCustomizerPrimaryColors[0].value)!.hex,
  )

  // 光学参数
  const opticalDeformationStrength = computed(() => effectiveGlassSettings.value.glassDeformationStrength)
  const opticalFlowStrength = computed(() => effectiveGlassSettings.value.glassFlowStrength)
  const opticalQuality = computed(() => effectiveGlassSettings.value.glassQuality)
  const opticalReflectionStrength = computed(() => effectiveGlassSettings.value.glassReflectionStrength)
  const opticalSurfaceMode = computed(() => effectiveGlassSettings.value.glassSurfaceMode)
  const opticalTransparencyStrength = computed(() => effectiveGlassSettings.value.glassTransparencyStrength)
  const opticalTransmissionStrength = computed(() => effectiveGlassSettings.value.glassTransmissionStrength)
  const opticalTranslationStrength = computed(() => effectiveGlassSettings.value.glassTranslationStrength)

  // 壁纸亮度模式与值 —— 手动模式时直接写入 CSS 变量，实时预览
  const wallpaperBrightnessMode = computed(() => effectiveGlassSettings.value.glassWallpaperBrightnessMode)
  const wallpaperBrightness = computed(() => effectiveGlassSettings.value.glassWallpaperBrightness)

  watch([wallpaperBrightnessMode, wallpaperBrightness], ([mode, brightness]) => {
    if (mode === 'manual') {
      document.documentElement.style.setProperty('--glass-wallpaper-brightness', String(brightness))
    }
    // auto 模式由 loadWallpaperTone 重新写入，不在此覆盖
  })

  /** 从后端加载壁纸配置和 API 源列表 */
  async function loadWallpaperConfig() {
    try {
      const [configRes, sourcesRes] = await Promise.all([
        appearanceApi.getConfig(),
        appearanceApi.getSources(),
      ])
      wallpaperConfig.value = configRes
      wallpaperSources.value = sourcesRes.sources
    } catch {
      // 后端不可用时使用默认值
      wallpaperConfig.value = {
        source_type: 'api',
        api_source_id: 'loliapi_acg_pc',
        custom_url: '',
        upload_filename: '',
        cache_ttl: 30,
      }
    }
  }

  /** 重新加载壁纸（从后端读取最新配置后刷新壁纸 URL） */
  async function refreshWallpaper() {
    await loadWallpaperConfig()
    // 随机源加 cache-buster，固定源不加
    const proxyUrl = isCurrentSourceRandom.value
      ? `/api/appearance/wallpaper_proxy?_ts=${Date.now()}`
      : `/api/appearance/wallpaper_proxy?_v=${Date.now()}`
    if (proxyUrl === wallpaperUrl.value) return
    previousWallpaperUrl.value = wallpaperUrl.value
    wallpaperUrl.value = proxyUrl
    transitionStartedAt.value = performance.now()
    syncWallpaperCssVar(proxyUrl)
    void loadWallpaperTone(proxyUrl)
  }

  /** 设置壁纸源 URL（兼容旧接口，内部转换为代理 URL） */
  function setWallpaperUrl(url: string) {
    if (!url) return
    const proxyUrl = buildProxyUrl(url)
    if (proxyUrl === wallpaperUrl.value) return
    previousWallpaperUrl.value = wallpaperUrl.value
    wallpaperUrl.value = proxyUrl
    transitionStartedAt.value = performance.now()
    syncWallpaperCssVar(proxyUrl)
    void loadWallpaperTone(proxyUrl)
  }

  /** 将壁纸 URL 同步到 CSS 变量 */
  function syncWallpaperCssVar(proxyUrl: string) {
    document.documentElement.style.setProperty('--glass-wallpaper-url', `url("${proxyUrl}")`)
  }

  /** 异步加载壁纸色调分析结果，用于材质亮度调节 */
  async function loadWallpaperTone(proxyUrl: string) {
    try {
      const result = await loadGlassWallpaperTone(proxyUrl)
      wallpaperToneProfile.value = result.profile
      // 同步亮度 CSS 变量，确保登录页面（不渲染 .background-container）也能使用正确的亮度
      const settings = effectiveGlassSettings.value
      if (settings.glassWallpaperBrightnessMode === 'manual') {
        document.documentElement.style.setProperty(
          '--glass-wallpaper-brightness',
          String(settings.glassWallpaperBrightness),
        )
      } else {
        const materialExposure = settings.glassAppearance === 'frosted' ? 0.82 : settings.glassAppearance === 'tinted' ? 0.85 : 0.86
        document.documentElement.style.setProperty(
          '--glass-wallpaper-brightness',
          String(materialExposure * result.profile.exposure),
        )
      }
    } catch {
      wallpaperToneProfile.value = DEFAULT_GLASS_WALLPAPER_TONE_PROFILE
    }
  }

  /** 初始化默认壁纸 —— 从后端读取配置，经代理供 WebGL 使用。 */
  async function initDefaultWallpaper() {
    if (defaultWallpaperInitialized) return
    defaultWallpaperInitialized = true

    // 先从后端加载配置
    await loadWallpaperConfig()

    // 根据配置构建正确的代理 URL
    const proxyUrl = isCurrentSourceRandom.value
      ? `/api/appearance/wallpaper_proxy?_ts=${Date.now()}`
      : `/api/appearance/wallpaper_proxy?_v=${Date.now()}`
    wallpaperUrl.value = proxyUrl
    syncWallpaperCssVar(proxyUrl)
    void loadWallpaperTone(proxyUrl)
  }

  // 当切换到 ACG 主题时，应用玻璃设置并初始化壁纸
  watch(
    () => themeStore.glassTheme,
    (theme) => {
      if (theme === 'acg') {
        applyStoredThemeCustomizerAppearance()
        void initDefaultWallpaper()
      }
    },
    { immediate: true },
  )

  onMounted(() => {
    if (isGlassTheme.value) {
      applyStoredThemeCustomizerAppearance()
      void initDefaultWallpaper()
    }
  })

  return {
    wallpaperUrl,
    previousWallpaperUrl,
    transitionStartedAt,
    transitionDuration: TRANSITION_DURATION_MS,
    pendingWallpaperUrl,
    pendingWallpaperRevision,
    activateWallpaperRevision,
    shouldRenderGlassOpticalLayer,
    glassMaterialTintColor,
    opticalDeformationStrength,
    opticalFlowStrength,
    opticalQuality,
    opticalReflectionStrength,
    opticalSurfaceMode,
    opticalTransparencyStrength,
    opticalTransmissionStrength,
    opticalTranslationStrength,
    effectiveGlassSettings,
    wallpaperToneProfile,
    wallpaperBrightnessMode,
    wallpaperBrightness,
    wallpaperConfig,
    wallpaperSources,
    setWallpaperUrl,
    refreshWallpaper,
    loadWallpaperConfig,
    wallpaperRefreshSignal,
  }
}
