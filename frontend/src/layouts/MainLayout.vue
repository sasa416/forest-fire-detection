<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  House,
  Picture,
  VideoCamera,
  Location,
  Bell,
  DataAnalysis,
  Setting,
  Tools,
  Expand,
  Fold,
  Monitor,
  Warning,
  User,
  Folder
} from '@element-plus/icons-vue'

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

const router = useRouter()
const route = useRoute()

const isCollapse = ref(false)
const unreadCount = ref(0)
const pendingCount = ref(0)

// ── 当前登录用户 ──
const currentUser = ref<{ username: string; real_name: string; role: string } | null>(null)
try {
  const raw = localStorage.getItem('user')
  if (raw) currentUser.value = JSON.parse(raw)
} catch { /* ignore */ }

const userRole = computed(() => currentUser.value?.role || 'viewer')
const userName = computed(() => currentUser.value?.real_name || currentUser.value?.username || '未登录')

/* ── 告警确认弹窗状态 ── */
const dialogVisible = ref(false)
const currentAlert = ref<AlertRecord | null>(null)
const handling = ref(false)
const operator = ref(localStorage.getItem('ffd_operator') || userName.value)
const handleNote = ref('')
/** 「稍后提醒」的告警在 60s 内不再弹出，避免一直打断操作 */
const snoozeUntil: Record<string, number> = {}

// ── 退出登录 ──
const handleLogout = () => {
  localStorage.removeItem('token')
  localStorage.removeItem('token_expires')
  localStorage.removeItem('user')
  router.push('/login')
}

// ── 菜单项：按角色过滤，分组展示，补充功能说明 ──
const allMenuGroups = [
  {
    title: '总览',
    roles: ['admin', 'operator', 'viewer'],
    items: [
      { path: '/dashboard', title: '系统首页', icon: House, roles: ['admin', 'operator', 'viewer'], desc: '查看整体运行状态与关键指标' }
    ]
  },
  {
    title: '检测执行',
    roles: ['admin', 'operator'],
    items: [
      { path: '/live-monitor', title: '实时监控', icon: Monitor, roles: ['admin', 'operator'], desc: '接入监控流，实时观察现场画面' },
      { path: '/image-detect', title: '图像检测', icon: Picture, roles: ['admin', 'operator'], desc: '上传图片，快速识别火灾与烟雾' },
      { path: '/video-detect', title: '视频检测', icon: VideoCamera, roles: ['admin', 'operator'], desc: '上传视频，逐帧检测并定位风险' },
      { path: '/aerial-detect', title: '航拍分析', icon: Location, roles: ['admin', 'operator'], desc: '分析航拍素材，覆盖大范围林区' }
    ]
  },
  {
    title: '风险处置',
    roles: ['admin', 'operator', 'viewer'],
    items: [
      { path: '/alert-center', title: '告警中心', icon: Bell, roles: ['admin', 'operator', 'viewer'], desc: '查看告警、确认处置、跟踪闭环' },
      { path: '/event-manage', title: '数据管理', icon: Folder, roles: ['admin', 'operator', 'viewer'], desc: '按事件编号检索险情记录与证据' },
      { path: '/data-analysis', title: '数据分析', icon: DataAnalysis, roles: ['admin', 'operator', 'viewer'], desc: '分析检测趋势、告警分布与热点时段' }
    ]
  },
  {
    title: '系统管理',
    roles: ['admin'],
    items: [
      { path: '/model-manage', title: '模型管理', icon: Setting, roles: ['admin'], desc: '管理检测模型、切换权重、导入导出' },
      { path: '/system-settings', title: '系统设置', icon: Tools, roles: ['admin'], desc: '配置检测参数、告警规则和系统信息' },
      { path: '/user-manage', title: '人员管理', icon: User, roles: ['admin'], desc: '管理员工账号、权限与启用状态' }
    ]
  }
]

interface MenuItemWithDesc {
  path: string
  title: string
  icon: unknown
  roles: string[]
  desc: string
}

const menuGroups = computed(() =>
  allMenuGroups
    .filter(group => group.roles.includes(userRole.value))
    .map(group => ({
      title: group.title,
      items: (group.items as MenuItemWithDesc[]).filter(item => item.roles.includes(userRole.value))
    }))
    .filter(group => group.items.length)
)

