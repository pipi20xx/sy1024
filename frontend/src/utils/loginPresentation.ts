import type { GlassAppearance, GlassOpticalPreset } from '@/glass'

export type LoginVisualProfile = 'classic' | 'glass' | 'transparent'

export interface LoginGlassPreference {
  /** 用户选择的玻璃材质。 */
  appearance: GlassAppearance
  /** 用户保存的局部非均匀形变强度。 */
  deformationStrength: number
  /** 用户保存的轨迹、尾波与惯性强度。 */
  flowStrength: number
  /** 用户选择的方案；登录页保持方案身份但只强制高质量能力。 */
  preset: GlassOpticalPreset
  /** 用户保存的方向反射亮度。 */
  reflectionStrength: number
  /** 用户保存的玻璃内部透射亮度。 */
  transmissionStrength: number
  /** 用户保存的统一采样平移强度。 */
  translationStrength: number
  /** 用户保存的壁纸可见度与材质遮罩强度。 */
  transparencyStrength: number
}

export interface LoginBackgroundLayer {
  /** 跨登录状态保持稳定的呈现槽位。 */
  key: 'back' | 'front'
  /** 壁纸在交叉淡化中的职责；standby 槽位可提前准备下一张。 */
  role: 'active' | 'previous' | 'standby'
  /** 当前槽位显示的壁纸地址。 */
  url: string
}

/** 将实际主题解析为互斥的登录视觉 profile。 */
export function resolveLoginVisualProfile(theme: string): LoginVisualProfile {
  if (theme === 'glass' || theme === 'acg') return 'glass'
  if (theme === 'transparent' || theme === 'liquid') return 'transparent'
  return 'classic'
}

export function createLoginBackgroundLayers(activeUrl = ''): LoginBackgroundLayer[] {
  return [
    { key: 'back', role: 'active', url: activeUrl },
    { key: 'front', role: 'standby', url: '' },
  ]
}

export function prepareLoginBackgroundLayer(layers: LoginBackgroundLayer[], url: string): LoginBackgroundLayer[] {
  return layers.map((layer) =>
    layer.role === 'standby' ? { ...layer, url } : layer
  )
}

export function activateLoginBackgroundLayer(layers: LoginBackgroundLayer[]): LoginBackgroundLayer[] {
  return layers.map((layer) => {
    if (layer.role === 'standby') return { ...layer, role: 'active' }
    if (layer.role === 'active') return { ...layer, role: 'previous' }
    return layer
  })
}

export function settleLoginBackgroundLayers(layers: LoginBackgroundLayer[]): LoginBackgroundLayer[] {
  return layers.map((layer) => {
    if (layer.role === 'previous') return { ...layer, role: 'standby', url: '' }
    return layer
  })
}
