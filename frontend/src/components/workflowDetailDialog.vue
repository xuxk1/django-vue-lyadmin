<template>
    <el-dialog v-model="dialogVisible" title="流程详情" width="900px">
        <div v-loading="loading">
            <!-- 基本信息 -->
            <el-descriptions :column="2" border v-if="currentRow">
                <el-descriptions-item label="流程编号">{{ currentRow.instance_no }}</el-descriptions-item>
                <el-descriptions-item label="流程类型">{{ currentRow.workflow_type_name }}</el-descriptions-item>
                <el-descriptions-item label="流程标题" :span="2">{{ currentRow.title }}</el-descriptions-item>
                <el-descriptions-item label="申请人">{{ currentRow.applicant_name }}</el-descriptions-item>
                <el-descriptions-item label="申请部门">{{ currentRow.applicant_dept_name || '-' }}</el-descriptions-item>
                <el-descriptions-item label="状态">
                    <el-tag v-if="currentRow.status==0" type="info">草稿</el-tag>
                    <el-tag v-else-if="currentRow.status==1" type="warning">审批中</el-tag>
                    <el-tag v-else-if="currentRow.status==2" type="success">已通过</el-tag>
                    <el-tag v-else-if="currentRow.status==3" type="danger">已驳回</el-tag>
                    <el-tag v-else-if="currentRow.status==4" type="">已撤回</el-tag>
                    <el-tag v-else-if="currentRow.status==6" type="primary">已退回</el-tag>
                </el-descriptions-item>
                <el-descriptions-item label="当前步骤">{{ getCurrentStepNumber(currentRow) }}/{{ currentRow.total_steps }}</el-descriptions-item>
                <el-descriptions-item label="创建时间" :span="2">{{ currentRow.create_datetime }}</el-descriptions-item>
                <el-descriptions-item label="备注" :span="2">{{ currentRow.remark || '-' }}</el-descriptions-item>
            </el-descriptions>

            <!-- 申请信息（表单数据） -->
            <div style="margin-top: 20px;" v-if="currentRow && currentRow.form_data">
                <h4 style="margin-bottom: 15px;">申请信息</h4>
                <!-- 布局：内容少的短字段（状态、产品线等）多列紧凑显示在上方，长内容字段（路径、说明等）单列显示在下方 -->
                <el-descriptions v-if="formDataGroups.shortFields.length > 0" :column="Math.min(4, formDataGroups.shortFields.length)" border>
                    <el-descriptions-item v-for="item in formDataGroups.shortFields" :key="item.key" :label="item.label">
                        <template v-if="isScanReportValue(item.value)">
                            <el-button type="primary" size="mini" @click="showScanReport(item.value)">点击查看报告</el-button>
                        </template>
                        <template v-else-if="isScanStatusField(item.key)">
                            <el-tag :type="getScanStatusTagType(item.value)" size="small">{{ formatFieldValue(item.value, item.key) }}</el-tag>
                        </template>
                        <template v-else>
                            <span style="word-break: break-all; overflow-wrap: break-word;">{{ formatFieldValue(item.value, item.key) }}</span>
                        </template>
                    </el-descriptions-item>
                </el-descriptions>
                <el-descriptions v-if="formDataGroups.longFields.length > 0" :column="1" border style="margin-top: 16px;">
                    <el-descriptions-item v-for="item in formDataGroups.longFields" :key="item.key" :label="item.label">
                        <template v-if="isScanReportValue(item.value)">
                            <el-button type="primary" size="mini" @click="showScanReport(item.value)">点击查看报告</el-button>
                        </template>
                        <template v-else-if="isScanStatusField(item.key)">
                            <el-tag :type="getScanStatusTagType(item.value)" size="small">{{ formatFieldValue(item.value, item.key) }}</el-tag>
                        </template>
                        <template v-else>
                            <!-- 长文本（如软件包路径）超宽时自动换行，避免撑开表格布局 -->
                            <span style="word-break: break-all; overflow-wrap: break-word;">{{ formatFieldValue(item.value, item.key) }}</span>
                        </template>
                    </el-descriptions-item>
                </el-descriptions>
            </div>

            <!-- 扫描报告弹窗 -->
            <el-dialog v-model="scanReportDialogVisible" title="扫描报告" width="80%" top="5vh" append-to-body>
                <div v-loading="scanReportLoading" style="min-height: 200px;">
                    <!-- iframe srcdoc 隔离报告自身样式（报告内的 style/全局选择器不影响外层页面） -->
                    <iframe v-if="scanReportContent" :srcdoc="scanReportContent"
                            style="width: 100%; height: 70vh; border: none; background: #fff;"></iframe>
                </div>
            </el-dialog>

            <!-- 完整审批流程 -->
            <div style="margin-top: 20px;" v-if="currentRow && currentRow.steps_info && currentRow.steps_info.length > 0">
                <h4 style="margin-bottom: 15px;">完整审批流程</h4>
                <el-card shadow="hover">
                    <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px;">
                        <div 
                            v-for="(step, index) in displaySteps" 
                            :key="step.id || 'complete'"
                            style="flex: 1; min-width: 200px; text-align: center; position: relative;"
                        >
                            <!-- 节点图标 -->
                            <div style="position: relative; display: inline-block;">
                                <el-avatar 
                                    :size="50" 
                                    :type="getStepIconType(step, index)"
                                    :style="{ backgroundColor: getStepColor(step, index), color: '#fff' }"
                                >
                                    <el-icon><component :is="getStepIcon(step)"></component></el-icon>
                                </el-avatar>
                                
                                <!-- 当前节点标记（仅对非完成节点且非结束节点） -->
                                <el-tag 
                                    v-if="!isCompleteNode(step) && !isEndNode(step) && checkHasPendingTasks(getStepLevelOrder(step)) && currentRow.status != 2" 
                                    type="warning" 
                                    size="small"
                                    style="position: absolute; top: -8px; right: -8px;"
                                >
                                    当前
                                </el-tag>
                            </div>
                            
                            <!-- 节点名称 -->
                            <div style="margin-top: 10px; font-weight: bold;">{{ step.step_name }}</div>
                            
                            <!-- 节点类型（完成节点不显示） -->
                            <div v-if="!isCompleteNode(step)" style="font-size: 12px; color: #909399; margin-top: 5px;">
                                <span v-if="isEndNode(step)">{{ getNodeTypeName(step.node_type) }}</span>
                                <span v-else-if="step.approver_type == null || step.approver_type === undefined">未配置</span>
                                <span v-else-if="step.approver_type == 6 && step.multi_level_config">{{ getMultiLevelTypeDisplay(step) }}</span>
                                <span v-else-if="step.approver_type == 8 && step.internal_conditions">{{ getConditionTypeDisplay(step) }}</span>
                                <span v-else>{{ getStepTypeName(step.approver_type) }}</span>
                            </div>
                            
                            <!-- 实际审批人（完成节点显示所有审批人，结束节点不显示） -->
                            <div style="margin-top: 8px; font-size: 13px;">
                                <span v-if="isCompleteNode(step)" style="color: #67C23A;">
                                    <strong>全部通过</strong>
                                </span>
                                <span v-else-if="isEndNode(step)" style="color: #909399;">
                                    <strong>流程结束</strong>
                                </span>
                                <span v-else-if="step.approver_type == null || step.approver_type === undefined" style="color: #F56C6C;">
                                    <strong>未配置审批人</strong>
                                </span>
                                <!-- 自动跳过的步骤显示绿色+已跳过+具体审批人 -->
                                <span v-else-if="isAutoSkippedStep(step)" style="color: #67C23A;">
                                    <strong>已跳过</strong><br/>
                                    <span style="font-size: 12px;">{{ getActualApprovers(step).join('、') }}</span>
                                </span>
                                <span v-else-if="getActualApprovers(step).length > 0" style="color: #606266;">
                                    <strong>审批人：</strong>{{ getActualApprovers(step).join('、') }}
                                </span>
                                <span v-else style="color: #C0C4CC;">待分配</span>
                            </div>
                            
                            <!-- 箭头（最后一个节点不显示） -->
                            <div v-if="index < displaySteps.length - 1" style="position: absolute; right: -20px; top: 20px; color: #C0C4CC; font-size: 20px;">
                                →
                            </div>
                        </div>
                    </div>
                </el-card>
            </div>

            <!-- 审批历史 -->
            <div style="margin-top: 20px;" v-if="currentRow && currentRow.approval_history && currentRow.approval_history.length > 0">
                <h4 style="margin-bottom: 15px; font-size: 16px; font-weight: bold;">审批历史</h4>
                <el-timeline>
                    <el-timeline-item 
                        v-for="(task, index) in currentRow.approval_history" 
                        :key="index" 
                        :type="getTimelineType(task.approve_result)"
                        size="large"
                    >
                        <div style="padding: 10px; background-color: #f5f7fa; border-radius: 4px; margin-bottom: 10px;">
                            <!-- 第一行：步骤名称 + 审批人类型 + 审批人 + 状态标签 -->
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                                <div style="display: flex; align-items: center; gap: 8px;">
                                    <strong style="font-size: 14px;">{{ task.step_name }}</strong>
                                    <el-tag v-if="task.level_approver_type_display" type="info" size="small" style="font-size: 12px;">{{ task.level_approver_type_display }}</el-tag>
                                    <span style="color: #606266; font-size: 13px;">→ {{ task.approver_name }}</span>
                                </div>
                                <el-tag v-if="isSkippedTask(task)" type="info" size="small">已跳过</el-tag>
                                <el-tag v-else-if="task.approve_result==1" type="success" size="small">通过</el-tag>
                                <el-tag v-else-if="task.approve_result==2" type="danger" size="small">驳回</el-tag>
                                <el-tag v-else-if="task.approve_result==3" type="warning" size="small">退回</el-tag>
                            </div>
                                            
                            <!-- 第二行：审批意见/跳过原因 -->
                            <div v-if="task.approve_comment" style="margin-bottom: 8px; padding-left: 8px; border-left: 3px solid #409EFF; background-color: #ecf5ff; padding: 8px; border-radius: 2px;">
                                <span v-if="isSkippedTask(task)" style="color: #909399; font-size: 13px;">
                                    <i class="el-icon-info"></i> 跳过原因：{{ getSkipReason(task) }}
                                </span>
                                <span v-else style="color: #606266; font-size: 13px;">{{ task.approve_comment }}</span>
                            </div>
                            
                            <!-- 第三行：审批时间 -->
                            <div style="text-align: right; color: #909399; font-size: 12px;">
                                <i class="el-icon-time"></i> {{ task.approve_time }}
                            </div>
                            
                            <!-- 评论列表：展示该节点下的历史评论 -->
                            <div v-if="getTaskComments(task).length > 0" style="margin-top: 8px; padding-top: 8px; border-top: 1px dashed #DCDFE6;">
                                <div v-for="comment in getTaskComments(task)" :key="comment.id" style="margin-bottom: 6px; background-color: #fff; border-radius: 4px; padding: 6px 8px;">
                                    <span style="font-weight: bold; font-size: 13px; color: #303133;">{{ comment.user_name }}</span>
                                    <span style="font-size: 13px; color: #606266;">：{{ comment.content }}</span>
                                    <!-- 评论附件列表：支持下载 -->
                                    <div v-if="comment.attachments && comment.attachments.length > 0" style="margin-top: 6px;">
                                        <div v-for="(att, attIdx) in comment.attachments" :key="attIdx" style="display: inline-flex; align-items: center; gap: 4px; background-color: #ecf5ff; border-radius: 4px; padding: 2px 8px; margin-right: 6px; font-size: 12px;">
                                            <i class="el-icon-paperclip" style="color: #409EFF;"></i>
                                            <span style="max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{{ att.name }}</span>
                                            <span style="color: #909399;">{{ formatFileSize(att.size) }}</span>
                                            <el-link type="primary" :underline="false" style="font-size: 12px;" @click="downloadCommentAttachment(comment, att)">下载</el-link>
                                        </div>
                                    </div>
                                    <div style="text-align: right; color: #C0C4CC; font-size: 12px; margin-top: 2px;">{{ comment.create_datetime }}</div>
                                </div>
                            </div>
                            
                            <!-- 评论输入：评论后邮件通知当前待审批节点（流程当前活动节点）的审批人 -->
                            <div v-if="canComment" style="margin-top: 8px;">
                                <div style="display: flex; align-items: center; gap: 8px;">
                                    <el-input v-model="commentInputs[task.id]" placeholder="添加评论，提交后将邮件通知当前待审批节点审批人" size="small" clearable @keyup.enter.native="submitComment(task)" />
                                    <!-- 隐藏的文件选择框（每个节点一个，点击附件按钮触发） -->
                                    <input type="file" multiple style="display: none;" :data-task-id="task.id" :ref="setCommentFileInputRef" @change="handleCommentFileChange(task, $event)" />
                                    <el-button size="small" icon="el-icon-paperclip" @click="triggerCommentFileSelect(task)">附件</el-button>
                                    <el-button type="primary" size="small" :loading="commentSubmitting[task.id]" @click="submitComment(task)">评论</el-button>
                                </div>
                                <!-- 待上传附件列表 -->
                                <div v-if="commentFiles[task.id] && commentFiles[task.id].length > 0" style="margin-top: 6px;">
                                    <el-tag v-for="(file, fileIdx) in commentFiles[task.id]" :key="fileIdx" closable size="small" @close="removeCommentFile(task, fileIdx)" style="margin-right: 6px;">
                                        <i class="el-icon-paperclip"></i> {{ file.name }}（{{ formatFileSize(file.size) }}）
                                    </el-tag>
                                </div>
                            </div>
                            <!-- 流程已通过或所有节点已完成时禁止评论 -->
                            <div v-else style="margin-top: 8px; color: #C0C4CC; font-size: 12px;">
                                <i class="el-icon-lock"></i> 流程已结束，无法继续评论
                            </div>
                        </div>
                    </el-timeline-item>
                </el-timeline>
            </div>
        </div>
        <template #footer>
            <el-button @click="dialogVisible = false">关闭</el-button>
        </template>
    </el-dialog>
