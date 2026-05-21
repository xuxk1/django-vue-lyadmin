<template>
    <div :class="{'ly-is-full':isFull}">
        <!-- 搜索区域 -->
        <div class="tableSelect" ref="tableSelect">
            <el-form :inline="true" :model="formInline" label-position="left">
                <el-form-item label="流程名称：">
                    <el-input size="default" v-model.trim="formInline.name" maxlength="60" clearable placeholder="流程名称" @change="search" style="width:150px"></el-input>
                </el-form-item>
                <el-form-item label="流程编码：">
                    <el-input size="default" v-model.trim="formInline.code" maxlength="60" clearable placeholder="流程编码" @change="search" style="width:150px"></el-input>
                </el-form-item>
                <el-form-item label="状态：">
                    <el-select v-model="formInline.status" placeholder="请选择" clearable @change="search" size="default" style="width:120px">
                        <el-option label="启用" :value="1"></el-option>
                        <el-option label="禁用" :value="0"></el-option>
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
            <el-button type="primary" icon="Plus" @click="handleAdd" v-show="hasPermission(this.$route.name,'Create')">新增流程类型</el-button>
        </div>

        <!-- 表格区域 -->
        <div class="table">
            <el-table :height="'calc('+(tableHeight)+'px)'" border :data="tableData" ref="tableref" v-loading="loadingPage" style="width: 100%">
                <el-table-column type="index" width="60" align="center" label="序号">
                    <template #default="scope">
                        <span v-text="getIndex(scope.$index)"></span>
                    </template>
                </el-table-column>
                <el-table-column min-width="150" prop="name" label="流程名称" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="120" prop="code" label="流程编码" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="200" prop="description" label="流程描述" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="100" prop="steps_count" label="步骤数" align="center"></el-table-column>
                <el-table-column min-width="100" label="状态">
                    <template #default="scope">
                        <el-tag v-if="scope.row.status==1" type="success">启用</el-tag>
                        <el-tag v-else type="info">禁用</el-tag>
                    </template>
                </el-table-column>
                <el-table-column min-width="80" prop="sort" label="排序" align="center"></el-table-column>
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
                        <span class="table-operate-btn" @click="handleEdit(scope.row)" v-show="hasPermission(this.$route.name,'Update')">编辑</span>
                        <span class="table-operate-btn" @click="handleConfigSteps(scope.row)" v-show="hasPermission(this.$route.name,'ConfigSteps')">配置步骤</span>
                        <span class="table-operate-btn" @click="handleConfigCC(scope.row)" v-show="hasPermission(this.$route.name,'ConfigCC')">配置抄送</span>
                        <span class="table-operate-btn" @click="handleDelete(scope.row)" v-show="hasPermission(this.$route.name,'Delete')">删除</span>
                    </template>
                </el-table-column>
            </el-table>
        </div>
        
        <!-- 分页 -->
        <Pagination v-bind:child-msg="pageparm" @callFather="callFather" :hide-on-single-page="false"></Pagination>

        <!-- 新增/编辑对话框 -->
        <el-dialog v-model="editDialogVisible" :title="editTitle" width="600px">
            <el-form :model="editForm" label-width="100px">
                <el-form-item label="流程名称" required>
                    <el-input v-model="editForm.name" placeholder="请输入流程名称"></el-input>
                </el-form-item>
                <el-form-item label="流程编码" required>
                    <el-input v-model="editForm.code" placeholder="请输入流程编码（英文）"></el-input>
                </el-form-item>
                <el-form-item label="流程描述">
                    <el-input v-model="editForm.description" type="textarea" :rows="3" placeholder="请输入流程描述"></el-input>
                </el-form-item>
                <el-form-item label="图标">
                    <el-input v-model="editForm.icon" placeholder="请输入图标class"></el-input>
                </el-form-item>
                <el-form-item label="状态">
                    <el-radio-group v-model="editForm.status">
                        <el-radio :label="1">启用</el-radio>
                        <el-radio :label="0">禁用</el-radio>
                    </el-radio-group>
                </el-form-item>
                <el-form-item label="排序">
                    <el-input-number v-model="editForm.sort" :min="1" :max="999"></el-input-number>
                </el-form-item>
            </el-form>
            <template #footer>
                <el-button @click="editDialogVisible = false">取消</el-button>
                <el-button type="primary" @click="handleEditSubmit" :loading="submitLoading">确定</el-button>
            </template>
        </el-dialog>

        <!-- 配置步骤对话框 -->
        <el-dialog v-model="stepDialogVisible" title="配置审批步骤" width="900px">
            <div style="margin-bottom: 10px;">
                <el-button type="primary" icon="Plus" @click="handleAddStep">新增步骤</el-button>
            </div>
            <el-table :data="stepsData" border style="width: 100%">
                <el-table-column prop="step_order" label="步骤顺序" width="100" align="center"></el-table-column>
                <el-table-column prop="step_name" label="步骤名称" width="150"></el-table-column>
                <el-table-column prop="approver_type_display" label="审批人类型" width="120"></el-table-column>
                <el-table-column label="审批人" min-width="200">
                    <template #default="scope">
                        <span v-if="scope.row.approver_type==1">{{ scope.row.approver_role_name || '-' }}</span>
                        <span v-else-if="scope.row.approver_type==2">{{ scope.row.approver_dept_name || '-' }}</span>
                        <span v-else-if="scope.row.approver_type==3">部门负责人</span>
                        <span v-else-if="scope.row.approver_type==4">
                            <span v-for="(user, index) in scope.row.approver_users_info" :key="index">
                                {{ user.name }}<span v-if="index < scope.row.approver_users_info.length - 1">, </span>
                            </span>
                        </span>
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
                <el-table-column label="操作" width="150" fixed="right">
                    <template #default="scope">
                        <span class="table-operate-btn" @click="handleEditStep(scope.row)">编辑</span>
                        <span class="table-operate-btn" @click="handleDeleteStep(scope.row)" style="color: #F56C6C;">删除</span>
                    </template>
                </el-table-column>
            </el-table>
            <template #footer>
                <el-button @click="stepDialogVisible = false">关闭</el-button>
            </template>
        </el-dialog>

        <!-- 新增/编辑步骤对话框 -->
        <el-dialog v-model="stepEditDialogVisible" :title="stepEditTitle" width="600px">
            <el-form :model="stepForm" label-width="120px">
                <el-form-item label="步骤名称" required>
                    <el-input v-model="stepForm.step_name" placeholder="请输入步骤名称"></el-input>
                </el-form-item>
                <el-form-item label="步骤顺序" required>
                    <el-input-number v-model="stepForm.step_order" :min="1" :max="99"></el-input-number>
                </el-form-item>
                <el-form-item label="审批人类型" required>
                    <el-select v-model="stepForm.approver_type" placeholder="请选择" style="width: 100%">
                        <el-option label="指定角色" :value="1"></el-option>
                        <el-option label="指定部门" :value="2"></el-option>
                        <el-option label="部门负责人" :value="3"></el-option>
                        <el-option label="指定人员" :value="4"></el-option>
                    </el-select>
                </el-form-item>
                <el-form-item label="审批角色" v-if="stepForm.approver_type==1" required>
                    <el-select v-model="stepForm.approver_role" placeholder="请选择角色" style="width: 100%">
                        <el-option v-for="item in roles" :key="item.id" :label="item.name" :value="item.id"></el-option>
                    </el-select>
                </el-form-item>
                <el-form-item label="审批部门" v-if="stepForm.approver_type==2 || stepForm.approver_type==3" required>
                    <el-select v-model="stepForm.approver_dept" placeholder="请选择部门" style="width: 100%">
                        <el-option v-for="item in depts" :key="item.id" :label="item.name" :value="item.id"></el-option>
                    </el-select>
                </el-form-item>
                <el-form-item label="审批人员" v-if="stepForm.approver_type==4" required>
                    <el-select v-model="stepForm.approver_users" multiple placeholder="请选择人员" style="width: 100%">
                        <el-option v-for="item in users" :key="item.id" :label="item.name" :value="item.id"></el-option>
                    </el-select>
                </el-form-item>
                <el-form-item label="允许退回">
                    <el-switch v-model="stepForm.allow_return"></el-switch>
                </el-form-item>
                <el-form-item label="允许驳回">
                    <el-switch v-model="stepForm.allow_reject"></el-switch>
                </el-form-item>
            </el-form>
            <template #footer>
                <el-button @click="stepEditDialogVisible = false">取消</el-button>
                <el-button type="primary" @click="handleStepSubmit" :loading="stepSubmitLoading">确定</el-button>
            </template>
        </el-dialog>

        <!-- 配置抄送对话框 -->
        <el-dialog v-model="ccDialogVisible" title="配置抄送人员" width="900px">
            <div style="margin-bottom: 10px;">
                <el-button type="primary" icon="Plus" @click="handleAddCC">新增抄送</el-button>
            </div>
            <el-table :data="ccData" border style="width: 100%">
                <el-table-column prop="cc_type_display" label="抄送人类型" width="120"></el-table-column>
                <el-table-column label="抄送人员/角色/部门" min-width="200">
                    <template #default="scope">
                        <span v-if="scope.row.cc_type==1">{{ scope.row.cc_role_name || '-' }}</span>
                        <span v-else-if="scope.row.cc_type==2">{{ scope.row.cc_dept_name || '-' }}</span>
                        <span v-else-if="scope.row.cc_type==3">部门负责人</span>
                        <span v-else-if="scope.row.cc_type==4">
                            <span v-for="(user, index) in scope.row.cc_users_info" :key="index">
                                {{ user.name }}<span v-if="index < scope.row.cc_users_info.length - 1">, </span>
                            </span>
                        </span>
                    </template>
                </el-table-column>
                <el-table-column label="可审批" width="100" align="center">
                    <template #default="scope">
                        <el-tag v-if="scope.row.can_approve" type="success" size="small">是</el-tag>
                        <el-tag v-else type="info" size="small">否</el-tag>
                    </template>
                </el-table-column>
                <el-table-column label="操作" width="150" fixed="right">
                    <template #default="scope">
                        <span class="table-operate-btn" @click="handleEditCC(scope.row)">编辑</span>
                        <span class="table-operate-btn" @click="handleDeleteCC(scope.row)" style="color: #F56C6C;">删除</span>
                    </template>
                </el-table-column>
            </el-table>
            <template #footer>
                <el-button @click="ccDialogVisible = false">关闭</el-button>
            </template>
        </el-dialog>

        <!-- 新增/编辑抄送对话框 -->
        <el-dialog v-model="ccEditDialogVisible" :title="ccEditTitle" width="600px">
            <el-form :model="ccForm" label-width="120px">
                <el-form-item label="抄送人类型" required>
                    <el-select v-model="ccForm.cc_type" placeholder="请选择" style="width: 100%">
                        <el-option label="指定角色" :value="1"></el-option>
                        <el-option label="指定部门" :value="2"></el-option>
                        <el-option label="部门负责人" :value="3"></el-option>
                        <el-option label="指定人员" :value="4"></el-option>
                    </el-select>
                </el-form-item>
                <el-form-item label="抄送角色" v-if="ccForm.cc_type==1" required>
                    <el-select v-model="ccForm.cc_role" placeholder="请选择角色" style="width: 100%">
                        <el-option v-for="item in roles" :key="item.id" :label="item.name" :value="item.id"></el-option>
                    </el-select>
                </el-form-item>
                <el-form-item label="抄送部门" v-if="ccForm.cc_type==2 || ccForm.cc_type==3" required>
                    <el-select v-model="ccForm.cc_dept" placeholder="请选择部门" style="width: 100%">
                        <el-option v-for="item in depts" :key="item.id" :label="item.name" :value="item.id"></el-option>
                    </el-select>
                </el-form-item>
                <el-form-item label="抄送人员" v-if="ccForm.cc_type==4" required>
                    <el-select v-model="ccForm.cc_users" multiple placeholder="请选择人员" style="width: 100%">
                        <el-option v-for="item in users" :key="item.id" :label="item.name" :value="item.id"></el-option>
                    </el-select>
                </el-form-item>
                <el-form-item label="可审批">
                    <el-switch v-model="ccForm.can_approve"></el-switch>
                </el-form-item>
            </el-form>
            <template #footer>
                <el-button @click="ccEditDialogVisible = false">取消</el-button>
                <el-button type="primary" @click="handleCCSubmit" :loading="ccSubmitLoading">确定</el-button>
            </template>
        </el-dialog>
    </div>
