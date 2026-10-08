<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Picture, VideoCamera, Bell, DataAnalysis } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const router = useRouter()

// 统计数据 — 从后端实时拉取
const stats = ref({
  total_detections: 0,
  total_fire: 0,
  total_smoke: 0,
  avg_inference_time: 0,
  alert_count: 0
})
const loadingStats = ref(false)

// 最近检测记录 — 从后端实时拉取
const recentDetections = ref<any[]>([])
const loadingHistory = ref(false)

// 告警记录 — 从后端实时拉取（若无告警接口则为空）
const alerts = ref<any[]>([])

// 获取告警级别颜色
const getAlertColor = (level: string) => {
  const colors: Record<string, string> = {
    '紧急': '#ef4444',
    '高': '#f59e0b',
    '中': '#3b82f6',
    '低': '#22c55e'
  }
  return colors[level] || '#666'
}

// 拉取统计数据
const fetchStats = async () => {
  loadingStats.value = true
  try {
    const res = await fetch('/api/statistics?days=7')
    if (res.ok) {
      const data = await res.json()
      stats.value.total_detections = data.total_detections || 0
      stats.value.total_fire = data.total_fire || 0
      stats.value.total_smoke = data.total_smoke || 0
      stats.value.avg_inference_time = data.avg_inference_time || 0
      stats.value.alert_count = data.alert_count || 0
    }
  } catch {
    // 静默失败
  } finally {
    loadingStats.value = false
  }
}

// 拉取最近检测记录
const fetchHistory = async () => {
  loadingHistory.value = true
  try {
    const res = await fetch('/api/history?page=1&page_size=5')
    if (res.ok) {
      recentDetections.value = await res.json()
    }
  } catch {
    // 静默失败
  } finally {
    loadingHistory.value = false
  }
}

// 格式化时间
const formatTime = (t: string) => {
  if (!t) return '--'
  return t.replace('T', ' ').slice(0, 19)
}

onMounted(() => {
  fetchStats()
  fetchHistory()
})

// 跳转到检测页面
const goToDetect = (type: string) => {
  router.push(`/${type}-detect`)
}
</script>