</template>

<script>
import { workflowInstanceDetail, workflowType, packageScanReport, workflowCommentAdd, workflowCommentDownload } from '@/api/api';

export default {
    name: 'workflowDetailDialog',
    props: {
        // v-model 控制弹窗显示
        modelValue: {
            type: Boolean,
            default: false
        },
        // 流程实例ID
        instanceId: {
            type: [String, Number],
            default: null
        }
    },
    emits: ['update:modelValue'],
    data() {
        return {
            currentRow: null,
            workflowTypes: [],  // 流程类型列表（用于解析表单字段标签/选项）
            loading: false,
            scanReportDialogVisible: false,  // 扫描报告弹窗
            scanReportContent: '',  // 扫描报告 html 内容
            scanReportLoading: false,
            commentInputs: {},  // 各节点评论输入框内容 key=task.id
            commentSubmitting: {},  // 各节点评论提交中状态 key=task.id
            commentFiles: {},  // 各节点待上传附件列表 key=task.id（元素为原始 File 对象）
            commentFileInputs: {}  // 各节点隐藏文件选择框引用 key=task.id
        }
    },
    computed: {
        dialogVisible: {
            get() { return this.modelValue },
            set(val) { this.$emit('update:modelValue', val) }
        },
        // 显示的步骤列表（包括完成节点）
        displaySteps() {
            if (!this.currentRow || !this.currentRow.steps_info) {
                return []
            }

            const steps = [...this.currentRow.steps_info]

            // 如果流程已通过，添加一个"完成"节点
            if (this.currentRow.status === 2) {
                steps.push({
                    id: 'complete',
                    step_name: '完成',
                    step_order: 999,
                    approver_type: 0,  // 特殊类型表示完成节点
                    is_complete_node: true
                })
            }

            return steps
        },
        // 申请信息按内容长度分组：长内容字段（路径、说明等）集中左侧显示，短字段（状态、产品线等）右侧显示
        formDataGroups() {
            const groups = { longFields: [], shortFields: [] }
            if (!this.currentRow || !this.currentRow.form_data) return groups
            const formData = this.visibleFormData(this.currentRow.form_data)
            Object.keys(formData).forEach(key => {
                const value = formData[key]
                const item = { key, value, label: this.getFieldLabel(this.currentRow.workflow_type, key) }
                if (this.isLongContentField(key, item.label, value)) {
                    groups.longFields.push(item)
                } else {
                    groups.shortFields.push(item)
                }
            })
            return groups
        },
        // 是否允许发表评论（流程已通过或所有节点已完成时禁止，由后端详情接口返回）
        canComment() {
            return !!(this.currentRow && this.currentRow.can_comment)
        }
    },
    watch: {
        // 弹窗打开时加载详情
        modelValue(val) {
            if (val && this.instanceId) {
                this.loadDetail()
            }
        },
        // 父组件先设置instanceId再打开弹窗时，兜底加载
        instanceId() {
            if (this.modelValue && this.instanceId) {
                this.loadDetail()
            }
        }
    },
    created() {
        this.getWorkflowTypes()
        // 首次挂载时弹窗即处于打开状态（如从邮件链接进入时父组件在 created 中同步打开弹窗，
        // watch 不会因初始值触发），需在此主动加载详情，否则弹窗内容为空
        if (this.modelValue && this.instanceId) {
            this.loadDetail()
        }
    },
    methods: {
        // 根据实例ID加载流程详情
        loadDetail() {
            this.loading = true
            workflowInstanceDetail(this.instanceId).then(res => {
                this.loading = false
                const detail = res.data?.data || res.data
                if (res.code === 2000 && detail) {
                    this.currentRow = detail
                } else {
                    this.currentRow = null
                    this.$message.warning('未找到对应的流程详情信息')
                }
            }).catch(err => {
                this.loading = false
                this.currentRow = null
                console.error('[WorkflowDetailDialog] 获取流程详情失败:', err)
                this.$message.error('获取流程详情失败')
            })
        },
        // 获取流程类型（用于解析表单字段标签/选项）
        getWorkflowTypes() {
            workflowType({status: 1}).then(res => {
                if (res.code === 2000) {
                    this.workflowTypes = res.data.data || []
                }
            }).catch(err => {
                console.error('[WorkflowDetailDialog] 获取流程类型失败:', err)
                this.workflowTypes = []
            })
        },
        // 获取指定任务（节点）下的评论列表
        getTaskComments(task) {
            if (!task || !this.currentRow || !this.currentRow.comments) {
                return []
            }
            return this.currentRow.comments.filter(c => c.task === task.id)
        },
        // 提交评论（支持附件上传，评论后邮件通知当前待审批节点审批人）
        submitComment(task) {
            const content = (this.commentInputs[task.id] || '').trim()
            if (!content) {
                this.$message.warning('请输入评论内容')
                return
            }
            if (!this.currentRow) {
                return
            }
            const files = this.commentFiles[task.id] || []
            // 附件大小校验（与后端保持一致：单文件不超过 50M）
            for (const file of files) {
                if (file.size > 50 * 1024 * 1024) {
                    this.$message.warning(`附件 ${file.name} 超过 50M 大小限制`)
                    return
                }
            }
            this.commentSubmitting[task.id] = true
            const formData = new FormData()
            formData.append('instance', this.currentRow.id)
            formData.append('task', task.id)
            formData.append('content', content)
            files.forEach(file => formData.append('files', file))
            workflowCommentAdd(formData).then(res => {
                this.commentSubmitting[task.id] = false
                if (res.code === 2000) {
                    this.$message.success('评论成功')
                    this.commentInputs[task.id] = ''
                    this.commentFiles[task.id] = []
                    // 刷新详情以获取最新评论列表
                    this.loadDetail()
                } else {
                    this.$message.error(res.msg || '评论失败')
                }
            }).catch(err => {
                this.commentSubmitting[task.id] = false
                console.error('[WorkflowDetailDialog] 提交评论失败:', err)
                this.$message.error('评论失败')
            })
        },
        // 记录各节点隐藏文件选择框的引用（v-for 中通过 data-task-id 关联）
        setCommentFileInputRef(el) {
            if (!el) return
            this.commentFileInputs[el.dataset.taskId] = el
        },
        // 触发节点附件文件选择
        triggerCommentFileSelect(task) {
            const input = this.commentFileInputs[task.id]
            if (input) input.click()
        },
        // 附件文件选择变化（追加到待上传列表，同名同大小文件去重）
        handleCommentFileChange(task, event) {
            const files = Array.from(event.target.files || [])
            if (files.length === 0) return
            const current = [...(this.commentFiles[task.id] || [])]
            files.forEach(file => {
                if (!current.some(existing => existing.name === file.name && existing.size === file.size)) {
                    current.push(file)
                }
            })
            this.commentFiles[task.id] = current
            // 清空 input 值，允许重复选择同一文件
            event.target.value = ''
        },
        // 移除待上传的评论附件
        removeCommentFile(task, index) {
            const files = [...(this.commentFiles[task.id] || [])]
            files.splice(index, 1)
            this.commentFiles[task.id] = files
        },
        // 下载评论附件（接口返回 blob，以原始文件名保存）
        downloadCommentAttachment(comment, attachment) {
            workflowCommentDownload({id: comment.id, name: attachment.name}).then(blob => {
                // 后端错误时返回 JSON，需从 blob 中解析提示
                if (blob.type && blob.type.includes('application/json')) {
                    const reader = new FileReader()
                    reader.onload = () => {
                        try {
                            const res = JSON.parse(reader.result)
                            this.$message.error(res.msg || '附件下载失败')
                        } catch (e) {
                            this.$message.error('附件下载失败')
                        }
                    }
                    reader.readAsText(blob)
                    return
                }
                const link = document.createElement('a')
                link.href = URL.createObjectURL(blob)
                link.download = attachment.name
                document.body.appendChild(link)
                link.click()
                document.body.removeChild(link)
                URL.revokeObjectURL(link.href)
            }).catch(err => {
                console.error('[WorkflowDetailDialog] 附件下载失败:', err)
                this.$message.error('附件下载失败')
            })
        },
        // 格式化文件大小（B/KB/MB）
        formatFileSize(size) {
            if (size === null || size === undefined || size === '') return ''
            size = Number(size)
            if (isNaN(size) || size < 0) return ''
            if (size < 1024) return size + ' B'
            if (size < 1024 * 1024) return (size / 1024).toFixed(1) + ' KB'
            return (size / 1024 / 1024).toFixed(1) + ' MB'
        },
        // 获取当前步骤序号（用于显示，如 3/4）
        getCurrentStepNumber(row) {
            if (!row) return 1
            
            const history = row.approval_history || []
            const stepsInfo = row.steps_info || []
            
            // 如果流程已通过，返回总步骤数
            if (row.status === 2) {
                return row.total_steps
            }
            
            // 将所有 steps_info 按 level_order 排序
            const sortedSteps = [...stepsInfo].sort((a, b) => a.level_order - b.level_order)
            
            // 找到第一个有待审批任务的层级的索引
            for (let i = 0; i < sortedSteps.length; i++) {
                const step = sortedSteps[i]
                const levelOrder = step.level_order
                
                // 检查该层级是否有待审批任务
                const hasPendingTasks = this.checkHasPendingTasksAtLevel(levelOrder, row)
                if (hasPendingTasks) {
                    // 返回索引 + 1 作为步骤序号
                    return i + 1
                }
            }
            
            // 如果所有层级都没有待审批任务，返回总步骤数
            return sortedSteps.length
        },
        // 获取时间线类型
        getTimelineType(result) {
            if (result === 1) return 'success'
            if (result === 2) return 'danger'
            if (result === 3) return 'warning'
            return ''
        },
        // 申请信息展示用表单数据（过滤下划线开头的内部隐藏字段，如包扫描路径确认记录）
        visibleFormData(formData) {
            const parsed = this.parseFormData(formData)
            const visible = {}
            Object.keys(parsed).forEach(key => {
                if (!key.startsWith('_')) visible[key] = parsed[key]
            })
            return visible
        },
        // 判断字段是否属于长内容（单列显示在下方）：字段名含客户/路径/说明/备注/描述/原因/内容/报告/地址/链接等关键字，
        // 或值长度超过20字符（如长文件名、长路径），其余短字段（状态、产品线等）多列紧凑显示在上方
        isLongContentField(fieldKey, label, value) {
            // "客户"相关字段（客户名称/其他客户）归入长内容组，保持相邻显示；"包扫描状态"不含关键字归入短字段组
            const LONG_KEYWORDS = /客户|路径|说明|备注|描述|原因|内容|报告|地址|链接|url|path|desc|remark|reason/i
            if (LONG_KEYWORDS.test(fieldKey) || LONG_KEYWORDS.test(label)) return true
            return String(value || '').length > 20
        },
        // 解析表单数据（将 JSON 字符串转换为对象）
        parseFormData(formData) {
            if (!formData) return {}
            try {
                return typeof formData === 'string' ? JSON.parse(formData) : formData
            } catch (e) {
                console.error('解析表单数据失败:', e)
                return {}
            }
        },
        // 判断是否为包扫描状态字段
        isScanStatusField(fieldKey) {
            return fieldKey === 'package_scan_status'
        },
        // 获取包扫描状态对应的标签类型（PASS绿色/SCANNING/WARN黄色/REJECT/FAIL/ERROR红色）
        getScanStatusTagType(value) {
            const v = String(value || '').trim().toUpperCase()
            if (v === 'PASS') return 'success'
            if (v === 'SCANNING' || v === 'WARN') return 'warning'
            if (v === 'REJECT' || v === 'FAIL' || v === 'ERROR') return 'danger'
            return 'info'
        },
        // 判断字段值是否为扫描报告（html 内容或以 / 开头的报告文件路径）
        isScanReportValue(value) {
            if (!value || typeof value !== 'string') return false
            const v = value.trim()
            if (!v) return false
            // html 报告内容：以 DOCTYPE/html 声明开头或包含 html 标签
            if (v.startsWith('<!DOCTYPE') || v.startsWith('<html') || v.includes('<html')) return true
            // 报告文件路径：以 / 开头的 .html 文件（回填内容获取失败时回退的路径字符串）
            return v.startsWith('/') && v.endsWith('.html')
        },
        // 查看扫描报告（html 内容直接展示；路径则请求后端获取内容后展示）
        showScanReport(value) {
            const v = (value || '').trim()
            if (v.startsWith('/')) {
                // 路径：请求后端接口获取报告内容（SSH 读取远程文件）
                this.scanReportLoading = true
                packageScanReport({report_path: v}).then(res => {
                    this.scanReportLoading = false
                    if (res.code === 2000) {
                        this.scanReportContent = res.data.content
                        this.scanReportDialogVisible = true
                    } else {
                        this.$message.error(res.msg || '获取扫描报告失败')
                    }
                }).catch(() => {
                    this.scanReportLoading = false
                    this.$message.error('获取扫描报告失败')
                })
            } else {
                // 已存储 html 内容，直接弹窗展示
                this.scanReportContent = v
                this.scanReportDialogVisible = true
            }
        },
        // 获取字段标签
        getFieldLabel(workflowTypeId, fieldKey) {
            // 包扫描四个固定字段（form_data 固定 key，无需流程表单配置）：form_schema 未配置时按固定 label 展示
            const SCAN_FIELD_LABELS = {
                package_scan_status: '包扫描状态',
                package_scan_report: '扫描报告',
                package_scan_path: '扫描软件包路径',
                package_scan_build_number: '扫描构建编号',
            }
            // 从 workflowTypes 中找到对应的流程类型
            const workflowType = this.workflowTypes.find(item => item.id === workflowTypeId)
            if (workflowType && workflowType.form_schema) {
                try {
                    const formSchema = typeof workflowType.form_schema === 'string' 
                        ? JSON.parse(workflowType.form_schema) 
                        : workflowType.form_schema
                    const field = formSchema.find(f => f.field === fieldKey)
                    return field ? field.label : (SCAN_FIELD_LABELS[fieldKey] || fieldKey)
                } catch (e) {
                    console.error('解析表单配置失败:', e)
                }
            }
            return SCAN_FIELD_LABELS[fieldKey] || fieldKey
        },
        // 格式化字段值
        formatFieldValue(value, fieldKey) {
            if (value === null || value === undefined) return '-'
            
            // 如果有 fieldKey，尝试获取选项的 label
            if (fieldKey && this.currentRow && this.currentRow.workflow_type) {
                const workflowType = this.workflowTypes.find(item => item.id === this.currentRow.workflow_type)
                if (workflowType && workflowType.form_schema) {
                    try {
                        const formSchema = typeof workflowType.form_schema === 'string' 
                            ? JSON.parse(workflowType.form_schema) 
                            : workflowType.form_schema
                        const field = formSchema.find(f => f.field === fieldKey)
                        
                        // 如果字段有 options，将 value 转换为 label
                        if (field && field.options) {
                            // 处理数组值（如复选框、多选下拉）
                            if (Array.isArray(value)) {
                                const labels = value.map(v => {
                                    const opt = field.options.find(opt => opt.value === v)
                                    return opt ? opt.label : v
                                })
                                return labels.join(', ')
                            }
                            // 处理单个值
                            const option = field.options.find(opt => opt.value === value)
                            if (option) {
                                return option.label
                            }
                        }
                    } catch (e) {
                        console.error('解析表单配置失败:', e)
                    }
                }
            }
            
            // 默认返回原始值
            if (Array.isArray(value)) {
                return value.length > 0 ? value.join(', ') : '-'
            }
            if (typeof value === 'object') {
                return JSON.stringify(value)
            }
            return value
        },
        // 获取步骤图标类型
        getStepIconType(step, index) {
            // 完成节点显示绿色
            if (step.is_complete_node) {
                return 'success'
            }
            
            // 结束节点（node_type=5）只有在流程已通过时才显示绿色
            if (this.isEndNode(step)) {
                if (this.currentRow && this.currentRow.status === 2) {
                    return 'success' // 流程已通过，结束节点显示绿色
                }
                return 'info' // 流程未通过，结束节点显示灰色
            }
            
            // 如果流程已通过，所有节点都显示为已完成（绿色）
            if (this.currentRow && this.currentRow.status === 2) {
                return 'success'
            }
            
            // 检查该步骤是否被自动跳过
            const stepId = step.id
            const skippedSteps = this.currentRow.skipped_steps || []
            if (skippedSteps.includes(stepId)) {
                return 'success' // 绿色 - 自动跳过（已完成）
            }
            
            const stepLevelOrder = this.getStepLevelOrder(step)
            const currentDisplayStep = this.calculateDisplayStep(this.currentRow)
            
            // 检查该步骤是否被驳回或退回
            const isRejected = this.checkStepIsRejected(stepLevelOrder)
            if (isRejected) {
                return 'danger' // 已驳回/退回
            }
            
            // 检查该步骤是否已完成（有审批通过的记录）
            const isCompleted = this.checkStepIsCompleted(stepLevelOrder)
            if (isCompleted) {
                return 'success' // 已完成
            }
            
            // 检查该步骤是否有待审批的任务
            const hasPendingTasks = this.checkHasPendingTasks(stepLevelOrder)
            
            if (hasPendingTasks) {
                return 'warning' // 当前节点（有待审批任务）
            } else if (stepLevelOrder < currentDisplayStep) {
                return 'success' // 已完成
            } else {
                // 对于后续节点，需要检查流程是否已经终止（驳回/退回）
                if (this.isWorkflowTerminated()) {
                    return 'info' // 流程已终止，后续节点显示灰色
                }
                return 'info' // 未开始
            }
        },
        // 获取步骤颜色
        getStepColor(step, index) {
            // 完成节点显示绿色
            if (step.is_complete_node) {
                return '#67C23A'
            }
            
            // 结束节点（node_type=5）只有在流程已通过时才显示绿色
            if (this.isEndNode(step)) {
                if (this.currentRow && this.currentRow.status === 2) {
                    return '#67C23A' // 流程已通过，结束节点显示绿色
                }
                return '#909399' // 流程未通过，结束节点显示灰色
            }
            
            // 如果流程已通过，所有节点都显示为已完成（绿色）
            if (this.currentRow && this.currentRow.status === 2) {
                return '#67C23A'
            }
            
            const stepLevelOrder = this.getStepLevelOrder(step)
            const currentDisplayStep = this.calculateDisplayStep(this.currentRow)
            
            // 检查该步骤是否被驳回或退回
            const isRejected = this.checkStepIsRejected(stepLevelOrder)
            if (isRejected) {
                return '#F56C6C' // 红色 - 已驳回/退回
            }
            
            // 检查该步骤是否被自动跳过（必须在检查已完成之前检查，因为跳过节点可能在审批历史中也有记录）
            const stepId = step.id
            const skippedSteps = this.currentRow.skipped_steps || []
            if (skippedSteps.includes(stepId)) {
                return '#67C23A' // 绿色 - 自动跳过（已完成）
            }
            
            // 检查该步骤是否已完成（有审批通过的记录）
            const isCompleted = this.checkStepIsCompleted(stepLevelOrder)
            if (isCompleted) {
                return '#67C23A' // 绿色 - 已完成
            }
            
            // 检查该步骤是否有待审批的任务
            const hasPendingTasks = this.checkHasPendingTasks(stepLevelOrder)
            
            if (hasPendingTasks) {
                return '#E6A23C' // 橙色 - 当前节点
            } else if (stepLevelOrder < currentDisplayStep) {
                return '#67C23A' // 绿色 - 已完成
            } else {
                // 对于后续节点，需要检查流程是否已经终止（驳回/退回）
                if (this.isWorkflowTerminated()) {
                    return '#909399' // 灰色 - 流程已终止，后续节点不执行
                }
                return '#909399' // 灰色 - 未开始
            }
        },
        // 获取步骤图标
        getStepIcon(step) {
            // 完成节点显示对勾
            if (step.is_complete_node) {
                return 'CircleCheck'
            }
            
            // 结束节点（node_type=5）也显示对勾
            if (this.isEndNode(step)) {
                return 'CircleCheck'
            }
            
            if (step.approver_type == 1) return 'UserFilled' // 指定角色
            if (step.approver_type == 2) return 'OfficeBuilding' // 指定部门
            if (step.approver_type == 3) return 'User' // 部门负责人
            if (step.approver_type == 4) return 'Avatar' // 指定人员
            if (step.approver_type == 5) return 'EditPen' // 申请人自选
            if (step.approver_type == 10) return 'Collection' // 自定义审批组
            return 'CircleCheck'
        },
        // 获取步骤类型名称
        getStepTypeName(approverType) {
            const typeMap = {
                0: '完成',  // 完成节点
                1: '指定角色',
                2: '指定部门',
                3: '部门负责人',
                4: '指定人员',
                5: '申请人自选',
                6: '多级审批',
                7: '发起人',
                8: '条件化审批人',
                9: '直接上级',
                10: '自定义审批组'
            }
            return typeMap[approverType] || '未知'
        },
        // 获取条件化审批人节点的类型显示（优先展示实际命中条件组的类型，如：直接上级）
        getConditionTypeDisplay(step) {
            const typeMap = { 1: '指定角色', 2: '指定部门', 3: '部门负责人', 4: '指定人员', 5: '申请人自选', 6: '多级审批', 7: '发起人', 9: '直接上级', 10: '自定义审批组' }

            // 优先使用后端根据表单数据匹配出的命中条件组审批人类型（只展示实际生效的类型）
            if (Array.isArray(step.matched_condition_types) && step.matched_condition_types.length > 0) {
                const matchedLabels = []
                step.matched_condition_types.forEach(type => {
                    const label = typeMap[type]
                    if (label && !matchedLabels.includes(label)) matchedLabels.push(label)
                })
                if (matchedLabels.length > 0) return matchedLabels.join('、')
            }

            let conditions = step.internal_conditions
            if (typeof conditions === 'string') {
                try { conditions = JSON.parse(conditions) } catch(e) { return '条件化审批人' }
            }
            if (!Array.isArray(conditions) || conditions.length === 0) return '条件化审批人'
            
            // 兜底：没有命中信息时，汇总所有条件组中的审批人类型（去重）
            const parts = []
            conditions.forEach(group => {
                let configs = (group && group.approvers_config) || []
                if (!Array.isArray(configs)) configs = [configs]
                configs.forEach(config => {
                    if (config && config.approver_type) {
                        const label = typeMap[config.approver_type] || '未知'
                        if (!parts.includes(label)) parts.push(label)
                    }
                })
            })
            
            return parts.join('、') || '条件化审批人'
        },
        // 获取多级审批各层级类型显示
        getMultiLevelTypeDisplay(step) {
            if (!step.multi_level_config) return '多级审批'
            let config = step.multi_level_config
            if (typeof config === 'string') {
                try { config = JSON.parse(config) } catch(e) { return '多级审批' }
            }
            if (!Array.isArray(config) || config.length === 0) return '多级审批'
            const typeMap = { 1: '指定角色', 2: '指定部门', 3: '部门负责人', 4: '指定人员', 5: '申请人自选', 7: '发起人', 9: '直接上级', 10: '自定义审批组' }
            const types = config.map(level => typeMap[level.approver_type] || '未知')
            return types.join('、')
        },
        // 获取节点类型名称（用于显示node_type）
        getNodeTypeName(nodeType) {
            const typeMap = {
                1: '普通审批',
                2: '抄送',
                3: '条件分支',
                4: '并行网关',
                5: '结束节点'
            }
            return typeMap[nodeType] || '未知'
        },
        // 获取步骤的层级顺序（用于多级审批）
        getStepLevelOrder(step) {
            // 如果是多级审批的子层级，使用 level_order
            if (step.level_order !== undefined && step.level_order !== null) {
                return step.level_order
            }
            // 否则使用 step_order
            return step.step_order
        },
        
        // 计算显示用的当前步骤数
        calculateDisplayStep(row) {
            if (!row) return 1
            
            const history = row.approval_history || []
            const stepsInfo = row.steps_info || []
            
            // 找出所有已完成的 node_key（有审批通过的记录）
            const completedNodeKeys = new Set()
            history.forEach(task => {
                if (task.approve_result === 1 && task.node_key) {
                    completedNodeKeys.add(task.node_key)
                }
            })
            
            // 如果没有待审批任务且流程已通过，返回总步骤数
            if (row.status === 2) {
                return row.total_steps
            }
            
            // 对于多级审批的情况，需要找到下一个未完成的层级
            // 将所有 steps_info 按 level_order 排序
            const sortedSteps = [...stepsInfo].sort((a, b) => a.level_order - b.level_order)
            
            // 找到第一个有待审批任务的层级
            for (let i = 0; i < sortedSteps.length; i++) {
                const step = sortedSteps[i]
                const levelOrder = step.level_order
                
                // 检查该层级是否有待审批任务
                const hasPendingTasks = this.checkHasPendingTasksAtLevel(levelOrder, row)
                if (hasPendingTasks) {
                    return levelOrder
                }
            }
            
            // 如果所有层级都没有待审批任务，返回最后一个层级
            return sortedSteps.length > 0 ? sortedSteps[sortedSteps.length - 1].level_order : 1
        },
        
        // 检查指定层级是否有待审批的任务
        checkHasPendingTasks(levelOrder) {
            if (!this.currentRow) return false
            
            // 如果流程状态是"已通过"（status=2），说明没有待审批任务
            if (this.currentRow.status === 2) {
                return false
            }
            
            // 检查该层级对应的步骤是否为结束节点（node_type=5）
            // 结束节点不创建任务，所以不应该显示为"当前"
            const stepsInfo = this.currentRow.steps_info || []
            const step = stepsInfo.find(s => {
                const stepLevelOrder = s.level_order !== undefined && s.level_order !== null ? s.level_order : s.step_order
                return stepLevelOrder == levelOrder
            })
            if (step && step.node_type === 5) {
                return false
            }
            
            // 检查该步骤是否被自动跳过
            // 如果被跳过，即使 levelOrder 等于 currentDisplayStep，也不应该被视为有待审批任务
            if (step) {
                const skippedSteps = this.currentRow.skipped_steps || []
                if (skippedSteps.includes(step.id)) {
                    return false
                }
            }
            
            // 计算当前应该显示的步骤数（基于审批历史）
            const currentDisplayStep = this.calculateDisplayStep(this.currentRow)
            
            // 如果 levelOrder 等于 currentDisplayStep，说明是当前待审批的节点
            return levelOrder == currentDisplayStep
        },
        
        // 检查指定层级是否有待审批任务（更精确）
        checkHasPendingTasksAtLevel(levelOrder, row) {
            if (!row || !row.approval_history) return false
            
            // 如果流程状态是"已通过"（status=2），说明没有待审批任务
            if (row.status === 2) {
                return false
            }
            
            // 检查该层级对应的步骤是否被自动跳过
            const stepsInfo = row.steps_info || []
            const step = stepsInfo.find(s => {
                const stepLevelOrder = s.level_order !== undefined && s.level_order !== null ? s.level_order : s.step_order
                return stepLevelOrder == levelOrder
            })
            if (step) {
                const skippedSteps = row.skipped_steps || []
                if (skippedSteps.includes(step.id)) {
                    return false
                }
            }
            
            // 从审批历史中查找该层级的所有任务
            const history = row.approval_history || []
            const tasksAtLevel = history.filter(task => {
                const taskLevelOrder = task.level_order !== undefined && task.level_order !== null ? task.level_order : task.step_order
                return taskLevelOrder == levelOrder
            })
            
            // 如果该层级没有任何任务记录，说明任务尚未创建（可能是引擎bug导致未分配审批人）
            // 此时应将此层级视为当前待处理步骤
            if (tasksAtLevel.length === 0) {
                return true
            }
            
            // 检查是否有待审批的任务（status=0）
            const pendingTasks = tasksAtLevel.filter(task => task.status === 0)
            
            return pendingTasks.length > 0
        },
        
        // 检查指定层级是否已完成（有审批通过的记录）
        checkStepIsCompleted(levelOrder) {
            if (!this.currentRow || !this.currentRow.approval_history) return false
            
            // 从审批历史中查找该层级的已审批通过的任务
            const history = this.currentRow.approval_history || []
            const completedTasks = history.filter(task => {
                const taskLevelOrder = task.level_order !== undefined && task.level_order !== null ? task.level_order : task.step_order
                // approve_result=1 表示通过，approve_result=2 表示驳回，approve_result=3 表示退回
                return taskLevelOrder == levelOrder && task.approve_result === 1
            })
            
            // 对于或签模式，只要有一个任务通过就算完成
            // 对于会签模式，需要所有任务都通过才算完成
            // 这里简化处理：只要有通过记录，就认为该层级已完成
            return completedTasks.length > 0
        },
        
        // 检查指定层级是否被驳回或退回
        checkStepIsRejected(levelOrder) {
            if (!this.currentRow || !this.currentRow.approval_history) return false
            
            // 从审批历史中查找该层级的已驳回或退回的任务
            const history = this.currentRow.approval_history || []
            const rejectedTasks = history.filter(task => {
                const taskLevelOrder = task.level_order !== undefined && task.level_order !== null ? task.level_order : task.step_order
                // approve_result=2 表示驳回，approve_result=3 表示退回
                return taskLevelOrder == levelOrder && (task.approve_result === 2 || task.approve_result === 3)
            })
            
            return rejectedTasks.length > 0
        },
        // 判断流程是否已终止（驳回或退回）
        isWorkflowTerminated() {
            if (!this.currentRow) return false
            
            // 如果流程状态是已驳回(3)、已撤回(4)或已退回(6)，则流程已终止
            if (this.currentRow.status === 3 || this.currentRow.status === 4 || this.currentRow.status === 6) {
                return true
            }
            
            // 检查审批历史中是否有驳回或退回的记录
            if (this.currentRow.approval_history && this.currentRow.approval_history.length > 0) {
                const hasRejectedOrReturned = this.currentRow.approval_history.some(task => 
                    task.approve_result === 2 || task.approve_result === 3
                )
                if (hasRejectedOrReturned) {
                    return true
                }
            }
            
            return false
        },
        // 判断是否为完成节点
        isCompleteNode(step) {
            return step.is_complete_node === true
        },
        // 判断是否为结束节点（node_type=5）
        isEndNode(step) {
            return step.node_type === 5
        },
        // 判断步骤是否被自动跳过
        isAutoSkippedStep(step) {
            const skippedSteps = this.currentRow.skipped_steps || []
            return skippedSteps.includes(step.id)
        },
        // 判断任务是否为自动跳过的任务
        isSkippedTask(task) {
            if (!task) return false
            // 跳过任务的特征：status=1(已完成), approve_result=0(未审批), approve_comment以'[自动跳过]'开头
            return task.status === 1 && task.approve_result === 0 && task.approve_comment && task.approve_comment.startsWith('[自动跳过]')
        },
        // 从跳过任务的approve_comment中提取跳过原因
        getSkipReason(task) {
            if (!task || !task.approve_comment) return ''
            const comment = task.approve_comment
            if (comment.startsWith('[自动跳过]')) {
                return comment.substring('[自动跳过] '.length)
            }
            return comment
        },
        // 获取实际审批人列表
        getActualApprovers(step) {
            if (!this.currentRow || !this.currentRow.steps_info) return []
            
            // 如果步骤被自动跳过，显示预期审批人（而非申请人）
            if (this.isAutoSkippedStep(step)) {
                return this.getExpectedApprovers(step)
            }
            
            // 从审批历史中查找该步骤的审批人
            const history = this.currentRow.approval_history || []
            const stepLevelOrder = this.getStepLevelOrder(step)
            const stepHistory = history.filter(task => {
                // 使用 level_order 匹配（如果有的话），否则使用 step_order
                const taskLevelOrder = task.level_order !== undefined && task.level_order !== null ? task.level_order : task.step_order
                return taskLevelOrder == stepLevelOrder
            })
            
            if (stepHistory.length > 0) {
                // 已审批，返回实际审批人（按姓名去重，兜底防止任务记录叠加导致重复展示）
                const names = stepHistory.map(task => task.approver_name).filter(name => name)
                return [...new Set(names)]
            } else {
                // 未审批，根据配置显示预期审批人
                return this.getExpectedApprovers(step)
            }
        },
        // 获取预期审批人（根据配置）
        getExpectedApprovers(step) {
            // 多级审批：显示每个层级的审批人类型
            if (step.approver_type == 6 && step.multi_level_config) {
                let config = step.multi_level_config
                if (typeof config === 'string') {
                    try { config = JSON.parse(config) } catch(e) { return ['多级审批'] }
                }
                if (Array.isArray(config) && config.length > 0) {
                    const typeMap = { 1: '指定角色', 2: '指定部门', 3: '部门负责人', 4: '指定人员', 5: '申请人自选', 7: '发起人', 9: '直接上级', 10: '自定义审批组' }
                    return config.map((level, idx) => {
                        const levelName = level.name || `第${idx + 1}级`
                        const typeName = typeMap[level.approver_type] || '未知'
                        return `${levelName}(${typeName})`
                    })
                }
                return ['多级审批']
            }
            if (step.approver_type == 1 && step.approver_role_name) {
                return [`角色: ${step.approver_role_name}`]
            } else if (step.approver_type == 2 && step.approver_dept_name) {
                return [`部门: ${step.approver_dept_name}`]
            } else if (step.approver_type == 3) {
                return ['部门负责人']
            } else if (step.approver_type == 4 && step.approver_users_info && step.approver_users_info.length > 0) {
                return step.approver_users_info.map(u => u.name)
            } else if (step.approver_type == 5 && step.approver_users_info && step.approver_users_info.length > 0) {
                // 申请人自选，从 selected_approvers 中获取
                if (this.currentRow.selected_approvers) {
                    try {
                        const selected = typeof this.currentRow.selected_approvers === 'string' 
                            ? JSON.parse(this.currentRow.selected_approvers) 
                            : this.currentRow.selected_approvers
                        const approvers = selected[String(step.step_order)]
                        if (approvers && approvers.length > 0) {
                            return approvers
                        }
                    } catch(e) {
                        console.error('解析自选审批人失败:', e)
                    }
                }
                return ['待选择']
            } else if (step.approver_type == 7) {
                return ['发起人']
            } else if (step.approver_type == 10) {
                // 自定义审批组：显示审批组成员
                if (step.approver_group_members_info && step.approver_group_members_info.length > 0) {
                    return step.approver_group_members_info.map(u => u.name)
                }
                return [step.approver_group_name ? `审批组: ${step.approver_group_name}` : '审批组未配置']
            }
            // 未知类型或未配置时，返回空数组（显示"待分配"）
            return []
        }
    }
}
</script>
