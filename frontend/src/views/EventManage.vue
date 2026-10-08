<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, View, Refresh, Warning, Check, Close } from '@element-plus/icons-vue'

interface EventItem {
  id: number
  event_no: string
  level: string
  status: string
  source_type: string
  source_ref: string
  first_seen_at: string
  last_seen_at: string
  fire_count: number
  smoke_count: number
  max_confidence: number
  risk_score: number
  hit_count: number
  handled_by: string
  created_at: string
}

interface EventDetail extends EventItem {
  location: string
  handled_at: string
  handled_note: string
  updated_at: string
  media: Array<{
    id: number
    media_type: string
    role: string
    file_url: string
    file_size: number
    width: number
    height: number
  }>
  logs: Array<{
    id: number
    action: string
    operator: string
    note: string
    created_at: string
  }>
}

const loading = ref(false)
const events = ref<EventItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const keyword = ref('')
const levelFilter = ref('')
const statusFilter = ref('')
const sourceFilter = ref('')

// 详情抽屉
const drawerVisible = ref(false)
const currentEvent = ref<EventDetail | null>(null)
const drawerLoading = ref(false)

// 处置
const handleDialogVisible = ref(false)
const handleAction = ref('')
const handleOperator = ref(localStorage.getItem('ffd_operator') || '管理员')
const handleNote = ref('')

const token = () => localStorage.getItem('token') || ''
const authHeaders = () => ({ 'Authorization': `Bearer ${token()}`, 'Content-Type': 'application/json' })

const LEVEL_MAP: Record<string, { text: string; type: string; color: string }> = {
  critical: { text: '紧急', type: 'danger', color: '#ef4444' },
  high: { text: '高', type: 'warning', color: '#f59e0b' },
  medium: { text: '中', type: 'primary', color: '#3b82f6' },
  low: { text: '低', type: 'info', color: '#94a3b8' }
}
const STATUS_MAP: Record<string, { text: string; type: string }> = {
  open: { text: '待处置', type: 'danger' },
  handling: { text: '处置中', type: 'warning' },
  closed: { text: '已结案', type: 'success' },
  false_alarm: { text: '误报', type: 'info' }
}
const SOURCE_MAP: Record<string, string> = {
  image: '图像检测',
  video: '视频检测',
  stream: '实时监控',
  aerial: '航拍分析'
}
const levelInfo = (level: string) => LEVEL_MAP[level] || LEVEL_MAP.low
const statusInfo = (status: string) => STATUS_MAP[status] || STATUS_MAP.open
const sourceLabel = (t: string) => SOURCE_MAP[t] || t

const fetchEvents = async () => {
  loading.value = true
  try {
    const params = new URLSearchParams({
      page: String(page.value),
      page_size: String(pageSize.value)
    })
    if (keyword.value) params.set('keyword', keyword.value)
    if (levelFilter.value) params.set('level', levelFilter.value)
    if (statusFilter.value) params.set('status', statusFilter.value)
    if (sourceFilter.value) params.set('source_type', sourceFilter.value)
    const res = await fetch(`/api/events?${params}`, { headers: authHeaders() })
    if (res.status === 401) {
      ElMessage.error('登录已过期')
      localStorage.clear()
      window.location.href = '/login'
      return
    }
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    events.value = data.list || []
    total.value = data.total || 0
  } catch (err: any) {
    ElMessage.error('加载失败：' + (err.message || '网络异常'))
  } finally {
    loading.value = false
  }
}

const openDetail = async (eventNo: string) => {
  drawerLoading.value = true
  drawerVisible.value = true
  try {
    const res = await fetch(`/api/events/${eventNo}`, { headers: authHeaders() })
    if (!res.ok) throw new Error('加载失败')
    currentEvent.value = await res.json()
  } catch (err: any) {
    ElMessage.error(err.message || '加载失败')
  } finally {
    drawerLoading.value = false
  }
}

const openHandle = (action: string) => {
  handleAction.value = action
  handleNote.value = ''
  handleDialogVisible.value = true
}

