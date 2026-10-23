/**
 * 认证 composable
 * 登录/登出/2FA
 */
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { loginApi, type LoginParams } from '@/api/auth'

export function useAuth() {
  const router = useRouter()
  const loading = ref(false)
  const showOtp = ref(false)

  const formValue = reactive<LoginParams>({
    username: '',
    password: '',
    otp_code: '',
  })

  const handleLogin = async () => {
    if (!formValue.username || !formValue.password) {
      throw new Error('请填写完整信息')
    }

    loading.value = true
    try {
      const res = await loginApi(formValue)

      if (res.status === '2fa_required') {
        showOtp.value = true
        localStorage.setItem('access_token', res.access_token)
        return { status: '2fa_required' }
      } else {
        localStorage.setItem('access_token', res.access_token)
        localStorage.setItem('username', res.username)
        router.push('/')
        return { status: 'success', username: res.username }
      }
    } catch (err: any) {
      if (showOtp.value) {
        formValue.otp_code = ''
      }
      throw err
    } finally {
      loading.value = false
    }
  }

  const resetOtp = () => {
    showOtp.value = false
    formValue.otp_code = ''
  }

  return {
    formValue,
    loading,
    showOtp,
    handleLogin,
    resetOtp,
  }
}
