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
                        <!-- 发起按钮：只有草稿状态(status=0)或已撤回状态(status=4)且是申请人时才显示 -->
                        <span class="table-operate-btn" @click="handleInitiate(scope.row)" v-show="hasPermission(this.$route.name,'Initiate')" v-if="(scope.row.status==0 || scope.row.status==4) && scope.row.applicant==currentUserId">发起</span>
                        <!-- 审批按钮：有待审批任务时显示 -->
                        <span class="table-operate-btn" @click="handleApprove(scope.row)" v-show="hasPermission(this.$route.name,'Approval')" v-if="scope.row.my_pending_task">审批</span>
                        <!-- 撤回按钮：审批中(status=1)、是申请人、且当前步骤为1时显示 -->
                        <span class="table-operate-btn" @click="handleWithdraw(scope.row)" v-show="hasPermission(this.$route.name,'Withdraw')" v-if="scope.row.status==1 && scope.row.applicant==currentUserId && scope.row.current_step==1">撤回</span>
                        <!-- 删除按钮：只有草稿状态(status=0)且是申请人时显示 -->
                        <span class="table-operate-btn" @click="handleDelete(scope.row)" v-show="hasPermission(this.$route.name,'Delete')" v-if="scope.row.status==0 && scope.row.applicant==currentUserId" style="color: #F56C6C;">删除</span>
                        <!-- 详情按钮：始终显示 -->
                        <span class="table-operate-btn" @click="handleViewDetail(scope.row)">详情</span>
                    </template>
                </el-table-column>
            </el-table>
        </div>
        
        <!-- 分页 -->
        <Pagination v-bind:child-msg="pageparm" @callFather="callFather" :hide-on-single-page="false"></Pagination>

        <!-- 创建流程对话框 -->
        <el-dialog v-model="createDialogVisible" title="创建流程申请" width="700px">
            <el-form :model="createForm" label-width="100px" ref="createFormRef">
                <el-form-item label="流程类型" required>
                    <el-select 
                        v-model="createForm.workflow_type" 
                        placeholder="请选择流程类型" 
                        style="width: 100%" 
                        @change="handleWorkflowTypeChange"
                        :disabled="isFromInitiate"
                    >
                        <el-option v-for="item in workflowTypes" :key="item.id" :label="item.name" :value="item.id"></el-option>
                    </el-select>
                </el-form-item>
                <el-form-item label="流程标题" required>
                    <el-input 
                        v-model="createForm.title" 
                        placeholder="请输入流程标题"
                        :disabled="isFromInitiate"
                    ></el-input>
                </el-form-item>
                
                <!-- 动态表单字段 -->
                <div v-if="dynamicFormFields.length > 0" style="margin-top: 20px; border-top: 1px solid #EBEEF5; padding-top: 20px;">
                    <h4 style="margin-bottom: 15px;">申请信息</h4>
                    <el-form-item 
                        v-for="field in dynamicFormFields" 
                        :key="field.field" 
                        :label="field.label"
                        :required="field.required"
                    >
                        <!-- 单行文本 -->
                        <el-input 
                            v-if="field.type === 'input'" 
                            v-model="createForm.form_data[field.field]" 
                            :placeholder="field.placeholder || '请输入' + field.label"
                        ></el-input>
                        
                        <!-- 多行文本 -->
                        <el-input 
                            v-else-if="field.type === 'textarea'" 
                            v-model="createForm.form_data[field.field]" 
                            type="textarea" 
                            :rows="3"
                            :placeholder="field.placeholder || '请输入' + field.label"
                        ></el-input>
                        
                        <!-- 数字 -->
                        <el-input-number 
                            v-else-if="field.type === 'number'" 
                            v-model="createForm.form_data[field.field]" 
                            :placeholder="field.placeholder"
                            style="width: 100%"
                        ></el-input-number>
                        
                        <!-- 下拉选择 -->
                        <el-select 
                            v-else-if="field.type === 'select'" 
                            v-model="createForm.form_data[field.field]" 
                            :placeholder="field.placeholder || '请选择' + field.label"
                            style="width: 100%"
                        >
                            <el-option 
                                v-for="opt in field.options" 
                                :key="opt.value" 
                                :label="opt.label" 
                                :value="opt.value"
                            ></el-option>
                        </el-select>
                        
                        <!-- 单选框 -->
                        <el-radio-group 
                            v-else-if="field.type === 'radio'" 
                            v-model="createForm.form_data[field.field]"
                        >
                            <el-radio 
                                v-for="opt in field.options" 
                                :key="opt.value" 
                                :label="opt.value"
                            >{{ opt.label }}</el-radio>
                        </el-radio-group>
                        
                        <!-- 复选框 -->
                        <el-checkbox-group 
                            v-else-if="field.type === 'checkbox'" 
                            v-model="createForm.form_data[field.field]"
                        >
                            <el-checkbox 
                                v-for="opt in field.options" 
                                :key="opt.value" 
                                :label="opt.value"
                            >{{ opt.label }}</el-checkbox>
                        </el-checkbox-group>
                        
                        <!-- 日期 -->
                        <el-date-picker 
                            v-else-if="field.type === 'date'" 
                            v-model="createForm.form_data[field.field]" 
                            type="date"
                            :placeholder="field.placeholder || '请选择' + field.label"
                            style="width: 100%"
                            value-format="YYYY-MM-DD"
                        ></el-date-picker>
                        
                        <!-- 日期时间 -->
                        <el-date-picker 
                            v-else-if="field.type === 'datetime'" 
                            v-model="createForm.form_data[field.field]" 
                            type="datetime"
                            :placeholder="field.placeholder || '请选择' + field.label"
                            style="width: 100%"
                            value-format="YYYY-MM-DD HH:mm:ss"
                        ></el-date-picker>
                        
                        <!-- 文件上传（占位） -->
                        <div v-else-if="field.type === 'upload'" style="color: #909399; font-size: 14px;">
                            {{ field.placeholder || '文件上传功能待实现' }}
                        </div>
                    </el-form-item>
                </div>
                
                <el-form-item label="备注">
                    <el-input v-model="createForm.remark" type="textarea" :rows="3" placeholder="请输入备注"></el-input>
                </el-form-item>
            </el-form>
            <template #footer>
                <el-button @click="handleCreateCancel">取消</el-button>
                <el-button type="primary" @click="handleCreateSubmit" :loading="submitLoading">确定</el-button>
            </template>
        </el-dialog>

        <!-- 选择审批人对话框 -->
        <el-dialog v-model="selectApproverDialogVisible" title="选择审批人" width="700px">
            <div style="margin-bottom: 15px; color: #606266;">
                以下节点需要您选择审批人，请为每个节点选择合适的审批人员：
            </div>
            <el-form label-width="120px">
                <el-form-item 
                    v-for="step in selfSelectSteps" 
                    :key="step.step_order"
                    :label="step.step_name"
                    required
                >
                    <el-select 
                        v-model="selectedApprovers[step.step_order]" 
                        placeholder="请选择审批人" 
                        style="width: 100%"
                        multiple
                    >
                        <el-option 
                            v-for="user in allUsers" 
                            :key="user.id" 
                            :label="user.name" 
                            :value="user.id"
                        ></el-option>
                    </el-select>
                </el-form-item>
            </el-form>
            <template #footer>
                <el-button @click="selectApproverDialogVisible = false">取消</el-button>
                <el-button type="primary" @click="handleSelectApproverSubmit" :loading="submitLoading">确定</el-button>
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
                <el-form-item label="审批意见" :required="isCommentRequired">
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

            <!-- 申请信息（表单数据） -->
            <div style="margin-top: 20px;" v-if="currentRow && currentRow.form_data">
                <h4 style="margin-bottom: 15px;">申请信息</h4>
                <el-descriptions :column="2" border>
                    <el-descriptions-item 
                        v-for="(value, key) in parseFormData(currentRow.form_data)" 
                        :key="key"
                        :label="getFieldLabel(currentRow.workflow_type, key)"
                    >
                        {{ formatFieldValue(value) }}
                    </el-descriptions-item>
                </el-descriptions>
            </div>

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
                                
                                <!-- 当前节点标记（仅对非完成节点） -->
                                <el-tag 
                                    v-if="!isCompleteNode(step) && checkHasPendingTasks(getStepLevelOrder(step)) && currentRow.status != 2" 
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
                            <div v-if="!isCompleteNode(step)" style="font-size: 12px; color: #909399; margin-top: 5px;">{{ getStepTypeName(step.approver_type) }}</div>
                            
                            <!-- 实际审批人（完成节点显示所有审批人） -->
                            <div style="margin-top: 8px; font-size: 13px;">
                                <span v-if="isCompleteNode(step)" style="color: #67C23A;">
                                    <strong>全部通过</strong>
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
                            <!-- 第一行：步骤名称 + 审批人 + 状态标签 -->
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                                <div style="display: flex; align-items: center; gap: 8px;">
                                    <strong style="font-size: 14px;">{{ task.step_name }}</strong>
                                    <span style="color: #606266; font-size: 13px;">→ {{ task.approver_name }}</span>
                                </div>
                                <el-tag v-if="task.approve_result==1" type="success" size="small">通过</el-tag>
                                <el-tag v-else-if="task.approve_result==2" type="danger" size="small">驳回</el-tag>
                                <el-tag v-else-if="task.approve_result==3" type="warning" size="small">退回</el-tag>
                            </div>
                            
                            <!-- 第二行：审批意见 -->
                            <div v-if="task.approve_comment" style="margin-bottom: 8px; padding-left: 8px; border-left: 3px solid #409EFF; background-color: #ecf5ff; padding: 8px; border-radius: 2px;">
                                <span style="color: #606266; font-size: 13px;">{{ task.approve_comment }}</span>
                            </div>
                            
                            <!-- 第三行：审批时间 -->
                            <div style="text-align: right; color: #909399; font-size: 12px;">
                                <i class="el-icon-time"></i> {{ task.approve_time }}
                            </div>
                        </div>
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
    import {workflowInstance, workflowInstanceCreate, workflowInstanceSubmit, workflowInstanceWithdraw, workflowInstanceReinitiate, workflowInstanceDelete, workflowType, workflowTaskApprove, workflowTaskReject, workflowTaskReturn, apiSystemUser, workflowStep} from '@/api/api';
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
                selectApproverDialogVisible: false,  // 选择审批人对话框
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
                    remark: '',
                    form_data: {}  // 动态表单数据
                },
                isFromInitiate: false,  // 标识是否从已有流程发起（true时流程类型和标题不可编辑）
                currentEditRowId: null,  // 当前编辑的流程ID（用于更新已撤回的流程）
                approveForm: {
                    approve_result: 1,
                    approve_comment: ''
                },
                tableData:[],
                dynamicFormFields: [],  // 动态表单字段配置
                selfSelectSteps: [],  // 需要申请人自选的节点列表
                selectedApprovers: {},  // 用户选择的审批人 {step_order: [user_ids]}
                allUsers: []  // 所有用户列表（用于选择审批人）
            }
        },
        computed: {
            // 审批意见是否必填（驳回或退回时必填）
            isCommentRequired() {
                return this.approveForm.approve_result === 2 || this.approveForm.approve_result === 3
            },
            // 显示的步骤列表（包括完成节点）
            displaySteps() {
                if (!this.currentRow || !this.currentRow.steps_info) {
                    return []
                }
                
                const steps = [...this.currentRow.steps_info]
                
                // 如果流程已通过，添加一个“完成”节点
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
            }
        },
        created() {
            this.currentUserId = this.mutitabsstore.getUserId
            this.getWorkflowTypes()
            this.getAllUsers()  // 获取所有用户列表
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
            // 获取所有用户列表
            getAllUsers(){
                let vm = this
                apiSystemUser({page: 1, limit: 1000}).then(res => {
                    if(res && res.code === 2000) {
                        vm.allUsers = (res.data && res.data.data) || []
                    }
                }).catch(err => {
                    console.error('获取用户列表失败:', err)
                    vm.allUsers = []  // 出错时设置为空数组
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
            // 创建流程（手动选择流程类型）
            handleCreate(){
                this.createForm = {
                    workflow_type: '',
                    title: '',
                    remark: '',
                    form_data: {}
                }
                this.dynamicFormFields = []
                this.selfSelectSteps = []  // 重置自选节点列表
                this.selectedApprovers = {}  // 重置选择的审批人
                this.isFromInitiate = false  // 手动创建，流程类型和标题可编辑
                this.currentEditRowId = null  // 重置编辑ID
                this.createDialogVisible = true
            },
            // 发起流程（从已有流程记录快速发起）
            handleInitiate(row){
                // 获取该行的流程类型 ID
                const workflowTypeId = row.workflow_type
                
                // 解析原流程的表单数据
                let originalFormData = {}
                if(row.form_data) {
                    try {
                        originalFormData = typeof row.form_data === 'string' 
                            ? JSON.parse(row.form_data) 
                            : row.form_data
                    } catch(e) {
                        console.error('解析原流程表单数据失败:', e)
                        originalFormData = {}
                    }
                }
                
                // 初始化表单，复制原流程的标题和表单数据
                this.createForm = {
                    workflow_type: workflowTypeId,
                    title: row.title || '',  // 复制原流程的标题
                    remark: '',
                    form_data: {...originalFormData}  // 复制原流程的表单数据
                }
                
                // 重置自选节点和审批人选择
                this.selfSelectSteps = []
                this.selectedApprovers = {}
                
                // 设置标识：从已有流程发起，流程类型不可编辑，但标题可编辑
                this.isFromInitiate = true
                this.currentEditRowId = row.id  // 保存当前编辑的流程ID
                
                // 加载对应的动态表单配置（保留原有数据）
                if(workflowTypeId) {
                    this.handleWorkflowTypeChange(workflowTypeId, true)  // preserveData = true
                } else {
                    this.dynamicFormFields = []
                }
                
                this.createDialogVisible = true
            },
            // 流程类型变化时加载动态表单配置
            handleWorkflowTypeChange(workflowTypeId, preserveData = false){
                let vm = this
                if(!workflowTypeId) {
                    vm.dynamicFormFields = []
                    return
                }
                
                // 从 workflowTypes 中找到对应的流程类型
                const workflowType = vm.workflowTypes.find(item => item.id === workflowTypeId)
                if(workflowType && workflowType.form_schema) {
                    try {
                        // 解析 form_schema
                        vm.dynamicFormFields = typeof workflowType.form_schema === 'string' 
                            ? JSON.parse(workflowType.form_schema) 
                            : workflowType.form_schema
                        
                        // 初始化 form_data（如果不需要保留数据）
                        if(!preserveData) {
                            vm.createForm.form_data = {}
                            vm.dynamicFormFields.forEach(field => {
                                // 设置默认值
                                vm.createForm.form_data[field.field] = field.defaultValue || (field.type === 'checkbox' ? [] : '')
                            })
                        } else {
                            // 保留原有数据，只补充缺失的字段
                            vm.dynamicFormFields.forEach(field => {
                                if(vm.createForm.form_data[field.field] === undefined) {
                                    vm.createForm.form_data[field.field] = field.defaultValue || (field.type === 'checkbox' ? [] : '')
                                }
                            })
                        }
                    } catch(e) {
                        console.error('解析表单配置失败:', e)
                        vm.dynamicFormFields = []
                    }
                } else {
                    vm.dynamicFormFields = []
                }
            },
            // 提交创建（发起并自动提交）
            handleCreateSubmit(){
                if(!this.createForm.workflow_type) {
                    this.$message.warning('请选择流程类型')
                    return
                }
                if(!this.createForm.title) {
                    this.$message.warning('请输入流程标题')
                    return
                }
                
                // 验证动态表单字段的必填项
                for(let field of this.dynamicFormFields) {
                    if(field.required) {
                        const value = this.createForm.form_data[field.field]
                        if(value === '' || value === null || value === undefined || (Array.isArray(value) && value.length === 0)) {
                            this.$message.warning('请填写必填项：' + field.label)
                            return
                        }
                    }
                }
                
                let vm = this
                
                // 检查是否有“申请人自选”节点
                vm.checkSelfSelectSteps().then(hasSelfSelect => {
                    if(hasSelfSelect) {
                        // 有自选节点，弹出选择框
                        vm.selectApproverDialogVisible = true
                    } else {
                        // 没有自选节点，直接创建
                        vm.submitCreateForm()
                    }
                }).catch(err => {
                    console.error('检查自选节点失败:', err)
                    vm.$message.error('检查流程配置失败')
                })
            },
            // 检查是否有申请人自选节点
            checkSelfSelectSteps(){
                return new Promise((resolve, reject) => {
                    let vm = this
                    workflowStep({workflow_type: vm.createForm.workflow_type}).then(res => {
                        if(res && res.code === 2000) {
                            const steps = (res.data && res.data.data) || []
                            // 筛选出审批人类型为5（申请人自选）的节点
                            vm.selfSelectSteps = steps.filter(step => step.approver_type === 5)
                            resolve(vm.selfSelectSteps.length > 0)
                        } else {
                            console.error('获取节点配置失败:', res)
                            vm.selfSelectSteps = []
                            resolve(false)  // 出错时返回false，允许继续创建流程
                        }
                    }).catch(err => {
                        console.error('获取节点配置异常:', err)
                        vm.selfSelectSteps = []
                        resolve(false)  // 异常时返回false，允许继续创建流程
                    })
                })
            },
            // 处理选择审批人提交
            handleSelectApproverSubmit(){
                let vm = this
                
                // 验证是否所有自选节点都选择了审批人
                if(vm.selfSelectSteps && vm.selfSelectSteps.length > 0) {
                    for(let step of vm.selfSelectSteps) {
                        if(!vm.selectedApprovers || !vm.selectedApprovers[step.step_order] || vm.selectedApprovers[step.step_order].length === 0) {
                            vm.$message.warning('请为节点「' + step.step_name + '」选择审批人')
                            return
                        }
                    }
                }
                
                // 关闭对话框并提交
                vm.selectApproverDialogVisible = false
                vm.submitCreateForm()
            },
            // 提交创建表单
            submitCreateForm(){
                if(!this.createForm.workflow_type) {
                    this.$message.warning('请选择流程类型')
                    return
                }
                if(!this.createForm.title) {
                    this.$message.warning('请输入流程标题')
                    return
                }
                
                // 验证动态表单字段的必填项
                for(let field of this.dynamicFormFields) {
                    if(field.required) {
                        const value = this.createForm.form_data[field.field]
                        if(value === '' || value === null || value === undefined || (Array.isArray(value) && value.length === 0)) {
                            this.$message.warning('请填写必填项：' + field.label)
                            return
                        }
                    }
                }
                
                let vm = this
                vm.submitLoading = true
                
                // 构建提交数据
                const submitData = {
                    workflow_type: vm.createForm.workflow_type,
                    title: vm.createForm.title,
                    remark: vm.createForm.remark,
                    form_data: JSON.stringify(vm.createForm.form_data),  // 将表单数据转换为 JSON 字符串
                    selected_approvers: vm.selectedApprovers ? JSON.stringify(vm.selectedApprovers) : null  // 将自选审批人转换为 JSON 字符串
                }
                
                // 判断是创建新流程还是更新已有流程
                if(vm.currentEditRowId) {
                    // 更新已有流程（从已撤回状态发起）
                    vm.updateAndSubmitInstance(submitData)
                } else {
                    // 创建新流程
                    vm.createNewAndSubmitInstance(submitData)
                }
            },
            // 取消创建流程
            handleCreateCancel(){
                this.createDialogVisible = false
                // 重置标识
                this.isFromInitiate = false
                this.currentEditRowId = null  // 重置编辑ID
            },
            // 创建新流程并提交
            createNewAndSubmitInstance(submitData){
                let vm = this
                
                // 先创建流程实例
                workflowInstanceCreate(submitData).then(res => {
                    if(res.code === 2000) {
                        const instanceId = res.data.id
                        
                        // 创建成功后自动提交流程
                        workflowInstanceSubmit(instanceId).then(submitRes => {
                            vm.submitLoading = false
                            if(submitRes.code === 2000) {
                                vm.$message.success('发起并提交成功')
                                vm.createDialogVisible = false
                                // 重置标识
                                vm.isFromInitiate = false
                                vm.currentEditRowId = null
                                vm.getData()
                            } else {
                                vm.$message.error('创建成功但提交失败：' + (submitRes.msg || ''))
                                vm.createDialogVisible = false
                                // 重置标识
                                vm.isFromInitiate = false
                                vm.currentEditRowId = null
                                vm.getData()
                            }
                        }).catch(err => {
                            vm.submitLoading = false
                            vm.$message.error('创建成功但提交失败')
                            vm.createDialogVisible = false
                            // 重置标识
                            vm.isFromInitiate = false
                            vm.currentEditRowId = null
                            vm.getData()
                        })
                    } else {
                        vm.submitLoading = false
                        vm.$message.error(res.msg || '创建失败')
                    }
                }).catch(err => {
                    vm.submitLoading = false
                    vm.$message.error('创建失败')
                })
            },
            // 更新已有流程并提交（从已撤回状态发起）
            updateAndSubmitInstance(submitData){
                let vm = this
                
                // 先重新发起流程（更新数据并重置状态为草稿）
                workflowInstanceReinitiate(vm.currentEditRowId, submitData).then(res => {
                    if(res.code === 2000) {
                        // 重新发起成功后自动提交流程
                        workflowInstanceSubmit(vm.currentEditRowId).then(submitRes => {
                            vm.submitLoading = false
                            if(submitRes.code === 2000) {
                                vm.$message.success('重新发起并提交成功')
                                vm.createDialogVisible = false
                                // 重置标识
                                vm.isFromInitiate = false
                                vm.currentEditRowId = null
                                vm.getData()
                            } else {
                                vm.$message.error('重新发起成功但提交失败：' + (submitRes.msg || ''))
                                vm.createDialogVisible = false
                                // 重置标识
                                vm.isFromInitiate = false
                                vm.currentEditRowId = null
                                vm.getData()
                            }
                        }).catch(err => {
                            vm.submitLoading = false
                            vm.$message.error('重新发起成功但提交失败')
                            vm.createDialogVisible = false
                            // 重置标识
                            vm.isFromInitiate = false
                            vm.currentEditRowId = null
                            vm.getData()
                        })
                    } else {
                        vm.submitLoading = false
                        vm.$message.error(res.msg || '重新发起失败')
                    }
                }).catch(err => {
                    vm.submitLoading = false
                    vm.$message.error('重新发起失败')
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
                
                // 验证：驳回和退回时必须填写审批意见
                if(vm.approveForm.approve_result === 2 || vm.approveForm.approve_result === 3) {
                    if(!vm.approveForm.approve_comment || vm.approveForm.approve_comment.trim() === '') {
                        vm.$message.warning('请选择驳回或退回时，审批意见为必填项')
                        return
                    }
                }
                
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
            // 删除流程
            handleDelete(row){
                let vm = this
                vm.$confirm('确认要删除该流程吗？删除后无法恢复！', '提示', {
                    confirmButtonText: '确定',
                    cancelButtonText: '取消',
                    type: 'warning'
                }).then(() => {
                    vm.loadingPage = true
                    workflowInstanceDelete(row.id).then(res => {
                        vm.loadingPage = false
                        if(res.code === 2000) {
                            vm.$message.success('删除成功')
                            vm.getData()
                        } else {
                            vm.$message.error(res.msg || '删除失败')
                            vm.getData()
                        }
                    }).catch(err => {
                        vm.loadingPage = false
                        vm.$message.error('删除失败')
                    })
                }).catch(() => {})
            },
            // 获取时间线类型
            getTimelineType(result){
                if(result === 1) return 'success'
                if(result === 2) return 'danger'
                if(result === 3) return 'warning'
                return ''
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
            // 获取字段标签
            getFieldLabel(workflowTypeId, fieldKey) {
                // 从 workflowTypes 中找到对应的流程类型
                const workflowType = this.workflowTypes.find(item => item.id === workflowTypeId)
                if (workflowType && workflowType.form_schema) {
                    try {
                        const formSchema = typeof workflowType.form_schema === 'string' 
                            ? JSON.parse(workflowType.form_schema) 
                            : workflowType.form_schema
                        const field = formSchema.find(f => f.field === fieldKey)
                        return field ? field.label : fieldKey
                    } catch (e) {
                        console.error('解析表单配置失败:', e)
                    }
                }
                return fieldKey
            },
            // 格式化字段值
            formatFieldValue(value) {
                if (value === null || value === undefined) return '-'
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
                
                // 如果流程已通过，所有节点都显示为已完成（绿色）
                if (this.currentRow && this.currentRow.status === 2) {
                    return 'success'
                }
                
                const stepLevelOrder = this.getStepLevelOrder(step)
                
                // 检查该步骤是否有待审批的任务
                const hasPendingTasks = this.checkHasPendingTasks(stepLevelOrder)
                
                if (hasPendingTasks) {
                    return 'warning' // 当前节点（有待审批任务）
                } else if (stepLevelOrder < this.currentRow.current_step) {
                    return 'success' // 已完成
                } else if (stepLevelOrder == this.currentRow.current_step) {
                    return 'warning' // 当前节点
                } else {
                    return 'info' // 未开始
                }
            },
            // 获取步骤颜色
            getStepColor(step, index) {
                // 完成节点显示绿色
                if (step.is_complete_node) {
                    return '#67C23A'
                }
                
                // 如果流程已通过，所有节点都显示为已完成（绿色）
                if (this.currentRow && this.currentRow.status === 2) {
                    return '#67C23A'
                }
                
                const stepLevelOrder = this.getStepLevelOrder(step)
                
                // 检查该步骤是否有待审批的任务
                const hasPendingTasks = this.checkHasPendingTasks(stepLevelOrder)
                
                if (hasPendingTasks) {
                    return '#E6A23C' // 橙色 - 当前节点（有待审批任务）
                } else if (stepLevelOrder < this.currentRow.current_step) {
                    return '#67C23A' // 绿色 - 已完成
                } else if (stepLevelOrder == this.currentRow.current_step) {
                    return '#E6A23C' // 橙色 - 当前节点
                } else {
                    return '#909399' // 灰色 - 未开始
                }
            },
            // 获取步骤图标
            getStepIcon(step) {
                // 完成节点显示对勾
                if (step.is_complete_node) {
                    return 'CircleCheck'
                }
                
                if (step.approver_type == 1) return 'UserFilled' // 指定角色
                if (step.approver_type == 2) return 'OfficeBuilding' // 指定部门
                if (step.approver_type == 3) return 'User' // 部门负责人
                if (step.approver_type == 4) return 'Avatar' // 指定人员
                if (step.approver_type == 5) return 'EditPen' // 申请人自选
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
                    5: '申请人自选'
                }
                return typeMap[approverType] || '未知'
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
            
            // 检查指定层级是否有待审批的任务
            checkHasPendingTasks(levelOrder) {
                if (!this.currentRow || !this.currentRow.approval_history) return false
                
                // 从审批历史中查找该层级的待审批任务
                const history = this.currentRow.approval_history || []
                const pendingTasks = history.filter(task => {
                    const taskLevelOrder = task.level_order !== undefined && task.level_order !== null ? task.level_order : task.step_order
                    return taskLevelOrder == levelOrder && task.status === 0 // status=0 表示待审批
                })
                
                return pendingTasks.length > 0
            },
            // 判断是否为完成节点
            isCompleteNode(step) {
                return step.is_complete_node === true
            },
            // 获取实际审批人列表
            getActualApprovers(step) {
                if (!this.currentRow || !this.currentRow.steps_info) return []
                
                // 从审批历史中查找该步骤的审批人
                const history = this.currentRow.approval_history || []
                const stepLevelOrder = this.getStepLevelOrder(step)
                const stepHistory = history.filter(task => {
                    // 使用 level_order 匹配（如果有的话），否则使用 step_order
                    const taskLevelOrder = task.level_order !== undefined && task.level_order !== null ? task.level_order : task.step_order
                    return taskLevelOrder == stepLevelOrder
                })
                
                if (stepHistory.length > 0) {
                    // 已审批，返回实际审批人
                    return stepHistory.map(task => task.approver_name).filter(name => name)
                } else {
                    // 未审批，根据配置显示预期审批人
                    return this.getExpectedApprovers(step)
                }
            },
            // 获取预期审批人（根据配置）
            getExpectedApprovers(step) {
                // 这里可以根据步骤配置和流程实例信息来推断预期审批人
                // 由于后端没有直接返回，我们暂时返回空数组或根据配置提示
                if (step.approver_type == 1 && step.approver_role_name) {
                    return [`角色: ${step.approver_role_name}`]
                } else if (step.approver_type == 2 && step.approver_dept_name) {
                    return [`部门: ${step.approver_dept_name}`]
                } else if (step.approver_type == 3) {
                    return ['部门负责人']
                } else if (step.approver_type == 4 && step.approver_users && step.approver_users.length > 0) {
                    return step.approver_users.map(u => u.name)
                } else if (step.approver_type == 5) {
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
                }
                return []
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
