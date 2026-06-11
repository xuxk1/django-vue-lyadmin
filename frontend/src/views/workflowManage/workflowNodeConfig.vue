<template>
    <div :class="{'ly-is-full':isFull}">
        <!-- 搜索区域 -->
        <div class="tableSelect" ref="tableSelect">
            <el-form :inline="true" :model="formInline" label-position="left">
                <el-form-item label="流程类型：">
                    <el-select v-model="formInline.workflow_type" placeholder="请选择流程类型" clearable @change="search" size="default" style="width:200px">
                        <el-option v-for="item in workflowTypes" :key="item.id" :label="item.name" :value="item.id"></el-option>
                    </el-select>
                </el-form-item>
                <el-form-item label="步骤名称：">
                    <el-input size="default" v-model.trim="formInline.step_name" maxlength="60" clearable placeholder="步骤名称" @change="search" style="width:150px"></el-input>
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
            <el-button type="primary" icon="Plus" @click="handleAdd" v-show="hasPermission(this.$route.name,'Create')" :disabled="!formInline.workflow_type">新增节点</el-button>
            <el-alert
                v-if="!formInline.workflow_type"
                title="请先选择流程类型"
                type="warning"
                :closable="false"
                show-icon
                style="display: inline-block; margin-left: 10px;"
            />
        </div>

        <!-- 表格区域 -->
        <div class="table">
            <el-table :height="'calc('+(tableHeight)+'px)'" border :data="tableData" ref="tableref" v-loading="loadingPage" style="width: 100%">
                <el-table-column type="index" width="60" align="center" label="序号">
                    <template #default="scope">
                        <span v-text="getIndex(scope.$index)"></span>
                    </template>
                </el-table-column>
                <el-table-column min-width="150" prop="workflow_type_name" label="流程类型" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="100" prop="step_order" label="步骤顺序" align="center"></el-table-column>
                <el-table-column min-width="150" prop="step_name" label="节点名称" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="120" prop="node_type_display" label="节点类型" align="center">
                    <template #default="scope">
                        <el-tag v-if="scope.row.node_type==1" type="primary" size="small">普通审批</el-tag>
                        <el-tag v-else-if="scope.row.node_type==2" type="info" size="small">抄送节点</el-tag>
                        <el-tag v-else-if="scope.row.node_type==3" type="warning" size="small">条件分支</el-tag>
                        <el-tag v-else-if="scope.row.node_type==4" type="success" size="small">并行网关</el-tag>
                        <el-tag v-else-if="scope.row.node_type==5" type="danger" size="small">结束节点</el-tag>
                    </template>
                </el-table-column>
                <el-table-column min-width="120" prop="approver_type_display" label="审批人类型" align="center"></el-table-column>
                <el-table-column label="审批人" min-width="200">
                    <template #default="scope">
                        <!-- 多级审批（组合） -->
                        <div v-if="scope.row.approver_type==6 && scope.row.multi_level_config && scope.row.multi_level_config.length > 0">
                            <div v-for="(level, index) in scope.row.multi_level_config" :key="index" style="margin-bottom: 5px; padding: 5px; background-color: #f5f7fa; border-radius: 3px;">
                                <strong style="color: #409EFF;">{{ level.name || '第' + (index+1) + '级' }}:</strong>
                                <span v-if="level.approver_type==1">角色: {{ getRoleName(level.approver_role) }}</span>
                                <span v-else-if="level.approver_type==2">部门: {{ getDeptName(level.approver_dept) }}</span>
                                <span v-else-if="level.approver_type==3">部门负责人</span>
                                <span v-else-if="level.approver_type==4">人员: {{ getUserNames(level.approver_users) }}</span>
                                <span v-else>未配置</span>
                            </div>
                        </div>
                        <!-- 普通审批 -->
                        <span v-else-if="scope.row.approver_type==1">{{ scope.row.approver_role_name || '-' }}</span>
                        <span v-else-if="scope.row.approver_type==2">{{ scope.row.approver_dept_name || '-' }}</span>
                        <span v-else-if="scope.row.approver_type==3">部门负责人</span>
                        <span v-else-if="scope.row.approver_type==4">
                            <span v-for="(user, index) in scope.row.approver_users_info" :key="index">
                                {{ user.name }}<span v-if="index < scope.row.approver_users_info.length - 1">, </span>
                            </span>
                        </span>
                        <span v-else>-</span>
                    </template>
                </el-table-column>
                <el-table-column label="审批模式" width="140" align="center">
                    <template #default="scope">
                        <el-tag v-if="scope.row.sign_mode==1" type="primary" size="small">或签</el-tag>
                        <el-tag v-else-if="scope.row.sign_mode==2" type="success" size="small">会签</el-tag>
                        <el-tag v-else-if="scope.row.sign_mode==3" type="warning" size="small">顺序审批</el-tag>
                    </template>
                </el-table-column>
                <el-table-column label="允许退回" width="100" align="center">
                    <template #default="scope">
                        <el-tag v-if="scope.row.allow_return" type="success" size="small">是</el-tag>
                        <el-tag v-else type="info" size="small">否</el-tag>
                    </template>
                </el-table-column>
                <el-table-column label="允许驳回" width="100" align="center">
                    <template #default="scope">
                        <el-tag v-if="scope.row.allow_reject" type="success" size="small">是</el-tag>
                        <el-tag v-else type="info" size="small">否</el-tag>
                    </template>
                </el-table-column>
                <el-table-column label="超时设置" width="150" align="center">
                    <template #default="scope">
                        <div v-if="scope.row.timeout_hours">
                            <div>{{ scope.row.timeout_hours }}小时</div>
                            <el-tag v-if="scope.row.auto_action==1" type="success" size="small">自动通过</el-tag>
                            <el-tag v-else-if="scope.row.auto_action==2" type="warning" size="small">自动退回</el-tag>
                            <el-tag v-else type="info" size="small">不处理</el-tag>
                        </div>
                        <span v-else>-</span>
                    </template>
                </el-table-column>
                <el-table-column label="通知方式" width="180" align="center">
                    <template #default="scope">
                        <el-tag v-if="scope.row.notify_email" type="info" size="small">邮件</el-tag>
                        <el-tag v-if="scope.row.notify_message" type="info" size="small">站内信</el-tag>
                        <el-tag v-if="scope.row.notify_sms" type="info" size="small">短信</el-tag>
                        <span v-if="!scope.row.notify_email && !scope.row.notify_message && !scope.row.notify_sms">-</span>
                    </template>
                </el-table-column>
                <el-table-column label="操作" fixed="right" width="180">
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
                        <span class="table-operate-btn" @click="handleEdit(scope.row)" v-show="hasPermission(this.$route.name,'Update')">编辑</span>
                        <span class="table-operate-btn" @click="handleDelete(scope.row)" v-show="hasPermission(this.$route.name,'Delete')" style="color: #F56C6C;">删除</span>
                    </template>
                </el-table-column>
            </el-table>
        </div>
        
        <!-- 分页 -->
        <Pagination v-bind:child-msg="pageparm" @callFather="callFather" :hide-on-single-page="false"></Pagination>

        <!-- 新增/编辑节点对话框 -->
        <el-dialog v-model="editDialogVisible" :title="editTitle" width="800px">
            <el-form :model="editForm" label-width="120px">
                <el-form-item label="流程类型" required>
                    <el-select v-model="editForm.workflow_type" placeholder="请选择流程类型" style="width: 100%" :disabled="!!editForm.id">
                        <el-option v-for="item in workflowTypes" :key="item.id" :label="item.name" :value="item.id"></el-option>
                    </el-select>
                </el-form-item>
                <el-form-item label="节点名称" required>
                    <el-input v-model="editForm.step_name" placeholder="请输入节点名称"></el-input>
                </el-form-item>
                <el-form-item label="步骤顺序" required>
                    <el-input-number v-model="editForm.step_order" :min="1" :max="99"></el-input-number>
                </el-form-item>
                
                <!-- 节点类型 -->
                <el-divider content-position="left">节点配置</el-divider>
                <el-form-item label="节点类型" required>
                    <el-select v-model="editForm.node_type" placeholder="请选择节点类型" style="width: 100%">
                        <el-option label="普通审批节点" :value="1"></el-option>
                        <el-option label="抄送节点" :value="2"></el-option>
                        <el-option label="条件分支节点" :value="3"></el-option>
                        <el-option label="并行网关节点" :value="4"></el-option>
                        <el-option label="结束节点" :value="5"></el-option>
                    </el-select>
                </el-form-item>
                
                <!-- 审批模式 -->
                <el-form-item label="审批模式" required v-if="editForm.node_type==1">
                    <el-radio-group v-model="editForm.approval_mode">
                        <el-radio :label="1">自动流转</el-radio>
                        <el-radio :label="2">手动配置</el-radio>
                    </el-radio-group>
                    <div style="margin-top: 5px; font-size: 12px; color: #909399;">
                        <span v-if="editForm.approval_mode==1">根据节点顺序自动流转到下一节点</span>
                        <span v-else>需要手动指定通过/驳回后的下一步骤</span>
                    </div>
                </el-form-item>
                
                <!-- 审批人配置（仅普通审批节点显示） -->
                <template v-if="editForm.node_type==1">
                    <el-form-item label="审批人类型" required>
                        <el-select v-model="editForm.approver_type" placeholder="请选择" style="width: 100%">
                            <el-option label="指定角色" :value="1"></el-option>
                            <el-option label="指定部门" :value="2"></el-option>
                            <el-option label="部门负责人" :value="3"></el-option>
                            <el-option label="指定人员" :value="4"></el-option>
                            <el-option label="申请人自选" :value="5"></el-option>
                            <el-option label="多级审批（组合）" :value="6"></el-option>
                        </el-select>
                    </el-form-item>
                    <el-form-item label="审批角色" v-if="editForm.approver_type==1" required>
                        <el-select v-model="editForm.approver_role" placeholder="请选择角色" style="width: 100%">
                            <el-option v-for="item in roles" :key="item.id" :label="item.name" :value="item.id"></el-option>
                        </el-select>
                    </el-form-item>
                    <el-form-item label="审批部门" v-if="editForm.approver_type==2 || editForm.approver_type==3" required>
                        <el-select v-model="editForm.approver_dept" placeholder="请选择部门" style="width: 100%">
                            <el-option v-for="item in depts" :key="item.id" :label="item.name" :value="item.id"></el-option>
                        </el-select>
                    </el-form-item>
                    <el-form-item label="审批人员" v-if="editForm.approver_type==4" required>
                        <el-select v-model="editForm.approver_users" multiple placeholder="请选择人员" style="width: 100%">
                            <el-option v-for="item in users" :key="item.id" :label="item.name" :value="item.id"></el-option>
                        </el-select>
                    </el-form-item>
                    
                    <!-- 多人审批模式 -->
                    <el-form-item label="审批模式">
                        <el-radio-group v-model="editForm.sign_mode">
                            <el-radio :label="1">或签（一人审批即可）</el-radio>
                            <el-radio :label="2">会签（所有人都需审批）</el-radio>
                            <el-radio :label="3">顺序审批（按顺序依次审批）</el-radio>
                        </el-radio-group>
                    </el-form-item>
                    
                    <!-- 多级审批（组合）配置 -->
                    <template v-if="editForm.approver_type==6">
                        <el-divider content-position="left">多级审批配置</el-divider>
                        <el-alert 
                            title="多级审批说明" 
                            type="info" 
                            :closable="false"
                            style="margin-bottom: 15px;"
                        >
                            <p style="margin: 0;">配置多个审批层级，每个层级可以设置不同的审批人类型和具体审批人。流程将按照层级顺序依次流转。</p>
                        </el-alert>
                        
                        <el-form-item label="审批层级列表">
                            <div style="width: 100%;">
                                <el-button 
                                    type="primary" 
                                    size="small" 
                                    icon="el-icon-plus"
                                    @click="addApprovalLevel"
                                    style="margin-bottom: 10px;"
                                >
                                    添加审批层级
                                </el-button>
                                
                                <div v-if="!editForm.multi_level_config || editForm.multi_level_config.length === 0" style="color: #909399; font-size: 13px; padding: 10px; background-color: #f5f7fa; border-radius: 4px;">
                                    <i class="el-icon-info"></i> 请添加至少一个审批层级
                                </div>
                                
                                <div v-for="(level, index) in editForm.multi_level_config" :key="index" style="border: 1px solid #dcdfe6; border-radius: 4px; padding: 15px; margin-bottom: 10px; background-color: #fafafa;">
                                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; padding-bottom: 10px; border-bottom: 1px dashed #dcdfe6;">
                                        <strong style="color: #409EFF; font-size: 14px;">第 {{ index + 1 }} 级审批</strong>
                                        <el-button 
                                            type="danger" 
                                            size="small" 
                                            icon="el-icon-delete"
                                            @click="removeApprovalLevel(index)"
                                            :disabled="editForm.multi_level_config.length <= 1"
                                        >
                                            删除
                                        </el-button>
                                    </div>
                                    
                                    <el-form-item label="层级名称" label-width="90px" style="margin-bottom: 12px;">
                                        <el-input v-model="level.name" placeholder="例如：部门经理审批" size="small"></el-input>
                                    </el-form-item>
                                    
                                    <el-form-item label="审批人类型" label-width="90px" style="margin-bottom: 12px;">
                                        <el-select v-model="level.approver_type" placeholder="请选择" size="small" style="width: 100%">
                                            <el-option label="指定角色" :value="1"></el-option>
                                            <el-option label="指定部门" :value="2"></el-option>
                                            <el-option label="部门负责人" :value="3"></el-option>
                                            <el-option label="指定人员" :value="4"></el-option>
                                        </el-select>
                                    </el-form-item>
                                    
                                    <el-form-item label="审批角色" label-width="90px" v-if="level.approver_type==1" style="margin-bottom: 12px;">
                                        <el-select v-model="level.approver_role" placeholder="请选择角色" size="small" style="width: 100%">
                                            <el-option v-for="item in roles" :key="item.id" :label="item.name" :value="item.id"></el-option>
                                        </el-select>
                                    </el-form-item>
                                    
                                    <el-form-item label="审批部门" label-width="90px" v-if="level.approver_type==2 || level.approver_type==3" style="margin-bottom: 12px;">
                                        <el-select v-model="level.approver_dept" placeholder="请选择部门" size="small" style="width: 100%">
                                            <el-option v-for="item in depts" :key="item.id" :label="item.name" :value="item.id"></el-option>
                                        </el-select>
                                    </el-form-item>
                                    
                                    <el-form-item label="审批人员" label-width="90px" v-if="level.approver_type==4" style="margin-bottom: 0;">
                                        <el-select v-model="level.approver_users" multiple placeholder="请选择人员" size="small" style="width: 100%">
                                            <el-option v-for="item in users" :key="item.id" :label="item.name" :value="item.id"></el-option>
                                        </el-select>
                                    </el-form-item>
                                </div>
                            </div>
                        </el-form-item>
                    </template>
                </template>
                
                <!-- 退回设置 -->
                <el-divider content-position="left">退回设置</el-divider>
                <el-form-item label="允许退回">
                    <el-switch v-model="editForm.allow_return"></el-switch>
                </el-form-item>
                <el-form-item label="允许驳回">
                    <el-switch v-model="editForm.allow_reject"></el-switch>
                </el-form-item>
                
                <!-- 超时设置 -->
                <el-divider content-position="left">超时设置</el-divider>
                <el-form-item label="超时时间(小时)">
                    <el-input-number v-model="editForm.timeout_hours" :min="1" :max="720" placeholder="不填则不限制"></el-input-number>
                </el-form-item>
                <el-form-item label="超时自动处理" v-if="editForm.timeout_hours">
                    <el-select v-model="editForm.auto_action" placeholder="请选择" style="width: 100%">
                        <el-option label="不自动处理" :value="0"></el-option>
                        <el-option label="自动通过" :value="1"></el-option>
                        <el-option label="自动退回" :value="2"></el-option>
                    </el-select>
                </el-form-item>
                
                <!-- 通知设置 -->
                <el-divider content-position="left">通知设置</el-divider>
                <el-form-item label="邮件通知">
                    <el-switch v-model="editForm.notify_email"></el-switch>
                </el-form-item>
                <el-form-item label="站内信通知">
                    <el-switch v-model="editForm.notify_message"></el-switch>
                </el-form-item>
                <el-form-item label="短信通知">
                    <el-switch v-model="editForm.notify_sms"></el-switch>
                </el-form-item>
                
                <!-- 节点说明 -->
                <el-form-item label="节点说明">
                    <el-input v-model="editForm.description" type="textarea" :rows="2" placeholder="请输入节点说明"></el-input>
                </el-form-item>
            </el-form>
            <template #footer>
                <el-button @click="editDialogVisible = false">取消</el-button>
                <el-button type="primary" @click="handleEditSubmit" :loading="submitLoading">确定</el-button>
            </template>
        </el-dialog>
    </div>
