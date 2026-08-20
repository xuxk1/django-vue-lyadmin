<template>
    <div :class="{'ly-is-full':isFull}">
        <!-- 标签页 -->
        <el-tabs v-model="activeTab" @tab-click="handleTabClick" style="margin-bottom: 20px;">
            <el-tab-pane label="我的待办" name="pending"></el-tab-pane>
            <el-tab-pane label="全部消息" name="all"></el-tab-pane>
            <el-tab-pane label="系统通知" name="1"></el-tab-pane>
            <el-tab-pane label="平台公告" name="2"></el-tab-pane>
        </el-tabs>

        <!-- 搜索栏 -->
        <div class="tableSelect" ref="tableSelect">
            <el-form :inline="true" :model="formInline" label-position="left">
                <el-form-item label="">
                    <el-button @click="refreshData" icon="Refresh">刷新</el-button>
                </el-form-item>
                <el-form-item label="" v-if="activeTab === 'pending'">
                    <el-button @click="batchApprove" type="primary" icon="Check">批量审批</el-button>
                </el-form-item>
                <el-form-item label="" v-if="activeTab !== 'pending'">
                    <el-button @click="markAllAsRead" type="primary" icon="Check">全部已读</el-button>
                </el-form-item>
            </el-form>
        </div>

        <!-- 消息/任务列表 -->
        <el-table 
            :height="'calc('+(tableHeight)+'px)'" 
            border 
            :data="tableData" 
            ref="tableref" 
            v-loading="loadingPage" 
            row-key="id"
            style="width: 100%">
            
            <el-table-column type="selection" width="55" align="center" v-if="activeTab === 'pending'">
            </el-table-column>
            
            <el-table-column type="index" width="60" align="center" label="序号">
                <template #default="scope">
                    <span v-text="getIndex(scope.$index)"></span>
                </template>
            </el-table-column>

            <!-- 流程待办任务的列 -->
            <template v-if="activeTab === 'pending'">
                <el-table-column key="pending-instance-no" min-width="200" prop="instance_no" label="流程编号">
                    <template #default="scope">
                        <span>{{ scope.row.instance_no }}</span>
                    </template>
                </el-table-column>
                
                <el-table-column key="pending-instance-title" min-width="200" prop="instance_title" label="流程标题">
                    <template #default="scope">
                        <span>{{ scope.row.instance_title }}</span>
                    </template>
                </el-table-column>
                
                <el-table-column key="pending-step-name" min-width="150" prop="step_name" label="当前步骤">
                    <template #default="scope">
                        <el-tag type="warning">{{ scope.row.step_name }}</el-tag>
                    </template>
                </el-table-column>
                
                <el-table-column key="pending-create-time" min-width="120" prop="create_datetime" label="到达时间"></el-table-column>
            </template>
            
            <!-- 消息的列 -->
            <template v-else>
                <el-table-column key="msg-status" min-width="80" label="状态">
                    <template #default="scope">
                        <el-tag v-if="!scope.row.is_read" type="warning">未读</el-tag>
                        <el-tag v-else type="success">已读</el-tag>
                    </template>
                </el-table-column>

                <el-table-column key="msg-title" min-width="200" prop="msg_title" label="标题">
                    <template #default="scope">
                        <span :style="{fontWeight: scope.row.is_read ? 'normal' : 'bold', color: scope.row.is_read ? '#606266' : '#303133'}">
                            {{ scope.row.msg_title }}
                        </span>
                    </template>
                </el-table-column>

                <el-table-column key="msg-content" min-width="300" prop="msg_content" show-overflow-tooltip label="内容">
                    <template #default="scope">
                        <div v-html="customEllipsis(scope.row.msg_content)" class="ellipsis"></div>
                    </template>
                </el-table-column>

                <el-table-column key="msg-create-time" min-width="150" prop="create_datetime" label="接收时间"></el-table-column>
            </template>

            <!-- 操作列 -->
            <el-table-column label="操作" fixed="right" width="240">
                <template #header>
                    <div style="display: flex;justify-content: space-between;align-items: center;">
                        <div>操作</div>
                        <div @click="setFull">
                            <el-tooltip content="全屏" placement="bottom">
                                <el-icon><full-screen /></el-icon>
                            </el-tooltip>
                        </div>
                    </div>
                </template>
                <template #default="scope">
                    <!-- 流程待办任务的操作 -->
                    <template v-if="activeTab === 'pending'">
                        <!-- 已退回的待办：申请人修改后重新提交 -->
                        <span class="table-operate-btn" 
                              v-if="scope.row.is_returned" 
                              @click="resubmitTask(scope.row)" 
                              style="color: #E6A23C;">
                            重新提交
                        </span>
                        <span class="table-operate-btn" 
                              v-else
                              @click="approveTask(scope.row)" 
                              :style="isConfirmNode(scope.row) ? { color: '#E6A23C' } : {}">
                            {{ isConfirmNode(scope.row) ? '确认' : '审批' }}
                        </span>
                        <span class="table-operate-btn" @click="viewWorkflowDetail(scope.row)">详情</span>
                    </template>
                    
                    <!-- 消息的操作 -->
                    <template v-else>
                        <!-- 如果是审批任务且未审批，显示审批按钮 -->
                        <span class="table-operate-btn" 
                              @click="approveTask(scope.row)" 
                              v-if="scope.row.is_approval_task && !scope.row.is_read"
                              style="color: #409EFF;">
                            审批
                        </span>
                        <span class="table-operate-btn" @click="viewMessage(scope.row)">查看</span>
                        <span class="table-operate-btn" @click="markAsRead(scope.row)" v-if="!scope.row.is_read">标记已读</span>
                        <span class="table-operate-btn" @click="deleteMessage(scope.row)">删除</span>
                    </template>
                </template>
            </el-table-column>
        </el-table>

        <!-- 分页 -->
        <Pagination v-bind:child-msg="pageparm" @callFather="callFather"></Pagination>

        <!-- 查看消息对话框 -->
        <el-dialog 
            v-model="viewDialogVisible" 
            title="消息详情" 
            width="600px"
            :close-on-click-modal="false">
            <div v-if="currentMessage">
                <h3>{{ currentMessage.msg_title }}</h3>
                <div style="color: #909399; margin-bottom: 15px;">
                    接收时间：{{ currentMessage.create_datetime }}
                </div>
                <div style="line-height: 1.8;" v-html="currentMessage.msg_content"></div>
            </div>
            <template #footer>
                <span class="dialog-footer">
                    <el-button @click="viewDialogVisible = false">关闭</el-button>
                    <el-button type="primary" @click="markAsReadAndClose" v-if="currentMessage && !currentMessage.is_read">
                        标记为已读
                    </el-button>
                </span>
            </template>
        </el-dialog>

        <!-- 审批对话框（与流程列表页审批弹窗保持一致） -->
        <el-dialog v-model="approveDialogVisible" title="流程审批" width="600px" :close-on-click-modal="false">
            <el-form :model="approveForm" label-width="100px">
                <el-form-item label="审批结果" required>
                    <el-radio-group v-model="approveForm.approve_result">
                        <el-radio :label="1">通过</el-radio>
                        <!-- 只有当步骤配置允许驳回时才显示驳回选项 -->
                        <el-radio :label="2" v-if="currentTask && canReject(currentTask)">驳回</el-radio>
                        <!-- 只有当步骤配置允许退回时才显示退回选项 -->
                        <el-radio :label="3" v-if="currentTask && canReturn(currentTask)">退回</el-radio>
                    </el-radio-group>
                    <!-- 提示信息 -->
                    <div v-if="currentTask && (!canReject(currentTask) || !canReturn(currentTask))" style="margin-top: 8px; color: #909399; font-size: 12px;">
                        <span v-if="!canReject(currentTask)">· 当前节点不允许驳回操作</span>
                        <span v-if="!canReturn(currentTask)" style="margin-left: 10px;">· 当前节点不允许退回操作</span>
                    </div>
                </el-form-item>
                <el-form-item label="审批意见" :required="isCommentRequired">
                    <el-input v-model="approveForm.approve_comment" type="textarea" :rows="4" placeholder="请输入审批意见"></el-input>
                </el-form-item>
            </el-form>
            <template #footer>
                <el-button @click="approveDialogVisible = false">取消</el-button>
                <el-button type="primary" @click="handleApproveSubmit" :loading="approveLoading">确定</el-button>
            </template>
        </el-dialog>

        <!-- 流程详情弹窗（公共组件：流程列表/我的待办/我的已办共用） -->
        <WorkflowDetailDialog v-model="detailDialogVisible" :instance-id="detailInstanceId" />
    </div>
