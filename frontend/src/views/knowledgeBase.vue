<template>
    <div :class="{'ly-is-full':isFull}" class="kb-container">
        <!-- 顶部操作栏 -->
        <div class="kb-toolbar" v-if="!isFull">
            <el-tag v-if="ssoStatus === 'connected'" type="success" size="small">SSO已连接</el-tag>
            <el-tag v-else-if="ssoStatus === 'loading'" type="info" size="small">SSO连接中...</el-tag>
            <el-tag v-else-if="ssoStatus === 'failed'" type="danger" size="small">SSO连接失败</el-tag>
            <el-tag v-else type="info" size="small">未连接</el-tag>

            <el-button size="small" @click="refreshWithNewToken">
                <el-icon><Refresh /></el-icon>
                刷新
            </el-button>

            <el-button size="small" @click="toggleFull" v-if="!isRedirectMode">
                <el-icon><FullScreen /></el-icon>
                全屏
            </el-button>

            <el-button size="small" @click="switchToIframe" v-if="isRedirectMode && !loading">
                <el-icon><FullScreen /></el-icon>
                切换回嵌入模式
            </el-button>
        </div>

        <!-- 全屏模式下的浮动工具栏 -->
        <div v-if="isFull" class="kb-fullscreen-toolbar">
            <el-button size="small" @click="exitFullscreen">
                <el-icon><FullScreen /></el-icon>
                退出全屏
            </el-button>
            <el-button size="small" @click="refreshWithNewToken">
                <el-icon><Refresh /></el-icon>
                刷新
            </el-button>
        </div>

        <!-- 加载中 -->
        <div v-if="loading" class="kb-loading">
            <el-icon class="is-loading" :size="40"><Loading /></el-icon>
            <p>正在加载知识库...</p>
            <p style="font-size:12px;color:#999;margin-top:8px;">SSO自动登录中</p>
        </div>

        <!-- 错误提示 -->
        <div v-else-if="errorMsg" class="kb-error">
            <el-alert :title="errorMsg" type="error" show-icon :closable="false">
                <template #default>
                    <p>{{ errorDetail }}</p>
                    <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap;">
                        <el-button type="primary" size="small" @click="initKnowledgeBase">重试</el-button>
                        <el-button type="warning" size="small" @click="directAccess">直接访问</el-button>
                    </div>
                </template>
            </el-alert>
        </div>

        <!-- 重定向模式：显示提示信息 -->
        <div v-else-if="isRedirectMode" class="kb-redirect-hint">
            <el-result icon="success" title="SSO登录成功" sub-title="知识库页面已在当前窗口打开">
                <template #extra>
                    <el-button size="small" @click="switchToIframe">切换回嵌入模式</el-button>
                </template>
            </el-result>
        </div>

        <!-- iframe嵌入区域 -->
        <iframe
            v-show="!loading && !errorMsg && iframeUrl && !isRedirectMode"
            ref="kbIframe"
            :src="iframeUrl"
            class="kb-iframe"
            frameborder="0"
            allowfullscreen
            @error="handleIframeError"
            @load="handleIframeLoad"
        ></iframe>
    </div>
</template>

<script>
import { Refresh, FullScreen, Loading } from '@element-plus/icons-vue'
import { phlexingConfig, phlexingSSOLogin } from '@/api/api'

