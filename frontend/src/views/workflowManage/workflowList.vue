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
                        <el-option label="已退回" :value="6"></el-option>
                    </el-select>
                </el-form-item>
                <el-form-item label="筛选：">
                    <el-checkbox v-model="formInline.show_only_pending" @change="search">只显示有待审批任务</el-checkbox>
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
            <el-button type="primary" icon="Plus" @click="handleCreate" v-show="hasPermission(this.$route.name,'Create')">发起流程</el-button>
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
                        <el-tag v-else-if="scope.row.status==6" type="primary">已退回</el-tag>
                    </template>
                </el-table-column>
                <el-table-column min-width="100" prop="current_step" label="当前步骤" align="center">
                    <template #default="scope">
                        <span>{{ getCurrentStepNumber(scope.row) }}/{{ scope.row.total_steps }}</span>
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
                        <!-- 发起/重新提交按钮：草稿(status=0)、已撤回(status=4)或已退回(status=6)且是申请人时显示 -->
                        <span class="table-operate-btn" @click="handleInitiate(scope.row)" v-show="hasPermission(this.$route.name,'Initiate')" v-if="(scope.row.status==0 || scope.row.status==4 || scope.row.status==6) && scope.row.applicant==currentUserId">{{ scope.row.status==6 ? '重新提交' : '发起' }}</span>
                        <!-- 确认按钮：流程审批中(status=1)、有待审批任务、是申请人、且当前任务是申请人确认任务(node_type!=1或approver_type=7)时才显示 -->
                        <span class="table-operate-btn" @click="handleConfirm(scope.row)" v-show="hasPermission(this.$route.name,'Approval')" v-if="scope.row.status==1 && scope.row.my_pending_task && scope.row.applicant==currentUserId && (scope.row.my_pending_task.step_node_type != 1 || scope.row.my_pending_task.step_approver_type == 7)" style="color: #E6A23C;">确认</span>
                        <!-- 审批按钮：流程审批中(status=1)、有待审批任务、满足以下条件之一时显示：
                             1. 不是申请人
                             2. 是申请人但任务是普通审批任务(node_type=1且approver_type!=7)
                        -->
                        <span class="table-operate-btn" @click="handleApprove(scope.row)" v-show="hasPermission(this.$route.name,'Approval')" v-if="scope.row.status==1 && scope.row.my_pending_task && ((scope.row.applicant!=currentUserId) || (scope.row.applicant==currentUserId && scope.row.my_pending_task.step_node_type == 1 && scope.row.my_pending_task.step_approver_type != 7))">审批</span>
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
        <el-dialog v-model="createDialogVisible" :title="createDialogTitle" width="700px">
            <el-form :model="createForm" label-width="100px" ref="createFormRef">
                <el-form-item label="流程类型" required>
                    <el-select 
                        v-model="createForm.workflow_type" 
                        placeholder="请选择流程类型" 
                        style="width: 100%" 
                        @change="handleWorkflowTypeChange"
                        :disabled="isFromInitiate"
                    >
                        <el-option v-for="item in filteredWorkflowTypes" :key="item.id" :label="item.name" :value="item.id"></el-option>
                    </el-select>
                    <div v-if="workflowTypes.length > filteredWorkflowTypes.length" style="margin-top: 5px; font-size: 12px; color: #E6A23C;">
                        部分流程类型因部门限制不可发起
                    </div>
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
                        v-for="field in visibleDynamicFormFields" 
                        :key="field.field" 
                        :label="field.label"
                        :required="isFieldRequired(field)"
                        :class="{ 'readonly-field': field.readonly }"
                    >
                        <!-- 单行文本 -->
                        <el-input 
                            v-if="field.type === 'input'" 
                            v-model="createForm.form_data[field.field]" 
                            :placeholder="field.placeholder || '请输入' + field.label"
                            :readonly="field.readonly"
                        ></el-input>
                        
                        <!-- 多行文本 -->
                        <el-input 
                            v-else-if="field.type === 'textarea'" 
                            v-model="createForm.form_data[field.field]" 
                            type="textarea" 
                            :rows="3"
                            :placeholder="field.placeholder || '请输入' + field.label"
                            :readonly="field.readonly"
                        ></el-input>
                        
                        <!-- 数字 -->
                        <el-input-number 
                            v-else-if="field.type === 'number'" 
                            v-model="createForm.form_data[field.field]" 
                            :placeholder="field.placeholder"
                            :disabled="field.readonly"
                            style="width: 100%"
                        ></el-input-number>
                        
                        <!-- 下拉选择 -->
                        <el-select 
                            v-else-if="field.type === 'select'" 
                            v-model="createForm.form_data[field.field]" 
                            :placeholder="field.placeholder || '请选择' + field.label"
                            :disabled="field.readonly"
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
                            :disabled="field.readonly"
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
                            :disabled="field.readonly"
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
                            :disabled="field.readonly"
                            style="width: 100%"
                            value-format="YYYY-MM-DD"
                        ></el-date-picker>
                        
                        <!-- 日期时间 -->
                        <el-date-picker 
                            v-else-if="field.type === 'datetime'" 
                            v-model="createForm.form_data[field.field]" 
                            type="datetime"
                            :placeholder="field.placeholder || '请选择' + field.label"
                            :disabled="field.readonly"
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

        <!-- 确认对话框 -->
        <el-dialog v-model="confirmDialogVisible" title="流程确认" width="500px">
            <el-form :model="confirmForm" label-width="100px">
                <el-form-item label="确认意见">
                    <el-input v-model="confirmForm.approve_comment" type="textarea" :rows="4" placeholder="请输入确认意见（可选）"></el-input>
                </el-form-item>
            </el-form>
            <template #footer>
                <el-button @click="confirmDialogVisible = false">取消</el-button>
                <el-button type="primary" @click="handleConfirmSubmit" :loading="confirmLoading">确认</el-button>
            </template>
        </el-dialog>

        <!-- 审批对话框 -->
        <el-dialog v-model="approveDialogVisible" title="流程审批" width="600px">
            <el-form :model="approveForm" label-width="100px">
                <el-form-item label="审批结果" required>
                    <el-radio-group v-model="approveForm.approve_result">
                        <el-radio :label="1">通过</el-radio>
                        <!-- 只有当步骤配置允许驳回时才显示驳回选项 -->
                        <el-radio :label="2" v-if="currentTask && currentTask.allow_reject">驳回</el-radio>
                        <!-- 只有当步骤配置允许退回时才显示退回选项 -->
                        <el-radio :label="3" v-if="currentTask && currentTask.allow_return">退回</el-radio>
                    </el-radio-group>
                    <!-- 提示信息 -->
                    <div v-if="currentTask && (!currentTask.allow_reject || !currentTask.allow_return)" style="margin-top: 8px; color: #909399; font-size: 12px;">
                        <span v-if="!currentTask.allow_reject">· 当前节点不允许驳回操作</span>
                        <span v-if="!currentTask.allow_return" style="margin-left: 10px;">· 当前节点不允许退回操作</span>
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

        <!-- 软件包路径确认弹窗：发起前自动填写未找到软件包时确认实际路径（确认后写回表单继续创建）；
            提交时共享路径未找到软件包时确认路径（确认后触发复制与扫描并自动重新提交） -->
        <el-dialog v-model="scanConfirmDialogVisible" title="软件包路径确认" width="560px" @closed="handleScanConfirmClosed">
            <div style="margin-bottom: 12px; color: #606266;">
                <template v-if="scanConfirmMode === 'fill'">发起流程时自动填写软件包存放路径失败：在共享路径中未找到软件包。请确认软件包的实际存放路径（服务器绝对路径），确认后将自动填写到申请表单：</template>
                <template v-else>在共享路径中未找到软件包，无法自动触发包安全扫描。请确认软件包的实际存放路径（服务器绝对路径）：</template>
            </div>
            <el-input v-model="scanConfirmPath" placeholder="请输入软件包完整路径，如 /TestHub/xxx/xxx.tar.gz"></el-input>
            <template #footer>
                <el-button @click="scanConfirmDialogVisible = false">取消</el-button>
                <el-button type="primary" :loading="scanConfirmLoading" @click="handleScanPathConfirm">{{ scanConfirmMode === 'fill' ? '确认路径' : '确认路径并触发扫描' }}</el-button>
            </template>
        </el-dialog>

        <!-- 流程详情弹窗（公共组件：流程列表/我的待办/我的已办共用） -->
        <WorkflowDetailDialog v-model="detailDialogVisible" :instance-id="detailInstanceId" />
    </div>