const activeMenu = computed(() => route.path)

const toggleCollapse = () => {
  isCollapse.value = !isCollapse.value
}

const handleMenuSelect = (path: string) => {
  router.push(path)
}

const goAlertCenter = () => {
  router.push('/alert-center')
}

/* ── 级别样式映射 ── */
const LEVEL_MAP: Record<string, { text: string; type: string; color: string; title: string }> = {
  critical: { text: '紧急', type: 'danger', color: '#ef4444', title: '🚨 紧急火灾告警 — 请立即确认' },
  high: { text: '高', type: 'warning', color: '#f59e0b', title: '⚠️ 火灾风险告警 — 请确认' },
  medium: { text: '中', type: 'primary', color: '#3b82f6', title: '告警提醒' },
  low: { text: '低', type: 'info', color: '#94a3b8', title: '告警提醒' }
}
const levelInfo = (level: string) => LEVEL_MAP[level] || LEVEL_MAP.low

/* ── 告警声音（Web Audio 合成，无需音频文件）── */
const playAlarm = () => {
  try {
    const Ctx = window.AudioContext || (window as any).webkitAudioContext
    if (!Ctx) return
    const ctx = new Ctx()
    if (ctx.state === 'suspended') ctx.resume().catch(() => { /* 忽略 */ })
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.type = 'triangle'
    gain.gain.value = 0.15
    osc.connect(gain)
    gain.connect(ctx.destination)
    const t = ctx.currentTime
    // 三声短鸣：880 → 1180 → 880 Hz
    osc.frequency.setValueAtTime(880, t)
    osc.frequency.setValueAtTime(1180, t + 0.18)
    osc.frequency.setValueAtTime(880, t + 0.36)
    osc.start(t)
    osc.stop(t + 0.56)
    window.setTimeout(() => {
      try { ctx.close() } catch { /* 已关闭 */ }
    }, 1200)
  } catch {
    /* 浏览器可能禁止自动播放音频，静默忽略 */
  }
}

/* ── 轮询：未读数 + 待处置告警 ── */
const fetchCounts = async () => {
  try {
    const res = await fetch('/api/alerts/unread-count')
    if (!res.ok) return
    const data = await res.json()
    unreadCount.value = data.unread_count || 0
    pendingCount.value = data.pending_count || 0
  } catch {
    /* 静默失败，下次轮询重试 */
  }
}

const openDialog = (alert: AlertRecord) => {
  currentAlert.value = alert
  handleNote.value = ''
  dialogVisible.value = true
  playAlarm()
}

const fetchPending = async () => {
  // 正在处置中不打断；弹窗已开不重复弹
  if (dialogVisible.value) return
  try {
    const res = await fetch('/api/alerts/pending?popup_levels_only=true&limit=10')
    if (!res.ok) return
    const data = await res.json()
    pendingCount.value = data.total || 0
    const now = Date.now()
    const next = (data.list || []).find(
      (a: AlertRecord) => !(snoozeUntil[a.alert_id] > now)
    )
    if (next) openDialog(next)
  } catch {
    /* 静默失败 */
  }
}

/* ── 处置：确认 / 忽略 ── */
const submitHandle = async (action: 'confirm' | 'ignore') => {
  const alert = currentAlert.value
  if (!alert) return
  if (!operator.value.trim()) {
    ElMessage.warning('请填写处置人')
    return
  }
  handling.value = true
  try {
    const res = await fetch(`/api/alerts/${alert.alert_id}/handle`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action,
        operator: operator.value.trim(),
        note: handleNote.value.trim()
      })
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    localStorage.setItem('ffd_operator', operator.value.trim())
    ElMessage.success(action === 'confirm' ? '已确认处置' : '已忽略该告警')
    dialogVisible.value = false
    currentAlert.value = null
    await fetchCounts()
    await fetchPending()
  } catch (err) {
    ElMessage.error(`处置失败: ${err}`)
  } finally {
    handling.value = false
  }
}

/* ── 稍后提醒 ── */
const snooze = () => {
  const alert = currentAlert.value
  if (alert) snoozeUntil[alert.alert_id] = Date.now() + 60_000
  dialogVisible.value = false
  currentAlert.value = null
}

let alertTimer: number | undefined