</template>

<script>
    import Pagination from "@/components/Pagination";
    import {getTableHeight} from "@/utils/util";
    import {workflowType, workflowTypeAdd, workflowTypeUpdate, workflowTypeDelete, workflowStep, workflowStepAdd, workflowStepUpdate, workflowStepDelete, workflowCC, workflowCCAdd, workflowCCUpdate, workflowCCDelete, apiSystemRole, apiSystemDept, apiSystemUser} from '@/api/api';
    
    export default {
        name: "workflowConfig",
        components:{
            Pagination,
        },
        data() {
            return {
                isFull:false,
                tableHeight:500,
                loadingPage:false,
                submitLoading: false,
                stepSubmitLoading: false,
                ccSubmitLoading: false,
                editDialogVisible: false,
                stepDialogVisible: false,
                stepEditDialogVisible: false,
                ccDialogVisible: false,
                ccEditDialogVisible: false,
                editTitle: '新增流程类型',
                stepEditTitle: '新增步骤',
                ccEditTitle: '新增抄送',
                currentWorkflowType: null,
                stepsData: [],
                ccData: [],
                roles: [],
                depts: [],
                users: [],
                formInline:{
                    page: 1,
                    limit: 10,
                    name:'',
                    code:'',
                    status:''
                },
                pageparm: {
                    page: 1,
                    limit: 10,
                    total: 0
                },
                editForm: {
                    id: '',
                    name: '',
                    code: '',
                    description: '',
                    icon: '',
                    status: 1,
                    sort: 1
                },
                stepForm: {
                    id: '',
                    workflow_type: '',
                    step_name: '',
                    step_order: 1,
                    approver_type: 1,
                    approver_role: '',
                    approver_dept: '',
                    approver_users: [],
                    allow_return: true,
                    allow_reject: false
                },
                ccForm: {
                    id: '',
                    workflow_type: '',
                    cc_type: 1,
                    cc_role: '',
                    cc_dept: '',
                    cc_users: [],
                    can_approve: true
                },
                tableData:[]
            }
        },
        created() {
            this.getData()
            this.getRoles()
            this.getDepts()
            this.getUsers()
        },
        methods:{
            getIndex($index) {
                return (this.pageparm.page - 1) * this.pageparm.limit + $index + 1
            },
            getData(){
                let vm = this
                vm.loadingPage = true
                workflowType(vm.formInline).then(res => {
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
            search(){
                this.formInline.page = 1
                this.getData()
            },
            handleReset(){
                this.formInline = {
                    page: 1,
                    limit: 10,
                    name:'',
                    code:'',
                    status:''
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
                this.editForm = {
                    id: '',
                    name: '',
                    code: '',
                    description: '',
                    icon: '',
                    status: 1,
                    sort: 1
                }
                this.editTitle = '新增流程类型'
                this.editDialogVisible = true
            },
            handleEdit(row){
                this.editForm = {...row}
                this.editTitle = '编辑流程类型'
                this.editDialogVisible = true
            },
            handleEditSubmit(){
                if(!this.editForm.name || !this.editForm.code) {
                    this.$message.warning('请填写必填项')
                    return
                }
                
                let vm = this
                vm.submitLoading = true
                let apiCall = vm.editForm.id ? workflowTypeUpdate(vm.editForm) : workflowTypeAdd(vm.editForm)
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
                vm.$confirm('确认要删除该流程类型吗？', '提示', {
                    confirmButtonText: '确定',
                    cancelButtonText: '取消',
                    type: 'warning'
                }).then(() => {
                    vm.loadingPage = true
                    workflowTypeDelete({id: row.id}).then(res => {
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
            handleConfigSteps(row){
                this.currentWorkflowType = row
                this.getSteps(row.id)
                this.stepDialogVisible = true
            },
            getSteps(workflowTypeId){
                let vm = this
                workflowStep({workflow_type: workflowTypeId}).then(res => {
                    if(res.code === 2000) {
                        vm.stepsData = res.data.data || []
                    }
                })
            },
            handleAddStep(){
                this.stepForm = {
                    id: '',
                    workflow_type: this.currentWorkflowType.id,
                    step_name: '',
                    step_order: this.stepsData.length + 1,
                    approver_type: 1,
                    approver_role: '',
                    approver_dept: '',
                    approver_users: [],
                    allow_return: true,
                    allow_reject: false
                }
                this.stepEditTitle = '新增步骤'
                this.stepEditDialogVisible = true
            },
            handleEditStep(row){
                this.stepForm = {...row}
                this.stepEditTitle = '编辑步骤'
                this.stepEditDialogVisible = true
            },
            handleStepSubmit(){
                if(!this.stepForm.step_name) {
                    this.$message.warning('请填写步骤名称')
                    return
                }
                
                let vm = this
                vm.stepSubmitLoading = true
                let apiCall = vm.stepForm.id ? workflowStepUpdate(vm.stepForm) : workflowStepAdd(vm.stepForm)
                apiCall.then(res => {
                    vm.stepSubmitLoading = false
                    if(res.code === 2000) {
                        vm.$message.success(vm.stepForm.id ? '编辑成功' : '新增成功')
                        vm.stepEditDialogVisible = false
                        vm.getSteps(vm.currentWorkflowType.id)
                    } else {
                        vm.$message.error(res.msg || '操作失败')
                    }
                }).catch(err => {
                    vm.stepSubmitLoading = false
                    vm.$message.error('操作失败')
                })
            },
            handleDeleteStep(row){
                let vm = this
                vm.$confirm('确认要删除该步骤吗？', '提示', {
                    confirmButtonText: '确定',
                    cancelButtonText: '取消',
                    type: 'warning'
                }).then(() => {
                    vm.loadingPage = true
                    workflowStepDelete({id: row.id}).then(res => {
                        vm.loadingPage = false
                        if(res.code === 2000) {
                            vm.$message.success('删除成功')
                            vm.getSteps(vm.currentWorkflowType.id)
                        } else {
                            vm.$message.error(res.msg || '删除失败')
                        }
                    }).catch(err => {
                        vm.loadingPage = false
                        vm.$message.error('删除失败')
                    })
                }).catch(() => {})
            },
            handleConfigCC(row){
                this.currentWorkflowType = row
                this.getCC(row.id)
                this.ccDialogVisible = true
            },
            getCC(workflowTypeId){
                let vm = this
                workflowCC({workflow_type: workflowTypeId}).then(res => {
                    if(res.code === 2000) {
                        vm.ccData = res.data.data || []
                    }
                })
            },
            handleAddCC(){
                this.ccForm = {
                    id: '',
                    workflow_type: this.currentWorkflowType.id,
                    cc_type: 1,
                    cc_role: '',
                    cc_dept: '',
                    cc_users: [],
                    can_approve: true
                }
                this.ccEditTitle = '新增抄送'
                this.ccEditDialogVisible = true
            },
            handleEditCC(row){
                this.ccForm = {...row}
                this.ccEditTitle = '编辑抄送'
                this.ccEditDialogVisible = true
            },
            handleCCSubmit(){
                let vm = this
                vm.ccSubmitLoading = true
                let apiCall = vm.ccForm.id ? workflowCCUpdate(vm.ccForm) : workflowCCAdd(vm.ccForm)
                apiCall.then(res => {
                    vm.ccSubmitLoading = false
                    if(res.code === 2000) {
                        vm.$message.success(vm.ccForm.id ? '编辑成功' : '新增成功')
                        vm.ccEditDialogVisible = false
                        vm.getCC(vm.currentWorkflowType.id)
                    } else {
                        vm.$message.error(res.msg || '操作失败')
                    }
                }).catch(err => {
                    vm.ccSubmitLoading = false
                    vm.$message.error('操作失败')
                })
            },
            handleDeleteCC(row){
                let vm = this
                vm.$confirm('确认要删除该抄送配置吗？', '提示', {
                    confirmButtonText: '确定',
                    cancelButtonText: '取消',
                    type: 'warning'
                }).then(() => {
                    vm.loadingPage = true
                    workflowCCDelete({id: row.id}).then(res => {
                        vm.loadingPage = false
                        if(res.code === 2000) {
                            vm.$message.success('删除成功')
                            vm.getCC(vm.currentWorkflowType.id)
                        } else {
                            vm.$message.error(res.msg || '删除失败')
                        }
                    }).catch(err => {
                        vm.loadingPage = false
                        vm.$message.error('删除失败')
                    })
                }).catch(() => {})
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
