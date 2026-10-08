<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Plus, Edit, Delete, Lock, Refresh } from '@element-plus/icons-vue'

interface UserItem {
  user_id: string
  username: string
  real_name: string
  role: string
  phone: string
  email: string
  is_active: boolean
  last_login: string | null
  created_at: string
}

const loading = ref(false)
const users = ref<UserItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const keyword = ref('')
const roleFilter = ref('')

// ── 新增/编辑弹窗 ──
const dialogVisible = ref(false)
const dialogTitle = ref('新增人员')
const editMode = ref(false)
const editUserId = ref('')
const form = reactive({
  username: '',
  password: '',
  real_name: '',
  role: 'operator',
  phone: '',
  email: ''
})
const formRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }, { min: 6, message: '密码至少6位', trigger: 'blur' }],
  real_name: [{ required: true, message: '请输入姓名', trigger: 'blur' }]
}

// ── 重置密码弹窗 ──
const pwdDialogVisible = ref(false)
const pwdUserId = ref('')
const pwdUserName = ref('')
const newPwd = ref('')

const token = () => localStorage.getItem('token') || ''

const authHeaders = () => ({
  'Authorization': `Bearer ${token()}`,
  'Content-Type': 'application/json'
})

const fetchUsers = async () => {
  loading.value = true
  try {
    const params = new URLSearchParams({
      page: String(page.value),
      page_size: String(pageSize.value)
    })
    if (keyword.value) params.set('keyword', keyword.value)
    if (roleFilter.value) params.set('role', roleFilter.value)
    const res = await fetch(`/api/admin/users?${params}`, { headers: authHeaders() })
    if (res.status === 401) {
      ElMessage.error('登录已过期，请重新登录')
      localStorage.clear()
      window.location.href = '/login'
      return
    }
    if (res.status === 403) {
      ElMessage.error('权限不足，需要管理员角色')
      return
    }
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    users.value = data.list || []
    total.value = data.total || 0
  } catch (err: any) {
    ElMessage.error('加载失败：' + (err.message || '网络异常'))
  } finally {
    loading.value = false
  }
}

const openCreate = () => {
  editMode.value = false
  dialogTitle.value = '新增人员'
  Object.assign(form, { username: '', password: '', real_name: '', role: 'operator', phone: '', email: '' })
  dialogVisible.value = true
}

const openEdit = (user: UserItem) => {
  editMode.value = true
  dialogTitle.value = '编辑人员'
  editUserId.value = user.user_id
  Object.assign(form, {
    username: user.username,
    password: '',
    real_name: user.real_name,
    role: user.role,
    phone: user.phone,
    email: user.email
  })
  dialogVisible.value = true
}