onMounted(() => {
  fetchCounts()
  fetchPending()
  alertTimer = window.setInterval(() => {
    fetchCounts()
    fetchPending()
  }, 5000)
})

onUnmounted(() => {
  if (alertTimer) window.clearInterval(alertTimer)
})
</script>

<template>
  <el-container class="h-screen">
    <!-- 侧边栏 -->
    <el-aside :width="isCollapse ? '64px' : '260px'" class="sidebar">
      <div class="logo">
        <img src="@/assets/logo.svg" alt="Logo" class="logo-img" />
        <span v-if="!isCollapse" class="logo-text">森林火灾检测</span>
      </div>

      <el-menu
        :default-active="activeMenu"
        :collapse="isCollapse"
        @select="handleMenuSelect"
        class="sidebar-menu"
        background-color="#001529"
        text-color="#ffffffa6"
        active-text-color="#ffffff"
      >
        <template v-for="group in menuGroups" :key="group.title">
          <div v-if="!isCollapse" class="menu-group-title">{{ group.title }}</div>
          <el-menu-item
            v-for="item in group.items"
            :key="item.path"
            :index="item.path"
          >
            <el-icon><component :is="item.icon" /></el-icon>
            <template #title>
              <div class="menu-title-wrap">
                <span class="menu-title">{{ item.title }}</span>
                <span v-if="!isCollapse" class="menu-desc">{{ item.desc }}</span>
              </div>
            </template>
          </el-menu-item>
        </template>
      </el-menu>
    </el-aside>

    <!-- 主内容区 -->
    <el-container>
      <!-- 顶部栏 -->
      <el-header class="header">
        <div class="header-left">
          <el-icon
            class="collapse-btn"
            @click="toggleCollapse"
          >
            <component :is="isCollapse ? Expand : Fold" />
          </el-icon>
          <el-breadcrumb separator="/">
            <el-breadcrumb-item :to="{ path: '/' }">首页</el-breadcrumb-item>
            <el-breadcrumb-item>{{ route.meta.title }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>

        <div class="header-right">
          <el-tag
            v-if="pendingCount"
            type="danger"
            effect="dark"
            size="small"
            class="pending-chip"
            @click="goAlertCenter"
          >
            <el-icon><Warning /></el-icon>
            待处置 {{ pendingCount }}
          </el-tag>

          <el-badge :value="unreadCount" :max="99" :hidden="!unreadCount" class="notification-badge">
            <el-icon :size="20" class="notification-icon" @click="goAlertCenter">
              <Bell />
            </el-icon>
          </el-badge>

          <el-dropdown @command="(cmd: string) => { if (cmd === 'logout') handleLogout() }">
            <div class="user-info">
              <el-avatar :size="32" src="https://cube.elemecdn.com/0/88/03b0d39583f48206768a7534e55bcpng.png" />
              <span class="username">{{ userName }}</span>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item disabled>{{ userRole === 'admin' ? '管理员' : userRole === 'operator' ? '操作员' : '查看者' }}</el-dropdown-item>
                <el-dropdown-item divided command="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <!-- 内容区 -->
      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>

    <!-- 火灾告警弹窗：必须由管理人员确认或忽略 -->
    <el-dialog
      v-model="dialogVisible"
      :title="currentAlert ? levelInfo(currentAlert.level).title : '火灾告警'"
      width="540px"
      top="12vh"
      append-to-body
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      class="alert-confirm-dialog"
    >
      <div v-if="currentAlert" class="ac-body">
        <div
          class="ac-banner"
          :style="{ background: levelInfo(currentAlert.level).color }"
        >
          <el-icon :size="20"><Bell /></el-icon>
          <span class="ac-banner-text">{{ currentAlert.message }}</span>
        </div>

        <div class="ac-grid">
          <div class="ac-cell">
            <span class="ac-label">告警级别</span>
            <el-tag
              :type="levelInfo(currentAlert.level).type as any"
              size="small"
              effect="dark"
            >
              {{ levelInfo(currentAlert.level).text }}
            </el-tag>
          </div>
          <div class="ac-cell">
            <span class="ac-label">告警时间</span>
            <span class="ac-value">{{ currentAlert.created_at }}</span>
          </div>
          <div class="ac-cell">
            <span class="ac-label">火焰数量</span>
            <span class="ac-value fire">{{ currentAlert.fire_count }} 处</span>
          </div>
          <div class="ac-cell">
            <span class="ac-label">烟雾数量</span>
            <span class="ac-value smoke">{{ currentAlert.smoke_count }} 处</span>
          </div>
          <div class="ac-cell ac-span">
            <span class="ac-label">来源编号</span>
            <span class="ac-value mono">{{ currentAlert.detection_id || '-' }}</span>
          </div>
        </div>

        <div class="ac-form">
          <div class="ac-form-row">
            <label>处置人</label>
            <el-input v-model="operator" size="small" placeholder="姓名 / 工号" style="width: 200px" />
          </div>
          <div class="ac-form-row">
            <label>处置备注</label>
            <el-input
              v-model="handleNote"
              type="textarea"
              :rows="2"
              size="small"
              placeholder="如：已通知巡护队现场核查（选填）"
            />
          </div>
        </div>

        <div class="ac-tip">
          点击「确认处置」记为该告警已处理；点击「忽略」记为误报。两者都会保存处置人与时间，可在告警中心追溯。
        </div>
      </div>

      <template #footer>
        <el-button @click="snooze">稍后提醒</el-button>
        <el-button type="info" plain :loading="handling" @click="submitHandle('ignore')">
          忽略
        </el-button>
        <el-button type="danger" :loading="handling" @click="submitHandle('confirm')">
          确认处置
        </el-button>
      </template>
    </el-dialog>
  </el-container>
</template>

<style scoped>
.sidebar {
  background-color: #001529;
  transition: width 0.3s;
  overflow: hidden;
}

.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.logo-img {
  width: 32px;
  height: 32px;
}

.logo-text {
  color: #fff;
  font-size: 16px;
  font-weight: 600;
  margin-left: 12px;
  white-space: nowrap;
}

.sidebar-menu {
  border-right: none;
}

.sidebar-menu:not(.el-menu--collapse) {
  width: 260px;
}

.menu-group-title {
  padding: 18px 20px 8px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.35);
  letter-spacing: 0.6px;
}