const submitHandle = async () => {
  if (!currentEvent.value) return
  if (!handleOperator.value.trim()) {
    ElMessage.warning('请填写处置人')
    return
  }
  try {
    const res = await fetch(`/api/events/${currentEvent.value.event_no}/handle`, {
      method: 'PUT',
      headers: authHeaders(),
      body: JSON.stringify({
        action: handleAction.value,
        operator: handleOperator.value.trim(),
        note: handleNote.value.trim()
      })
    })
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || '处置失败')
    localStorage.setItem('ffd_operator', handleOperator.value.trim())
    ElMessage.success('处置成功')
    handleDialogVisible.value = false
    drawerVisible.value = false
    await fetchEvents()
  } catch (err: any) {
    ElMessage.error('处置失败：' + (err.message || '网络异常'))
  }
}

const handleSearch = () => {
  page.value = 1
  fetchEvents()
}

const handlePageChange = (p: number) => {
  page.value = p
  fetchEvents()
}

onMounted(fetchEvents)
</script>

<template>
  <div class="event-manage-page">
    <!-- 筛选栏 -->
    <el-card shadow="never" class="search-card">
      <div class="search-row">
        <div class="search-left">
          <el-input
            v-model="keyword"
            placeholder="搜索事件编号"
            clearable
            :prefix-icon="Search"
            style="width: 220px"
            @keyup.enter="handleSearch"
            @clear="handleSearch"
          />
          <el-select v-model="levelFilter" placeholder="级别" clearable style="width: 110px" @change="handleSearch">
            <el-option label="紧急" value="critical" />
            <el-option label="高" value="high" />
            <el-option label="中" value="medium" />
            <el-option label="低" value="low" />
          </el-select>
          <el-select v-model="statusFilter" placeholder="状态" clearable style="width: 110px" @change="handleSearch">
            <el-option label="待处置" value="open" />
            <el-option label="处置中" value="handling" />
            <el-option label="已结案" value="closed" />
            <el-option label="误报" value="false_alarm" />
          </el-select>
          <el-select v-model="sourceFilter" placeholder="来源" clearable style="width: 130px" @change="handleSearch">
            <el-option label="图像检测" value="image" />
            <el-option label="视频检测" value="video" />
            <el-option label="实时监控" value="stream" />
            <el-option label="航拍分析" value="aerial" />
          </el-select>
          <el-button :icon="Search" type="primary" @click="handleSearch">搜索</el-button>
        </div>
        <div class="search-right">
          <el-button :icon="Refresh" @click="fetchEvents">刷新</el-button>
        </div>
      </div>
    </el-card>

    <!-- 事件列表 -->
    <el-card shadow="never" class="table-card">
      <el-table :data="events" v-loading="loading" stripe style="width: 100%" @row-dblclick="(row: EventItem) => openDetail(row.event_no)">
        <el-table-column label="事件编号" width="220">
          <template #default="{ row }">
            <el-link type="primary" @click="openDetail(row.event_no)" :underline="false" class="mono">
              {{ row.event_no }}
            </el-link>
          </template>
        </el-table-column>
        <el-table-column label="级别" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="levelInfo(row.level).type as any" size="small" effect="dark">
              {{ levelInfo(row.level).text }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="statusInfo(row.status).type as any" size="small">
              {{ statusInfo(row.status).text }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="100">
          <template #default="{ row }">
            <span>{{ sourceLabel(row.source_type) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="火焰" width="60" align="center">
          <template #default="{ row }">
            <span :class="{ 'text-danger': row.fire_count > 0 }">{{ row.fire_count }}</span>
          </template>
        </el-table-column>
        <el-table-column label="烟雾" width="60" align="center">
          <template #default="{ row }">
            <span :class="{ 'text-warning': row.smoke_count > 0 }">{{ row.smoke_count }}</span>
          </template>
        </el-table-column>
        <el-table-column label="风险分" width="80" align="center">
          <template #default="{ row }">
            <span :style="{ color: row.risk_score >= 70 ? '#ef4444' : row.risk_score >= 40 ? '#f59e0b' : '#606266' }">
              {{ row.risk_score }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="命中次数" width="80" align="center">
          <template #default="{ row }">
            <span>{{ row.hit_count }}</span>
          </template>
        </el-table-column>
        <el-table-column label="首次发现" width="170">
          <template #default="{ row }">
            <span>{{ row.first_seen_at }}</span>
          </template>
        </el-table-column>
        <el-table-column label="处置人" width="100">
          <template #default="{ row }">
            <span v-if="row.handled_by">{{ row.handled_by }}</span>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ row }">
            <el-button :icon="View" size="small" @click="openDetail(row.event_no)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap" v-if="total > pageSize">
        <el-pagination
          background
          layout="prev, pager, next, total"
          :total="total"
          :page-size="pageSize"
          :current-page="page"
          @current-change="handlePageChange"
        />
      </div>
    </el-card>

    <!-- 详情抽屉 -->
    <el-drawer
      v-model="drawerVisible"
      title="事件详情"
      size="680px"
      :destroy-on-close="true"
    >
      <div v-if="drawerLoading" v-loading="true" style="height:200px"></div>
      <div v-else-if="currentEvent" class="event-detail">
        <!-- 基本信息 -->
        <div class="detail-section">
          <div class="detail-header">
            <h3 class="mono">{{ currentEvent.event_no }}</h3>
            <div class="detail-tags">
              <el-tag :type="levelInfo(currentEvent.level).type as any" size="small" effect="dark">
                {{ levelInfo(currentEvent.level).text }}
              </el-tag>
              <el-tag :type="statusInfo(currentEvent.status).type as any" size="small">
                {{ statusInfo(currentEvent.status).text }}
              </el-tag>
              <el-tag size="small" effect="plain">{{ sourceLabel(currentEvent.source_type) }}</el-tag>
            </div>
          </div>
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="首次发现">{{ currentEvent.first_seen_at }}</el-descriptions-item>
            <el-descriptions-item label="最近命中">{{ currentEvent.last_seen_at }}</el-descriptions-item>
            <el-descriptions-item label="火焰数量">
              <span :class="{ 'text-danger': currentEvent.fire_count > 0 }">{{ currentEvent.fire_count }} 处</span>
            </el-descriptions-item>
            <el-descriptions-item label="烟雾数量">
              <span :class="{ 'text-warning': currentEvent.smoke_count > 0 }">{{ currentEvent.smoke_count }} 处</span>
            </el-descriptions-item>
            <el-descriptions-item label="最高置信度">{{ (currentEvent.max_confidence * 100).toFixed(1) }}%</el-descriptions-item>
            <el-descriptions-item label="风险分">
              <span :style="{ color: currentEvent.risk_score >= 70 ? '#ef4444' : currentEvent.risk_score >= 40 ? '#f59e0b' : '#606266', fontWeight: 600 }">
                {{ currentEvent.risk_score }}/100
              </span>
            </el-descriptions-item>
            <el-descriptions-item label="命中次数">{{ currentEvent.hit_count }} 次</el-descriptions-item>
            <el-descriptions-item label="来源标识">{{ currentEvent.source_ref || '-' }}</el-descriptions-item>
            <el-descriptions-item label="点位" :span="2">{{ currentEvent.location || '未标注' }}</el-descriptions-item>
          </el-descriptions>
        </div>

        <!-- 媒体 -->
        <div class="detail-section" v-if="currentEvent.media && currentEvent.media.length">
          <h4>关联媒体</h4>
          <div class="media-grid">
            <div v-for="m in currentEvent.media" :key="m.id" class="media-item">
              <div class="media-preview">
                <img :src="m.file_url" :alt="m.role" v-if="m.media_type === 'image'" />
                <span v-else class="media-placeholder">视频</span>
              </div>
              <div class="media-info">
                <el-tag size="small" effect="plain">
                  {{ m.role === 'original' ? '原图' : m.role === 'annotated' ? '标注' : m.role }}
                </el-tag>
                <span v-if="m.width" class="media-size">{{ m.width }}×{{ m.height }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 处置流水 -->
        <div class="detail-section" v-if="currentEvent.logs && currentEvent.logs.length">
          <h4>处置流水</h4>
          <el-timeline>
            <el-timeline-item
              v-for="log in currentEvent.logs"
              :key="log.id"
              :timestamp="log.created_at"
              placement="top"
            >
              <el-tag :type="log.action === 'confirm' ? 'success' : log.action === 'ignore' ? 'info' : 'primary'" size="small">
                {{ log.action === 'confirm' ? '确认处置' : log.action === 'ignore' ? '忽略' : log.action === 'close' ? '结案' : '标记误报' }}
              </el-tag>
              <span style="margin-left:8px;color:#606266">{{ log.operator }}</span>
              <span v-if="log.note" style="margin-left:8px;color:#909399">— {{ log.note }}</span>
            </el-timeline-item>
          </el-timeline>
        </div>

        <!-- 处置操作 -->
        <div class="detail-section" v-if="currentEvent.status === 'open' || currentEvent.status === 'handling'">
          <h4>处置操作</h4>
          <div class="handle-actions">
            <el-button type="danger" :icon="Warning" @click="openHandle('confirm')">确认处置</el-button>
            <el-button type="info" plain :icon="Close" @click="openHandle('ignore')">标记误报</el-button>
            <el-button type="primary" plain @click="openHandle('close')">结案</el-button>
          </div>
        </div>
        <div class="detail-section" v-else>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="处置人">{{ currentEvent.handled_by || '-' }}</el-descriptions-item>
            <el-descriptions-item label="处置时间">{{ currentEvent.handled_at || '-' }}</el-descriptions-item>
            <el-descriptions-item label="处置备注">{{ currentEvent.handled_note || '-' }}</el-descriptions-item>
          </el-descriptions>
        </div>
      </div>
    </el-drawer>

    <!-- 处置弹窗 -->
    <el-dialog v-model="handleDialogVisible" title="处置确认" width="440px" :close-on-click-modal="false">
      <p style="margin-bottom:12px;color:#606266">
        操作：<el-tag size="small">{{ handleAction === 'confirm' ? '确认处置' : handleAction === 'ignore' ? '标记误报' : '结案' }}</el-tag>
      </p>
      <el-form label-width="60px">
        <el-form-item label="处置人">
          <el-input v-model="handleOperator" placeholder="姓名 / 工号" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="handleNote" type="textarea" :rows="2" placeholder="选填" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="handleDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitHandle">确认</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.event-manage-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.search-card { border-radius: 8px; }

.search-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.search-left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.search-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.table-card { border-radius: 8px; }

.pagination-wrap {
  display: flex;
  justify-content: center;
  padding-top: 16px;
}

.mono {
  font-family: ui-monospace, Menlo, Consolas, monospace;
}

.text-danger { color: #ef4444; font-weight: 600; }
.text-warning { color: #f59e0b; font-weight: 600; }
.text-muted { color: #c0c4cc; font-size: 12px; }

/* 详情抽屉 */
.event-detail {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.detail-section h4 {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 12px;
  padding-bottom: 6px;
  border-bottom: 1px solid #ebeef5;
}

.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.detail-header h3 {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}
.detail-tags {
  display: flex;
  gap: 8px;
}

.media-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
}

.media-item {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  overflow: hidden;
}

.media-preview {
  height: 120px;
  background: #f5f7fa;
  display: flex;
  align-items: center;
  justify-content: center;
}
.media-preview img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}
.media-placeholder {
  color: #909399;
  font-size: 14px;
}

.media-info {
  padding: 8px 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: #909399;
}

.handle-actions {
  display: flex;
  gap: 12px;
}
</style>