export default {
    name: 'knowledgeBase',
    components: { Refresh, FullScreen, Loading },
    data() {
        return {
            loading: true,
            errorMsg: '',
            errorDetail: '',
            iframeUrl: '',
            ssoStatus: 'loading',
            isFull: false,
            phlexingBaseUrl: '',
            isRedirectMode: false,
            refreshInProgress: false,
            iframeLoadAttempts: 0, // 记录加载尝试次数
        }
    },
    mounted() {
        this.initKnowledgeBase()
    },
    methods: {
        async initKnowledgeBase() {
            // 重置状态
            this.loading = true
            this.errorMsg = ''
            this.errorDetail = ''
            this.ssoStatus = 'loading'
            this.iframeUrl = ''
            this.isRedirectMode = false
            this.iframeLoadAttempts = 0

            try {
                // 1. 获取配置
                const configRes = await phlexingConfig()
                if (configRes.code !== 2000) {
                    this.errorMsg = '获取知识库配置失败'
                    this.errorDetail = configRes.msg || '请联系管理员'
                    this.ssoStatus = 'failed'
                    this.loading = false
                    return
                }

                const config = configRes.data
                this.phlexingBaseUrl = config.base_url

                if (!config.enabled) {
                    this.errorMsg = '知识库功能未启用'
                    this.errorDetail = '请联系管理员启用知识库功能'
                    this.ssoStatus = 'failed'
                    this.loading = false
                    return
                }

                // 2. SSO登录
                if (config.sso_enabled) {
                    // 先获取token，成功后再加载iframe
                    const success = await this.getSSOTokenAndLoad()
                    if (!success) {
                        // token获取失败，已经由 getSSOTokenAndLoad 处理错误状态
                        return
                    }
                } else {
                    // SSO未启用，直接访问
                    this.iframeUrl = config.base_url
                    this.ssoStatus = ''
                    this.loading = false
                }
            } catch (err) {
                console.error('初始化知识库失败:', err)
                this.errorMsg = '初始化知识库失败'
                this.errorDetail = err.message || '网络异常，请稍后重试'
                this.ssoStatus = 'failed'
                this.loading = false
            }
        },

        async getSSOTokenAndLoad() {
            try {
                const ssoRes = await phlexingSSOLogin({})

                if (ssoRes.code === 2000 && ssoRes.data && ssoRes.data.login_success) {
                    const ssoUrl = ssoRes.data.sso_url

                    // 先设置iframeUrl，但保持loading状态
                    this.iframeUrl = ssoUrl
                    this.ssoStatus = 'connected'
                    this.errorMsg = ''
                    this.errorDetail = ''

                    // 等待DOM更新后再加载iframe
                    await this.$nextTick()

                    // 直接加载iframe，不需要测试iframe
                    this.loading = false

                    // 如果iframe已存在，直接设置src
                    if (this.$refs.kbIframe) {
                        this.$refs.kbIframe.src = ssoUrl
                    }

                    return true
                } else {
                    console.warn('SSO令牌生成失败:', ssoRes.msg)
                    this.errorMsg = 'SSO令牌生成失败'
                    this.errorDetail = ssoRes.msg || '请检查AnythingLLM配置'
                    this.ssoStatus = 'failed'
                    this.loading = false
                    return false
                }
            } catch (ssoErr) {
                console.warn('SSO请求异常:', ssoErr)
                this.errorMsg = 'SSO请求异常'
                this.errorDetail = ssoErr.message || '网络异常'
                this.ssoStatus = 'failed'
                this.loading = false
                return false
            }
        },

        // 刷新（重新获取Token）
        async refreshWithNewToken() {
            if (this.refreshInProgress) return

            this.refreshInProgress = true
            this.loading = true

            try {
                const ssoRes = await phlexingSSOLogin({})

                if (ssoRes.code === 2000 && ssoRes.data && ssoRes.data.login_success) {
                    const ssoUrl = ssoRes.data.sso_url
                    this.iframeUrl = ssoUrl
                    this.ssoStatus = 'connected'
                    this.loading = false
                    this.errorMsg = ''
                    this.errorDetail = ''

                    // 重新加载iframe
                    if (this.$refs.kbIframe) {
                        // 先清空再设置，确保强制刷新
                        this.$refs.kbIframe.src = ''
                        await this.$nextTick()
                        this.$refs.kbIframe.src = ssoUrl
                    }

                    this.$message.success('刷新成功')
                } else {
                    this.$message.error('刷新失败: ' + (ssoRes.msg || '未知错误'))
                    this.loading = false
                }
            } catch (err) {
                console.error('刷新失败:', err)
                this.$message.error('刷新失败: ' + (err.message || '网络异常'))
                this.loading = false
            } finally {
                this.refreshInProgress = false
            }
        },

        handleIframeLoad() {
            console.log('iframe加载成功')
            // 加载成功后重置尝试次数
            this.iframeLoadAttempts = 0
        },

        handleIframeError(event) {
            console.warn('iframe加载错误:', event)
            this.iframeLoadAttempts++

            // 如果加载失败且少于3次尝试，自动重试
            if (this.iframeLoadAttempts < 3 && this.iframeUrl) {
                console.log(`第${this.iframeLoadAttempts}次重试...`)
                setTimeout(() => {
                    if (this.$refs.kbIframe) {
                        this.$refs.kbIframe.src = this.iframeUrl
                    }
                }, 1000)
            } else if (this.iframeLoadAttempts >= 3) {
                // 3次失败后，切换到重定向模式
                this.switchToRedirectMode(this.iframeUrl)
            }
        },

        switchToRedirectMode(ssoUrl) {
            this.isRedirectMode = true
            this.ssoStatus = 'connected'
            this.loading = false
            this.iframeUrl = ssoUrl
            this.errorMsg = ''
            this.errorDetail = ''
        },

        switchToIframe() {
            this.isRedirectMode = false
            if (this.iframeUrl) {
                this.$nextTick(() => {
                    if (this.$refs.kbIframe) {
                        this.$refs.kbIframe.src = this.iframeUrl
                    }
                })
            }
        },

        toggleFull() {
            this.isFull = true
            // 进入全屏时刷新token
            this.refreshWithNewToken()
        },

        exitFullscreen() {
            this.isFull = false
        },

        directAccess() {
            this.iframeUrl = this.phlexingBaseUrl
            this.ssoStatus = ''
            this.isRedirectMode = false
            this.loading = false
            this.errorMsg = ''
            this.errorDetail = ''
        },
    },
}
</script>

<style scoped>
.kb-container {
    width: 100%;
    height: calc(100vh - 120px);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    position: relative;
}
.kb-container.ly-is-full {
    position: fixed;
    top: 0; left: 0;
    width: 100vw; height: 100vh;
    z-index: 9999;
    background: #fff;
}
.kb-toolbar {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    background: #fff;
    border-bottom: 1px solid #eee;
    flex-shrink: 0;
    flex-wrap: wrap;
}
.kb-fullscreen-toolbar {
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
.kb-iframe {
    flex: 1;
    width: 100%;
    height: 100%;
    border: none;
}
.kb-loading {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    color: #666;
    font-size: 14px;
}
.kb-loading p { margin-top: 12px; }
.kb-error {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 40px;
}
.kb-redirect-hint {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 40px;
    background: #f5f7fa;
}
.kb-redirect-hint .el-result {
    background: #fff;
    padding: 40px;
    border-radius: 8px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.1);
}
</style>