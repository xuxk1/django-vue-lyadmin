<template>
    <div :class="{'ly-is-full':isFull}">
        <!-- 搜索区域 -->
        <div class="tableSelect" ref="tableSelect">
            <el-form :inline="true" :model="formInline" label-position="left">
                <el-form-item label="流程类型：">
                    <el-select v-model="formInline.workflow_type" placeholder="请选择" clearable @change="search" size="default" style="width:150px">
                        <el-option v-for="item in workflowTypes" :key="item.id" :label="item.name" :value="item.id"></el-option>
                    </el-select>
                </el-form-item>
                <el-form-item label="流程标题：">
                    <el-input size="default" v-model.trim="formInline.title" maxlength="60" clearable placeholder="流程标题" @change="search" style="width:150px"></el-input>
                </el-form-item>
                <el-form-item label="状态：">
                    <el-select v-model="formInline.status" placeholder="请选择" clearable @change="search" size="default" style="width:120px">
                        <el-option label="草稿" :value="0"></el-option>
                        <el-option label="审批中" :value="1"></el-option>
                        <el-option label="已通过" :value="2"></el-option>
                        <el-option label="已驳回" :value="3"></el-option>
                        <el-option label="已撤回" :value="4"></el-option>
                    </el-select>
                </el-form-item>
                <el-form-item label="">
                    <el-button @click="search" type="primary" icon="Search" v-show="hasPermission(this.$route.name,'Search')">查询</el-button>
                </el-form-item>
                <el-form-item label="">
                    <el-button @click="handleReset" icon="Refresh">重置</el-button>
                </el-form-item>
            </el-form>
        </div>

        <!-- 操作按钮 -->
        <div class="operate-btns" style="margin-bottom: 10px;">
            <el-button type="primary" icon="Plus" @click="handleCreate" v-show="hasPermission(this.$route.name,'Create')">创建流程申请</el-button>
        </div>

        <!-- 表格区域 -->
        <div class="table">
            <el-table :height="'calc('+(tableHeight)+'px)'" border :data="tableData" ref="tableref" v-loading="loadingPage" style="width: 100%">
                <el-table-column type="index" width="60" align="center" label="序号">
                    <template #default="scope">
                        <span v-text="getIndex(scope.$index)"></span>
                    </template>
                </el-table-column>
                <el-table-column min-width="150" prop="instance_no" label="流程编号" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="120" prop="workflow_type_name" label="流程类型" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="200" prop="title" label="流程标题" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="100" prop="applicant_name" label="申请人" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="100" label="状态">
                    <template #default="scope">
                        <el-tag v-if="scope.row.status==0" type="info">草稿</el-tag>
                        <el-tag v-else-if="scope.row.status==1" type="warning">审批中</el-tag>
                        <el-tag v-else-if="scope.row.status==2" type="success">已通过</el-tag>
                        <el-tag v-else-if="scope.row.status==3" type="danger">已驳回</el-tag>
                        <el-tag v-else-if="scope.row.status==4" type="">已撤回</el-tag>
                    </template>
                </el-table-column>
                <el-table-column min-width="100" prop="current_step" label="当前步骤" align="center">
                    <template #default="scope">
                        <span>{{ scope.row.current_step }}/{{ scope.row.total_steps }}</span>
                    </template>
                </el-table-column>
                <el-table-column min-width="150" prop="create_datetime" label="创建时间"></el-table-column>
                <el-table-column label="操作" fixed="right" width="280">
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
                        <span class="table-operate-btn" @click="handleSubmit(scope.row)" v-show="hasPermission(this.$route.name,'Submit') && scope.row.status==0 && scope.row.applicant==currentUserId">提交</span>
                        <span class="table-operate-btn" @click="handleApprove(scope.row)" v-show="hasPermission(this.$route.name,'Approve') && scope.row.my_pending_task">审批</span>
                        <span class="table-operate-btn" @click="handleWithdraw(scope.row)" v-show="hasPermission(this.$route.name,'Withdraw') && scope.row.status==1 && scope.row.applicant==currentUserId && scope.row.current_step==1">撤回</span>
                        <span class="table-operate-btn" @click="handleViewDetail(scope.row)" v-show="hasPermission(this.$route.name,'Retrieve')">详情</span>
                    </template>
                </el-table-column>
            </el-table>
        </div>
        
        <!-- 分页 -->
        <Pagination v-bind:child-msg="pageparm" @callFather="callFather" :hide-on-single-page="false"></Pagination>

        <!-- 创建流程对话框 -->
        <el-dialog v-model="createDialogVisible" title="创建流程申请" width="600px">
            <el-form :model="createForm" label-width="100px">
                <el-form-item label="流程类型" required>
                    <el-select v-model="createForm.workflow_type" placeholder="请选择流程类型" style="width: 100%">
                        <el-option v-for="item in workflowTypes" :key="item.id" :label="item.name" :value="item.id"></el-option>
                    </el-select>
                </el-form-item>
                <el-form-item label="流程标题" required>
                    <el-input v-model="createForm.title" placeholder="请输入流程标题"></el-input>
                </el-form-item>
                <el-form-item label="备注">
                    <el-input v-model="createForm.remark" type="textarea" :rows="3" placeholder="请输入备注"></el-input>
                </el-form-item>
            </el-form>
            <template #footer>
                <el-button @click="createDialogVisible = false">取消</el-button>
                <el-button type="primary" @click="handleCreateSubmit" :loading="submitLoading">确定</el-button>
            </template>
        </el-dialog>

        <!-- 审批对话框 -->
        <el-dialog v-model="approveDialogVisible" title="流程审批" width="600px">
            <el-form :model="approveForm" label-width="100px">
                <el-form-item label="审批结果" required>
                    <el-radio-group v-model="approveForm.approve_result">
                        <el-radio :label="1">通过</el-radio>
                        <el-radio :label="2">驳回</el-radio>
                        <el-radio :label="3">退回</el-radio>
                    </el-radio-group>
                </el-form-item>
                <el-form-item label="审批意见">
                    <el-input v-model="approveForm.approve_comment" type="textarea" :rows="4" placeholder="请输入审批意见"></el-input>
                </el-form-item>
            </el-form>
            <template #footer>
                <el-button @click="approveDialogVisible = false">取消</el-button>
                <el-button type="primary" @click="handleApproveSubmit" :loading="approveLoading">确定</el-button>
            </template>
        </el-dialog>

        <!-- 详情对话框 -->
        <el-dialog v-model="detailDialogVisible" title="流程详情" width="900px">
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
                </el-descriptions-item>
                <el-descriptions-item label="当前步骤">{{ currentRow.current_step }}/{{ currentRow.total_steps }}</el-descriptions-item>
                <el-descriptions-item label="创建时间" :span="2">{{ currentRow.create_datetime }}</el-descriptions-item>
                <el-descriptions-item label="备注" :span="2">{{ currentRow.remark || '-' }}</el-descriptions-item>
            </el-descriptions>

            <!-- 审批历史 -->
            <div style="margin-top: 20px;" v-if="currentRow && currentRow.approval_history && currentRow.approval_history.length > 0">
                <h4>审批历史</h4>
                <el-timeline>
                    <el-timeline-item v-for="(task, index) in currentRow.approval_history" :key="index" :type="getTimelineType(task.approve_result)">
                        <div>
                            <strong>{{ task.step_name }}</strong> - {{ task.approver_name }}
                            <span style="margin-left: 10px;">
                                <el-tag v-if="task.approve_result==1" type="success" size="small">通过</el-tag>
                                <el-tag v-else-if="task.approve_result==2" type="danger" size="small">驳回</el-tag>
                                <el-tag v-else-if="task.approve_result==3" type="warning" size="small">退回</el-tag>
                            </span>
                        </div>
                        <div v-if="task.approve_comment" style="margin-top: 5px; color: #606266;">{{ task.approve_comment }}</div>
                        <div style="margin-top: 5px; font-size: 12px; color: #909399;">{{ task.approve_time }}</div>
                    </el-timeline-item>
                </el-timeline>
            </div>
            
            <template #footer>
                <el-button @click="detailDialogVisible = false">关闭</el-button>
            </template>
        </el-dialog>
    </div>
