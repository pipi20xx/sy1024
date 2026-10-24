/**
 * Vuetify 插件配置
 *
 * 默认主题：经典实色（classic）
 * - 亮色：纯白底 + 主强调色
 * - 暗色：纯黑底 #121212 + 主强调色
 * - 主色调可通过主题定制器（PrimaryColorDialog）动态切换，不分白天/夜晚
 * - ACG / 液态玻璃主题通过 CSS 覆盖实现
 * - 圆角统一由 visual.css 的 --am-*-radius 令牌控制，不用 Vuetify rounded 默认值
 * - 图标：webfont 版 MDI 图标集（vuetify/iconsets/mdi，依赖 @mdi/font 的
 *   webfont，在 main.ts 引入；不是 @mdi/js 的 SVG 版 mdi-svg）
 */
import { createVuetify } from 'vuetify'
import { aliases, mdi } from 'vuetify/iconsets/mdi'

import 'vuetify/styles'

import { isThemeDark, readStoredAppTheme } from '@/composables/useThemeStore'

// 亮色主题 — 经典实色
const lightTheme = {
  dark: false,
  colors: {
    background: '#FFFFFF',  // 页面背景
    surface: '#FFFFFF',      // 卡片/面板背景
    'surface-variant': '#F5F5F5',
    'on-surface-variant': '#64748B',
    primary: '#a855f7',
    'primary-darken-1': '#9333EA',
    secondary: '#6b7280',
    'secondary-darken-1': '#4b5563',
    accent: '#4ecdc4',
    error: '#ef4444',
    info: '#1565C0',
    success: '#1B8134',
    warning: '#E65100',
  },
}

// 暗色主题 — 经典实色（纯黑底）
// 规则：强调色（primary/secondary/accent/error/info/success/warning）
//       与 light 完全一致，只改 background/surface 明暗值
const darkTheme = {
  dark: true,
  colors: {
    background: '#121212',  // 页面背景（纯黑）
    surface: '#1E1E1E',      // 卡片/面板背景
    'surface-variant': '#2C2C2C',
    'on-surface-variant': '#BFC2CE',
    primary: '#a855f7',
    'primary-darken-1': '#9333EA',
    secondary: '#6b7280',
    'secondary-darken-1': '#4b5563',
    accent: '#4ecdc4',
    error: '#ef4444',
    info: '#1565C0',
    success: '#1B8134',
    warning: '#E65100',
  },
}

export default createVuetify({
  icons: {
    defaultSet: 'mdi',
    aliases,
    sets: {
      mdi,
    },
  },
  theme: {
    defaultTheme: isThemeDark(readStoredAppTheme()) ? 'dark' : 'light',
    themes: {
      light: lightTheme,
      dark: darkTheme,
    },
  },
  defaults: {
    VCard: {
      // 圆角由 visual.css 的 var(--am-surface-radius) 统一控制
      // 不在此设置 rounded，避免 Vuetify 的 .rounded-xl 工具类干扰
    },
    VBtn: {
      // 圆角由 visual.css 的 var(--am-btn-radius) 统一控制
      variant: 'tonal',
      density: 'default',
    },
    VChip: {
      // 圆角由 visual.css 的 var(--am-chip-radius) 统一控制
      label: true,
    },
    VTextField: {
      variant: 'outlined',
      density: 'compact',
      // 圆角由 visual.css 的 var(--am-field-radius) 统一控制
      hideDetails: 'auto',
      persistentPlaceholder: true,
    },
    VSelect: {
      variant: 'outlined',
      density: 'compact',
      // 圆角由 visual.css 的 var(--am-field-radius) 统一控制
      hideDetails: 'auto',
      persistentPlaceholder: true,
    },
    VTextarea: {
      variant: 'outlined',
      density: 'compact',
      // 圆角由 visual.css 的 var(--am-field-radius) 统一控制
      hideDetails: 'auto',
      persistentPlaceholder: true,
    },
    VAutocomplete: {
      variant: 'outlined',
      density: 'compact',
      // 圆角由 visual.css 的 var(--am-field-radius) 统一控制
      hideDetails: 'auto',
      persistentPlaceholder: true,
    },
    VCombobox: {
      variant: 'outlined',
      density: 'compact',
      // 圆角由 visual.css 的 var(--am-field-radius) 统一控制
      hideDetails: 'auto',
      persistentPlaceholder: true,
    },
  },
})
