<script setup lang="ts">
import { ref, reactive, watch, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Check, Refresh, Delete } from '@element-plus/icons-vue'

interface AlertRecord {
  alert_id: string
  detection_id: string
  level: string
  message: string
  fire_count: number
  smoke_count: number
  is_read: boolean
  status: string
  handled_by: string
  handled_at: string
  handled_note: string
  created_at: string
}

const alerts = ref<AlertRecord[]>([])
const loading = ref(false)

const filterLevel = ref('')
const filterStatus = ref('')
const filterRead = ref('')
const keyword = ref('')
const currentPage = ref(1)
const pageSize = ref(20)
const total = ref(0)

const stats = reactive({
  total: 0,
  unread_count: 0,
  pending: 0,
  confirmed: 0,
  ignored: 0,
  critical: 0,
  high: 0,
  medium: 0,
  low: 0
})

const operator = ref(localStorage.getItem('ffd_operator') || '管理员')

const buildQuery = () => {
  const p = new URLSearchParams()
  p.set('page', String(currentPage.value))
  p.set('page_size', String(pageSize.value))
  if (filterLevel.value) p.set('level', filterLevel.value)
  if (filterStatus.value) p.set('status', filterStatus.value)
  if (filterRead.value) p.set('is_read', String(filterRead.value === 'read'))
  if (keyword.value.trim()) p.set('keyword', keyword.value.trim())
  return p.toString()
}

const fetchAlerts = async (silent = false) => {
  if (!silent) loading.value = true
  try {
    const res = await fetch(`/api/alerts?${buildQuery()}`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    alerts.value = data.list || []
    total.value = data.total || 0
  } catch (err) {
    if (!silent) ElMessage.error(`获取告警失败: ${err}`)
  } finally {
    loading.value = false
  }
}

const fetchStats = async () => {
  try {
    const res = await fetch('/api/alerts/stats')
    if (!res.ok) return
    const data = await res.json()
    Object.assign(stats, data)
  } catch {
    /* 静默失败，下次轮询重试 */
  }
}

const refreshAll = async (silent = false) => {
  await Promise.all([fetchAlerts(silent), fetchStats()])
}

/* ── 处置：确认 / 忽略 ── */
const handleAlert = async (alert: AlertRecord, action: 'confirm' | 'ignore') => {
  let note = ''
  try {
    if (action === 'confirm') {
      const { value } = await ElMessageBox.prompt(
        '请填写处置备注（选填）',
        '确认处置',
        {
          confirmButtonText: '确认处置',
          cancelButtonText: '取消',
          inputPlaceholder: '如：已通知巡护队现场核查',
          inputValue: '',
          inputValidator: () => true
        }
      )
      note = value || ''
    } else {
      await ElMessageBox.confirm(
        '确认将该告警标记为「已忽略」（判定为误报）？',
        '忽略告警',
        { type: 'warning', confirmButtonText: '忽略', cancelButtonText: '取消' }
      )
    }
  } catch {
    return // 用户取消
  }

  try {
    const res = await fetch(`/api/alerts/${alert.alert_id}/handle`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, operator: operator.value || '管理员', note })
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    await refreshAll(true)
    ElMessage.success(action === 'confirm' ? '已确认处置' : '已忽略')
  } catch (err) {
    ElMessage.error(`处置失败: ${err}`)
  }
}

const markAsRead = async (alert: AlertRecord) => {
  try {
    const res = await fetch(`/api/alerts/${alert.alert_id}/read`, { method: 'PUT' })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    alert.is_read = true
    await fetchStats()
    ElMessage.success('已标记为已读')
  } catch (err) {
    ElMessage.error(`操作失败: ${err}`)
  }
}

const markAllRead = async () => {
  try {
    const res = await fetch('/api/alerts/read-all', { method: 'PUT' })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    await refreshAll(true)
    ElMessage.success(data.message || '全部已读')
  } catch (err) {
    ElMessage.error(`操作失败: ${err}`)
  }
}

