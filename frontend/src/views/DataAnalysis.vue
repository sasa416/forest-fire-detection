<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { PieChart, BarChart, LineChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, LegendComponent, GridComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import { Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

use([CanvasRenderer, PieChart, BarChart, LineChart, TitleComponent, TooltipComponent, LegendComponent, GridComponent])

const days = ref(7)
const loading = ref(false)
const loaded = ref(false)

// 全部来自后端 /api/statistics，不再用随机数
const stats = ref({
  totalDetections: 0,
  totalFire: 0,
  totalSmoke: 0,
  avgInferenceTime: 0,
  alertCount: 0
})
const fireByDay = ref<Record<string, number>>({})
const smokeByDay = ref<Record<string, number>>({})
const fireByHour = ref<Record<string, number>>({})
const smokeByHour = ref<Record<string, number>>({})

const p2 = (n: number) => String(n).padStart(2, '0')

// 最近 N 天的日期与标签（本地时区，与后端 strftime("%Y-%m-%d") 对齐）
const dayKeys = computed(() => {
  const out: { key: string; label: string }[] = []
  for (let i = days.value - 1; i >= 0; i--) {
    const d = new Date()
    d.setDate(d.getDate() - i)
    out.push({
      key: `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}`,
      label: `${d.getMonth() + 1}/${d.getDate()}`
    })
  }
  return out
})

const hourKeys = computed(() =>
  Array.from({ length: 24 }, (_, i) => p2(i))
)

const pieOption = computed(() => ({
  tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
  legend: { bottom: 0, data: ['火焰', '烟雾'] },
  series: [{
    type: 'pie', radius: ['42%', '68%'], center: ['50%', '45%'],
    label: { show: true, fontSize: 12, formatter: '{b}\n{c}' },
    data: [
      { value: stats.value.totalFire, name: '火焰', itemStyle: { color: '#ef4444' } },
      { value: stats.value.totalSmoke, name: '烟雾', itemStyle: { color: '#f59e0b' } }
    ]
  }]
}))

const barOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  legend: { data: ['火焰', '烟雾'], bottom: 0 },
  grid: { left: 48, right: 20, top: 20, bottom: 42 },
  xAxis: { type: 'category', data: dayKeys.value.map(d => d.label), axisLabel: { fontSize: 11 } },
  yAxis: { type: 'value', axisLabel: { fontSize: 11 }, minInterval: 1 },
  series: [
    {
      name: '火焰', type: 'bar', barWidth: 14,
      data: dayKeys.value.map(d => fireByDay.value[d.key] || 0),
      itemStyle: { color: '#ef4444' }
    },
    {
      name: '烟雾', type: 'bar', barWidth: 14,
      data: dayKeys.value.map(d => smokeByDay.value[d.key] || 0),
      itemStyle: { color: '#f59e0b' }
    }
  ]
}))

const lineOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  legend: { data: ['火焰', '烟雾'], bottom: 0 },
  grid: { left: 48, right: 20, top: 20, bottom: 42 },
  xAxis: {
    type: 'category',
    data: hourKeys.value.map(h => `${h}:00`),
    axisLabel: { fontSize: 10, interval: 2 }
  },
  yAxis: { type: 'value', axisLabel: { fontSize: 11 }, minInterval: 1 },
  series: [
    {
      name: '火焰', type: 'line', smooth: true, symbol: 'none',
      data: hourKeys.value.map(h => fireByHour.value[h] || 0),
      lineStyle: { color: '#ef4444', width: 2 }, itemStyle: { color: '#ef4444' },
      areaStyle: {
        color: {
          type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(239,68,68,0.25)' },
            { offset: 1, color: 'rgba(239,68,68,0.02)' }
          ]
        }
      }
    },
    {
      name: '烟雾', type: 'line', smooth: true, symbol: 'none',
      data: hourKeys.value.map(h => smokeByHour.value[h] || 0),
      lineStyle: { color: '#f59e0b', width: 2 }, itemStyle: { color: '#f59e0b' }
    }
  ]
}))