const submitUser = async () => {
  if (!form.username.trim() || !form.real_name.trim()) {
    ElMessage.warning('请填写必填项')
    return
  }
  if (!editMode.value && form.password.length < 6) {
    ElMessage.warning('密码至少6位')
    return
  }
  try {
    if (editMode.value) {
      // 更新
      const body: any = {
        real_name: form.real_name,
        role: form.role,
        phone: form.phone,
        email: form.email
      }
      if (form.password) body.password = form.password
      const res = await fetch(`/api/admin/users/${editUserId.value}`, {
        method: 'PUT',
        headers: authHeaders(),
        body: JSON.stringify(body)
      })
      if (res.status === 403) { ElMessage.error('权限不足'); return }
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`)
      ElMessage.success('更新成功')
    } else {
      // 新增
      const res = await fetch('/api/admin/users', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify(form)
      })
      if (res.status === 409) { ElMessage.error('用户名已存在'); return }
      if (res.status === 403) { ElMessage.error('权限不足'); return }
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    await fetchUsers()
  } catch (err: any) {
    ElMessage.error('操作失败：' + (err.message || '网络异常'))
  }
}

const toggleStatus = async (user: UserItem) => {
  const action = user.is_active ? '禁用' : '启用'
  await ElMessageBox.confirm(`确定要${action}用户「${user.real_name || user.username}」吗？`, '确认', { type: 'warning' })
  try {
    const res = await fetch(`/api/admin/users/${user.user_id}/status?is_active=${!user.is_active}`, {
      method: 'PUT',
      headers: authHeaders()
    })
    if (res.status === 403) { ElMessage.error('权限不足'); return }
    if (!res.ok) throw new Error('操作失败')
    ElMessage.success(`已${action}`)
    await fetchUsers()
  } catch (err: any) {
    if (err !== 'cancel') ElMessage.error(err.message || '操作失败')
  }
}

const deleteUser = async (user: UserItem) => {
  await ElMessageBox.confirm(
    `确定要删除用户「${user.real_name || user.username}」吗？此操作不可恢复。`,
    '删除确认',
    { type: 'error', confirmButtonText: '确认删除', cancelButtonText: '取消' }
  )
  try {
    const res = await fetch(`/api/admin/users/${user.user_id}`, {
      method: 'DELETE',
      headers: authHeaders()
    })
    if (res.status === 403) { ElMessage.error('权限不足'); return }
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || '删除失败')
    ElMessage.success('已删除')
    await fetchUsers()
  } catch (err: any) {
    if (err !== 'cancel') ElMessage.error(err.message || '删除失败')
  }
}

const openResetPwd = (user: UserItem) => {
  pwdUserId.value = user.user_id
  pwdUserName.value = user.real_name || user.username
  newPwd.value = ''
  pwdDialogVisible.value = true
}

const submitResetPwd = async () => {
  if (newPwd.value.length < 6) {
    ElMessage.warning('新密码至少6位')
    return
  }
  try {
    const res = await fetch(`/api/admin/users/${pwdUserId.value}`, {
      method: 'PUT',
      headers: authHeaders(),
      body: JSON.stringify({ password: newPwd.value })
    })
    if (res.status === 403) { ElMessage.error('权限不足'); return }
    if (!res.ok) throw new Error('重置失败')
    ElMessage.success(`已重置「${pwdUserName.value}」的密码`)
    pwdDialogVisible.value = false
  } catch (err: any) {
    ElMessage.error(err.message || '重置失败')
  }
}

const handleSearch = () => {
  page.value = 1
  fetchUsers()
}

const handlePageChange = (p: number) => {
  page.value = p
  fetchUsers()
}

const roleLabel = (role: string) => {
  const map: Record<string, string> = { admin: '管理员', operator: '操作员', viewer: '查看者' }
  return map[role] || role
}

const roleTagType = (role: string): string => {
  const map: Record<string, string> = { admin: 'danger', operator: 'primary', viewer: 'info' }
  return map[role] || 'info'
}

onMounted(fetchUsers)
</script>

<template>
  <div class="user-manage-page">
    <!-- 顶部操作栏 -->
    <el-card shadow="never" class="search-card">
      <div class="search-row">
        <div class="search-left">
          <el-input
            v-model="keyword"
            placeholder="搜索用户名 / 姓名 / 手机号"
            clearable
            :prefix-icon="Search"
            style="width: 260px"
            @keyup.enter="handleSearch"
            @clear="handleSearch"
          />
          <el-select v-model="roleFilter" placeholder="角色筛选" clearable style="width: 140px" @change="handleSearch">
            <el-option label="管理员" value="admin" />
            <el-option label="操作员" value="operator" />
            <el-option label="查看者" value="viewer" />
          </el-select>
          <el-button :icon="Search" type="primary" @click="handleSearch">搜索</el-button>
        </div>
        <div class="search-right">
          <el-button :icon="Plus" type="success" @click="openCreate">新增人员</el-button>
          <el-button :icon="Refresh" @click="fetchUsers">刷新</el-button>
        </div>
      </div>
    </el-card>

    <!-- 用户列表 -->
    <el-card shadow="never" class="table-card">
      <el-table :data="users" v-loading="loading" stripe style="width: 100%">
        <el-table-column prop="username" label="用户名" width="120" />
        <el-table-column prop="real_name" label="姓名" width="100" />
        <el-table-column label="角色" width="100">
          <template #default="{ row }">
            <el-tag :type="roleTagType(row.role) as any" size="small" effect="plain">
              {{ roleLabel(row.role) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="phone" label="手机号" width="130" />
        <el-table-column prop="email" label="邮箱" min-width="160" show-overflow-tooltip />
        <el-table-column label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">
              {{ row.is_active ? '正常' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最后登录" width="170">
          <template #default="{ row }">
            <span v-if="row.last_login">{{ row.last_login }}</span>
            <span v-else class="text-muted">从未登录</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button :icon="Edit" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button :icon="Lock" size="small" @click="openResetPwd(row)">重置密码</el-button>
            <el-button
              :type="row.is_active ? 'warning' : 'success'"
              size="small"
              @click="toggleStatus(row)"
            >
              {{ row.is_active ? '禁用' : '启用' }}
            </el-button>
            <el-button
              :icon="Delete"
              type="danger"
              size="small"
              :disabled="row.username === 'admin'"
              @click="deleteUser(row)"
            />
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap" v-if="total > pageSize">
        <el-pagination
          background
          layout="prev, pager, next"
          :total="total"
          :page-size="pageSize"
          :current-page="page"
          @current-change="handlePageChange"
        />
      </div>
    </el-card>

    <!-- 新增/编辑弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="480px"
      :close-on-click-modal="false"
    >
      <el-form :model="form" label-width="80px">
        <el-form-item label="用户名" required>
          <el-input v-model="form.username" :disabled="editMode" placeholder="登录用户名" />
        </el-form-item>
        <el-form-item :label="editMode ? '新密码' : '密码'" :required="!editMode">
          <el-input v-model="form.password" type="password" show-password :placeholder="editMode ? '留空则不修改' : '至少6位'" />
        </el-form-item>
        <el-form-item label="姓名" required>
          <el-input v-model="form.real_name" placeholder="真实姓名" />
        </el-form-item>
        <el-form-item label="角色" required>
          <el-select v-model="form.role" style="width: 100%">
            <el-option label="管理员" value="admin">
              <span>管理员</span>
              <span style="color:#999;font-size:12px;margin-left:8px">全部权限</span>
            </el-option>
            <el-option label="操作员" value="operator">
              <span>操作员</span>
              <span style="color:#999;font-size:12px;margin-left:8px">检测+处置</span>
            </el-option>
            <el-option label="查看者" value="viewer">
              <span>查看者</span>
              <span style="color:#999;font-size:12px;margin-left:8px">只读</span>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="手机号">
          <el-input v-model="form.phone" placeholder="选填" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="form.email" placeholder="选填" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitUser">{{ editMode ? '保存' : '创建' }}</el-button>
      </template>
    </el-dialog>

    <!-- 重置密码弹窗 -->
    <el-dialog v-model="pwdDialogVisible" title="重置密码" width="400px">
      <p style="margin-bottom:12px;color:#606266">
        为 <strong>{{ pwdUserName }}</strong> 设置新密码：
      </p>
      <el-input v-model="newPwd" type="password" show-password placeholder="新密码（至少6位）" />
      <template #footer>
        <el-button @click="pwdDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitResetPwd">确认重置</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.user-manage-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.search-card {
  border-radius: 8px;
}

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

.table-card {
  border-radius: 8px;
}

.pagination-wrap {
  display: flex;
  justify-content: center;
  padding-top: 16px;
}

.text-muted {
  color: #c0c4cc;
  font-size: 12px;
}
</style>