</template>

<script>
import Pagination from "@/components/Pagination";
import { getTableHeight } from "@/utils/util";
import { getUserMessages, updateUserMessageStatus, workflowTaskApprove, workflowTaskReject, workflowTaskReturn, workflowTaskConfirm, getMyPendingTasks } from '@/api/api';
import WorkflowDetailDialog from "@/components/workflowDetailDialog";

export default {
    components: {
        Pagination,
        WorkflowDetailDialog
    },
    name: 'myMessages',
    data() {
        return {
            isFull: false,
            tableHeight: 500,
            loadingPage: false,
            activeTab: 'pending', // 当前激活的标签页：pending=我的待办，all=全部，1=系统通知，2=平台公告
            formInline: {
                page: 1,
                limit: 10,
                type: null, // null=全部，1=系统通知，2=平台公告
                status: 0 // 待办任务状态：0=待审批
            },
            pageparm: {
                page: 1,
                limit: 10,
                total: 0
            },
            tableData: [],
            viewDialogVisible: false,
            currentMessage: null,
            selectedTasks: [], // 选中的待办任务
            // 审批弹窗相关（与流程列表页审批弹窗保持一致）
            approveDialogVisible: false,
            approveLoading: false,
            currentTask: null,
            approveForm: {
                approve_result: 1,
                approve_comment: ''
            },
            detailDialogVisible: false,
            detailInstanceId: null  // 查看详情的流程实例ID（传递给公共详情组件）
        }
    },
    computed: {
        // 审批意见是否必填（驳回或退回时必填）
        isCommentRequired() {
            return this.approveForm.approve_result === 2 || this.approveForm.approve_result === 3
        }
    },
    methods: {
        // 表格序列号
        getIndex($index) {
            return (this.pageparm.page - 1) * this.pageparm.limit + $index + 1
        },
        
        setFull() {
            this.isFull = !this.isFull
            window.dispatchEvent(new Event('resize'))
        },
        
        // 当渲染的文字超出10字后显示省略号
        customEllipsis(value) {
            if (!value) return ""
            // 确保 value 是字符串
            value = String(value)
            value = value.replace(/<.*?>/ig, "") // 把v-html的格式标签替换掉
            if (value.length > 10) {
                return value.slice(0, 10) + "..."
            }
            return value
        },
        
        // 标签页切换
        handleTabClick(tab) {
            this.activeTab = tab.paneName
            // 先清空表格数据，避免旧数据残留导致错位
            this.tableData = []
            if (tab.paneName === 'pending') {
                // 我的待办
                this.formInline.status = 0
            } else {
                // 消息中心
                this.formInline.type = tab.paneName === 'all' ? null : tab.paneName
            }
            this.formInline.page = 1
            this.getData()
        },
        
        // 刷新数据
        refreshData() {
            this.formInline.page = 1
            this.getData()
        },
        
        // 标记全部为已读
        markAllAsRead() {
            let vm = this
            vm.$confirm('确定要将所有消息标记为已读吗？', {
                closeOnClickModal: false
            }).then(res => {
                // 获取所有未读消息的ID
                const unreadIds = vm.tableData.filter(item => !item.is_read).map(item => item.id)
                
                if (unreadIds.length === 0) {
                    vm.$message.info('没有未读消息')
                    return
                }
                
                // 逐个标记为已读
                let successCount = 0
                let promises = unreadIds.map(id => {
                    return updateUserMessageStatus({ id: id, type: 'isread' })
                        .then(res => {
                            if (res.code === 2000) {
                                successCount++
                            }
                        })
                })
                
                Promise.all(promises).then(() => {
                    vm.$message.success(`已将 ${successCount} 条消息标记为已读`)
                    vm.getData()
                })
            }).catch(() => {})
        },
        
        // 查看消息
        viewMessage(row) {
            this.currentMessage = row
            this.viewDialogVisible = true
            
            // 如果未读，自动标记为已读
            if (!row.is_read) {
                this.markAsRead(row, false)
            }
        },
        
        // 标记为已读
        markAsRead(row, showMessage = true) {
            let vm = this
            updateUserMessageStatus({ id: row.id, type: 'isread' }).then(res => {
                if (res.code === 2000) {
                    row.is_read = true
                    if (showMessage) {
                        vm.$message.success('已标记为已读')
                    }
                } else {
                    vm.$message.warning(res.msg || '操作失败')
                }
            }).catch(err => {
                vm.$message.error('操作失败')
            })
        },
        
        // 标记为已读并关闭对话框
        markAsReadAndClose() {
            if (this.currentMessage) {
                this.markAsRead(this.currentMessage, true)
                this.currentMessage.is_read = true
            }
            this.viewDialogVisible = false
        },
        
        // 删除消息
        deleteMessage(row) {
            let vm = this
            vm.$confirm('确定要删除这条消息吗？', {
                closeOnClickModal: false
            }).then(res => {
                updateUserMessageStatus({ id: row.id, type: 'del' }).then(res => {
                    if (res.code === 2000) {
                        vm.$message.success('删除成功')
                        vm.getData()
                    } else {
                        vm.$message.warning(res.msg || '删除失败')
                    }
                }).catch(err => {
                    vm.$message.error('删除失败')
                })
            }).catch(() => {})
        },
        
        // 审批任务（通过）
        approveTask(row) {
            let vm = this
            
            // 如果是流程待办任务
            if (this.activeTab === 'pending') {
                const taskId = row.id
                if (!taskId) {
                    vm.$message.warning('无法找到对应的审批任务')
                    return
                }
                
                // 申请人确认类节点（发起人确认/申请人自选）保持原确认流程
                if (vm.isConfirmNode(row)) {
                    vm.$prompt('请输入审批意见（可选）', '确认通过', {
                        confirmButtonText: '确定',
                        cancelButtonText: '取消',
                        inputPlaceholder: '请输入审批意见',
                        closeOnClickModal: false
                    }).then(({ value }) => {
                        const data = {
                            approve_result: 1,  // 1=通过
                            approve_comment: value || ''
                        }
                        
                        workflowTaskConfirm(taskId, data).then(res => {
                            if (res.code === 2000) {
                                vm.$message.success('确认成功')
                                // 刷新列表
                                vm.getData()
                            } else {
                                vm.$message.error(res.msg || '确认失败')
                            }
                        }).catch(err => {
                            vm.$message.error('确认失败')
                        })
                    }).catch(() => {})
                    return
                }
                
                // 普通审批节点：打开与流程列表一致的审批弹窗（通过/驳回/退回）
                vm.currentTask = row
                vm.approveForm = {
                    approve_result: 1,
                    approve_comment: ''
                }
                vm.approveDialogVisible = true
            } else {
                // 如果是消息中的审批任务
                if (!row.task_id) {
                    vm.$message.warning('无法找到对应的审批任务')
                    return
                }
                
                // 判断是否为申请人确认（发起人确认/申请人自选节点）
                const isConfirm = vm.isConfirmNode(row)
                const title = isConfirm ? '确认通过' : '流程审批'
                
                vm.$prompt('请输入审批意见（可选）', title, {
                    confirmButtonText: '确定',
                    cancelButtonText: '取消',
                    inputPlaceholder: '请输入审批意见',
                    closeOnClickModal: false
                }).then(({ value }) => {
                    const data = {
                        approve_result: 1,  // 1=通过
                        approve_comment: value || ''
                    }
                    
                    const apiCall = isConfirm ? workflowTaskConfirm(row.task_id, data) : workflowTaskApprove(row.task_id, data)
                    apiCall.then(res => {
                        if (res.code === 2000) {
                            vm.$message.success(isConfirm ? '确认成功' : '审批通过')
                            // 标记消息为已读
                            vm.markAsRead(row, false)
                            // 刷新列表
                            vm.getData()
                        } else {
                            vm.$message.error(res.msg || (isConfirm ? '确认失败' : '审批失败'))
                        }
                    }).catch(err => {
                        vm.$message.error(isConfirm ? '确认失败' : '审批失败')
                    })
                }).catch(() => {})
            }
        },
        
        // 判断是否为发起人确认类节点（申请人自选/发起人确认）：仅此类节点显示“确认”按钮，
        // 普通审批节点即使申请人是审批人也显示“审批”按钮（与流程列表页逻辑一致）
        isConfirmNode(row) {
            if (!row.is_applicant) return false
            const approverType = row.level_approver_type || row.step_approver_type
            // 发起人(7)或申请人自选(5)节点才走确认逻辑
            return approverType == 7 || approverType == 5
        },
        
        // 根据后端返回的 allow_reject 字段判断当前节点是否允许驳回（仅当后端明确返回 true 时才允许）
        canReject(row) {
            const v = row.allow_reject
            return v === true || v === 'true' || v === 'True' || v === 1 || v === '1'
        },
        
        // 根据后端返回的 allow_return 字段判断当前节点是否允许退回（仅当后端明确返回 true 时才允许）
        canReturn(row) {
            const v = row.allow_return
            return v === true || v === 'true' || v === 'True' || v === 1 || v === '1'
        },
        
        // 提交审批（与流程列表页审批弹窗提交逻辑一致）
        handleApproveSubmit() {
            let vm = this
            
            // 验证：驳回和退回时必须填写审批意见
            if (vm.approveForm.approve_result === 2 || vm.approveForm.approve_result === 3) {
                if (!vm.approveForm.approve_comment || vm.approveForm.approve_comment.trim() === '') {
                    vm.$message.warning('选择驳回或退回时，审批意见为必填项')
                    return
                }
            }
            
            vm.approveLoading = true
            
            let apiCall = null
            if (vm.approveForm.approve_result === 1) {
                apiCall = workflowTaskApprove(vm.currentTask.id, vm.approveForm)
            } else if (vm.approveForm.approve_result === 2) {
                apiCall = workflowTaskReject(vm.currentTask.id, vm.approveForm)
            } else if (vm.approveForm.approve_result === 3) {
                apiCall = workflowTaskReturn(vm.currentTask.id, vm.approveForm)
            }
            
            apiCall.then(res => {
                vm.approveLoading = false
                if (res.code === 2000) {
                    vm.$message.success('审批成功')
                    vm.approveDialogVisible = false
                    vm.getData()
                } else {
                    vm.$message.error(res.msg || '审批失败')
                    // 即使失败也关闭对话框并刷新数据（避免重复操作）
                    vm.approveDialogVisible = false
                    vm.getData()
                }
            }).catch(err => {
                vm.approveLoading = false
                vm.$message.error('审批失败')
                // 异常情况下也关闭对话框并刷新数据
                vm.approveDialogVisible = false
                vm.getData()
            })
        },
        
        // 退回待办重新提交：跳转到流程列表页并自动打开重新提交弹窗
        resubmitTask(row) {
            let vm = this
            const instanceId = row.instance
            if (!instanceId) {
                vm.$message.warning('未获取到对应的流程实例信息')
                return
            }
            vm.$router.push({ path: '/workflowList', query: { resubmit_instance: instanceId } })
        },
        
        // 查看流程详情：打开公共详情弹窗（与流程列表/我的已办展示一致）
        viewWorkflowDetail(row) {
            let vm = this
            const instanceId = row.instance
            if (!instanceId) {
                vm.$message.warning('未获取到对应的流程实例信息')
                return
            }
            vm.detailInstanceId = instanceId
            vm.detailDialogVisible = true
        },
        
        // 批量审批
        batchApprove() {
            let vm = this
            const selectedRows = vm.$refs.tableref.getSelectionRows()
            
            if (selectedRows.length === 0) {
                vm.$message.warning('请先选择要审批的任务')
                return
            }
            
            vm.$prompt('请输入审批意见（可选）', `批量审批通过 (${selectedRows.length}项)`, {
                confirmButtonText: '确定',
                cancelButtonText: '取消',
                inputPlaceholder: '请输入审批意见',
                closeOnClickModal: false
            }).then(({ value }) => {
                const data = {
                    approve_result: 1,  // 1=通过
                    approve_comment: value || ''
                }
                
                // 逐个审批
                let successCount = 0
                let failCount = 0
                let promises = selectedRows.map(row => {
                    return workflowTaskApprove(row.id, data)
                        .then(res => {
                            if (res.code === 2000) {
                                successCount++
                            } else {
                                failCount++
                            }
                        })
                        .catch(() => {
                            failCount++
                        })
                })
                
                Promise.all(promises).then(() => {
                    vm.$message.success(`成功审批 ${successCount} 项，失败 ${failCount} 项`)
                    // 清空选择
                    vm.$refs.tableref.clearSelection()
                    // 刷新列表
                    vm.getData()
                })
            }).catch(() => {})
        },
        
        callFather(parm) {
            this.formInline.page = parm.page
            this.formInline.limit = parm.limit
            this.getData()
        },
        
        // 获取列表
        async getData() {
            this.loadingPage = true
            
            if (this.activeTab === 'pending') {
                // 获取我的待办任务
                getMyPendingTasks(this.formInline).then(res => {
                    this.loadingPage = false
                    if (res.code === 2000) {
                        this.tableData = res.data.data || []
                        this.pageparm.page = res.data.page
                        this.pageparm.limit = res.data.limit
                        this.pageparm.total = res.data.total
                    }
                }).catch(err => {
                    this.loadingPage = false
                    this.$message.error('获取待办任务列表失败')
                })
            } else {
                // 获取消息列表
                getUserMessages(this.formInline).then(res => {
                    this.loadingPage = false
                    if (res.code === 2000) {
                        this.tableData = res.data.data || []
                        this.pageparm.page = res.data.page
                        this.pageparm.limit = res.data.limit
                        this.pageparm.total = res.data.total
                    }
                }).catch(err => {
                    this.loadingPage = false
                    this.$message.error('获取消息列表失败')
                })
            }
        },
        
        // 计算搜索栏的高度
        listenResize() {
            this.$nextTick(() => {
                this.getTheTableHeight()
            })
        },
        
        getTheTableHeight() {
            let tabSelectHeight = this.$refs.tableSelect ? this.$refs.tableSelect.offsetHeight : 0
            tabSelectHeight = this.isFull ? tabSelectHeight - 110 : tabSelectHeight
            this.tableHeight = getTableHeight(tabSelectHeight)
        }
    },
    created() {
        this.getData()
    },
    mounted() {
        // 监听页面宽度变化搜索框的高度
        window.addEventListener('resize', this.listenResize);
        this.$nextTick(() => {
            this.getTheTableHeight()
        })
    },
    unmounted() {
        // 页面销毁，去掉监听事件
        window.removeEventListener("resize", this.listenResize);
    },
}
</script>

<style scoped>
.ellipsis {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
</style>
