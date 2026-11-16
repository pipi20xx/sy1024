import { ref, computed, watch, onMounted } from 'vue'
import { useThemeStore } from '@/composables/useThemeStore'
import { useEffectiveGlassSettings, applyStoredThemeCustomizerAppearance, themeCustomizerPrimaryColors } from '@/composables/useThemeCustomizer'
import { normalizeThemeMaterialAccent } from '../utils/glassColor'
import { loadGlassWallpaperTone, DEFAULT_GLASS_WALLPAPER_TONE_PROFILE, type GlassWallpaperToneProfile } from '../utils/glassWallpaperTone'
import { useTheme } from 'vuetify'
import { appearanceApi, type WallpaperConfig, type WallpaperApiSource, type WallpaperHistory, type WallpaperUpload } from '@/api/appearance'
import { createBackgroundCandidateOrderResolver, normalizeBackgroundRotationIntervalSeconds } from '../utils/backgroundRotation'
import { createBackgroundTimer, type BackgroundTimerHandle } from '@/utils/backgroundManager'

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
    // upload / history 本地图不是随机的
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
        history_filename: '',
        refresh_interval: 60,
        display_mode: 'latest',
        rotation_interval: 60,
        rotation_include_history: true,
        rotation_include_uploads: false,
      }
    }
  }

  /** 根据当前配置构建代理 URL（随机源加 cache-buster，固定源不加）。 */
  function proxyUrlForConfiguredSource() {
    return isCurrentSourceRandom.value
      ? `/api/appearance/wallpaper_proxy?_ts=${Date.now()}`
      : `/api/appearance/wallpaper_proxy?_v=${Date.now()}`
  }

  /** 应用当前配置对应的壁纸；api 源默认 = 历史图库最新一张，轮播模式则由轮播范围决定。 */
  async function applyConfiguredWallpaper() {
    await loadWallpaperConfig()
    if (wallpaperConfig.value?.source_type !== 'api') {
      applyWallpaperUrl(proxyUrlForConfiguredSource())
      void setupDisplayStrategy()
      return
    }
    if (displayMode.value === 'rotation') {
      // 轮播模式：初始壁纸交给 setupRotation 从轮播范围挑选，避免回落到代理实时下载
      await setupDisplayStrategy()
      return
    }
    const items = await loadHistoryItems()
    const latest = items[0]?.filename ?? ''
    applyWallpaperUrl(latest ? historyUrlForFilename(latest) : proxyUrlForConfiguredSource())
    void setupDisplayStrategy()
  }

  /** 重新加载壁纸（从后端读取最新配置后刷新壁纸 URL） */
  async function refreshWallpaper() {
    await applyConfiguredWallpaper()
  }

  /** 设置壁纸源 URL（兼容旧接口，内部转换为代理 URL） */
  function setWallpaperUrl(url: string) {
    if (!url) return
    applyWallpaperUrl(buildProxyUrl(url))
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

  let previousWallpaperClearTimer: ReturnType<typeof setTimeout> | null = null

  /** 切换壁纸 URL，并触发 CSS 变量同步、tone 分析与过渡计时。 */
  function applyWallpaperUrl(url: string) {
    if (!url || url === wallpaperUrl.value) return
    previousWallpaperUrl.value = wallpaperUrl.value
    wallpaperUrl.value = url
    transitionStartedAt.value = performance.now()
    syncWallpaperCssVar(url)
    void loadWallpaperTone(url)

    // 过渡结束后清空 previous 槽，作为「共享切换事务完成」信号驱动 renderer 归一
    if (previousWallpaperClearTimer !== null) window.clearTimeout(previousWallpaperClearTimer)
    previousWallpaperClearTimer = window.setTimeout(() => {
      previousWallpaperClearTimer = null
      previousWallpaperUrl.value = ''
    }, TRANSITION_DURATION_MS)
  }

  // ── 显示策略：跟随最新（latest）或 图库轮播（rotation） ──
  const latestHistoryFilename = ref<string>('')
  const rotationOrder = ref<string[]>([])
  const resolveCandidateOrder = createBackgroundCandidateOrderResolver()
  const rotationAvailable = new Set<string>()
  const rotationFailed = new Set<string>()
  let displayTimer: BackgroundTimerHandle | null = null
  let displayGeneration = 0
  let rotationIndex = 0

  /** 只有在线随机源（api）未手动选图时启用显示策略；upload/history/url 为手动固定。 */
  const isOnlineSource = computed(() => wallpaperConfig.value?.source_type === 'api')
  /** 显示方式：latest 跟随最新 | rotation 图库轮播。 */
  const displayMode = computed(() => (wallpaperConfig.value?.display_mode === 'rotation' ? 'rotation' : 'latest'))

  function historyUrlForFilename(filename: string) {
    return `/api/appearance/wallpaper/uploads/${encodeURIComponent(filename)}`
  }

  async function loadHistoryItems(): Promise<WallpaperHistory[]> {
    try {
      return await appearanceApi.listHistory()
    } catch {
      return []
    }
  }

  async function loadUploadItems(): Promise<WallpaperUpload[]> {
    try {
      return await appearanceApi.listUploads()
    } catch {
      return []
    }
  }

  function stopDisplayTimer() {
    displayTimer?.stop()
    displayTimer = null
  }

  function reducedMotionQuery() {
    return matchMedia('(prefers-reduced-motion: reduce)').matches
  }

  // —— latest：跟随历史最新一张 ——
  async function followLatestOnce() {
    const items = await loadHistoryItems()
    if (!isOnlineSource.value || displayMode.value !== 'latest') return
    const filename = items[0]?.filename ?? ''
    if (!filename || filename === latestHistoryFilename.value) return
    latestHistoryFilename.value = filename
    applyWallpaperUrl(historyUrlForFilename(filename))
  }

  async function setupLatestFollowing(generation: number) {
    const items = await loadHistoryItems()
    if (generation !== displayGeneration) return
    latestHistoryFilename.value = items[0]?.filename ?? ''
    const configured = normalizeBackgroundRotationIntervalSeconds(wallpaperConfig.value?.refresh_interval)
    if (configured <= 0) return
    // 后端按 refresh_interval 下载新图；前端用更短周期发现变化，避免多等一整轮
    const pollInterval = Math.max(10, Math.min(configured, 60))
    displayTimer = createBackgroundTimer({
      intervalSeconds: pollInterval,
      onTick: () => void followLatestOnce(),
      reducedMotion: reducedMotionQuery,
    })
  }

  // —— rotation：只在历史图库内随机轮播 ——
  async function preloadCandidate(url: string): Promise<boolean> {
    if (rotationAvailable.has(url)) return true
    if (rotationFailed.has(url)) return false
    try {
      const result = await loadGlassWallpaperTone(url)
      if (result.corsReady) {
        rotationAvailable.add(url)
        return true
      }
      rotationFailed.add(url)
      return false
    } catch {
      rotationFailed.add(url)
      return false
    }
  }

  async function rotateToNextWallpaper() {
    const order = rotationOrder.value
    if (order.length === 0) return
    for (let step = 0; step < order.length; step += 1) {
      rotationIndex = (rotationIndex + 1) % order.length
      const url = order[rotationIndex]
      if (!url || url === wallpaperUrl.value) continue
      const available = await preloadCandidate(url)
      if (!isOnlineSource.value || displayMode.value !== 'rotation') return
      if (available) {
        applyWallpaperUrl(url)
        return
      }
    }
  }

  async function setupRotation(generation: number) {
    let includeHistory = wallpaperConfig.value?.rotation_include_history !== false
    let includeUploads = wallpaperConfig.value?.rotation_include_uploads === true
    // 兜底：两个范围都没勾选时回到历史图库
    if (!includeHistory && !includeUploads) includeHistory = true

    const [historyItems, uploadItems] = await Promise.all([
      includeHistory ? loadHistoryItems() : Promise.resolve<WallpaperHistory[]>([]),
      includeUploads ? loadUploadItems() : Promise.resolve<WallpaperUpload[]>([]),
    ])
    if (generation !== displayGeneration) return

    const filenames = new Set<string>()
    for (const item of historyItems) if (item.filename) filenames.add(item.filename)
    for (const item of uploadItems) if (item.filename) filenames.add(item.filename)

    const urls = [...filenames].map(historyUrlForFilename)
    rotationOrder.value = resolveCandidateOrder(urls)
    rotationAvailable.clear()
    rotationFailed.clear()
    rotationIndex = -1
    if (rotationOrder.value.length === 0) return
    // 立即从轮播范围选中首个可用候选，避免开启轮播瞬间仍停留在代理/旧图
    await rotateToNextWallpaper()
    if (generation !== displayGeneration) return
    if (rotationOrder.value.length < 2) return
    const interval = normalizeBackgroundRotationIntervalSeconds(wallpaperConfig.value?.rotation_interval)
    if (interval <= 0) return
    displayTimer = createBackgroundTimer({
      intervalSeconds: interval,
      onTick: () => void rotateToNextWallpaper(),
      reducedMotion: reducedMotionQuery,
    })
  }

  /** 根据配置选择显示策略；手动选中时停掉一切跟随/轮播。 */
  async function setupDisplayStrategy() {
    const generation = ++displayGeneration
    stopDisplayTimer()
    if (!isOnlineSource.value) {
      latestHistoryFilename.value = ''
      rotationOrder.value = []
      return
    }
    if (displayMode.value === 'rotation') {
      await setupRotation(generation)
    } else {
      await setupLatestFollowing(generation)
    }
  }

  /** 初始化默认壁纸 —— 从后端读取配置；api 源默认显示历史图库最新一张。 */
  async function initDefaultWallpaper() {
    if (defaultWallpaperInitialized) return
    defaultWallpaperInitialized = true
    await applyConfiguredWallpaper()
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
