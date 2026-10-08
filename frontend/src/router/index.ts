import { createRouter, createWebHistory } from 'vue-router'
import MainLayout from '@/layouts/MainLayout.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      component: MainLayout,
      redirect: '/dashboard',
      children: [
        {
          path: 'dashboard',
          name: 'Dashboard',
          component: () => import('@/views/Dashboard.vue'),
          meta: { title: '首页', icon: 'House' }
        },
        {
          path: 'live-monitor',
          name: 'LiveMonitor',
          component: () => import('@/views/LiveMonitor.vue'),
          meta: { title: '实时监控', icon: 'VideoCamera' }
        },
        {
          path: 'image-detect',
          name: 'ImageDetect',
          component: () => import('@/views/ImageDetect.vue'),
          meta: { title: '图像检测', icon: 'Picture' }
        },
        {
          path: 'video-detect',
          name: 'VideoDetect',
          component: () => import('@/views/VideoDetect.vue'),
          meta: { title: '视频检测', icon: 'VideoCamera' }
        },
        {
          path: 'aerial-detect',
          name: 'AerialDetect',
          component: () => import('@/views/AerialDetect.vue'),
          meta: { title: '航拍分析', icon: 'Location' }
        },
        {
          path: 'alert-center',
          name: 'AlertCenter',
          component: () => import('@/views/AlertCenter.vue'),
          meta: { title: '告警中心', icon: 'Bell' }
        },
        {
          path: 'data-analysis',
          name: 'DataAnalysis',
          component: () => import('@/views/DataAnalysis.vue'),
          meta: { title: '数据分析', icon: 'DataAnalysis' }
        },
        {
          path: 'model-manage',
          name: 'ModelManage',
          component: () => import('@/views/ModelManage.vue'),
          meta: { title: '模型管理', icon: 'Setting' }
        },
        {
          path: 'system-settings',
          name: 'SystemSettings',
          component: () => import('@/views/SystemSettings.vue'),
          meta: { title: '系统设置', icon: 'Tools' }
        },
        {
          path: 'user-manage',
          name: 'UserManage',
          component: () => import('@/views/UserManage.vue'),
          meta: { title: '人员管理', icon: 'User' }
        },
        {
          path: 'event-manage',
          name: 'EventManage',
          component: () => import('@/views/EventManage.vue'),
          meta: { title: '数据管理', icon: 'Folder' }
        }
      ]
    },
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/Login.vue')
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'NotFound',
      component: () => import('@/views/NotFound.vue')
    }
  ]
})

// 路由守卫
router.beforeEach((to, from, next) => {
  // 设置页面标题
  document.title = `${to.meta.title || '森林火灾烟雾检测系统'} - 森林火灾烟雾检测系统`

  // 公开页面不拦截
  if (to.path === '/login') {
    next()
    return
  }

  // 检查 token 是否存在且未过期
  const token = localStorage.getItem('token')
  const tokenExpires = Number(localStorage.getItem('token_expires') || 0)
  if (!token || Date.now() > tokenExpires) {
    // token 不存在或已过期，清除本地存储，跳转登录
    localStorage.removeItem('token')
    localStorage.removeItem('token_expires')
    localStorage.removeItem('user')
    next('/login')
    return
  }

  // 检查角色权限（前端层面的菜单级控制）
  const userStr = localStorage.getItem('user')
  if (userStr) {
    try {
      const user = JSON.parse(userStr)
      const role = user.role as string
      // viewer 不能访问写操作页面（前端隐藏，后端也会 403）
      // operator 不能访问人员管理（前端隐藏）
      // 这里不做细粒度拦截，主要由菜单隐藏 + 后端 403 双重保障
    } catch {
      // 解析失败，继续放行（后端会兜底）
    }
  }

  next()
})

export default router