<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, defineAsyncComponent } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useThemeStore, useSystemStore, useDetailsStore, useUiStore, CARDS_PER_ROW_OPTIONS } from '@/stores'
import { useNotification } from '@/composables'
import { useGlassFixedShellBackplate } from '@/glass'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import LogTerminal from '@/components/common/LogTerminal.vue'

// 异步加载玻璃设置弹窗（three.js 渲染引擎较大，按需加载）
const GlassSettingsDialog = defineAsyncComponent(() => import('@/glass/components/GlassSettingsDialog.vue'))
// 异步加载主题色设置弹窗
const PrimaryColorDialog = defineAsyncComponent(() => import('@/components/common/PrimaryColorDialog.vue'))
// 异步加载圆角设置弹窗
const BorderRadiusDialog = defineAsyncComponent(() => import('@/components/common/BorderRadiusDialog.vue'))
// 异步加载边框设置弹窗
const BorderDialog = defineAsyncComponent(() => import('@/components/common/BorderDialog.vue'))
// 异步加载阴影设置弹窗
const ShadowDialog = defineAsyncComponent(() => import('@/components/common/ShadowDialog.vue'))
// 异步加载壁纸管理弹窗
const WallpaperDialog = defineAsyncComponent(() => import('@/components/common/WallpaperDialog.vue'))
// 异步加载 Fixed Shell Backplate 组件（Chromium 固定导航栏壁纸背板）
const GlassFixedShellBackplate = defineAsyncComponent(() => import('@/glass/components/GlassFixedShellBackplate.vue'))

// Fixed Shell Backplate —— 消费 App.vue 提供的背板层上下文
const fixedShellBackplate = useGlassFixedShellBackplate()
const isACG = computed(() => themeStore.glassTheme === 'acg')
const isOverlayNav = computed(() => isMobile.value)
const isOverlayNavActive = computed(() => isMobile.value && drawer.value)

// 主题设置弹窗开关
const showGlassSettings = ref(false)
const showPrimaryColorDialog = ref(false)
const showBorderRadiusDialog = ref(false)
const showBorderDialog = ref(false)
const showShadowDialog = ref(false)
const showWallpaperDialog = ref(false)

const route = useRoute()
const router = useRouter()
const themeStore = useThemeStore()
const systemStore = useSystemStore()
const uiStore = useUiStore()
const { notify, state: notifyState } = useNotification()

const username = ref(localStorage.getItem('username') || 'admin')

const appVersion = __APP_VERSION__ as string

const drawer = ref(true)
const rail = ref(false)

// 需要缓存的视图组件（切换页面后保留状态）
const cachedViews = [
  'HomeView',
  'CollectionsView',
  'CollectionDetailView',
  'ActorsView',
  'TmdbBgmMappingView',
  'TmdbBgmMappingDetailView',
  'TagRulesView',
  'TasksView',
  'BangumiView',
  'CoverGeneratorView',
  'PreviewGeneratorView',
  'ShenYiConfigView',
  'ExternalControlView',
  'ItemDetailView',
  'SettingsView',
]

const navItems = [
  { title: '首页', icon: 'mdi-home-outline', to: '/' },
  { title: '合集', icon: 'mdi-folder-multiple-outline', to: '/collections' },
  { title: '演员库', icon: 'mdi-account-group-outline', to: '/actors' },
  { title: 'TMDB-BGM 映射', icon: 'mdi-link-variant-plus', to: '/tmdb-bgm-mapping' },
  { title: '标签规则', icon: 'mdi-tag-heart-outline', to: '/tag-rules' },
  { title: '定时任务', icon: 'mdi-clock-outline', to: '/tasks' },
  { title: 'Bangumi', icon: 'mdi-animation-outline', to: '/bangumi' },
  { title: '封面生成器', icon: 'mdi-image-edit-outline', to: '/cover-generator' },
  { title: '预览截图', icon: 'mdi-movie-open-outline', to: '/preview-generator' },
  { title: '神医配置', icon: 'mdi-shield-account-outline', to: '/shenyi' },
  { title: '外部控制', icon: 'mdi-api', to: '/external-control' },
  { title: '设置', icon: 'mdi-cog-outline', to: '/settings' },
]

const detailsStore = useDetailsStore()

