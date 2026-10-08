<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'

const router = useRouter()
const loading = ref(false)
const rememberMe = ref(true)

const form = reactive({
  username: '',
  password: ''
})

const handleLogin = async () => {
  if (!form.username.trim() || !form.password.trim()) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    const res = await fetch('/api/admin/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: form.username.trim(), password: form.password })
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || `HTTP ${res.status}`)
    }
    const data = await res.json()
    const ttl = rememberMe.value ? 30 * 24 * 3600 * 1000 : 24 * 3600 * 1000
    const expires = Date.now() + ttl
    localStorage.setItem('token', data.token)
    localStorage.setItem('token_expires', String(expires))
    localStorage.setItem('user', JSON.stringify({
      user_id: data.user_id,
      username: data.username,
      real_name: data.real_name,
      role: data.role
    }))
    ElMessage.success(`欢迎回来，${data.real_name || data.username}`)
    router.push('/dashboard')
  } catch (err: any) {
    ElMessage.error('登录失败：' + (err.message || '网络异常'))
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-header">
        <div class="logo-circle">
          <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M17.657 18.657A8 8 0 016.343 7.343S7 9 9 10c0-2 .5-5 2.986-7C14 5 16.09 5.777 17.656 7.343A7.975 7.975 0 0120 13a7.975 7.975 0 01-2.343 5.657z" />
            <path d="M9.879 16.121A3 3 0 1012.015 11L11 14H9c0 .768.293 1.536.879 2.121z" />
          </svg>
        </div>
        <h1 class="login-title">森林火灾烟雾检测系统</h1>
        <p class="login-subtitle">基于 YOLOv8 的智能检测平台</p>
      </div>

      <el-form :model="form" @submit.prevent="handleLogin" class="login-form">
        <el-form-item>
          <el-input
            v-model="form.username"
            placeholder="请输入用户名"
            size="large"
            :prefix-icon="User"
          />
        </el-form-item>
        <el-form-item>
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            size="large"
            :prefix-icon="Lock"
            show-password
          />
        </el-form-item>
        <div class="form-options">
          <el-checkbox v-model="rememberMe">记住我</el-checkbox>
          <a href="#" class="forgot-link">忘记密码？</a>
        </div>
        <el-button
          type="primary"
          size="large"
          :loading="loading"
          @click="handleLogin"
          class="login-btn"
        >
          登录
        </el-button>
      </el-form>

      <div class="login-footer">
        <p>© 2026 森林火灾烟雾检测系统</p>
        <p>基于 YOLOv8 深度学习技术</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #334155 100%);
  background-image:
    radial-gradient(ellipse at 20% 50%, rgba(22, 163, 74, 0.15) 0%, transparent 50%),
    radial-gradient(ellipse at 80% 50%, rgba(22, 163, 74, 0.1) 0%, transparent 50%),
    linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #334155 100%);
}

.login-card {
  width: 420px;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(10px);
  border-radius: 16px;
  padding: 48px 40px;
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
}

.login-header {
  text-align: center;
  margin-bottom: 36px;
}

.logo-circle {
  width: 64px;
  height: 64px;
  background: #16a34a;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 16px;
}

.login-title {
  font-size: 22px;
  font-weight: 600;
  color: #1e293b;
  margin-bottom: 8px;
}

.login-subtitle {
  font-size: 14px;
  color: #94a3b8;
}

.login-form {
  margin-bottom: 24px;
}

.form-options {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}

.forgot-link {
  font-size: 14px;
  color: #16a34a;
  text-decoration: none;
}
.forgot-link:hover { text-decoration: underline; }

.login-btn {
  width: 100%;
  height: 44px;
  font-size: 16px;
  background: #16a34a;
  border-color: #16a34a;
}
.login-btn:hover {
  background: #15803d;
  border-color: #15803d;
}

.login-footer {
  text-align: center;
  font-size: 12px;
  color: #94a3b8;
  line-height: 1.8;
}
</style>