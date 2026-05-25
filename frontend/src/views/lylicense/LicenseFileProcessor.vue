<template>
  <div class="license-file-processor">
    <el-card class="box-card">
      <div slot="header" class="clearfix">
        <span>License 文件处理</span>
      </div>
      
      <!-- 操作按钮 -->
      <div class="operation-buttons">
        <el-button 
          type="primary" 
          icon="el-icon-search"
          @click="handleScanFiles"
          :loading="scanning">
          手动扫描目录
        </el-button>
        
        <el-button 
          type="success" 
          icon="el-icon-video-play"
          @click="handleStartWatcher"
          :loading="watcherStarting"
          :disabled="watcherRunning">
          启动自动监听
        </el-button>
        
        <el-tag v-if="watcherRunning" type="success" effect="dark">
          <i class="el-icon-check"></i> 监听器运行中
        </el-tag>
      </div>
      
      <!-- 说明信息 -->
      <el-alert
        title="使用说明"
        type="info"
        :closable="false"
        style="margin-top: 20px;">
        <div slot="default">
          <p><strong>手动扫描：</strong>点击按钮扫描指定目录中的 JSON/TXT 文件并创建申请记录</p>
          <p><strong>自动监听：</strong>启动后台监听器，实时监控目录变化，自动处理新文件</p>
          <p><strong>监听目录：</strong>{{ watchDir }}</p>
        </div>
      </el-alert>
      
      <!-- 扫描结果 -->
      <div v-if="scanResult" class="scan-result" style="margin-top: 20px;">
        <el-descriptions title="扫描结果" :column="3" border>
          <el-descriptions-item label="文件总数">
            {{ scanResult.total_files }}
          </el-descriptions-item>
          <el-descriptions-item label="成功处理">
            <span style="color: #67C23A">{{ scanResult.processed }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="处理失败">
            <span style="color: #F56C6C">{{ scanResult.errors }}</span>
          </el-descriptions-item>
        </el-descriptions>
      </div>
    </el-card>
  </div>
</template>

<script>
import { scanTxtFiles, startFileWatcher } from '@/api/license-file'

export default {
  name: 'LicenseFileProcessor',
  data() {
    return {
      scanning: false,
      watcherStarting: false,
      watcherRunning: false,
      scanResult: null,
      watchDir: 'backend/license_data/incoming/'
    }
  },
  methods: {
    /**
     * 手动扫描目录
     */
    async handleScanFiles() {
      this.scanning = true
      try {
        const res = await scanTxtFiles()
        this.$message.success(res.msg)
        this.scanResult = res.data
        
        // 刷新申请列表（如果父组件有这个方法）
        if (this.$parent && this.$parent.getList) {
          this.$parent.getList()
        }
      } catch (error) {
        this.$message.error(error.message || '扫描失败')
      } finally {
        this.scanning = false
      }
    },
    
    /**
     * 启动文件监听器
     */
    async handleStartWatcher() {
      this.watcherStarting = true
      try {
        const res = await startFileWatcher()
        this.$message.success(res.msg)
        this.watcherRunning = true
      } catch (error) {
        this.$message.error(error.message || '启动失败')
      } finally {
        this.watcherStarting = false
      }
    }
  }
}
</script>

<style scoped>
.license-file-processor {
  padding: 20px;
}

.operation-buttons {
  display: flex;
  gap: 10px;
  align-items: center;
}

.scan-result {
  animation: fadeIn 0.5s ease-in;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