.menu-title-wrap {
  display: flex;
  flex-direction: column;
}

.menu-title {
  line-height: 20px;
}

.menu-desc {
  margin-top: 2px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.45);
  line-height: 16px;
}

.header {
  background: #fff;
  border-bottom: 1px solid #e8e8e8;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.collapse-btn {
  font-size: 20px;
  cursor: pointer;
  color: #666;
  transition: color 0.3s;
}

.collapse-btn:hover {
  color: #16a34a;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 20px;
}

.pending-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
}

.notification-badge {
  cursor: pointer;
}

.notification-icon {
  color: #666;
  transition: color 0.3s;
}

.notification-icon:hover {
  color: #16a34a;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.username {
  font-size: 14px;
  color: #333;
}

.main-content {
  background-color: #f0f2f5;
  padding: 20px;
  overflow-y: auto;
}

/* ── 告警确认弹窗 ── */
.ac-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.ac-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border-radius: 8px;
  color: #fff;
  font-size: 14px;
  font-weight: 500;
  line-height: 1.5;
}

.ac-banner-text {
  flex: 1;
}

.ac-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 16px;
}

.ac-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.ac-span {
  grid-column: span 2;
}

.ac-label {
  color: #909399;
  flex-shrink: 0;
}

.ac-value {
  color: #303133;
}

.ac-value.fire {
  color: #dc2626;
  font-weight: 600;
}

.ac-value.smoke {
  color: #d97706;
  font-weight: 600;
}

.ac-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-top: 12px;
  border-top: 1px dashed #ebeef5;
}

.ac-form-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  font-size: 13px;
  color: #606266;
}

.ac-form-row label {
  width: 60px;
  flex-shrink: 0;
  padding-top: 6px;
}

.ac-form-row :deep(.el-textarea),
.ac-form-row :deep(.el-input) {
  flex: 1;
}

.ac-tip {
  font-size: 12px;
  color: #909399;
  line-height: 1.6;
  background: #f8fafc;
  border-radius: 6px;
  padding: 8px 10px;
}

.mono {
  font-family: ui-monospace, Menlo, Consolas, monospace;
}
</style>
