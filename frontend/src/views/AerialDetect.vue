<script setup lang="ts">
import { useRouter } from 'vue-router'
import { Picture, ArrowRight } from '@element-plus/icons-vue'

const router = useRouter()
</script>

<template>
  <div class="aerial-page">
    <el-card shadow="hover">
      <template #header>
        <span class="card-title">航拍图分析</span>
      </template>
      <div class="content">
        <div class="info-section">
          <div class="info-icon">
            <el-icon :size="48"><Picture /></el-icon>
          </div>
          <h3>航拍图已并入图像检测</h3>
          <p class="desc">
            航拍图本质上是高分辨率静态图片，检测流程与图像检测完全一致：
            上传图片 → YOLOv8 推理 → 返回火焰/烟雾检测结果。
          </p>
          <p class="desc">
            对于超大尺寸航拍图（如 8000×6000），系统会自动切片后逐块检测，
            再合并结果，确保不遗漏小目标。
          </p>
          <el-button type="primary" :icon="ArrowRight" @click="router.push('/image-detect')">
            前往图像检测
          </el-button>
        </div>
        <div class="feature-list">
          <div class="feature-item">
            <span class="feature-dot"></span>
            <span>支持任意分辨率图片上传</span>
          </div>
          <div class="feature-item">
            <span class="feature-dot"></span>
            <span>大图自动切片，逐块检测</span>
          </div>
          <div class="feature-item">
            <span class="feature-dot"></span>
            <span>火焰 / 烟雾双类别识别</span>
          </div>
          <div class="feature-item">
            <span class="feature-dot"></span>
            <span>检测结果可视化标注</span>
          </div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.aerial-page { height: 100%; }
.card-title { font-size: 16px; font-weight: 600; color: #303133; }

.content { display: flex; gap: 48px; align-items: flex-start; padding: 20px 0; }
.info-section { flex: 1; }
.info-icon { color: #16a34a; margin-bottom: 16px; }
.info-section h3 { font-size: 20px; font-weight: 600; color: #303133; margin-bottom: 12px; }
.desc { font-size: 14px; color: #606266; line-height: 1.7; margin-bottom: 12px; }

.feature-list { flex-shrink: 0; width: 280px; }
.feature-item { display: flex; align-items: center; gap: 10px; padding: 10px 0; font-size: 14px; color: #303133; }
.feature-dot { width: 8px; height: 8px; border-radius: 50%; background: #16a34a; flex-shrink: 0; }
</style>