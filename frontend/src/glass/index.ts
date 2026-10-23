/**
 * glass/index.ts — 玻璃特效模块统一入口
 *
 * 将所有从 MoviePilot 移植的玻璃光学渲染相关文件收拢到此目录，
 * 方便整体移植到其他项目。外部代码只需 `import { ... } from '@/glass'`。
 *
 * 目录结构：
 *   composables/  — 响应式逻辑（Vue ref/watch/computed）
 *   utils/        — 纯函数工具（无 Vue 依赖）
 *   rendering/    — WebGL 动力学引擎（fluid / ripple）
 *   components/   — Vue 组件
 *   styles/       — 玻璃主题样式（glass-acg.scss / glass-themes.css）
 *
 * 外部依赖（由宿主项目提供）：
 *   - @/composables/useThemeStore     — 主题状态管理
 *   - @/composables/useThemeCustomizer — 玻璃定制器设置
 *   - @/utils/loginPresentation        — 登录页背景层类型
 *   - @/utils/appActivityLifecycle     — 应用活跃状态生命周期
 *   - @/​core/utils/corsImage            — CORS 图片预加载工具
 *   - vue / vuetify / @vueuse / three  — 框架依赖
 */

// ─── composables ──────────────────────────────────────────────
export {
  prepareGlassWebGLContext,
  createGlassWallpaperSourceCache,
  getGlassWallpaperPreparationKey,
  setGlassRendererState,
  useGlassOpticalRenderer,
  useGlassOpticalInteractionSource,
  containsGlassOpticalSurface,
  resolveGlassOpticalSurfaceMode,
  collectGlassOpticalRects,
  type GlassRendererState,
  type GlassPresentationSpace,
  type GlassOpticalInteractionSource,
  type PreparedWallpaperSource,
  type GlassWallpaperSourceCache,
} from './composables/useGlassOpticalRenderer'

export {
  isChromiumFixedShellBackplateBrowser,
  shouldUseGlassFixedShellBackplate,
  provideGlassFixedShellBackplate,
  useGlassFixedShellBackplate,
  type GlassFixedShellBackplateLayer,
  type GlassFixedShellBackplateContext,
} from './composables/useGlassFixedShellBackplate'

export {
  useGlassMobilePresentation,
} from './composables/useGlassPresentationCapabilities'

export {
  useGlassWallpaper,
} from './composables/useGlassWallpaper'

export {
  useGlassWallpaperTransaction,
} from './composables/useGlassWallpaperTransaction'

export {
  PAGE_PRESENTATION_MOTION_DURATION_MS,
  PAGE_PRESENTATION_MOTION_START_OPACITY,
  PAGE_PRESENTATION_MOTION_START_TRANSLATE_Y,
  PAGE_PRESENTATION_FROSTED_START_TRANSLATE_Y,
  PAGE_PRESENTATION_LAYOUT_STABLE_MS,
  PAGE_PRESENTATION_LAYOUT_HOLD_MAX_MS,
  usePagePresentationMotion,
  type PagePresentationMotionReader,
} from './composables/usePagePresentationMotion'

// ─── utils ─────────────────────────────────────────────────────
export {
  normalizeThemeMaterialAccent,
} from './utils/glassColor'

export {
  GLASS_OPTICAL_MAX_SURFACES_DESKTOP,
  GLASS_OPTICAL_MAX_SURFACES_MOBILE,
  GLASS_OPTICAL_MOTION_MAX_SCALE,
  GLASS_OPTICAL_DEFORMATION_MAX_SCALE,
  GLASS_OPTICAL_FLOW_MAX_SCALE,
  GLASS_OPTICAL_REFLECTION_MAX_SCALE,
  GLASS_OPTICAL_TRANSLATION_MAX_SCALE,
  GLASS_OPTICAL_STRENGTH_DEFAULT,
  GLASS_OPTICAL_STRENGTH_MAX,
  GLASS_OPTICAL_STRENGTH_MIN,
  GLASS_OPTICAL_REFERENCE_STRENGTH,
  normalizeGlassOpticalStrength,
  canUseGlassWallpaperTexture,
  getGlassCoverScale,
  getGlassMaterialResponse,
  getGlassOpticalBufferSize,
  getGlassOpticalDecay,
  getGlassOpticalDeformationStrengthScale,
  getGlassOpticalFlowStrengthScale,
  getGlassOpticalMaxRefractionPixels,
  getGlassOpticalMotionExpansion,
  getGlassOpticalMotionEnergy,
  getGlassOpticalReflectionStrengthScale,
  getGlassOpticalRenderProfile,
  getGlassOpticalTransmissionStrength,
  getGlassOpticalTranslationStrengthScale,
  getGlassOpticalSurfaceTransitionWeights,
  getGlassOpticalWakeDirection,
  getGlassWallpaperTransitionProgress,
  getGlassCssFrostBlur,
  getGlassOverlayClarityBlur,
  getGlassOpticalCssTransmissionBrightness,
  getGlassOpticalPresetKey,
  getGlassOpticalPresetParameters,
  getGlassOpticalPresetParametersWithOverrides,
  getAvailableGlassOpticalPresets,
  getGlassScrollBufferSize,
  normalizeGlassOpticalRect,
  reconcileGlassOpticalSurfaceSlots,
  selectGlassOpticalRects,
  type GlassAppearance,
  type GlassOpticalCapability,
  type GlassOpticalPreset,
  type GlassOpticalPresetKey,
  type GlassOpticalPresetOverrides,
  type GlassOpticalParameters,
  type GlassMaterialResponse,
  type GlassInteractionPoint,
  type GlassOpticalQuality,
  type GlassOpticalRect,
  type GlassOpticalBufferSize,
  type GlassOpticalPoint,
  type GlassOpticalSpringState,
  type GlassOpticalSurfaceMode,
  type GlassOpticalSurfaceCandidate,
  type GlassOpticalSurfaceSlot,
  type GlassOpticalRenderProfile,
  type GlassCornerRadii,
} from './utils/glassOptics'

export {
  DEFAULT_GLASS_WALLPAPER_TONE_PROFILE,
  getGlassWallpaperToneProfile,
  analyzeGlassWallpaperTone,
  takeGlassWallpaperDecodedSource,
  loadGlassWallpaperTone,
  loadGlassWallpaperToneProfile,
  type GlassWallpaperToneProfile,
  type GlassWallpaperToneLoadResult,
  type GlassWallpaperDecodedSource,
} from './utils/glassWallpaperTone'

// ─── rendering ─────────────────────────────────────────────────
export {
  createGlassRippleDynamics,
  type GlassRippleDynamics,
  type GlassRippleQuality,
} from './rendering/glassRippleDynamics'

export {
  createGlassFluidDynamics,
  GLASS_FLUID_FRAGMENT_SETUP,
  GLASS_FLUID_FRAGMENT_SURFACE_OPTICS,
  GLASS_FLUID_FRAGMENT_SURFACE_REFRACTION,
  GLASS_FLUID_FRAGMENT_SURFACE_SHAPE,
  GLASS_FLUID_FRAGMENT_TRAIL_AND_FIELD,
  type GlassFluidDynamics,
} from './rendering/glassFluidDynamics'

// ─── components ─────────────────────────────────────────────────
export { default as GlassOpticalLayer } from './components/GlassOpticalLayer.vue'
export { default as GlassFixedShellBackplate } from './components/GlassFixedShellBackplate.vue'
export { default as GlassSettingsDialog } from './components/GlassSettingsDialog.vue'
export { default as AppGlassCard } from './components/AppGlassCard.vue'
export { default as GlassDialog } from './components/GlassDialog.vue'