const currentTitle = computed(() => {
  // 详情页显示项目标题
  if (route.name === 'itemDetail' && detailsStore.itemDetails) {
    const d = detailsStore.itemDetails
    const title = d.name || d.title || d.full_metadata?.name || d.full_metadata?.title || '详情'
    const year = d.year || ''
    return year ? `${title} (${year})` : title
  }
  const item = navItems.find(n => n.to === route.path)
  return item?.title ?? 'SYTMDB'
})

// 扫描进度
const scanPercent = computed(() => {
  const p = systemStore.scanProgress
  if (p.status !== 'running' && p.status !== 'scanning') return -1
  return p.total > 0 ? Math.round((p.current / p.total) * 100) : 0
})

const downloadPercent = computed(() => {
  const p = systemStore.downloadProgress
  if (p.status !== 'running' && p.status !== 'scanning') return -1
  return p.total > 0 ? Math.round((p.current / p.total) * 100) : 0
})

const hasActiveProgress = computed(() => scanPercent.value >= 0 || downloadPercent.value >= 0)

const progressLabel = computed(() => {
  if (scanPercent.value >= 0) return `扫描 ${scanPercent.value}%`
  if (downloadPercent.value >= 0) return `下载 ${downloadPercent.value}%`
  return ''
})

function handleLogout() {
  localStorage.removeItem('access_token')
  localStorage.removeItem('username')
  router.push('/login')
}

// 移动端：路由变化时自动收起 drawer
const isMobile = ref(false)
function checkMobile() {
  isMobile.value = window.innerWidth < 960
  if (isMobile.value) drawer.value = false
}

onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
})
onUnmounted(() => {
  window.removeEventListener('resize', checkMobile)
})
</script>