</template>

<script>
    import Pagination from "@/components/Pagination";
    import {getTableHeight} from "@/utils/util";
    import {workflowStep, workflowStepAdd, workflowStepUpdate, workflowStepDelete, workflowType, apiSystemRole, apiSystemDept, apiSystemUser} from '@/api/api';
    
    export default {
        name: "workflowNodeConfig",
        components:{
            Pagination,
        },
        data() {
            return {
                isFull:false,
                tableHeight:500,
                loadingPage:false,
                submitLoading: false,
                editDialogVisible: false,
                editTitle: '新增节点',
                workflowTypes: [],
                roles: [],
                depts: [],
                users: [],
                formInline:{
                    page: 1,
                    limit: 10,
                    workflow_type: '',
                    step_name: ''
                },
                pageparm: {
                    page: 1,
                    limit: 10,
                    total: 0
                },
                editForm: {
                    id: '',
                    workflow_type: '',
                    step_name: '',
                    step_order: 1,
                    node_type: 1,  // 默认为普通审批节点
                    approval_mode: 1,  // 默认为自动流转
                    approver_type: 1,
                    approver_role: '',
                    approver_dept: '',
                    approver_users: [],
                    sign_mode: 1,  // 默认为或签
                    allow_return: true,
                    allow_reject: false,
                    timeout_hours: null,  // 超时时间
                    auto_action: 0,  // 不自动处理
                    notify_email: true,  // 邮件通知
                    notify_message: true,  // 站内信通知
                    notify_sms: false,  // 短信通知
                    description: '',  // 节点说明
                    multi_level_config: []  // 多级审批配置
                },
                tableData:[]
            }
        },
        created() {
            this.getWorkflowTypes()
            this.getRoles()
            this.getDepts()
            this.getUsers()
            this.getData()
        },
        mounted(){
            this.getTheTableHeight()
            window.addEventListener('resize',this.getTheTableHeight)
        },
        beforeDestroy(){
            window.removeEventListener('resize',this.getTheTableHeight)
        },
        methods:{
            getIndex($index){
                return (this.formInline.page - 1) * this.formInline.limit + $index + 1
            },
            search(){
                this.formInline.page = 1
                this.getData()
            },
            getData(){
                let vm = this
                vm.loadingPage = true
                workflowStep(vm.formInline).then(res => {
                    vm.loadingPage = false
                    if(res.code === 2000) {
                        vm.tableData = res.data.data || []
                        vm.pageparm.total = res.data.total || 0
                    }
                }).catch(err => {
                    vm.loadingPage = false
                })
            },
            getWorkflowTypes(){
                let vm = this
                workflowType({page: 1, limit: 1000, status: 1}).then(res => {
                    if(res.code === 2000) {
                        vm.workflowTypes = res.data.data || []
                    }
                })
            },
            getRoles(){
                let vm = this
                apiSystemRole({page: 1, limit: 1000}).then(res => {
                    if(res.code === 2000) {
                        vm.roles = res.data.data || []
                    }
                })
            },
            getDepts(){
                let vm = this
                apiSystemDept({page: 1, limit: 1000}).then(res => {
                    if(res.code === 2000) {
                        vm.depts = res.data.data || []
                    }
                })
            },
            getUsers(){
                let vm = this
                apiSystemUser({page: 1, limit: 1000}).then(res => {
                    if(res.code === 2000) {
                        vm.users = res.data.data || []
                    }
                })
            },
            handleReset(){
                this.formInline = {
                    page: 1,
                    limit: 10,
                    workflow_type: this.formInline.workflow_type,
                    step_name: ''
                }
                this.getData()
            },
            callFather(parm){
                this.formInline.page = parm.page
                this.formInline.limit = parm.limit
                this.getData()
            },
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
            handleAdd(){
                if(!this.formInline.workflow_type) {
                    this.$message.warning('请先选择流程类型')
                    return
                }
                this.editForm = {
                    id: '',
                    workflow_type: this.formInline.workflow_type,
                    step_name: '',
                    step_order: this.tableData.length + 1,
                    node_type: 1,  // 默认为普通审批节点
                    approver_type: 1,
                    approver_role: '',
                    approver_dept: '',
                    approver_users: [],
                    sign_mode: 1,  // 默认为或签
                    allow_return: true,
                    allow_reject: false,
                    timeout_hours: null,  // 超时时间
                    auto_action: 0,  // 不自动处理
                    notify_email: true,  // 邮件通知
                    notify_message: true,  // 站内信通知
                    notify_sms: false,  // 短信通知
                    description: '',  // 节点说明
                    multi_level_config: []  // 多级审批配置
                }
                this.editTitle = '新增节点'
                this.editDialogVisible = true
            },
            handleEdit(row){
                this.editForm = {...row}
                // 确保数组字段正确复制
                if(row.approver_users && Array.isArray(row.approver_users)) {
                    this.editForm.approver_users = [...row.approver_users]
                }
                // 确保多级审批配置正确复制
                if(row.multi_level_config && Array.isArray(row.multi_level_config)) {
                    this.editForm.multi_level_config = JSON.parse(JSON.stringify(row.multi_level_config))
                } else {
                    this.editForm.multi_level_config = []
                }
                this.editTitle = '编辑节点'
                this.editDialogVisible = true
            },
            handleEditSubmit(){
                if(!this.editForm.step_name) {
                    this.$message.warning('请填写节点名称')
                    return
                }
                
                // 验证多级审批配置
                if(this.editForm.approver_type == 6) {
                    if(!this.editForm.multi_level_config || this.editForm.multi_level_config.length === 0) {
                        this.$message.warning('请至少添加一个审批层级')
                        return
                    }
                    // 验证每个层级的配置
                    for(let i = 0; i < this.editForm.multi_level_config.length; i++) {
                        const level = this.editForm.multi_level_config[i]
                        if(!level.name) {
                            this.$message.warning(`请填写第 ${i + 1} 级的层级名称`)
                            return
                        }
                        if(!level.approver_type) {
                            this.$message.warning(`请选择第 ${i + 1} 级的审批人类型`)
                            return
                        }
                        if(level.approver_type == 1 && !level.approver_role) {
                            this.$message.warning(`请选择第 ${i + 1} 级的审批角色`)
                            return
                        }
                        if((level.approver_type == 2 || level.approver_type == 3) && !level.approver_dept) {
                            this.$message.warning(`请选择第 ${i + 1} 级的审批部门`)
                            return
                        }
                        if(level.approver_type == 4 && (!level.approver_users || level.approver_users.length === 0)) {
                            this.$message.warning(`请选择第 ${i + 1} 级的审批人员`)
                            return
                        }
                    }
                }
                
                let vm = this
                vm.submitLoading = true
                let apiCall = vm.editForm.id ? workflowStepUpdate(vm.editForm) : workflowStepAdd(vm.editForm)
                apiCall.then(res => {
                    vm.submitLoading = false
                    if(res.code === 2000) {
                        vm.$message.success(vm.editForm.id ? '编辑成功' : '新增成功')
                        vm.editDialogVisible = false
                        vm.getData()
                    } else {
                        vm.$message.error(res.msg || '操作失败')
                    }
                }).catch(err => {
                    vm.submitLoading = false
                    vm.$message.error('操作失败')
                })
            },
            handleDelete(row){
                let vm = this
                vm.$confirm('确认要删除该节点吗？', '提示', {
                    confirmButtonText: '确定',
                    cancelButtonText: '取消',
                    type: 'warning'
                }).then(() => {
                    vm.loadingPage = true
                    workflowStepDelete({id: row.id}).then(res => {
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
            // 添加审批层级
            addApprovalLevel() {
                if(!this.editForm.multi_level_config) {
                    this.editForm.multi_level_config = []
                }
                this.editForm.multi_level_config.push({
                    name: '',
                    approver_type: 1,
                    approver_role: '',
                    approver_dept: '',
                    approver_users: []
                })
            },
            // 删除审批层级
            removeApprovalLevel(index) {
                if(this.editForm.multi_level_config && this.editForm.multi_level_config.length > 1) {
                    this.editForm.multi_level_config.splice(index, 1)
                }
            },
            // 辅助方法：根据ID获取角色名称
            getRoleName(roleId) {
                if(!roleId) return '未配置'
                const role = this.roles.find(r => r.id === roleId)
                return role ? role.name : '角色'
            },
            // 辅助方法：根据ID获取部门名称
            getDeptName(deptId) {
                if(!deptId) return '未配置'
                const dept = this.depts.find(d => d.id === deptId)
                return dept ? dept.name : '部门'
            },
            // 辅助方法：根据ID数组获取人员名称列表
            getUserNames(userIds) {
                if(!userIds || userIds.length === 0) return '未配置'
                const names = userIds.map(id => {
                    const user = this.users.find(u => u.id === id)
                    return user ? user.name : ''
                }).filter(name => name !== '')
                return names.join(', ') || '人员'
            }
        }
    }
</script>

<style scoped>
</style>