const removeAlert = async (alert: AlertRecord) => {
  try {
    await ElMessageBox.confirm('确认删除该告警记录？', '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    const res = await fetch(`/api/alerts/${alert.alert_id}`, { method: 'DELETE' })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    await refreshAll(true)
    ElMessage.success('已删除')
  } catch (err) {
    ElMessage.error(`删除失败: ${err}`)
  }
}

const clearAll = async () => {
  try {
    await ElMessageBox.confirm('确认清空全部告警记录？该操作不可恢复。', '警告', {
      type: 'warning',
      confirmButtonText: '确认清空',
      confirmButtonClass: 'el-button--danger'
    })
  } catch {
    return
  }
  try {
    const res = await fetch('/api/alerts/clear', { method: 'DELETE' })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    currentPage.value = 1
    await refreshAll(true)
    ElMessage.success('已清空')
  } catch (err) {
    ElMessage.error(`清空失败: ${err}`)
  }
}

const getLevelTag = (level: string) => {
  const map: Record<string, { text: string; type: string }> = {
    critical: { text: '紧急', type: 'danger' },
    high: { text: '高', type: 'warning' },
    medium: { text: '中', type: 'primary' },
    low: { text: '低', type: 'info' }
  }
  return map[level] || { text: level, type: 'info' }
}

const getLevelColor = (level: string) => {
  const map: Record<string, string> = {
    critical: '#ef4444', high: '#f59e0b', medium: '#3b82f6', low: '#94a3b8'
  }
  return map[level] || '#94a3b8'
}

const getStatusTag = (status: string) => {
  const map: Record<string, { text: string; type: string }> = {
    pending: { text: '待处置', type: 'danger' },
    confirmed: { text: '已确认处置', type: 'success' },
    ignored: { text: '已忽略', type: 'info' }
  }
  return map[status] || map.pending
}

const handlePageChange = (page: number) => {
  currentPage.value = page
  fetchAlerts()
}

// 筛选条件变化时回到第一页并重新查询
watch([filterLevel, filterStatus, filterRead, keyword], () => {
  currentPage.value = 1
  fetchAlerts()
})

let pollTimer: number | undefined

onMounted(() => {
  refreshAll()
  // 10 秒轮询，保证新告警自动出现（无需手动刷新）
  pollTimer = window.setInterval(() => refreshAll(true), 10000)
})

onUnmounted(() => {
  if (pollTimer) window.clearInterval(pollTimer)
})
</script>

<template>
  <div class="alert-center">
    <el-card shadow="hover">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <span class="card-title">告警中心</span>
            <el-badge :value="stats.pending" :max="99" :hidden="!stats.pending" class="unread-badge" />
          </div>
          <div class="header-actions">
            <el-button :icon="Check" @click="markAllRead" :disabled="!stats.unread_count">全部已读</el-button>
            <el-button :icon="Refresh" @click="refreshAll()">刷新</el-button>
            <el-button :icon="Delete" type="danger" plain :disabled="!stats.total" @click="clearAll">
              清空
            </el-button>
          </div>
        </div>
      </template>

      <div class="stats-bar">
        <div class="stat-item" style="background:#fef2f2;">
          <span class="stat-count" style="color:#ef4444;">{{ stats.critical }}</span>
          <span class="stat-text">紧急待处置</span>
        </div>
        <div class="stat-item" style="background:#fffbeb;">
          <span class="stat-count" style="color:#f59e0b;">{{ stats.high }}</span>
          <span class="stat-text">高级待处置</span>
        </div>
        <div class="stat-item" style="background:#eff6ff;">
          <span class="stat-count" style="color:#3b82f6;">{{ stats.pending }}</span>
          <span class="stat-text">待处置总数</span>
        </div>
        <div class="stat-item" style="background:#f0fdf4;">
          <span class="stat-count" style="color:#22c55e;">{{ stats.confirmed }}</span>
          <span class="stat-text">已确认处置</span>
        </div>
      </div>

      <div class="filter-bar">
        <el-select v-model="filterStatus" placeholder="处置状态" clearable size="small" style="width:130px">
          <el-option label="待处置" value="pending" />
          <el-option label="已确认处置" value="confirmed" />
          <el-option label="已忽略" value="ignored" />
        </el-select>
        <el-select v-model="filterLevel" placeholder="告警级别" clearable size="small" style="width:120px">
          <el-option label="紧急" value="critical" />
          <el-option label="高级" value="high" />
          <el-option label="中级" value="medium" />
          <el-option label="低级" value="low" />
        </el-select>
        <el-select v-model="filterRead" placeholder="已读状态" clearable size="small" style="width:120px">
          <el-option label="未读" value="unread" />
          <el-option label="已读" value="read" />
        </el-select>
        <el-input
          v-model="keyword"
          placeholder="搜索告警内容"
          clearable
          size="small"
          style="width: 200px"
        />
        <span class="filter-count">共 {{ total }} 条</span>
      </div>

      <div class="alert-list" v-loading="loading">
        <div
          v-for="alert in alerts"
          :key="alert.alert_id"
          class="alert-card"
          :class="[`st-${alert.status}`, { unread: !alert.is_read && alert.status === 'pending' }]"
        >
          <div class="alert-left">
            <div class="level-indicator" :style="{ backgroundColor: getLevelColor(alert.level) }"></div>
            <div class="alert-content">
              <div class="alert-header">
                <el-tag :type="getLevelTag(alert.level).type as any" size="small" effect="dark">
                  {{ getLevelTag(alert.level).text }}
                </el-tag>
                <el-tag :type="getStatusTag(alert.status).type as any" size="small" effect="plain">
                  {{ getStatusTag(alert.status).text }}
                </el-tag>
                <span class="alert-time">{{ alert.created_at }}</span>
              </div>
              <div class="alert-message">{{ alert.message }}</div>
              <div class="alert-meta">
                <span v-if="alert.fire_count" class="meta-fire">火焰 {{ alert.fire_count }} 处</span>
                <span v-if="alert.smoke_count" class="meta-smoke">烟雾 {{ alert.smoke_count }} 处</span>
                <span class="meta-id">{{ alert.alert_id }}</span>
              </div>
              <div v-if="alert.status !== 'pending'" class="handle-info">
                <span>{{ alert.status === 'confirmed' ? '已确认' : '已忽略' }} by
                  <b>{{ alert.handled_by || '-' }}</b></span>
                <span v-if="alert.handled_at"> · {{ alert.handled_at }}</span>
                <span v-if="alert.handled_note" class="handle-note"> · 备注：{{ alert.handled_note }}</span>
              </div>
            </div>
          </div>
          <div class="alert-actions">
            <template v-if="alert.status === 'pending'">
              <el-button size="small" type="danger" plain @click="handleAlert(alert, 'confirm')">
                确认处置
              </el-button>
              <el-button size="small" plain @click="handleAlert(alert, 'ignore')">忽略</el-button>
            </template>
            <el-button
              v-else-if="!alert.is_read"
              size="small"
              text
              type="primary"
              @click="markAsRead(alert)"
            >
              标记已读
            </el-button>
            <el-button size="small" text type="danger" @click="removeAlert(alert)">删除</el-button>
          </div>
        </div>

        <el-empty v-if="!alerts.length && !loading" description="暂无告警记录" />
      </div>

      <div class="pager" v-if="total > pageSize">
        <el-pagination
          layout="prev, pager, next"
          :total="total"
          :page-size="pageSize"
          :current-page="currentPage"
          @current-change="handlePageChange"
        />
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.alert-center { height: 100%; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.header-left { display: flex; align-items: center; gap: 12px; }
.card-title { font-size: 16px; font-weight: 600; color: #303133; }
.header-actions { display: flex; gap: 8px; }

.stats-bar { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px; }
.stat-item { display: flex; flex-direction: column; align-items: center; padding: 14px; border-radius: 8px; }
.stat-count { font-size: 24px; font-weight: 600; }
.stat-text { font-size: 12px; color: #909399; margin-top: 4px; }

.filter-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.filter-count { font-size: 13px; color: #909399; margin-left: auto; }

.alert-list { display: flex; flex-direction: column; gap: 8px; }
.alert-card {
  display: flex; align-items: flex-start; justify-content: space-between;
  padding: 16px; border-radius: 8px; background: #fafafa;
  border-left: 3px solid transparent; transition: all 0.3s;
}
.alert-card:hover { background: #f0f0f0; }
.alert-card.unread { background: #fffbeb; border-left-color: #f59e0b; }
.alert-card.st-confirmed { border-left-color: #22c55e; }
.alert-card.st-ignored { border-left-color: #cbd5e1; background: #f8fafc; }
.alert-card.st-ignored .alert-message { color: #94a3b8; }

.alert-left { display: flex; gap: 12px; flex: 1; min-width: 0; }
.level-indicator { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; margin-top: 6px; }
.alert-content { flex: 1; min-width: 0; }
.alert-header { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.alert-time { font-size: 12px; color: #909399; }
.alert-message { font-size: 14px; color: #303133; line-height: 1.5; margin-bottom: 6px; }
.alert-meta { display: flex; align-items: center; gap: 12px; font-size: 12px; }
.meta-fire { color: #ef4444; font-weight: 500; }
.meta-smoke { color: #f59e0b; font-weight: 500; }
.meta-id { color: #c0c4cc; margin-left: auto; }

.handle-info {
  margin-top: 6px; font-size: 12px; color: #64748b;
  background: #f1f5f9; border-radius: 4px; padding: 4px 8px;
}
.handle-note { color: #475569; }

.alert-actions { display: flex; gap: 4px; flex-shrink: 0; align-items: center; }

.pager { display: flex; justify-content: center; margin-top: 16px; }
</style>
