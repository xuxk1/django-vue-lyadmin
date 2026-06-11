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
        <el-dialog v-model="editDialogVisible" :title="editTitle" width="900px">
            <el-form :model="editForm" label-width="100px">
                <!-- 基本信息区域 -->
                <div style="margin-bottom: 20px; padding-bottom: 20px; border-bottom: 1px solid #EBEEF5;">
                    <h4 style="margin-bottom: 15px;">基本信息</h4>
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
                </div>
                
                <!-- 表单配置区域 -->
                <div>
                    <h4 style="margin-bottom: 15px;">流程内容（表单配置）</h4>
                    <div style="margin-bottom: 10px;">
                        <el-button type="primary" icon="Plus" @click="handleAddFormField">添加字段</el-button>
                        <el-alert
                            title="提示：配置发起流程时需要填写的表单字段"
                            type="info"
                            :closable="false"
                            show-icon
                            style="margin-top: 10px;"
                        />
                    </div>
                    <el-table :data="formFieldsData" border style="width: 100%">
                        <el-table-column prop="label" label="字段标签" width="150"></el-table-column>
                        <el-table-column prop="field" label="字段名" width="150"></el-table-column>
                        <el-table-column prop="type" label="字段类型" width="120">
                            <template #default="scope">
                                <el-tag size="small">{{ getFieldTypeLabel(scope.row.type) }}</el-tag>
                            </template>
                        </el-table-column>
                        <el-table-column prop="required" label="是否必填" width="100" align="center">
                            <template #default="scope">
                                <el-tag v-if="scope.row.required" type="success" size="small">是</el-tag>
                                <el-tag v-else type="info" size="small">否</el-tag>
                            </template>
                        </el-table-column>
                        <el-table-column prop="placeholder" label="占位符" min-width="150" show-overflow-tooltip></el-table-column>
                        <el-table-column label="操作" width="150" fixed="right">
                            <template #default="scope">
                                <span class="table-operate-btn" @click="handleEditFormField(scope.row, scope.$index)">编辑</span>
                                <span class="table-operate-btn" @click="handleDeleteFormField(scope.$index)" style="color: #F56C6C;">删除</span>
                            </template>
                        </el-table-column>
                    </el-table>
                </div>
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
                <el-table-column label="审批模式" width="100" align="center">
                    <template #default="scope">
                        <el-tag v-if="scope.row.sign_mode==1" type="primary" size="small">或签</el-tag>
                        <el-tag v-else type="success" size="small">会签</el-tag>
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
                <el-table-column label="超时设置" width="120" align="center">
                    <template #default="scope">
                        <span v-if="scope.row.timeout_hours">
                            {{ scope.row.timeout_hours }}小时
                            <el-tag v-if="scope.row.auto_action==1" type="success" size="small">自动通过</el-tag>
                            <el-tag v-else-if="scope.row.auto_action==2" type="warning" size="small">自动退回</el-tag>
                        </span>
                        <span v-else>-</span>
                    </template>
                </el-table-column>
                <el-table-column label="通知方式" width="150" align="center">
                    <template #default="scope">
                        <el-tag v-if="scope.row.notify_email" type="info" size="small">邮件</el-tag>
                        <el-tag v-if="scope.row.notify_message" type="info" size="small">站内信</el-tag>
                        <el-tag v-if="scope.row.notify_sms" type="info" size="small">短信</el-tag>
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
        <el-dialog v-model="stepEditDialogVisible" :title="stepEditTitle" width="700px">
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
                
                <!-- 多人审批模式 -->
                <el-form-item label="审批模式">
                    <el-radio-group v-model="stepForm.sign_mode">
                        <el-radio :label="1">或签（一人审批即可）</el-radio>
                        <el-radio :label="2">会签（所有人都需审批）</el-radio>
                    </el-radio-group>
                </el-form-item>
                
                <!-- 退回设置 -->
                <el-form-item label="允许退回">
                    <el-switch v-model="stepForm.allow_return"></el-switch>
                </el-form-item>
                <el-form-item label="允许驳回">
                    <el-switch v-model="stepForm.allow_reject"></el-switch>
                </el-form-item>
                
                <!-- 超时设置 -->
                <el-divider content-position="left">超时设置</el-divider>
                <el-form-item label="超时时间(小时)">
                    <el-input-number v-model="stepForm.timeout_hours" :min="1" :max="720" placeholder="不填则不限制"></el-input-number>
                </el-form-item>
                <el-form-item label="超时自动处理" v-if="stepForm.timeout_hours">
                    <el-select v-model="stepForm.auto_action" placeholder="请选择" style="width: 100%">
                        <el-option label="不自动处理" :value="0"></el-option>
                        <el-option label="自动通过" :value="1"></el-option>
                        <el-option label="自动退回" :value="2"></el-option>
                    </el-select>
                </el-form-item>
                
                <!-- 通知设置 -->
                <el-divider content-position="left">通知设置</el-divider>
                <el-form-item label="邮件通知">
                    <el-switch v-model="stepForm.notify_email"></el-switch>
                </el-form-item>
                <el-form-item label="站内信通知">
                    <el-switch v-model="stepForm.notify_message"></el-switch>
                </el-form-item>
                <el-form-item label="短信通知">
                    <el-switch v-model="stepForm.notify_sms"></el-switch>
                </el-form-item>
                
                <!-- 节点说明 -->
                <el-form-item label="节点说明">
                    <el-input v-model="stepForm.description" type="textarea" :rows="2" placeholder="请输入节点说明"></el-input>
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

        <!-- 新增/编辑表单字段对话框 -->
        <el-dialog v-model="fieldEditDialogVisible" :title="fieldEditTitle" width="600px">
            <el-form :model="fieldForm" label-width="100px">
                <el-form-item label="字段标签" required>
                    <el-input v-model="fieldForm.label" placeholder="如：产品名称"></el-input>
                </el-form-item>
                <el-form-item label="字段名" required>
                    <el-input v-model="fieldForm.field" placeholder="如：product_name（英文）"></el-input>
                </el-form-item>
                <el-form-item label="字段类型" required>
                    <el-select v-model="fieldForm.type" placeholder="请选择" style="width: 100%">
                        <el-option label="单行文本" value="input"></el-option>
                        <el-option label="多行文本" value="textarea"></el-option>
                        <el-option label="数字" value="number"></el-option>
                        <el-option label="下拉选择" value="select"></el-option>
                        <el-option label="单选框" value="radio"></el-option>
                        <el-option label="复选框" value="checkbox"></el-option>
                        <el-option label="日期" value="date"></el-option>
                        <el-option label="日期时间" value="datetime"></el-option>
                        <el-option label="文件上传" value="upload"></el-option>
                    </el-select>
                </el-form-item>
                <el-form-item label="是否必填">
                    <el-switch v-model="fieldForm.required"></el-switch>
                </el-form-item>
                <el-form-item label="占位符">
                    <el-input v-model="fieldForm.placeholder" placeholder="请输入占位符提示"></el-input>
                </el-form-item>
                <el-form-item label="默认值">
                    <el-input v-model="fieldForm.defaultValue" placeholder="可选"></el-input>
                </el-form-item>
                <el-form-item label="选项配置" v-if="fieldForm.type === 'select' || fieldForm.type === 'radio' || fieldForm.type === 'checkbox'">
                    <el-input 
                        v-model="fieldForm.options" 
                        type="textarea" 
                        :rows="3" 
                        placeholder="每行一个选项，格式：label:value&#10;例如：&#10;基线版本:baseline&#10;客户定制版本:custom"
                    ></el-input>
                </el-form-item>
            </el-form>
            <template #footer>
                <el-button @click="fieldEditDialogVisible = false">取消</el-button>
                <el-button type="primary" @click="handleFieldSubmit" :loading="fieldSubmitLoading">确定</el-button>
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
                fieldSubmitLoading: false,  // 字段编辑加载状态
                editDialogVisible: false,
                stepDialogVisible: false,
                stepEditDialogVisible: false,
                ccDialogVisible: false,
                ccEditDialogVisible: false,
                fieldEditDialogVisible: false,  // 字段编辑对话框
                editTitle: '新增流程类型',
                stepEditTitle: '新增步骤',
                ccEditTitle: '新增抄送',
                fieldEditTitle: '新增字段',
                currentWorkflowType: null,
                stepsData: [],
                ccData: [],
                formFieldsData: [],  // 表单字段数据
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
                    sort: 1,
                    form_schema: null  // 表单配置
                },
                fieldForm: {
                    label: '',
                    field: '',
                    type: 'input',
                    required: false,
                    placeholder: '',
                    defaultValue: '',
                    options: ''  // 选项配置（用于 select/radio/checkbox）
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
                    sign_mode: 1,  // 默认为或签
                    allow_return: true,
                    allow_reject: false,
                    timeout_hours: null,  // 超时时间
                    auto_action: 0,  // 不自动处理
                    notify_email: true,  // 邮件通知
                    notify_message: true,  // 站内信通知
                    notify_sms: false,  // 短信通知
                    description: ''  // 节点说明
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
                    sort: 1,
                    form_schema: null
                }
                this.formFieldsData = []  // 清空字段数据
                this.editTitle = '新增流程类型'
                this.editDialogVisible = true
            },
            handleEdit(row){
                this.editForm = {...row}
                // 解析表单配置
                if(row.form_schema) {
                    try {
                        this.formFieldsData = typeof row.form_schema === 'string' ? JSON.parse(row.form_schema) : row.form_schema
                    } catch(e) {
                        this.formFieldsData = []
                    }
                } else {
                    this.formFieldsData = []
                }
                this.editTitle = '编辑流程类型'
                this.editDialogVisible = true
            },
            handleEditSubmit(){
                if(!this.editForm.name || !this.editForm.code) {
                    this.$message.warning('请填写必填项')
                    return
                }
                
                let vm = this
                // 将表单字段数据转换为 JSON 字符串保存到 form_schema
                vm.editForm.form_schema = JSON.stringify(vm.formFieldsData)
                
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
                    sign_mode: 1,  // 默认为或签
                    allow_return: true,
                    allow_reject: false,
                    timeout_hours: null,  // 超时时间
                    auto_action: 0,  // 不自动处理
                    notify_email: true,  // 邮件通知
                    notify_message: true,  // 站内信通知
                    notify_sms: false,  // 短信通知
                    description: ''  // 节点说明
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
            },
            // ========== 表单字段配置相关方法 ==========
            getFieldTypeLabel(type) {
                const typeMap = {
                    'input': '单行文本',
                    'textarea': '多行文本',
                    'number': '数字',
                    'select': '下拉选择',
                    'radio': '单选框',
                    'checkbox': '复选框',
                    'date': '日期',
                    'datetime': '日期时间',
                    'upload': '文件上传'
                }
                return typeMap[type] || type
            },
            handleAddFormField() {
                this.fieldForm = {
                    label: '',
                    field: '',
                    type: 'input',
                    required: false,
                    placeholder: '',
                    defaultValue: '',
                    options: ''
                }
                this.fieldEditTitle = '新增字段'
                this.fieldEditDialogVisible = true
            },
            handleEditFormField(row, index) {
                this.fieldForm = {...row}
                // 如果是选项类型，将 options 数组转为字符串
                if(row.options && Array.isArray(row.options)) {
                    this.fieldForm.options = row.options.map(opt => `${opt.label}:${opt.value}`).join('\n')
                }
                this._editingFieldIndex = index  // 记录正在编辑的字段索引
                this.fieldEditTitle = '编辑字段'
                this.fieldEditDialogVisible = true
            },
            handleFieldSubmit() {
                if(!this.fieldForm.label || !this.fieldForm.field) {
                    this.$message.warning('请填写字段标签和字段名')
                    return
                }
                
                // 验证字段名（只能包含字母、数字、下划线）
                if(!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(this.fieldForm.field)) {
                    this.$message.warning('字段名只能包含字母、数字和下划线，且不能以数字开头')
                    return
                }
                
                let vm = this
                vm.fieldSubmitLoading = true
                
                // 解析选项配置
                let fieldData = {...vm.fieldForm}
                if(fieldData.type === 'select' || fieldData.type === 'radio' || fieldData.type === 'checkbox') {
                    if(fieldData.options) {
                        try {
                            // 将 "label:value\nlabel2:value2" 格式转换为 [{label: 'label', value: 'value'}, ...]
                            fieldData.options = fieldData.options.split('\n')
                                .filter(line => line.trim())
                                .map(line => {
                                    const parts = line.split(':')
                                    return {
                                        label: parts[0].trim(),
                                        value: parts.length > 1 ? parts[1].trim() : parts[0].trim()
                                    }
                                })
                        } catch(e) {
                            vm.fieldSubmitLoading = false
                            vm.$message.error('选项配置格式错误')
                            return
                        }
                    } else {
                        fieldData.options = []
                    }
                }
                
                // 判断是新增还是编辑
                if(vm._editingFieldIndex !== undefined) {
                    // 编辑模式：更新现有字段
                    vm.formFieldsData[vm._editingFieldIndex] = fieldData
                    delete vm._editingFieldIndex
                } else {
                    // 新增模式：添加到列表
                    vm.formFieldsData.push(fieldData)
                }
                
                vm.fieldSubmitLoading = false
                vm.fieldEditDialogVisible = false
                vm.$message.success(vm._editingFieldIndex !== undefined ? '编辑成功' : '新增成功')
            },
            handleDeleteFormField(index) {
                let vm = this
                vm.$confirm('确认要删除该字段吗？', '提示', {
                    confirmButtonText: '确定',
                    cancelButtonText: '取消',
                    type: 'warning'
                }).then(() => {
                    vm.formFieldsData.splice(index, 1)
                    vm.$message.success('删除成功')
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
