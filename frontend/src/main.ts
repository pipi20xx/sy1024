import { createApp } from 'vue'
import { createPinia } from 'pinia'
import vuetify from './plugins/vuetify'
import App from './App.vue'
import router from './router'

// MDI 图标字体本地打包（替代 index.html 里的 jsdelivr CDN，避免慢网络下回退字体）。
// 注意：plugins/vuetify.ts 用的 vuetify/iconsets/mdi 是【字体】图标集，
// 运行时生成 "mdi mdi-*" class 依赖此 webfont，不能移除（移除后按钮图标全部消失）。
import '@mdi/font/css/materialdesignicons.min.css'

// 仅开发环境：过滤 Vuetify VSlideGroup 的滚动动画警告。
// 切 tab 时若布局在动画期间变化（图片加载/字体切换），动画无法收敛会触发
// "Scroll target is not reachable"，属 Vuetify 内部已知噪声，非应用问题。
if (import.meta.env.DEV) {
  const originalWarn = console.warn.bind(console)
  console.warn = (...args: unknown[]) => {
    const first = args[0]
    if (typeof first === 'string' && first.includes('Scroll target is not reachable')) return
    originalWarn(...args)
  }
}

// 全局样式 — 分层设计系统入口（base/tokens/visual/主题覆盖/sytmdb 补充）
import '@/styles/index.css'

const app = createApp(App)

app.use(createPinia())
app.use(vuetify)
app.use(router)

app.mount('#app')