<template>
  <v-app>
    <!-- 玻璃 Fixed Shell Backplate —— 在固定导航栏后面渲染壁纸背板 -->
    <GlassFixedShellBackplate
      v-if="isACG && fixedShellBackplate.layers.value.length > 0"
      :is-overlay-nav-active="isOverlayNavActive"
      :is-overlay-nav="isOverlayNav"
      :layers="fixedShellBackplate.layers.value"
      :transition-duration-ms="fixedShellBackplate.transitionDurationMs"
    />

    <!-- 侧边导航 —— layout-vertical-nav class 供玻璃渲染器发现表面 -->
    <v-navigation-drawer
      v-model="drawer"
      :rail="rail && !isMobile"
      :permanent="!isMobile"
      :temporary="isMobile"
      width="256"
      rail-width="72"
      :class="['layout-vertical-nav', { 'overlay-nav': isMobile }]"
    >
      <!-- Logo 区域 -->
      <div class="logo-header" :class="{ 'logo-header--rail': rail && !isMobile }">
        <v-avatar class="liquid-avatar" rounded="xl" size="40">
          <img src="/favicon.svg" alt="SYTMDB" class="app-logo" />
        </v-avatar>
        <div v-if="!rail || isMobile" class="logo-text">
          <div class="text-subtitle-1 font-weight-bold liquid-glass-subtitle">SYTMDB</div>
          <div class="text-caption text-medium-emphasis">影视元数据管理</div>
          <div class="sidebar-version">v{{ appVersion }}</div>
        </div>
        <v-btn
          v-if="!isMobile"
          variant="text"
          :icon="rail ? 'mdi-chevron-right' : 'mdi-chevron-left'"
          size="x-small"
          density="comfortable"
          @click.stop="rail = !rail"
        />
      </div>

      <v-divider />

      <!-- 导航菜单 -->
      <v-list density="compact" nav class="px-3 py-2 flex-grow-0 overflow-y-auto">
        <v-list-item
          v-for="item in navItems"
          :key="item.to"
          :prepend-icon="item.icon"
          :title="item.title"
          :to="item.to"
          :value="item.to"
          rounded="xl"
          class="mb-1"
          :exact="item.to === '/'"
        />
      </v-list>

      <!-- 底部区域 -->
      <template #append>
        <v-divider />

        <!-- 进度指示 -->
        <div v-if="hasActiveProgress" class="px-4 py-3">
          <div class="d-flex align-center mb-2">
            <v-progress-circular
              indeterminate
              :size="16"
              :width="2"
              color="primary"
              class="mr-2"
            />
            <span class="text-caption font-weight-medium text-truncate">{{ progressLabel }}</span>
          </div>
          <v-progress-linear
            :model-value="scanPercent >= 0 ? scanPercent : downloadPercent"
            color="primary"
            height="6"
            rounded="pill"
          />
        </div>
      </template>
    </v-navigation-drawer>

    <!-- 顶栏 —— layout-navbar class 供玻璃渲染器发现表面 -->
    <v-app-bar elevation="0" density="comfortable" class="layout-navbar navbar-blur">
      <!-- 移动端菜单按钮 -->
      <v-app-bar-nav-icon v-if="isMobile" @click="drawer = !drawer" />

      <v-app-bar-title class="font-weight-bold text-body-1">{{ currentTitle }}</v-app-bar-title>

      <template #append>
        <div class="d-flex align-center ga-2">
          <!-- WS 连接状态 -->
          <v-chip
            :color="systemStore.isConnected ? 'success' : 'error'"
            size="small"
            variant="tonal"
            label
          >
            <v-icon start size="14">{{ systemStore.isConnected ? 'mdi-access-point-check' : 'mdi-access-point-off' }}</v-icon>
            {{ systemStore.isConnected ? '已连接' : '断开' }}
          </v-chip>

          <!-- 每行卡片数量 -->
          <v-menu location="bottom end">
            <template #activator="{ props }">
              <v-btn
                variant="text"
                density="comfortable"
                size="small"
                icon="mdi-view-grid"
                v-bind="props"
              />
            </template>
            <v-list density="compact" min-width="160">
              <v-list-item
                v-for="opt in CARDS_PER_ROW_OPTIONS"
                :key="opt.value"
                :active="uiStore.cardsPerRow === opt.value"
                :title="opt.title"
                @click="uiStore.setCardsPerRow(opt.value)"
              />
            </v-list>
          </v-menu>

          <!-- 主题选择菜单 -->
          <v-menu>
            <template #activator="{ props: menuProps }">
              <v-btn
                v-bind="menuProps"
                variant="text"
                density="comfortable"
                size="small"
                :color="{ liquid: 'accent', acg: 'secondary', classic: 'primary' }[themeStore.glassTheme]"
                :icon="{ liquid: 'mdi-layers-outline', acg: 'mdi-image-multiple', classic: 'mdi-contrast-box' }[themeStore.glassTheme]"
              />
            </template>
            <v-list density="compact" min-width="200" nav>
              <!-- 每个主题的明暗都是写死的，切换主题即整体切换 -->
              <!-- 液态玻璃 -->
              <v-list-item
                prepend-icon="mdi-white-balance-sunny"
                title="液态玻璃 · 白天"
                subtitle="Apple 液态玻璃风格"
                :active="themeStore.theme === 'liquid-light'"
                @click="themeStore.setTheme('liquid-light')"
              />
              <v-list-item
                prepend-icon="mdi-weather-night"
                title="液态玻璃 · 黑夜"
                subtitle="Apple 液态玻璃风格"
                :active="themeStore.theme === 'liquid-dark'"
                @click="themeStore.setTheme('liquid-dark')"
              />
              <!-- ACG 毛玻璃 -->
              <v-list-item
                prepend-icon="mdi-image-multiple"
                title="ACG 毛玻璃"
                subtitle="二次元壁纸 + 暗色毛玻璃"
                :active="themeStore.theme === 'acg'"
                @click="themeStore.setTheme('acg')"
              />
              <!-- 经典 -->
              <v-list-item
                prepend-icon="mdi-white-balance-sunny"
                title="经典 · 白天"
                subtitle="纯白最简风格"
                :active="themeStore.theme === 'classic-light'"
                @click="themeStore.setTheme('classic-light')"
              />
              <v-list-item
                prepend-icon="mdi-weather-night"
                title="经典 · 黑夜"
                subtitle="纯黑最简风格"
                :active="themeStore.theme === 'classic-dark'"
                @click="themeStore.setTheme('classic-dark')"
              />
              <v-divider class="my-2 mx-2" />
              <v-list-item
                prepend-icon="mdi-palette"
                title="主题色"
                subtitle="选择应用主色调"
                @click="showPrimaryColorDialog = true"
              />
              <v-list-item
                prepend-icon="mdi-border-radius"
                title="圆角"
                subtitle="无 / 小 / 默认 / 大 / 更大"
                @click="showBorderRadiusDialog = true"
              />
              <v-list-item
                prepend-icon="mdi-border-all-variant"
                title="边框"
                subtitle="无 / 轻微 / 默认 / 明显 / 强边框"
                @click="showBorderDialog = true"
              />
              <v-list-item
                prepend-icon="mdi-box-shadow"
                title="阴影"
                subtitle="无 / 轻微 / 默认 / 明显 / 夸张"
                @click="showShadowDialog = true"
              />
              <v-list-item
                prepend-icon="mdi-wallpaper"
                title="壁纸管理"
                subtitle="API / 上传 / 自定义 URL"
                @click="showWallpaperDialog = true"
              />
              <v-list-item
                prepend-icon="mdi-tune-variant"
                title="玻璃材质设置"
                subtitle="材质 / 质量 / 动态效果 / 参数"
                :disabled="themeStore.glassTheme !== 'acg'"
                @click="showGlassSettings = true"
              />
            </v-list>
          </v-menu>

          <!-- 任务日志 -->
          <v-btn
            variant="text"
            density="comfortable"
            size="small"
            color="primary"
            icon="mdi-card-text-outline"
            @click="systemStore.showLogModal = true"
          />

          <!-- 用户菜单 -->
          <v-menu>
            <template #activator="{ props: menuProps }">
              <v-chip size="small" variant="outlined" label v-bind="menuProps" class="cursor-pointer">
                <v-icon start size="14">mdi-account-circle</v-icon>
                {{ username }}
                <v-icon end size="14">mdi-chevron-down</v-icon>
              </v-chip>
            </template>
            <v-list density="compact" min-width="160">
              <v-list-item
                prepend-icon="mdi-cog-outline"
                title="设置"
                to="/settings"
                rounded="xl"
              />
              <v-divider />
              <v-list-item
                prepend-icon="mdi-logout"
                title="退出登录"
                @click="handleLogout"
                rounded="xl"
                color="error"
              />
            </v-list>
          </v-menu>
        </div>
      </template>
    </v-app-bar>

    <!-- 主内容 —— layout-page-content / page-content-container 供渲染器发现滚动表面 -->
    <v-main class="layout-content-wrapper">
      <main class="layout-page-content">
        <section class="page-content-container">
          <router-view v-slot="{ Component }">
            <keep-alive :include="cachedViews">
              <component :is="Component" />
            </keep-alive>
          </router-view>
        </section>
      </main>
    </v-main>

    <!-- 全局底部进度条 -->
    <v-progress-linear
      v-if="hasActiveProgress"
      :model-value="scanPercent >= 0 ? scanPercent : downloadPercent"
      color="warning"
      height="3"
      absolute
      location="bottom"
    />

    <!-- 系统日志终端 -->
    <LogTerminal />

    <!-- 确认对话框 -->
    <ConfirmDialog />

    <!-- 全局通知 SnackBar -->
    <v-snackbar
      v-model="notifyState.show"
      :color="notifyState.color"
      :timeout="notifyState.timeout"
      location="top right"
    >
      <div v-if="notifyState.title" class="font-weight-bold mb-1">{{ notifyState.title }}</div>
      {{ notifyState.message }}
      <template #actions>
        <v-btn variant="text" icon="mdi-close" size="small" @click="notifyState.show = false" />
      </template>
    </v-snackbar>

    <!-- 玻璃材质设置弹窗 -->
    <GlassSettingsDialog
      v-model="showGlassSettings"
      @close="showGlassSettings = false"
    />

    <!-- 主题色设置弹窗 -->
    <PrimaryColorDialog
      v-model="showPrimaryColorDialog"
      @close="showPrimaryColorDialog = false"
    />

    <!-- 圆角设置弹窗 -->
    <BorderRadiusDialog
      v-model="showBorderRadiusDialog"
      @close="showBorderRadiusDialog = false"
    />

    <!-- 边框设置弹窗 -->
    <BorderDialog
      v-model="showBorderDialog"
      @close="showBorderDialog = false"
    />

    <!-- 阴影设置弹窗 -->
    <ShadowDialog
      v-model="showShadowDialog"
      @close="showShadowDialog = false"
    />

    <!-- 壁纸管理弹窗 -->
    <WallpaperDialog
      v-model="showWallpaperDialog"
      @close="showWallpaperDialog = false"
    />
  </v-app>
</template>

<style scoped>
/* 导航项 — 图标与文字收紧间距 + 整体居中 */
:deep(.v-navigation-drawer .v-list-item) {
  display: flex;
  justify-content: center;
}

/* 缩小图标与文字之间的默认 spacer（Vuetify 默认 32px） */
:deep(.v-navigation-drawer .v-list-item__spacer) {
  width: 8px !important;
  min-width: 8px !important;
}

.app-logo {
  width: 28px;
  height: 28px;
}
</style>