const refreshData = async () => {
  loading.value = true
  try {
    const res = await fetch(`/api/statistics?days=${days.value}`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const d = await res.json()
    stats.value = {
      totalDetections: d.total_detections || 0,
      totalFire: d.total_fire || 0,
      totalSmoke: d.total_smoke || 0,
      avgInferenceTime: Math.round((d.avg_inference_time || 0) * 10) / 10,
      alertCount: d.alert_count || 0
    }
    fireByDay.value = d.fire_by_day || {}
    smokeByDay.value = d.smoke_by_day || {}
    fireByHour.value = d.fire_by_hour || {}
    smokeByHour.value = d.smoke_by_hour || {}
    loaded.value = true
  } catch (e: any) {
    ElMessage.error('读取统计数据失败: ' + (e.message || e))
  } finally {
    loading.value = false
  }
}

onMounted(() => { refreshData() })
</script>

<template>
  <div class="data-analysis" v-loading="loading">
    <el-card shadow="hover">
      <template #header>
        <div class="card-header">
          <span class="card-title">数据分析</span>
          <div class="header-actions">
            <el-select v-model="days" size="small" style="width:110px" @change="refreshData">
              <el-option :value="7" label="近7天" />
              <el-option :value="14" label="近14天" />
              <el-option :value="30" label="近30天" />
            </el-select>
            <el-button :icon="Refresh" size="small" @click="refreshData">刷新</el-button>
          </div>
        </div>
      </template>

      <div class="stats-row">
        <div class="stat-card">
          <div class="stat-icon" style="background:#eff6ff;"><span style="color:#3b82f6;">📊</span></div>
          <div><div class="stat-value">{{ stats.totalDetections }}</div><div class="stat-label">总检测次数</div></div>
        </div>
        <div class="stat-card">
          <div class="stat-icon" style="background:#fef2f2;"><span style="color:#ef4444;">🔥</span></div>
          <div><div class="stat-value" style="color:#ef4444;">{{ stats.totalFire }}</div><div class="stat-label">火焰目标数</div></div>
        </div>
        <div class="stat-card">
          <div class="stat-icon" style="background:#fffbeb;"><span style="color:#f59e0b;">💨</span></div>
          <div><div class="stat-value" style="color:#f59e0b;">{{ stats.totalSmoke }}</div><div class="stat-label">烟雾目标数</div></div>
        </div>
        <div class="stat-card">
          <div class="stat-icon" style="background:#f0fdf4;"><span style="color:#16a34a;">⚡</span></div>
          <div><div class="stat-value">{{ stats.avgInferenceTime }}ms</div><div class="stat-label">平均推理耗时</div></div>
        </div>
        <div class="stat-card">
          <div class="stat-icon" style="background:#fff7ed;"><span style="color:#f97316;">🔔</span></div>
          <div><div class="stat-value" style="color:#f97316;">{{ stats.alertCount }}</div><div class="stat-label">告警次数</div></div>
        </div>
      </div>

      <el-alert
        v-if="loaded && stats.totalDetections === 0"
        type="info" show-icon :closable="false"
        title="所选时间范围内暂无检测记录"
        description="先用「图像检测 / 视频检测 / 实时监控」跑几次，这里就会出现真实趋势数据。"
        style="margin-bottom: 16px;"
      />

      <div class="chart-grid">
        <el-card shadow="never" class="chart-card">
          <template #header><span class="chart-title">火焰/烟雾占比</span></template>
          <v-chart :option="pieOption" style="height: 280px;" autoresize />
        </el-card>
        <el-card shadow="never" class="chart-card">
          <template #header><span class="chart-title">每日火焰 / 烟雾目标数</span></template>
          <v-chart :option="barOption" style="height: 280px;" autoresize />
        </el-card>
      </div>

      <el-card shadow="never" class="chart-card" style="margin-top: 16px;">
        <template #header><span class="chart-title">24 小时检测分布</span></template>
        <v-chart :option="lineOption" style="height: 240px;" autoresize />
      </el-card>
    </el-card>
  </div>
</template>

<style scoped>
.data-analysis { height: 100%; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.card-title { font-size: 16px; font-weight: 600; color: #303133; }
.header-actions { display: flex; gap: 8px; }

.stats-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px; margin-bottom: 20px; }
.stat-card { display: flex; align-items: center; gap: 14px; padding: 16px; background: #fafafa; border-radius: 8px; }
.stat-icon { width: 44px; height: 44px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 20px; }
.stat-value { font-size: 24px; font-weight: 600; color: #303133; }
.stat-label { font-size: 12px; color: #909399; margin-top: 2px; }

.chart-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.chart-card { border: 1px solid #f0f0f0; }
.chart-title { font-size: 14px; font-weight: 600; color: #303133; }
</style>
