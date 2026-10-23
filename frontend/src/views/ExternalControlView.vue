<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { externalControlApi, type AuditLog } from '@/api/externalControl'
defineOptions({ name: 'ExternalControlView' })
import { useNotification, useConfirm } from '@/composables'
import PasswordInput from '@/components/common/PasswordInput.vue'

const { notify } = useNotification()
const { confirm } = useConfirm()

const config = ref<{ api_token: string | null; audit_log_enabled: boolean }>({ api_token: null, audit_log_enabled: false })
const isLoading = ref(false)
const isSaving = ref(false)
const isGenerating = ref(false)

const logs = ref<AuditLog[]>([])
const logsTotal = ref(0)
const logsPage = ref(1)
const logsPageSize = ref(20)
const logsSearch = ref('')
const isLoadingLogs = ref(false)

onMounted(() => {
  loadConfig()
  loadLogs()
})

async function loadConfig() {
  isLoading.value = true
  try { config.value = await externalControlApi.getConfig() }
  catch (e: any) { notify('加载配置失败', e.message, 'error') }
  finally { isLoading.value = false }
}

async function handleSaveConfig() {
  isSaving.value = true
  try {
    await externalControlApi.updateConfig(config.value)
    notify('配置已保存', '', 'success')
  } catch (e: any) { notify('保存失败', e.message, 'error') }
  finally { isSaving.value = false }
}

async function handleGenerateToken() {
  const ok = await confirm({ title: '生成新 Token', content: '生成新 Token 后，旧 Token 将立即失效。确定继续？', confirmColor: 'warning' })
  if (!ok) return
  isGenerating.value = true
  try {
    const res = await externalControlApi.generateToken()
    config.value.api_token = res.token
    notify('Token 已生成', '请妥善保管，关闭后将无法再次查看完整 Token', 'success')
  } catch (e: any) { notify('生成失败', e.message, 'error') }
  finally { isGenerating.value = false }
}

async function loadLogs() {
  isLoadingLogs.value = true
  try {
    const res = await externalControlApi.getAuditLogs({ page: logsPage.value, size: logsPageSize.value, search: logsSearch.value || undefined })
    logs.value = res.items
    logsTotal.value = res.total
  } catch { /* ignore */ }
  finally { isLoadingLogs.value = false }
}

function handlePageChange(page: number) {
  logsPage.value = page
  loadLogs()
}

const docsUrl = computed(() => externalControlApi.getDocsUrl())
</script>

<template>
  <v-container fluid class="pa-6">
    <div class="d-flex flex-wrap align-center mb-6 ga-3">
      <div class="flex-grow-1">
        <h1 class="text-h5 font-weight-bold">外部控制 API</h1>
        <p class="text-caption text-medium-emphasis mt-1">管理外部 API 访问和审计日志</p>
      </div>
      <div class="d-flex ga-2 flex-wrap">
        <v-btn color="primary" variant="tonal" size="small" prepend-icon="mdi-book-open-outline"
          :href="docsUrl" target="_blank">
          API 文档
        </v-btn>
      </div>
    </div>

    <!-- 配置卡片 -->
    <v-card variant="outlined" rounded="xl" class="mb-4">
      <v-card-title class="d-flex align-center py-3">
        <v-icon icon="mdi-key-chain" class="mr-2" color="primary" />
        API 访问控制
      </v-card-title>
      <v-divider />
      <v-card-text>
        <div class="d-flex align-center justify-space-between py-2">
          <div>
            <div class="text-subtitle-1 font-weight-medium">开启访问审计</div>
            <div class="text-caption text-medium-emphasis">在系统日志中详细记录每一次外部 API 的请求信息。</div>
          </div>
          <v-switch v-model="config.audit_log_enabled" color="primary" hide-details density="compact" />
        </div>

        <v-divider class="my-4" />

        <div class="mb-2 text-subtitle-1 font-weight-medium">API Token</div>
        <v-row align="center" class="mb-4">
          <v-col cols="12" sm="6">
            <PasswordInput :model-value="config.api_token || '未设置'" label="API Token" density="compact" variant="outlined" readonly prepend-inner-icon="mdi-key">
              <template #append-inner>
                <v-btn size="x-small" variant="text" icon="mdi-refresh" :loading="isGenerating" @click="handleGenerateToken" />
              </template>
            </PasswordInput>
          </v-col>
          <v-col cols="12" sm="6" class="d-flex align-end">
            <v-btn color="warning" variant="tonal" prepend-icon="mdi-key-plus" :loading="isGenerating" @click="handleGenerateToken">
              生成新 Token
            </v-btn>
          </v-col>
        </v-row>

        <v-btn color="primary" variant="tonal" prepend-icon="mdi-content-save" :loading="isSaving" @click="handleSaveConfig">
          保存配置
        </v-btn>
      </v-card-text>
    </v-card>

    <!-- 审计日志 -->
    <v-card variant="outlined" rounded="xl">
      <v-card-title class="d-flex align-center py-3">
        <v-icon icon="mdi-file-document-outline" class="mr-2" color="primary" />
        审计日志
        <v-chip size="x-small" variant="tonal" class="ml-2">{{ logsTotal }} 条</v-chip>
        <v-spacer />
        <v-text-field v-model="logsSearch" placeholder="搜索..." density="compact" variant="outlined" hide-details
          prepend-inner-icon="mdi-magnify" clearable max-width="200" @keyup.enter="loadLogs" @click:clear="loadLogs" />
      </v-card-title>
      <v-divider />

      <v-table v-if="logs.length" density="compact">
        <thead>
          <tr>
            <th class="text-left">时间</th>
            <th class="text-left">方法</th>
            <th class="text-left">路径</th>
            <th class="text-center">状态</th>
            <th class="text-left">IP</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="log in logs" :key="log.id">
            <td class="text-caption">{{ log.timestamp?.substring(0, 19).replace('T', ' ') }}</td>
            <td><v-chip size="x-small" variant="tonal" label>{{ log.method }}</v-chip></td>
            <td class="text-body-2 text-truncate" max-width="200px">{{ log.path }}</td>
            <td class="text-center">
              <v-chip :color="log.status_code < 400 ? 'success' : 'error'" size="x-small" variant="tonal" label>
                {{ log.status_code }}
              </v-chip>
            </td>
            <td class="text-caption">{{ log.ip }}</td>
          </tr>
        </tbody>
      </v-table>

      <div v-else-if="isLoadingLogs" class="text-center pa-4">
        <v-progress-circular indeterminate color="primary" />
      </div>

      <v-card-text v-else class="text-center text-medium-emphasis pa-8">
        <v-icon size="48" color="grey-lighten-1">mdi-file-cancel-outline</v-icon>
        <p class="mt-2">暂无审计日志</p>
      </v-card-text>

      <v-divider v-if="logsTotal > logsPageSize" />
      <v-card-actions v-if="logsTotal > logsPageSize" class="justify-center">
        <v-pagination :model-value="logsPage" :length="Math.ceil(logsTotal / logsPageSize)" @update:model-value="handlePageChange" />
      </v-card-actions>
    </v-card>
  </v-container>
</template>