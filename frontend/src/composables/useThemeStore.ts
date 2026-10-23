import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

/** 主题风格（视觉系列），只作为主题的一部分暴露，不再单独切换 */
export type ThemeStyle = 'classic' | 'acg' | 'liquid'

/**
 * 完整主题 = 风格 + 写死的明暗模式。
 * 白天/夜晚不是独立开关：每个主题创建时就固定了明暗，切主题即整体切换。
 */
export type AppTheme = 'classic-light' | 'classic-dark' | 'liquid-light' | 'liquid-dark' | 'acg'

const THEME_STORAGE_KEY = 'app_theme'
const LEGACY_STYLE_KEY = 'glass_theme'
const LEGACY_MODE_KEY = 'theme_mode'

const THEME_STYLE: Record<AppTheme, ThemeStyle> = {
  'classic-light': 'classic',
  'classic-dark': 'classic',
  'liquid-light': 'liquid',
  'liquid-dark': 'liquid',
  acg: 'acg',
}

const THEME_DARK: Record<AppTheme, boolean> = {
  'classic-light': false,
  'classic-dark': true,
  'liquid-light': false,
  'liquid-dark': true,
  acg: true,
}

export function isThemeDark(theme: AppTheme): boolean {
  return THEME_DARK[theme]
}

/** 主题风格（如 'classic'），供 glass-theme-xxx class 使用 */
export function themeStyle(theme: AppTheme): ThemeStyle {
  return THEME_STYLE[theme]
}

/**
 * 读取持久化主题。新key app_theme 优先；
 * 旧版 glass_theme + theme_mode 双 key 自动合并迁移（ACG 始终视为暗色）。
 */
export function readStoredAppTheme(): AppTheme {
  const stored = localStorage.getItem(THEME_STORAGE_KEY)
  if (stored && stored in THEME_STYLE) return stored as AppTheme

  const style = localStorage.getItem(LEGACY_STYLE_KEY)
  const dark = style === 'acg' ? true : localStorage.getItem(LEGACY_MODE_KEY) !== 'light'

  if (style === 'acg') return 'acg'
  const base = style === 'liquid' ? 'liquid' : 'classic'
  return `${base}-${dark ? 'dark' : 'light'}` as AppTheme
}

export const useThemeStore = defineStore('theme', () => {
  const theme = ref<AppTheme>(readStoredAppTheme())

  // 首次加载旧版数据时立即迁移为单一 app_theme，保证之后只有一个存储来源
  if (!localStorage.getItem(THEME_STORAGE_KEY)) {
    localStorage.setItem(THEME_STORAGE_KEY, theme.value)
    localStorage.removeItem(LEGACY_STYLE_KEY)
    localStorage.removeItem(LEGACY_MODE_KEY)
  }

  /** 视觉风格（classic / liquid / acg） */
  const glassTheme = computed<ThemeStyle>(() => themeStyle(theme.value))
  /** 明暗模式，由主题写死 */
  const isDarkMode = computed(() => isThemeDark(theme.value))

  function setTheme(next: AppTheme) {
    theme.value = next
    localStorage.setItem(THEME_STORAGE_KEY, next)
  }

  return { theme, glassTheme, isDarkMode, setTheme }
})