</template>

<script>
    import Pagination from "@/components/Pagination";
    import {getTableHeight} from "@/utils/util";
    import {workflowInstance, workflowInstanceCreate, workflowInstanceSubmit, workflowInstanceWithdraw, workflowType, workflowTaskApprove, workflowTaskReject, workflowTaskReturn} from '@/api/api';
    import {useMutitabsStore} from "@/store/mutitabs";
    
    export default {
        name: "workflowList",
        setup(){
            const mutitabsstore = useMutitabsStore()
            return { mutitabsstore}
        },
        components:{
            Pagination,
        },
        data() {
            return {
                isFull:false,
                tableHeight:500,
                loadingPage:false,
                submitLoading: false,
                approveLoading: false,
                createDialogVisible: false,
                approveDialogVisible: false,
                detailDialogVisible: false,
                currentRow: null,
                currentUserId: null,
                workflowTypes: [],
                currentTask: null,
                formInline:{
                    page: 1,
                    limit: 10,
                    workflow_type:'',
                    title:'',
                    status:''
                },
                pageparm: {
                    page: 1,
                    limit: 10,
                    total: 0
                },
                createForm: {
                    workflow_type: '',
                    title: '',
                    remark: ''
                },
                approveForm: {
                    approve_result: 1,
                    approve_comment: ''
                },
                tableData:[]
            }
        },
        created() {
            this.currentUserId = this.mutitabsstore.getUserId
            this.getWorkflowTypes()
            this.getData()
        },
        methods:{
            // 表格序列号
            getIndex($index) {
                return (this.pageparm.page - 1) * this.pageparm.limit + $index + 1
            },
            // 获取数据
            getData(){
                let vm = this
                vm.loadingPage = true
                workflowInstance(vm.formInline).then(res => {
                    vm.loadingPage = false
                    if(res.code === 2000) {
                        vm.tableData = res.data.data
                        vm.pageparm.page = res.data.page
                        vm.pageparm.limit = res.data.limit
                        vm.pageparm.total = res.data.total
                    }
                }).catch(err => {
                    vm.loadingPage = false
                    vm.$message.error('获取数据失败')
                })
            },
            // 获取流程类型
            getWorkflowTypes(){
                let vm = this
                workflowType({status: 1}).then(res => {
                    if(res.code === 2000) {
                        vm.workflowTypes = res.data.data || []
                    }
                })
            },
            // 搜索
            search(){
                this.formInline.page = 1
                this.getData()
            },
            // 重置
            handleReset(){
                this.formInline = {
                    page: 1,
                    limit: 10,
                    workflow_type:'',
                    title:'',
                    status:''
                }
                this.getData()
            },
            // 分页
            callFather(parm){
                this.formInline.page = parm.page
                this.formInline.limit = parm.limit
                this.getData()
            },
            // 全屏
            setFull(){
                this.isFull = !this.isFull
                this.$nextTick(() => {
                    this.getTheTableHeight()
                })
            },
            getTheTableHeight(){
                let tabSelectHeight = this.$refs.tableSelect?this.$refs.tableSelect.offsetHeight:0
                tabSelectHeight = this.isFull?tabSelectHeight - 110:tabSelectHeight
                this.tableHeight = getTableHeight(tabSelectHeight)
            },
            // 创建流程
            handleCreate(){
                this.createForm = {
                    workflow_type: '',
                    title: '',
                    remark: ''
                }
                this.createDialogVisible = true
            },
            // 提交创建
            handleCreateSubmit(){
                if(!this.createForm.workflow_type) {
                    this.$message.warning('请选择流程类型')
                    return
                }
                if(!this.createForm.title) {
                    this.$message.warning('请输入流程标题')
                    return
                }
                
                let vm = this
                vm.submitLoading = true
                workflowInstanceCreate(vm.createForm).then(res => {
                    vm.submitLoading = false
                    if(res.code === 2000) {
                        vm.$message.success('创建成功')
                        vm.createDialogVisible = false
                        vm.getData()
                    } else {
                        vm.$message.error(res.msg || '创建失败')
                    }
                }).catch(err => {
                    vm.submitLoading = false
                    vm.$message.error('创建失败')
                })
            },
            // 提交流程
            handleSubmit(row){
                let vm = this
                vm.$confirm('确认要提交该流程吗？', '提示', {
                    confirmButtonText: '确定',
                    cancelButtonText: '取消',
                    type: 'warning'
                }).then(() => {
                    vm.loadingPage = true
                    workflowInstanceSubmit(row.id).then(res => {
                        vm.loadingPage = false
                        if(res.code === 2000) {
                            vm.$message.success('提交成功')
                            vm.getData()
                        } else {
                            vm.$message.error(res.msg || '提交失败')
                            vm.getData()
                        }
                    }).catch(err => {
                        vm.loadingPage = false
                        vm.$message.error('提交失败')
                    })
                }).catch(() => {})
            },
            // 审批
            handleApprove(row){
                if(!row.my_pending_task) {
                    this.$message.warning('没有待审批的任务')
                    return
                }
                this.currentTask = row.my_pending_task
                this.approveForm = {
                    approve_result: 1,
                    approve_comment: ''
                }
                this.approveDialogVisible = true
            },
            // 提交审批
            handleApproveSubmit(){
                let vm = this
                vm.approveLoading = true
                
                let apiCall = null
                if(vm.approveForm.approve_result === 1) {
                    apiCall = workflowTaskApprove(vm.currentTask.id, vm.approveForm)
                } else if(vm.approveForm.approve_result === 2) {
                    apiCall = workflowTaskReject(vm.currentTask.id, vm.approveForm)
                } else if(vm.approveForm.approve_result === 3) {
                    apiCall = workflowTaskReturn(vm.currentTask.id, vm.approveForm)
                }
                
                apiCall.then(res => {
                    vm.approveLoading = false
                    if(res.code === 2000) {
                        vm.$message.success('审批成功')
                        vm.approveDialogVisible = false
                        vm.getData()
                    } else {
                        vm.$message.error(res.msg || '审批失败')
                    }
                }).catch(err => {
                    vm.approveLoading = false
                    vm.$message.error('审批失败')
                })
            },
            // 撤回流程
            handleWithdraw(row){
                let vm = this
                vm.$confirm('确认要撤回该流程吗？', '提示', {
                    confirmButtonText: '确定',
                    cancelButtonText: '取消',
                    type: 'warning'
                }).then(() => {
                    vm.loadingPage = true
                    workflowInstanceWithdraw(row.id).then(res => {
                        vm.loadingPage = false
                        if(res.code === 2000) {
                            vm.$message.success('撤回成功')
                            vm.getData()
                        } else {
                            vm.$message.error(res.msg || '撤回失败')
                            vm.getData()
                        }
                    }).catch(err => {
                        vm.loadingPage = false
                        vm.$message.error('撤回失败')
                    })
                }).catch(() => {})
            },
            // 查看详情
            handleViewDetail(row){
                this.currentRow = row
                this.detailDialogVisible = true
            },
            // 获取时间线类型
            getTimelineType(result){
                if(result === 1) return 'success'
                if(result === 2) return 'danger'
                if(result === 3) return 'warning'
                return ''
            }
        }
    }
</script>

<style scoped>
    .table-operate-btn {
        cursor: pointer;
        color: #409EFF;
        margin-right: 10px;
    }
    .table-operate-btn:hover {
        color: #66b1ff;
    }
</style>