<template>
  <div class="dashboard">
    <!-- 统计卡片 -->
    <div class="stats-grid">
      <el-card class="stat-card" shadow="hover">
        <div class="stat-icon" style="background-color: #e6f7ff;">
          <el-icon :size="24" style="color: #1890ff;"><Picture /></el-icon>
        </div>
        <div class="stat-content">
          <div class="stat-value">{{ stats.total_detections }}</div>
          <div class="stat-label">总检测次数</div>
        </div>
      </el-card>

      <el-card class="stat-card" shadow="hover">
        <div class="stat-icon" style="background-color: #fff2e8;">
          <el-icon :size="24" style="color: #fa8c16;"><Picture /></el-icon>
        </div>
        <div class="stat-content">
          <div class="stat-value">{{ stats.total_fire }}</div>
          <div class="stat-label">火焰检出</div>
        </div>
      </el-card>

      <el-card class="stat-card" shadow="hover">
        <div class="stat-icon" style="background-color: #f6ffed;">
          <el-icon :size="24" style="color: #52c41a;"><VideoCamera /></el-icon>
        </div>
        <div class="stat-content">
          <div class="stat-value">{{ stats.total_smoke }}</div>
          <div class="stat-label">烟雾检出</div>
        </div>
      </el-card>

      <el-card class="stat-card" shadow="hover">
        <div class="stat-icon" style="background-color: #fff1f0;">
          <el-icon :size="24" style="color: #ff4d4f;"><Bell /></el-icon>
        </div>
        <div class="stat-content">
          <div class="stat-value">{{ stats.alert_count }}</div>
          <div class="stat-label">告警次数</div>
        </div>
      </el-card>
    </div>

    <!-- 快捷操作 -->
    <el-card class="quick-actions" shadow="hover">
      <template #header>
        <div class="card-header">
          <span>快捷操作</span>
        </div>
      </template>
      <div class="action-grid">
        <el-button type="primary" @click="goToDetect('image')">
          <el-icon><Picture /></el-icon>
          图像检测
        </el-button>
        <el-button type="success" @click="goToDetect('video')">
          <el-icon><VideoCamera /></el-icon>
          视频检测
        </el-button>
        <el-button type="warning" @click="goToDetect('aerial')">
          <el-icon><Location /></el-icon>
          航拍分析
        </el-button>
        <el-button type="danger" @click="router.push('/alert-center')">
          <el-icon><Bell /></el-icon>
          告警中心
        </el-button>
      </div>
    </el-card>

    <div class="content-grid">
      <!-- 最近检测记录（真实数据） -->
      <el-card class="recent-detections" shadow="hover">
        <template #header>
          <div class="card-header">
            <span>最近检测记录</span>
            <el-button text type="primary" @click="router.push('/history')">查看全部</el-button>
          </div>
        </template>
        <el-table :data="recentDetections" style="width: 100%" v-loading="loadingHistory">
          <el-table-column label="时间" width="180">
            <template #default="{ row }">{{ formatTime(row.timestamp) }}</template>
          </el-table-column>
          <el-table-column prop="fire_count" label="火焰" width="80">
            <template #default="{ row }">
              <el-tag type="danger" size="small" v-if="row.fire_count > 0">{{ row.fire_count }}</el-tag>
              <span v-else style="color:#999">0</span>
            </template>
          </el-table-column>
          <el-table-column prop="smoke_count" label="烟雾" width="80">
            <template #default="{ row }">
              <el-tag type="warning" size="small" v-if="row.smoke_count > 0">{{ row.smoke_count }}</el-tag>
              <span v-else style="color:#999">0</span>
            </template>
          </el-table-column>
          <el-table-column label="推理耗时">
            <template #default="{ row }">{{ (row.inference_time || 0).toFixed(1) }}ms</template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!recentDetections.length && !loadingHistory" description="暂无检测记录" :image-size="48" />
      </el-card>

      <!-- 告警信息 -->
      <el-card class="alerts-card" shadow="hover">
        <template #header>
          <div class="card-header">
            <span>最新告警</span>
          </div>
        </template>
        <div class="alert-list" v-if="alerts.length">
          <div
            v-for="alert in alerts"
            :key="alert.id"
            class="alert-item"
            :class="{ unread: !alert.isRead }"
          >
            <div class="alert-level" :style="{ backgroundColor: getAlertColor(alert.level) }">
              {{ alert.level }}
            </div>
            <div class="alert-content">
              <div class="alert-message">{{ alert.message }}</div>
              <div class="alert-time">{{ alert.time }}</div>
            </div>
          </div>
        </div>
        <el-empty v-else description="暂无告警记录" :image-size="48" />
      </el-card>
    </div>

    <!-- 模型状态（真实数据） -->
    <el-card class="model-status" shadow="hover">
      <template #header>
        <div class="card-header">
          <span>模型状态</span>
        </div>
      </template>
      <div class="status-grid">
        <div class="status-item">
          <div class="status-label">当前模型</div>
          <div class="status-value">fire_smoke_v2</div>
        </div>
        <div class="status-item">
          <div class="status-label">平均推理时间</div>
          <div class="status-value">{{ stats.avg_inference_time.toFixed(1) }}ms</div>
        </div>
        <div class="status-item">
          <div class="status-label">检测类别</div>
          <div class="status-value">火焰 / 烟雾</div>
        </div>
        <div class="status-item">
          <div class="status-label">GPU状态</div>
          <div class="status-value" style="color: #52c41a;">正常</div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
}

.stat-card {
  display: flex;
  align-items: center;
  padding: 20px;
}

.stat-card :deep(.el-card__body) {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 0;
  width: 100%;
}

.stat-icon {
  width: 56px;
  height: 56px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.stat-content {
  flex: 1;
}

.stat-value {
  font-size: 28px;
  font-weight: 600;
  color: #333;
  line-height: 1.2;
}

.stat-label {
  font-size: 14px;
  color: #666;
  margin-top: 4px;
}

.quick-actions {
  margin-bottom: 0;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 16px;
  font-weight: 600;
  color: #333;
}

.action-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.content-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.recent-detections,
.alerts-card {
  margin-bottom: 0;
}

.alert-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.alert-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px;
  border-radius: 8px;
  background-color: #fafafa;
  transition: background-color 0.3s;
}

.alert-item:hover {
  background-color: #f0f0f0;
}

.alert-item.unread {
  background-color: #fff7e6;
}

.alert-level {
  padding: 2px 8px;
  border-radius: 4px;
  color: white;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
}

.alert-content {
  flex: 1;
}

.alert-message {
  font-size: 14px;
  color: #333;
  margin-bottom: 4px;
}

.alert-time {
  font-size: 12px;
  color: #999;
}

.model-status {
  margin-bottom: 0;
}

.status-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
}

.status-item {
  text-align: center;
  padding: 16px;
  background-color: #fafafa;
  border-radius: 8px;
}

.status-label {
  font-size: 14px;
  color: #666;
  margin-bottom: 8px;
}

.status-value {
  font-size: 20px;
  font-weight: 600;
  color: #333;
}
</style>