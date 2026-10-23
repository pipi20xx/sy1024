import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import DefaultLayout from '@/layouts/DefaultLayout.vue'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { requiresAuth: false },
  },
  {
    path: '/',
    component: DefaultLayout,
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        name: 'home',
        component: () => import('@/views/HomeView.vue'),
      },
      {
        path: 'collections',
        name: 'collections',
        component: () => import('@/views/CollectionsView.vue'),
      },
      {
        path: 'collections/:filename',
        name: 'collectionDetail',
        component: () => import('@/views/CollectionDetailView.vue'),
      },
      {
        path: 'actors',
        name: 'actors',
        component: () => import('@/views/ActorsView.vue'),
      },
      {
        path: 'actors/:actorId',
        name: 'actorDetail',
        component: () => import('@/views/ActorDetailView.vue'),
      },
      {
        path: 'actors/tmdb/:tmdbId',
        name: 'actorDetailByTmdbId',
        component: () => import('@/views/ActorDetailView.vue'),
      },
      {
        path: 'tmdb-bgm-mapping',
        name: 'tmdbBgmMapping',
        component: () => import('@/views/TmdbBgmMappingView.vue'),
      },
      {
        path: 'tmdb-bgm-mapping/:tmdbId/:tmdbType',
        name: 'tmdbBgmMappingDetail',
        component: () => import('@/views/TmdbBgmMappingDetailView.vue'),
      },
      {
        path: 'tag-rules',
        name: 'tagRules',
        component: () => import('@/views/TagRulesView.vue'),
      },
      {
        path: 'tasks',
        name: 'tasks',
        component: () => import('@/views/TasksView.vue'),
      },
      {
        path: 'bangumi',
        name: 'bangumi',
        component: () => import('@/views/BangumiView.vue'),
      },
      {
        path: 'shenyi',
        name: 'shenyi',
        component: () => import('@/views/ShenYiConfigView.vue'),
      },
      {
        path: 'external-control',
        name: 'externalControl',
        component: () => import('@/views/ExternalControlView.vue'),
      },
      {
        path: 'cover-generator',
        name: 'coverGenerator',
        component: () => import('@/views/CoverGeneratorView.vue'),
      },
      {
        path: 'preview-generator',
        name: 'previewGenerator',
        component: () => import('@/views/PreviewGeneratorView.vue'),
      },
      {
        path: 'settings',
        name: 'settings',
        component: () => import('@/views/SettingsView.vue'),
      },
      {
        path: 'item/:itemType/:tmdbId',
        name: 'itemDetail',
        component: () => import('@/views/ItemDetailView.vue'),
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior(to, from, savedPosition) {
    // 浏览器前进/后退时恢复位置
    if (savedPosition) return savedPosition
    // 导航到新页面时回到顶部
    return { top: 0, left: 0 }
  },
})

// 导航守卫：未登录时跳转 login
router.beforeEach((to) => {
  const token = localStorage.getItem('access_token')
  if (to.meta.requiresAuth !== false && !token) {
    return { name: 'login' }
  } else if (to.name === 'login' && token) {
    return { name: 'home' }
  }
})

export default router