</template>

<script>
    import Pagination from "@/components/Pagination";
    import {getTableHeight} from "@/utils/util";
    import {workflowInstance, workflowInstanceDetail, workflowInstanceCreate, workflowInstanceSubmit, workflowInstanceWithdraw, workflowInstanceReinitiate, workflowInstanceDelete, workflowType, workflowTaskApprove, workflowTaskReject, workflowTaskReturn, workflowTaskConfirm, apiSystemAllUser, workflowStep, checkWorkflowTypeInitiatorPermission, workflowConfirmScanPath, workflowTypeAutoFillForm} from '@/api/api';
    import {useMutitabsStore} from "@/store/mutitabs";
    import WorkflowDetailDialog from "@/components/workflowDetailDialog";
    
    export default {
        name: "workflowList",
        setup(){
            const mutitabsstore = useMutitabsStore()
            return { mutitabsstore}
        },
        components:{
            Pagination,
            WorkflowDetailDialog,
        },
        data() {
            return {
                isFull:false,
                tableHeight:500,
                loadingPage:false,
                submitLoading: false,
                approveLoading: false,
                confirmLoading: false,
                createDialogVisible: false,
                approveDialogVisible: false,
                confirmDialogVisible: false,
                detailDialogVisible: false,
                detailInstanceId: null,  // 查看详情的流程实例ID（传递给公共详情组件）
                scanConfirmDialogVisible: false,  // 包扫描路径确认弹窗
                scanConfirmLoading: false,
                scanConfirmPath: '',  // 用户确认的软件包路径
                pendingSubmitInstanceId: null,  // 待重新提交的流程实例ID（确认路径后自动重试提交）
                selectApproverDialogVisible: false,  // 选择审批人对话框
                currentUserId: null,
                workflowTypes: [],
                currentTask: null,
                formInline:{
                    page: 1,
                    limit: 10,
                    workflow_type:'',
                    title:'',
                    status:'',
                    show_only_pending: false  // 是否只显示有待审批任务的流程
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
                currentEditRowId: null,  // 当前编辑的流程ID（用于更新已撤回/已退回的流程）
                currentEditRowStatus: null,  // 当前编辑流程的原状态（用于区分重新发起/退回后重新提交）
                approveForm: {
                    approve_result: 1,
                    approve_comment: ''
                },
                confirmForm: {
                    approve_comment: ''
                },
                tableData:[],
                dynamicFormFields: [],  // 动态表单字段配置
                packageScanConfig: null,  // 发起前自动填写配置 {sharedPath, packageNameField, pathField}（仅当路径字段开启"自动回填"开关时识别，点击创建时异步自动填写）
                manualCreateMode: false,  // 手动创建模式：仅此模式下点击创建时触发发起前自动填写（从已有流程发起/打包管理跳转时保留后端预填路径）
                scanConfirmMode: 'submit',  // 软件包路径确认弹窗模式：'fill'=发起前自动填写确认（确认后写回表单继续创建）；'submit'=提交失败确认（确认后触发扫描并重新提交）
                autoFillTimer: null,  // 软件包名称变化后防抖自动回填路径字段的定时器（避免频繁调用后端接口）
                selfSelectSteps: [],  // 需要申请人自选的节点列表
                selectedApprovers: {},  // 用户选择的审批人 {step_order: [user_ids]}
                allUsers: [],  // 所有用户列表（用于选择审批人）
                allowedWorkflowTypeIds: [],  // 允许发起的流程类型ID列表
                workflowTypePermissionChecked: false,  // 是否已检查流程类型权限
                pendingApproveInstanceId: null,  // 从邮件链接跳转过来时，待自动打开审批的流程实例ID
                pendingViewInstanceId: null,  // 从待办/消息页跳转过来时，待自动打开详情的流程实例ID
                pendingResubmitInstanceId: null,  // 从待办页退回待办跳转过来时，待自动打开重新提交弹窗的流程实例ID
                pendingInitiateInstanceId: null  // 从打包管理发包跳转过来时，待自动打开发起弹窗补全申请信息的流程实例ID
            }
        },
        computed: {
            // 当前软件包名称（trim 后的字符串）：单独 watch 此计算属性以获取正确的 old/new 值
            // （deep watch 对象时 oldVal 与 newVal 是同一响应式代理，无法比较出字段变化）
            currentPackageName() {
                const cfg = this.packageScanConfig
                if(!cfg || !cfg.packageNameField || !this.createForm.form_data) {
                    return ''
                }
                return String(this.createForm.form_data[cfg.packageNameField] || '').trim()
            },
            // 根据部门权限过滤的流程类型列表
            filteredWorkflowTypes() {
                // 如果权限未检查或用户是超级管理员，显示所有流程类型
                if (!this.workflowTypePermissionChecked) {
                    return this.workflowTypes
                }
                return this.workflowTypes.filter(item => this.allowedWorkflowTypeIds.includes(item.id))
            },
            // 根据联动规则过滤可见字段
            visibleDynamicFormFields() {
                return this.dynamicFormFields.filter(field => {
                    // 检查是否有隐藏规则
                    if (field.conditional_rules) {
                        for (let rule of field.conditional_rules) {
                            if (rule.action === 'hidden') {
                                // 检查触发条件是否满足
                                if (this.checkCondition(rule)) {
                                    return false  // 字段应该被隐藏
                                }
                            } else if (rule.action === 'visible') {
                                // 检查触发条件是否满足
                                if (!this.checkCondition(rule)) {
                                    return false  // 字段应该被隐藏（因为不满足显示条件）
                                }
                            }
                        }
                    }
                    return true  // 默认显示
                })
            },
            // 审批意见是否必填（驳回或退回时必填）
            isCommentRequired() {
                return this.approveForm.approve_result === 2 || this.approveForm.approve_result === 3
            },
            // 创建/发起流程弹窗标题（根据编辑流程的原状态区分）
            createDialogTitle() {
                if (this.currentEditRowStatus == 6) return '退回后重新提交流程'
                if (this.currentEditRowStatus == 0) return '发起流程（补全申请信息）'
                if (this.currentEditRowId) return '重新发起流程'
                return '发起流程'
            }
        },
        created() {
            this.currentUserId = this.mutitabsstore.getUserId
            console.log('[WorkflowList] currentUserId:', this.currentUserId, '(类型:', typeof this.currentUserId, ')')
            // 从邮件审批链接跳转过来时，携带 approve_instance 参数，自动过滤待审批流程并打开审批弹窗
            const approveInstanceId = this.$route.query.approve_instance
            if (approveInstanceId) {
                this.pendingApproveInstanceId = String(approveInstanceId)
                this.formInline.show_only_pending = true
                console.log('[WorkflowList] 检测到邮件审批链接，待审批流程ID:', this.pendingApproveInstanceId)
            }
            // 从我的待办/消息页跳转过来时，携带 view_instance 参数，自动打开与流程列表一致的详情弹窗
            const viewInstanceId = this.$route.query.view_instance
            if (viewInstanceId) {
                this.pendingViewInstanceId = String(viewInstanceId)
                console.log('[WorkflowList] 检测到详情跳转参数，流程实例ID:', this.pendingViewInstanceId)
                this.tryOpenDetailFromLink()
            }
            // 从我的待办页退回待办跳转过来时，携带 resubmit_instance 参数，自动打开重新提交弹窗
            const resubmitInstanceId = this.$route.query.resubmit_instance
            if (resubmitInstanceId) {
                this.pendingResubmitInstanceId = String(resubmitInstanceId)
                console.log('[WorkflowList] 检测到重新提交跳转参数，流程实例ID:', this.pendingResubmitInstanceId)
                this.tryOpenResubmitFromLink()
            }
            // 从打包管理"发包"跳转过来时，携带 initiate_instance 参数，自动打开发起弹窗补全申请信息
            const initiateInstanceId = this.$route.query.initiate_instance
            if (initiateInstanceId) {
                this.pendingInitiateInstanceId = String(initiateInstanceId)
                console.log('[WorkflowList] 检测到发包跳转参数，流程实例ID:', this.pendingInitiateInstanceId)
                this.tryOpenInitiateFromLink()
            }
            this.getWorkflowTypes()
            this.getAllUsers()  // 获取所有用户列表
            this.getData()
        },
        watch: {
            // 兜底：当页面已被缓存（created不会重新触发）时，监听URL参数变化，仍支持从待办页跳转打开详情
            '$route.query.view_instance'(val) {
                if (val) {
                    this.pendingViewInstanceId = String(val)
                    this.tryOpenDetailFromLink()
                }
            },
            // 兜底：监听重新提交跳转参数变化，仍支持从待办页退回待办跳转打开重新提交弹窗
            '$route.query.resubmit_instance'(val) {
                if (val) {
                    this.pendingResubmitInstanceId = String(val)
                    this.tryOpenResubmitFromLink()
                }
            },
            // 兜底：监听发包跳转参数变化，仍支持从打包管理发包跳转打开发起弹窗补全申请信息
            '$route.query.initiate_instance'(val) {
                if (val) {
                    this.pendingInitiateInstanceId = String(val)
                    this.tryOpenInitiateFromLink()
                }
            },
            // 兜底：流程类型列表加载完成时，若发起/补全弹窗已打开但动态表单未加载（打包管理"发包"跳转时
            // 详情接口可能先于流程类型列表返回，导致 loadDynamicFormFields 执行时 workflowTypes 为空），
            // 补加载申请信息表单（幂等：表单已正常加载时条件不满足）
            'workflowTypes'(val) {
                if(this.createDialogVisible && this.createForm.workflow_type && this.dynamicFormFields.length === 0) {
                    this.loadDynamicFormFields(true)
                }
            },
            // 监听软件包名称变化：填写"软件包名称"后防抖自动回填"软件包存放路径"字段（感官上即时显示回填值）；
            // 点击创建时后端仍会兜底校验文件真实存在（不存在时弹窗确认实际路径）
            currentPackageName(newName, oldName) {
                if(newName !== oldName) {
                    console.log('[Watch] 软件包名称变化:', oldName, '->', newName)
                    this.scheduleAutoFillPath()
                }
            },
            'createForm.form_data': {
                handler(newVal) {
                    console.log('[Watch] 表单数据变化:', newVal)
                    // 特别关注客户名称字段
                    if (newVal['customer_name'] !== undefined) {
                        console.log('[Watch] 客户名称字段值:', newVal['customer_name'], '(类型:', typeof newVal['customer_name'], Array.isArray(newVal['customer_name']) ? '数组' : '非数组', ')') 
                    }
                },
                deep: true
            }
        },
        methods:{
            // 处理详情跳转：根据 view_instance 参数设置实例ID并打开公共详情弹窗
            tryOpenDetailFromLink(){
                if(!this.pendingViewInstanceId) {
                    return
                }
                const targetId = this.pendingViewInstanceId
                // 无论成功与否都只处理一次，避免重复触发
                this.pendingViewInstanceId = null
                this.detailInstanceId = targetId
                this.detailDialogVisible = true

                // 移除URL中的 view_instance 参数，避免刷新页面重复触发
                const query = { ...this.$route.query }
                delete query.view_instance
                this.$router.replace({ path: this.$route.path, query }).catch(() => {})
            },
            // 处理退回待办重新提交跳转：根据 resubmit_instance 参数调用详情接口，自动打开重新提交弹窗
            tryOpenResubmitFromLink(){
                if(!this.pendingResubmitInstanceId) {
                    return
                }
                const targetId = this.pendingResubmitInstanceId
                // 无论成功与否都只处理一次，避免重复触发
                this.pendingResubmitInstanceId = null

                workflowInstanceDetail(targetId).then(res => {
                    const detail = res.data?.data || res.data
                    if(res.code === 2000 && detail) {
                        if(detail.status !== 6) {
                            this.$message.warning('该流程当前不是已退回状态，无法重新提交')
                            return
                        }
                        // 复用流程列表"重新提交"入口，打开退回后重新提交弹窗
                        this.handleInitiate(detail)
                    } else {
                        this.$message.warning('未找到对应的流程信息')
                    }
                }).catch(err => {
                    console.error('[WorkflowList] 获取流程详情失败:', err)
                    this.$message.error('获取流程详情失败')
                })

                // 移除URL中的 resubmit_instance 参数，避免刷新页面重复触发
                const query = { ...this.$route.query }
                delete query.resubmit_instance
                this.$router.replace({ path: this.$route.path, query }).catch(() => {})
            },
            // 处理发包跳转：根据 initiate_instance 参数调用详情接口，自动打开对应草稿流程的发起弹窗（软件包存放路径已预填，补全申请信息后提交）
            tryOpenInitiateFromLink(){
                if(!this.pendingInitiateInstanceId) {
                    return
                }
                const targetId = this.pendingInitiateInstanceId
                // 无论成功与否都只处理一次，避免重复触发
                this.pendingInitiateInstanceId = null

                workflowInstanceDetail(targetId).then(res => {
                    const detail = res.data?.data || res.data
                    if(res.code === 2000 && detail) {
                        if(detail.status !== 0) {
                            this.$message.warning('该流程已提交或状态已变化，无法补全申请信息')
                            return
                        }
                        // 复用流程列表"发起"入口，打开补全申请信息弹窗（自动填充的软件包存放路径会一并带入）
                        this.handleInitiate(detail)
                    } else {
                        this.$message.warning('未找到对应的流程信息')
                    }
                }).catch(err => {
                    console.error('[WorkflowList] 获取流程详情失败:', err)
                    this.$message.error('获取流程详情失败')
                })

                // 移除URL中的 initiate_instance 参数，避免刷新页面重复触发
                const query = { ...this.$route.query }
                delete query.initiate_instance
                this.$router.replace({ path: this.$route.path, query }).catch(() => {})
            },
            // 处理邮件审批链接跳转：根据 approve_instance 参数自动打开审批/确认弹窗
            tryOpenApproveFromLink(){
                if(!this.pendingApproveInstanceId) {
                    return
                }
                const targetId = this.pendingApproveInstanceId
                // 无论是否找到都只处理一次，避免重复触发
                this.pendingApproveInstanceId = null
                
                const row = this.tableData.find(item => item.id === targetId)
                if(row && row.my_pending_task) {
                    // 有待处理任务，区分审批与确认：申请人确认任务（node_type!=1 或 approver_type==7）打开流程确认弹窗，其余打开流程审批弹窗
                    const task = row.my_pending_task
                    const isConfirmTask = task.step_node_type != 1 || task.step_approver_type == 7
                    if(isConfirmTask && row.applicant == this.currentUserId) {
                        this.handleConfirm(row)
                    } else {
                        this.handleApprove(row)
                    }
                } else if(row) {
                    // 流程存在但没有待审批任务（可能已被审批），打开详情
                    this.$message.info('该流程暂无待审批任务，已为您打开流程详情')
                    this.handleViewDetail(row)
                } else {
                    this.$message.warning('未找到对应的待审批流程，可能已被处理或不在当前列表中')
                }
                
                // 移除URL中的 approve_instance 参数，避免刷新页面重复触发
                const query = { ...this.$route.query }
                delete query.approve_instance
                this.$router.replace({ path: this.$route.path, query }).catch(() => {})
            },
            // 表格序列号
            getIndex($index) {
                return (this.pageparm.page - 1) * this.pageparm.limit + $index + 1
            },
            // 获取数据
            getData(){
                let vm = this
                vm.loadingPage = true
                console.log('[WorkflowList] 发送请求，参数:', vm.formInline)
                workflowInstance(vm.formInline).then(res => {
                    vm.loadingPage = false
                    console.log('[WorkflowList] 后端响应:', JSON.stringify(res, null, 2))
                    
                    if(res.code === 2000) {
                        // 注意：Django REST Framework 的分页响应结构可能是 res.data.data 或 res.data
                        const responseData = res.data?.data || res.data
                        console.log('[WorkflowList] 解析后的数据:', responseData)
                        
                        vm.tableData = Array.isArray(responseData) ? responseData : []
                        
                        // 如果有分页信息，更新分页参数
                        if (res.data?.page) {
                            vm.pageparm.page = res.data.page
                        }
                        if (res.data?.limit) {
                            vm.pageparm.limit = res.data.limit
                        }
                        if (res.data?.total) {
                            vm.pageparm.total = res.data.total
                        }
                        
                        // 调试日志：打印流程列表数据
                        console.log('[WorkflowList] 获取到流程数据:', vm.tableData.length, '条')
                        console.log('[WorkflowList] currentUserId:', vm.currentUserId, '(类型:', typeof vm.currentUserId, ')')
                        
                        vm.tableData.forEach((item, index) => {
                            console.log(`[WorkflowList] 流程${index}: ID=${item.id}, applicant=${item.applicant}(类型:${typeof item.applicant}), title=${item.title}, status=${item.status}`)
                            
                            // 关键：检查是否与当前用户创建
                            if (item.applicant === vm.currentUserId) {
                                console.log(`[WorkflowList] ✓✓✓ 流程${index} 是用户 ${vm.currentUserId} 创建的！`)
                            } else {
                                console.log(`[WorkflowList] ✗✗ 流程${index} 不是用户创建的，申请人=${item.applicant}, currentUserId=${vm.currentUserId}`)
                            }
                        })
                        
                        // 处理邮件审批链接跳转：自动打开对应流程的审批弹窗
                        vm.tryOpenApproveFromLink()
                    } else {
                        console.error('[WorkflowList] 后端返回错误:', res.msg, res.code)
                    }
                }).catch(err => {
                    vm.loadingPage = false
                    console.error('[WorkflowList] 请求失败:', err)
                    vm.$message.error('获取数据失败')
                })
            },
            // 获取流程类型
            getWorkflowTypes(){
                let vm = this
                workflowType({status: 1}).then(res => {
                    if(res.code === 2000) {
                        vm.workflowTypes = res.data.data || []
                        // 检查每个流程类型的发起人权限
                        vm.checkAllWorkflowTypePermissions()
                    }
                })
            },
            // 检查所有流程类型的发起人权限
            checkAllWorkflowTypePermissions(){
                let vm = this
                vm.allowedWorkflowTypeIds = []
                vm.workflowTypePermissionChecked = false
                
                const checkPromises = vm.workflowTypes.map(item => {
                    return checkWorkflowTypeInitiatorPermission(item.id).then(res => {
                        if(res && res.code === 2000 && res.data && res.data.allowed) {
                            vm.allowedWorkflowTypeIds.push(item.id)
                        }
                    }).catch(err => {
                        console.error(`检查流程类型 ${item.name} 权限失败:`, err)
                    })
                })
                
                Promise.all(checkPromises).then(() => {
                    vm.workflowTypePermissionChecked = true
                    console.log('允许发起的流程类型ID列表:', vm.allowedWorkflowTypeIds)
                })
            },
            // 获取所有用户列表
            getAllUsers(){
                let vm = this
                apiSystemAllUser({page: 1, limit: 1000}).then(res => {
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
                    status:'',
                    show_only_pending: false
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
                this.packageScanConfig = null  // 重置发起前自动填写配置
                if(this.autoFillTimer) {  // 清理防抖定时器（可能遗留未触发的回填请求）
                    clearTimeout(this.autoFillTimer)
                    this.autoFillTimer = null
                }
                this.manualCreateMode = true  // 手动创建：路径字段由系统按"自动回填"开关接管
                this.selfSelectSteps = []  // 重置自选节点列表
                this.selectedApprovers = {}  // 重置选择的审批人
                this.isFromInitiate = false  // 手动创建，流程类型和标题可编辑
                this.currentEditRowId = null  // 重置编辑ID
                this.currentEditRowStatus = null  // 重置编辑状态
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
                
                // 从已有流程发起：不接管只读路径字段，保留原流程/后端预填的路径（避免覆盖真实制品路径）
                this.manualCreateMode = false
                
                // 设置标识：从已有流程发起，流程类型不可编辑，但标题可编辑
                this.isFromInitiate = true
                this.currentEditRowId = row.id  // 保存当前编辑的流程ID
                this.currentEditRowStatus = row.status  // 保存原流程状态
                
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
                // 选择流程类型后立即加载申请信息表单；从已有流程发起/打包管理跳转时（preserveData=true）
                // 保留原流程表单数据
                this.loadDynamicFormFields(preserveData)
            },
            // 加载流程类型的申请信息表单字段配置：解析 form_schema、识别"自动回填"配置（软件包存放路径字段）、初始化表单默认值
            loadDynamicFormFields(preserveData = false){
                let vm = this
                const workflowTypeId = vm.createForm.workflow_type
                if(!workflowTypeId) {
                    vm.dynamicFormFields = []
                    vm.packageScanConfig = null
                    return
                }
                
                // 从 workflowTypes 中找到对应的流程类型
                const workflowType = vm.workflowTypes.find(item => item.id === workflowTypeId)
                if(workflowType && workflowType.form_schema) {
                    try {
                        // 解析 form_schema
                        let schema = typeof workflowType.form_schema === 'string' 
                            ? JSON.parse(workflowType.form_schema) 
                            : workflowType.form_schema
                        
                        // 兼容两种格式：{fields: [...]} 或直接 [...]
                        if (schema.fields && Array.isArray(schema.fields)) {
                            vm.dynamicFormFields = schema.fields
                        } else if (Array.isArray(schema)) {
                            vm.dynamicFormFields = schema
                        } else {
                            console.error('form_schema 格式不正确:', schema)
                            vm.dynamicFormFields = []
                            return
                        }
                        
                        // 调试日志：打印字段配置
                        console.log('=== 动态表单字段配置 ===')
                        console.log('字段总数:', vm.dynamicFormFields.length)
                        vm.dynamicFormFields.forEach(field => {
                            console.log(`\n字段: ${field.label} (${field.field})`)
                            console.log('  - 类型:', field.type)
                            console.log('  - 必填:', field.required)
                            if (field.conditional_rules && field.conditional_rules.length > 0) {
                                console.log('  - ✅ 检测到联动规则:', JSON.stringify(field.conditional_rules, null, 2))
                            } else {
                                console.log('  - ❌ 无联动规则')
                            }
                        })
                        console.log('\n========================')
                        
                        // 提取发起前自动填写配置：当"软件包存放路径"字段开启"自动回填"开关（auto_fill）时由系统接管
                        // （与打包管理发包链路的自动回填共用同一开关：打包管理发包时回填制品实际路径，
                        //  手动创建时按"共享路径 + 包名"拼接并校验文件真实存在；
                        //  共享路径与包名字段 key 由后端流程类型接口注入，避免前端硬编码路径）
                        const pathField = workflowType.package_scan_path_field || ''
                        const pathFieldObj = vm.dynamicFormFields.find(f => f.field === pathField)
                        if(pathField && pathFieldObj && pathFieldObj.auto_fill) {
                            vm.packageScanConfig = {
                                sharedPath: workflowType.package_scan_shared_path || '',
                                packageNameField: workflowType.package_scan_package_name_field || '',
                                pathField: pathField
                            }
                            console.log('[WorkflowList] 检测到自动回填软件包存放路径字段:', vm.packageScanConfig)
                        } else {
                            vm.packageScanConfig = null
                        }
                        
                        // 初始化 form_data（如果不需要保留数据）
                        // 注意：项目为 Vue 3（Proxy 响应式），直接赋值即可自动追踪，无需 $set
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
                        vm.packageScanConfig = null  // 重置包扫描路径拼接配置
                    }
                } else {
                    vm.dynamicFormFields = []
                    vm.packageScanConfig = null
                    // 流程类型列表可能尚未加载完成（打包管理"发包"跳转打开发起弹窗时详情接口先返回的竞态场景）：
                    // 置空后由 watch workflowTypes 在列表就绪后补加载，避免申请信息表单缺失
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
                
                // 验证动态表单字段的必填项（包括联动规则）；跳过只读字段
                // （只读字段用户无法编辑，由系统按"自动回填"开关异步自动填写/用户确认路径后回填，提交时再由后端兜底校验）
                for(let field of this.visibleDynamicFormFields) {
                    // 只读字段：跳过必填校验，等待异步自动填写回填
                    if(field.readonly) {
                        continue
                    }
                    // 检查字段是否必填（基础必填 + 联动规则）
                    const isRequired = this.isFieldRequired(field)
                    if(isRequired) {
                        const value = this.createForm.form_data[field.field]
                        if(value === '' || value === null || value === undefined || (Array.isArray(value) && value.length === 0)) {
                            this.$message.warning('请填写必填项：' + field.label)
                            return
                        }
                    }
                }
                
                let vm = this
                vm.submitLoading = true
                
                // 发起流程前先异步自动填写（按流程配置中开启"自动回填"开关的字段，如软件包存放路径：
                // 拼接"共享路径 + 软件包名称"并校验文件真实存在；路径不存在时弹窗让用户确认实际路径）
                vm.autoFillBeforeCreate().then(canContinue => {
                    if(!canContinue) {
                        // 路径确认弹窗已打开（确认后自动继续创建）或自动填写失败：等待用户处理
                        vm.submitLoading = false
                        return
                    }
                    vm.submitLoading = false
                    // 检查是否有"申请人自选"节点
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
                })
            },
            // 软件包名称变化后防抖调度自动回填（填写包名时即时回填路径字段，感官上"填写进去了"；
            // 文件存在时回填"共享路径 + 包名"，不存在时保持空白，点击创建时再弹窗确认实际路径）
            scheduleAutoFillPath(){
                const cfg = this.packageScanConfig
                // 仅手动创建模式且路径字段开启"自动回填"开关才触发（从已有流程发起/打包管理跳转时保留原值）
                if(!this.manualCreateMode || !cfg || !cfg.pathField) {
                    return
                }
                const packageName = String(this.createForm.form_data[cfg.packageNameField] || '').trim()
                if(!packageName) {
                    return
                }
                if(this.autoFillTimer) {
                    clearTimeout(this.autoFillTimer)
                }
                this.autoFillTimer = setTimeout(() => {
                    this.autoFillPathField()
                }, 500)
            },
            // 调用后端接口自动回填路径字段（不弹窗：文件存在时回填校验后的路径；
            // 不存在时也回填候选路径（共享路径+包名拼接结果）供用户查看，点击创建时再弹窗确认实际路径）
            autoFillPathField(){
                this.autoFillTimer = null
                const cfg = this.packageScanConfig
                const pathFieldObj = this.dynamicFormFields.find(f => f.field === (cfg && cfg.pathField))
                if(!cfg || !cfg.pathField || !pathFieldObj || !pathFieldObj.auto_fill) {
                    console.warn('[WorkflowList] 跳过自动回填：配置或开关不满足', cfg, pathFieldObj && pathFieldObj.auto_fill)
                    return
                }
                console.log('[WorkflowList] 开始自动回填路径字段, 包名:', this.createForm.form_data[cfg.packageNameField])
                let vm = this
                workflowTypeAutoFillForm(this.createForm.workflow_type, {form_data: this.createForm.form_data}).then(res => {
                    console.log('[WorkflowList] 自动回填接口返回:', res)
                    if(res.code === 2000) {
                        const data = res.data || {}
                        const filled = data.filled_fields || {}
                        Object.keys(filled).forEach(key => {
                            if(vm.createForm.form_data[key] !== filled[key]) {
                                vm.createForm.form_data[key] = filled[key]
                            }
                        })
                        // 文件不存在时后端返回 need_confirm + candidate_path（共享路径+包名拼接结果）：
                        // 也回填到路径字段显示，感官上"已填写"；点击创建时再由后端兜底校验弹窗确认实际路径
                        if(data.need_confirm && data.candidate_path && !filled[cfg.pathField] &&
                           vm.createForm.form_data[cfg.pathField] !== data.candidate_path) {
                            vm.createForm.form_data[cfg.pathField] = data.candidate_path
                        }
                    }
                }).catch(err => {
                    console.error('[WorkflowList] 自动回填路径异常:', err)
                })
            },
            // 发起前异步自动填写：按流程配置中路径字段的"自动回填"开关（auto_fill）触发，
            // 调用后端接口计算回填值（软件包存放路径：按"共享路径 + 软件包名称"拼接并校验文件是否真实存在）
            // 路径不存在时打开确认弹窗，用户确认后写回路径并自动继续创建；返回 Promise<boolean> 是否可继续创建
            autoFillBeforeCreate(){
                const cfg = this.packageScanConfig
                const pathFieldObj = this.dynamicFormFields.find(f => f.field === (cfg && cfg.pathField))
                // 仅手动创建模式且路径字段开启"自动回填"开关才触发（系统接管，用户无需手动填写）；
                // 从已有流程发起时保留原流程/后端预填的路径
                if(!this.manualCreateMode || !cfg || !cfg.pathField || !pathFieldObj || !pathFieldObj.auto_fill) {
                    return Promise.resolve(true)
                }
                // 未填写软件包名称时无需自动填写（提交时后端仍按包名拼接共享路径兜底校验）
                const packageName = String(this.createForm.form_data[cfg.packageNameField] || '').trim()
                if(!packageName) {
                    return Promise.resolve(true)
                }
                let vm = this
                return workflowTypeAutoFillForm(this.createForm.workflow_type, {form_data: this.createForm.form_data}).then(res => {
                    if(res.code === 2000) {
                        const data = res.data || {}
                        // 回填自动填写字段（如软件包存放路径 = 共享路径 + 包名）
                        const filled = data.filled_fields || {}
                        Object.keys(filled).forEach(key => {
                            if(vm.createForm.form_data[key] !== filled[key]) {
                                vm.createForm.form_data[key] = filled[key]
                            }
                        })
                        if(data.need_confirm) {
                            // 自动填写时共享路径未找到软件包：弹窗让用户确认实际路径，确认后写回表单继续创建
                            vm.scanConfirmMode = 'fill'
                            vm.scanConfirmPath = data.candidate_path || ''
                            vm.scanConfirmDialogVisible = true
                            return false
                        }
                        return true
                    }
                    // 自动填写失败不阻塞创建：提交时后端仍会兜底校验并弹窗确认
                    console.error('[WorkflowList] 发起前自动填写失败:', res.msg)
                    return true
                }).catch(err => {
                    console.error('[WorkflowList] 发起前自动填写异常:', err)
                    return true
                })
            },
            // 检查是否有申请人自选节点
            checkSelfSelectSteps(){
                return new Promise((resolve, reject) => {
                    let vm = this
                    workflowStep({workflow_type: vm.createForm.workflow_type}).then(res => {
                        if(res && res.code === 2000) {
                            const steps = (res.data && res.data.data) || []
                            // 筛选出审批人类型为5（申请人自选）的节点，排除结束节点（node_type=5）
                            vm.selfSelectSteps = steps.filter(step => step.approver_type === 5 && step.node_type !== 5)
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
                
                // 验证动态表单字段的必填项；跳过只读字段（系统按"自动回填"开关自动填写，提交后由后端校验路径并弹窗确认）
                for(let field of this.dynamicFormFields) {
                    if(field.readonly) {
                        continue
                    }
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
                if(this.autoFillTimer) {  // 清理防抖定时器
                    clearTimeout(this.autoFillTimer)
                    this.autoFillTimer = null
                }
                this.createDialogVisible = false
                // 重置标识
                this.isFromInitiate = false
                this.currentEditRowId = null  // 重置编辑ID
                this.currentEditRowStatus = null  // 重置编辑状态
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
                            } else if(vm.handleSubmitError(instanceId, submitRes)) {
                                // 包扫描路径确认弹窗已打开：确认路径后自动重新提交
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
                            } else if(vm.handleSubmitError(vm.currentEditRowId, submitRes)) {
                                // 包扫描路径确认弹窗已打开：确认路径后自动重新提交
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
                        } else if(vm.handleSubmitError(row.id, res)) {
                            // 包扫描路径确认弹窗已打开：确认路径后自动重新提交
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
            // 处理提交流程失败：包扫描路径需确认时打开路径确认弹窗（返回 true），否则返回 false
            handleSubmitError(instanceId, res) {
                if(res && res.data && res.data.need_confirm) {
                    this.scanConfirmMode = 'submit'  // 提交失败确认模式：确认路径后触发复制与扫描并重新提交
                    this.pendingSubmitInstanceId = instanceId
                    this.scanConfirmPath = (res.data.candidate_path) || ''
                    this.scanConfirmDialogVisible = true
                    // 关闭发起弹窗（流程草稿已创建，保留在列表中，确认路径后自动重新提交）
                    this.createDialogVisible = false
                    return true
                }
                return false
            },
            // 确认软件包路径：发起前自动填写确认时写回表单并继续创建；提交失败确认时触发复制与扫描，成功后自动重新提交流程
            handleScanPathConfirm() {
                let vm = this
                if(!vm.scanConfirmPath || !vm.scanConfirmPath.trim()) {
                    vm.$message.warning('请填写软件包路径')
                    return
                }
                // 发起前自动填写确认：将确认的路径写回表单对应字段，关闭弹窗后继续创建流程
                if(vm.scanConfirmMode === 'fill') {
                    const cfg = vm.packageScanConfig
                    if(cfg && cfg.pathField) {
                        vm.createForm.form_data[cfg.pathField] = vm.scanConfirmPath.trim()
                    }
                    vm.scanConfirmDialogVisible = false
                    // 继续创建（发起前自动填写已确认过路径，无需再次调用）
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
                    return
                }
                // 提交失败确认（现有逻辑）：触发复制与扫描，成功后自动重新提交流程
                vm.scanConfirmLoading = true
                workflowConfirmScanPath(vm.pendingSubmitInstanceId, {package_path: vm.scanConfirmPath.trim()}).then(res => {
                    vm.scanConfirmLoading = false
                    if(res.code === 2000) {
                        vm.$message.success('路径已确认，扫描已触发，正在重新提交...')
                        vm.scanConfirmDialogVisible = false
                        vm.retrySubmitInstance()
                    } else {
                        vm.$message.error(res.msg || '路径确认失败')
                    }
                }).catch(err => {
                    vm.scanConfirmLoading = false
                    vm.$message.error('路径确认失败')
                })
            },
            // 路径确认弹窗关闭后复位模式：发起前自动填写确认模式仅本次生效，后续默认回到提交失败确认模式
            handleScanConfirmClosed() {
                this.scanConfirmMode = 'submit'
            },
            // 确认路径后自动重新提交流程（字段3已回填，后端跳过路径确认）
            retrySubmitInstance() {
                let vm = this
                vm.loadingPage = true
                workflowInstanceSubmit(vm.pendingSubmitInstanceId).then(res => {
                    vm.loadingPage = false
                    if(res.code === 2000) {
                        vm.$message.success('流程提交成功')
                        vm.isFromInitiate = false
                        vm.currentEditRowId = null
                        vm.pendingSubmitInstanceId = null
                        vm.getData()
                    } else if(res.data && res.data.need_confirm) {
                        // 路径仍不存在：重新打开确认弹窗
                        vm.scanConfirmPath = (res.data.candidate_path) || vm.scanConfirmPath
                        vm.scanConfirmDialogVisible = true
                        vm.$message.warning(res.msg || '请再次确认软件包路径')
                    } else {
                        vm.$message.error('提交失败：' + (res.msg || ''))
                        vm.pendingSubmitInstanceId = null
                        vm.getData()
                    }
                }).catch(err => {
                    vm.loadingPage = false
                    vm.$message.error('提交失败')
                })
            },
            // 确认（申请人确认自己的流程）
            handleConfirm(row){
                if(!row.my_pending_task) {
                    this.$message.warning('没有待确认的任务')
                    return
                }
                this.currentTask = row.my_pending_task
                this.confirmForm = {
                    approve_comment: ''
                }
                this.confirmDialogVisible = true
            },
            // 提交确认
            handleConfirmSubmit(){
                let vm = this
                vm.confirmLoading = true
                workflowTaskConfirm(vm.currentTask.id, vm.confirmForm).then(res => {
                    vm.confirmLoading = false
                    if(res.code === 2000) {
                        vm.$message.success('确认成功')
                        vm.confirmDialogVisible = false
                        vm.getData()
                    } else {
                        vm.$message.error(res.msg || '确认失败')
                        vm.confirmDialogVisible = false
                        vm.getData()
                    }
                }).catch(err => {
                    vm.confirmLoading = false
                    vm.$message.error('确认失败')
                    vm.confirmDialogVisible = false
                    vm.getData()
                })
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
                this.detailInstanceId = row.id
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
            
            // 检查指定层级是否有待审批任务（新方法，更精确）
            checkHasPendingTasksAtLevel(levelOrder, row) {
                if (!row || !row.approval_history) return false
                
                // 关键修复：如果流程状态是"已通过"（status=2），说明没有待审批任务
                if (row.status === 2) {
                    return false
                }
                
                // 关键修复：检查该层级对应的步骤是否被自动跳过
                const stepsInfo = row.steps_info || []
                const step = stepsInfo.find(s => {
                    const stepLevelOrder = s.level_order !== undefined && s.level_order !== null ? s.level_order : s.step_order
                    return stepLevelOrder == levelOrder
                })
                if (step) {
                    const skippedSteps = row.skipped_steps || []
                    if (skippedSteps.includes(step.id)) {
                        console.log('checkHasPendingTasksAtLevel - 步骤', step.id, '被自动跳过，不应视为有待审批任务')
                        return false
                    }
                }
                
                // 从审批历史中查找该层级的所有任务
                const history = row.approval_history || []
                const tasksAtLevel = history.filter(task => {
                    const taskLevelOrder = task.level_order !== undefined && task.level_order !== null ? task.level_order : task.step_order
                    return taskLevelOrder == levelOrder
                })
                
                // 关键修复：获取被自动跳过的步骤列表
                const skippedSteps = row.skipped_steps || []
                
                // 关键修复：如果该层级被自动跳过，即使没有任务记录，也不应视为有待审批任务
                if (step && skippedSteps.includes(step.id)) {
                    console.log('checkHasPendingTasksAtLevel - 层级', levelOrder, '的步骤', step.id, '被自动跳过，不视为待审批')
                    return false
                }
                
                // 关键修复：如果该层级没有任何任务记录，说明任务尚未创建（可能是引擎bug导致未分配审批人）
                // 此时应将此层级视为当前待处理步骤
                if (tasksAtLevel.length === 0) {
                    console.log('checkHasPendingTasksAtLevel - 层级', levelOrder, '无任何任务记录，视为当前待处理')
                    return true
                }
                
                // 检查是否有待审批的任务（status=0）
                const pendingTasks = tasksAtLevel.filter(task => task.status === 0)
                
                return pendingTasks.length > 0
            },
            
            // 检查联动条件是否满足
            checkCondition(rule) {
                if (!rule || !rule.trigger_field || !rule.operator) {
                    console.log('[checkCondition] 规则不完整:', rule)
                    return false
                }
                
                const triggerValue = this.createForm.form_data[rule.trigger_field]
                const conditionValue = rule.trigger_value
                
                console.log(`[checkCondition] 触发字段: ${rule.trigger_field}, 操作符: ${rule.operator}`)
                console.log(`[checkCondition] 当前值:`, triggerValue, '(类型:', typeof triggerValue, Array.isArray(triggerValue) ? '数组' : '非数组', ')')
                console.log(`[checkCondition] 条件值:`, conditionValue)
                
                let result = false
                switch (rule.operator) {
                    case '==':
                        // 如果触发值是数组（复选框），检查是否包含该值
                        if (Array.isArray(triggerValue)) {
                            // 尝试精确匹配
                            result = triggerValue.includes(conditionValue)
                            console.log(`[checkCondition] 数组比较 - includes(${conditionValue}):`, result)
                            
                            // 如果精确匹配失败，尝试从字段配置中查找对应的value
                            if (!result) {
                                const fieldConfig = this.dynamicFormFields.find(f => f.field === rule.trigger_field)
                                if (fieldConfig && fieldConfig.options && Array.isArray(fieldConfig.options)) {
                                    // 查找label匹配的选项
                                    const matchedOption = fieldConfig.options.find(opt => 
                                        opt.label === conditionValue || opt.value === conditionValue
                                    )
                                    if (matchedOption) {
                                        // 用找到的value重新检查
                                        result = triggerValue.includes(matchedOption.value)
                                        console.log(`[checkCondition] 尝试匹配选项: label=${matchedOption.label}, value=${matchedOption.value}, 结果:`, result)
                                    }
                                }
                            }
                        } else {
                            // 否则直接比较
                            result = triggerValue == conditionValue
                            console.log(`[checkCondition] 直接比较 - ${triggerValue} == ${conditionValue}:`, result)
                        }
                        break
                    case '!=':
                        // 如果触发值是数组（复选框），检查是否不包含该值
                        if (Array.isArray(triggerValue)) {
                            result = !triggerValue.includes(conditionValue)
                            console.log(`[checkCondition] 数组比较 - !includes(${conditionValue}):`, result)
                        } else {
                            // 否则直接比较
                            result = triggerValue != conditionValue
                            console.log(`[checkCondition] 直接比较 - ${triggerValue} != ${conditionValue}:`, result)
                        }
                        break
                    case 'contains':
                        if (Array.isArray(triggerValue)) {
                            result = triggerValue.includes(conditionValue)
                            console.log(`[checkCondition] contains(数组) - includes(${conditionValue}):`, result)
                            
                            // 如果精确匹配失败，尝试从字段配置中查找对应的value
                            if (!result) {
                                const fieldConfig = this.dynamicFormFields.find(f => f.field === rule.trigger_field)
                                if (fieldConfig && fieldConfig.options && Array.isArray(fieldConfig.options)) {
                                    // 查找label匹配的选项
                                    const matchedOption = fieldConfig.options.find(opt => 
                                        opt.label === conditionValue || opt.value === conditionValue
                                    )
                                    if (matchedOption) {
                                        // 用找到的value重新检查
                                        result = triggerValue.includes(matchedOption.value)
                                        console.log(`[checkCondition] contains尝试匹配选项: label=${matchedOption.label}, value=${matchedOption.value}, 结果:`, result)
                                    }
                                }
                            }
                        } else {
                            result = String(triggerValue || '').includes(conditionValue)
                            console.log(`[checkCondition] contains(字符串) - includes(${conditionValue}):`, result)
                        }
                        break
                    case 'not_contains':
                        if (Array.isArray(triggerValue)) {
                            result = !triggerValue.includes(conditionValue)
                            console.log(`[checkCondition] not_contains(数组) - !includes(${conditionValue}):`, result)
                        } else {
                            result = !String(triggerValue || '').includes(conditionValue)
                            console.log(`[checkCondition] not_contains(字符串) - !includes(${conditionValue}):`, result)
                        }
                        break
                    default:
                        console.log(`[checkCondition] 未知操作符: ${rule.operator}`)
                        result = false
                }
                
                console.log(`[checkCondition] 最终结果:`, result)
                return result
            },
            // 判断字段是否必填（包括基础必填和联动规则）
            isFieldRequired(field) {
                // 首先检查基础必填属性
                if (field.required) {
                    console.log(`[isFieldRequired] ${field.label} - 基础必填: true`)
                    return true
                }
                
                // 然后检查联动规则
                if (field.conditional_rules && field.conditional_rules.length > 0) {
                    console.log(`[isFieldRequired] ${field.label} - 检测到联动规则:`, field.conditional_rules)
                    for (let rule of field.conditional_rules) {
                        console.log(`[isFieldRequired] ${field.label} - 检查规则:`, rule)
                        const conditionMet = this.checkCondition(rule)
                        console.log(`[isFieldRequired] ${field.label} - 条件是否满足:`, conditionMet)
                        
                        if (rule.action === 'required') {
                            // 如果触发条件满足，则设为必填
                            if (conditionMet) {
                                console.log(`[isFieldRequired] ${field.label} - 联动规则生效: 设为必填`)
                                return true
                            }
                        } else if (rule.action === 'not_required') {
                            // 如果触发条件满足，则取消必填
                            if (conditionMet) {
                                console.log(`[isFieldRequired] ${field.label} - 联动规则生效: 取消必填`)
                                return false
                            }
                        }
                    }
                }
                
                console.log(`[isFieldRequired] ${field.label} - 最终结果: false`)
                return false
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

    /* 只读字段置灰：readonly 属性本身不会改变控件外观，这里手动置灰以明确提示该字段不可编辑
       （input/textarea 使用 readonly 保留文本可复制，select/radio 等使用 disabled 自带置灰） */
    .readonly-field ::v-deep .el-input__inner,
    .readonly-field ::v-deep .el-textarea__inner {
        background-color: #f5f7fa;
        color: #c0c4cc;
        cursor: not-allowed;
    }
    /* hover 时边框不再变蓝，避免产生可交互的错觉 */
    .readonly-field ::v-deep .el-input__inner:hover,
    .readonly-field ::v-deep .el-textarea__inner:hover {
        border-color: #dcdfe6;
    }
</style>
