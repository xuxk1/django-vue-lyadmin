<template>
    <div :class="{'ly-is-full':isFull}" class="cb-container">
        <!-- 顶部操作栏 -->
        <div class="cb-toolbar" v-if="!isFull">
            <el-tag v-if="loadStatus === 'success'" type="success" size="small">已连接</el-tag>
            <el-tag v-else-if="loadStatus === 'loading'" type="info" size="small">加载中...</el-tag>
            <el-tag v-else-if="loadStatus === 'failed'" type="danger" size="small">加载失败</el-tag>

            <el-button size="small" @click="refresh">
                <el-icon><Refresh /></el-icon>
                刷新
            </el-button>

            <el-button size="small" @click="toggleFull">
                <el-icon><FullScreen /></el-icon>
                全屏
            </el-button>
        </div>

        <!-- 全屏模式下的浮动工具栏 -->
        <div v-if="isFull" class="cb-fullscreen-toolbar">
            <el-button size="small" @click="exitFullscreen">
                <el-icon><FullScreen /></el-icon>
                退出全屏
            </el-button>
            <el-button size="small" @click="refresh">
                <el-icon><Refresh /></el-icon>
                刷新
            </el-button>
        </div>

        <!-- 加载中 -->
        <div v-if="loading" class="cb-loading">
            <el-icon class="is-loading" :size="40"><Loading /></el-icon>
            <p>正在加载案例看板...</p>
            <p style="font-size:12px;color:#999;margin-top:8px;">正在通过后端代理访问 GitLab</p>
        </div>

        <!-- 错误提示 -->
        <div v-else-if="errorMsg" class="cb-error">
            <el-alert :title="errorMsg" type="error" show-icon :closable="false">
                <template #default>
                    <p>{{ errorDetail }}</p>
                    <div style="margin-top:12px;">
                        <el-button type="primary" size="small" @click="initCaseBoard">重试</el-button>
                    </div>
                </template>
            </el-alert>
        </div>

        <!-- iframe嵌入区域 -->
        <iframe
            v-show="!loading && !errorMsg && iframeUrl"
            ref="cbIframe"
            :src="iframeUrl"
            class="cb-iframe"
            frameborder="0"
            allowfullscreen
            @load="handleIframeLoad"
        ></iframe>
    </div>
</template>

<script>
import { Refresh, FullScreen, Loading } from '@element-plus/icons-vue'
import { caseBoardConfig } from '@/api/api'

export default {
    name: 'caseBoard',
    components: { Refresh, FullScreen, Loading },
    data() {
        return {
            loading: true,
            errorMsg: '',
            errorDetail: '',
            iframeUrl: '',
            loadStatus: 'loading', // loading / success / failed
            isFull: false,
        }
    },
    mounted() {
        this.initCaseBoard()
    },
    methods: {
        async initCaseBoard() {
            // 重置状态
            this.loading = true
            this.errorMsg = ''
            this.errorDetail = ''
            this.iframeUrl = ''
            this.loadStatus = 'loading'

            try {
                const configRes = await caseBoardConfig({})
                if (configRes.code !== 2000) {
                    this.errorMsg = '获取案例看板配置失败'
                    this.errorDetail = configRes.msg || '请联系管理员'
                    this.loadStatus = 'failed'
                    this.loading = false
                    return
                }

                const config = configRes.data
                if (!config.enabled) {
                    this.errorMsg = '案例看板功能未启用'
                    this.errorDetail = '请联系管理员在 config.py 中启用 GitLab 案例看板配置'
                    this.loadStatus = 'failed'
                    this.loading = false
                    return
                }

                if (!config.page_url) {
                    this.errorMsg = '案例看板页面未配置'
                    this.errorDetail = '请联系管理员配置 GITLAB_CASE_BOARD_PAGE（HTML 页面在 GitLab 上的路径）'
                    this.loadStatus = 'failed'
                    this.loading = false
                    return
                }

                this.iframeUrl = config.page_url
                await this.$nextTick()
                this.loading = false
            } catch (err) {
                console.error('初始化案例看板失败:', err)
                this.errorMsg = '初始化案例看板失败'
                this.errorDetail = err.message || '网络异常，请稍后重试'
                this.loadStatus = 'failed'
                this.loading = false
            }
        },

        // 刷新（重新加载 iframe）
        refresh() {
            if (this.iframeUrl) {
                this.$refs.cbIframe.src = ''
                this.$nextTick(() => {
                    this.$refs.cbIframe.src = this.iframeUrl
                })
            } else {
                this.initCaseBoard()
            }
        },

        handleIframeLoad() {
            console.log('案例看板 iframe 加载成功')
            this.loadStatus = 'success'
        },

        toggleFull() {
            this.isFull = true
        },

        exitFullscreen() {
            this.isFull = false
        },
    },
}
</script>

<style scoped>
.cb-container {
    width: 100%;
    height: calc(100vh - 120px);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    position: relative;
}
.cb-container.ly-is-full {
    position: fixed;
    top: 0; left: 0;
    width: 100vw; height: 100vh;
    z-index: 9999;
    background: #fff;
}
.cb-toolbar {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    background: #fff;
    border-bottom: 1px solid #eee;
    flex-shrink: 0;
    flex-wrap: wrap;
}
.cb-fullscreen-toolbar {
    position: fixed;
    top: 20px;
    right: 20px;
    z-index: 10000;
    background: rgba(255, 255, 255, 0.95);
    border-radius: 8px;
    padding: 8px 12px;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.15);
    display: flex;
    gap: 8px;
    border: 1px solid #e4e7ed;
}
.cb-iframe {
    flex: 1;
    width: 100%;
    height: 100%;
    border: none;
}
.cb-loading {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    color: #666;
    font-size: 14px;
}
.cb-loading p { margin-top: 12px; }
.cb-error {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 40px;
}
</style>
