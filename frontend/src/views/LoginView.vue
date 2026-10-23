<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { loginApi } from '@/api/auth'
import { useNotification } from '@/composables'
import PasswordInput from '@/components/common/PasswordInput.vue'

defineOptions({ name: 'LoginView' })

const router = useRouter()
const { notify, state: notifyState } = useNotification()

const loading = ref(false)
const showOtp = ref(false)
const form = reactive({ username: '', password: '', otp_code: '' })

async function handleLogin() {
  if (!form.username || !form.password) {
    notify('提示', '请输入用户名和密码', 'warning')
    return
  }
  loading.value = true
  try {
    const res = await loginApi({ username: form.username, password: form.password, otp_code: form.otp_code || undefined })
    if (res.access_token) {
      localStorage.setItem('access_token', res.access_token)
      localStorage.setItem('username', form.username)
      notify('登录成功', '', 'success')
      router.push('/')
    } else if (res.require_otp) {
      showOtp.value = true
    }
  } catch (e: any) {
    notify('登录失败', e.message || '凭据错误', 'error')
  } finally {
    loading.value = false
  }
}

function resetOtp() {
  showOtp.value = false
  form.otp_code = ''
}
</script>

<template>
  <v-app>
    <!-- Liquid Glass 背景光源 -->
    <div class="login-light-wells" />

    <v-main>
      <v-container fluid class="fill-height d-flex align-center justify-center">
        <!-- 登录卡片 — Liquid Glass -->
        <v-card width="440" max-width="92vw" rounded="xl" class="pa-2">
          <!-- 顶部装饰 -->
          <v-card-title class="text-center pt-8 pb-2">
          <v-avatar class="liquid-avatar" size="64" rounded="xl">
            <img src="/favicon.svg" alt="SYTMDB" class="app-logo" />
          </v-avatar>
            <div class="text-h5 font-weight-bold mt-3 liquid-glass-subtitle">SYTMDB</div>
            <div class="text-body-2 text-medium-emphasis mt-1">影视元数据管理系统</div>
          </v-card-title>

          <v-divider class="mx-6" />

          <v-card-text class="px-6 pb-2 pt-6">
            <v-form @submit.prevent="handleLogin">
              <v-text-field
                v-if="!showOtp"
                v-model="form.username"
                label="用户名"
                prepend-inner-icon="mdi-account"
                variant="outlined"
                density="comfortable"
                rounded="xl"
              />
              <PasswordInput
                v-if="!showOtp"
                v-model="form.password"
                label="密码"
                prepend-inner-icon="mdi-key"
                variant="outlined"
                density="comfortable"
                rounded="xl"
                @keyup.enter="handleLogin"
              />
              <v-text-field
                v-if="showOtp"
                v-model="form.otp_code"
                label="双重验证码"
                placeholder="请输入 6 位动态验证码"
                maxlength="6"
                prepend-inner-icon="mdi-shield-lock"
                variant="outlined"
                density="comfortable"
                rounded="xl"
                @keyup.enter="handleLogin"
              />
              <v-btn v-if="showOtp" variant="tonal" size="small" @click="resetOtp" class="mb-2">返回账号登录</v-btn>
              <!-- 登录按钮 — Liquid Glass 强调 -->
              <v-btn type="submit" block size="large" :loading="loading" rounded="xl" color="primary" variant="tonal">
                登录
              </v-btn>

              <!-- 默认账号说明 -->
              <div class="text-center mt-4">
                <v-chip size="small" variant="tonal" color="info" label>
                  <v-icon start size="14">mdi-information-outline</v-icon>
                  默认账号: admin / admin123
                </v-chip>
              </div>
            </v-form>
          </v-card-text>

          <v-card-text class="text-center pb-6 pt-0">
            <span class="text-caption text-medium-emphasis">请输入管理员凭据以访问系统</span>
          </v-card-text>
        </v-card>
      </v-container>
    </v-main>

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
  </v-app>
</template>

<style scoped>
.app-logo {
  width: 40px;
  height: 40px;
}
</style>
