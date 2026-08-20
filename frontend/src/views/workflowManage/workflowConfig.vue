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
                <el-table-column min-width="150" prop="allowed_initiator_depts_name" label="允许发起部门" show-overflow-tooltip></el-table-column>
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
                
                <!-- 发起人部门限制 -->
                <div style="margin-bottom: 20px; padding-bottom: 20px; border-bottom: 1px solid #EBEEF5;">
                    <h4 style="margin-bottom: 15px;">发起人部门限制</h4>
                    <el-form-item label="允许发起的部门">
                        <el-select 
                            v-model="editForm.allowed_initiator_depts" 
                            multiple 
                            placeholder="不选则表示所有部门均可发起" 
                            style="width: 100%" 
                            filterable
                        >
                            <el-option v-for="item in depts" :key="item.id" :label="item.name" :value="item.id"></el-option>
                        </el-select>
                        <div style="margin-top: 5px; font-size: 12px; color: #909399;">
                            不选择任何部门表示所有部门均可发起该流程；选择特定部门后，只有这些部门的用户可以发起
                        </div>
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
                        <!-- auto_fill 开关列：开启后该字段由系统自动回填（打包管理发包时回填制品路径/版本名；手动创建时软件包存放路径按"共享路径+包名"拼接并校验文件存在），回填字段清单见 config.DELIVERY_AUTO_FILL_FIELDS -->
                        <el-table-column prop="auto_fill" label="自动回填" width="90" align="center">
                            <template #default="scope">
                                <el-tag v-if="scope.row.auto_fill" type="warning" size="small">是</el-tag>
                                <el-tag v-else type="info" size="small">否</el-tag>
                            </template>
                        </el-table-column>
                        <!-- readonly 只读列：开启后发起流程时该字段不可编辑（如软件包存放路径由系统自动回填） -->
                        <el-table-column prop="readonly" label="只读" width="90" align="center">
                            <template #default="scope">
                                <el-tag v-if="scope.row.readonly" type="primary" size="small">是</el-tag>
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
                <el-table-column prop="node_type_display" label="节点类型" width="120">
                    <template #default="scope">
                        <el-tag v-if="scope.row.node_type==1" type="primary" size="small">普通审批</el-tag>
                        <el-tag v-else-if="scope.row.node_type==2" type="info" size="small">抄送节点</el-tag>
                        <el-tag v-else-if="scope.row.node_type==3" type="warning" size="small">条件分支</el-tag>
                        <el-tag v-else-if="scope.row.node_type==4" type="success" size="small">并行网关</el-tag>
                        <el-tag v-else-if="scope.row.node_type==5" type="danger" size="small">结束节点</el-tag>
                    </template>
                </el-table-column>
                <el-table-column label="审批人/配置" min-width="200">
                    <template #default="scope">
                        <!-- 普通审批节点 -->
                        <span v-if="scope.row.node_type==1">
                            <span v-if="scope.row.approver_type==1">{{ scope.row.approver_role_name || '-' }}</span>
                            <span v-else-if="scope.row.approver_type==2">{{ scope.row.approver_dept_name || '-' }}</span>
                            <span v-else-if="scope.row.approver_type==3">部门负责人</span>
                            <span v-else-if="scope.row.approver_type==4">
                                <span v-for="(user, index) in scope.row.approver_users_info" :key="index">
                                    {{ user.name }}<span v-if="index < scope.row.approver_users_info.length - 1">, </span>
                                </span>
                            </span>
                            <span v-else-if="scope.row.approver_type==5">申请人自选</span>
                            <span v-else-if="scope.row.approver_type==7">发起人</span>
                            <span v-else-if="scope.row.approver_type==8">条件化审批人</span>
                            <span v-else-if="scope.row.approver_type==10">审批组: {{ scope.row.approver_group_name || '-' }}</span>
                        </span>
                        <!-- 抄送节点 -->
                        <span v-else-if="scope.row.node_type==2">
                            <span v-if="scope.row.condition_rules && scope.row.condition_rules.cc_type==1">{{ scope.row.condition_rules.cc_role_name || '角色' }}</span>
                            <span v-else-if="scope.row.condition_rules && scope.row.condition_rules.cc_type==2">{{ scope.row.condition_rules.cc_dept_name || '部门' }}</span>
                            <span v-else-if="scope.row.condition_rules && scope.row.condition_rules.cc_type==3">部门负责人</span>
                            <span v-else-if="scope.row.condition_rules && scope.row.condition_rules.cc_type==4">
                                <span v-for="(user, index) in scope.row.condition_rules.cc_users" :key="index">
                                    {{ user.name }}<span v-if="index < scope.row.condition_rules.cc_users.length - 1">, </span>
                                </span>
                            </span>
                            <span v-else-if="scope.row.condition_rules && scope.row.condition_rules.cc_type==6">审批组: {{ getApprovalGroupName(scope.row.condition_rules.cc_group) }}</span>
                        </span>
                        <!-- 条件分支节点 -->
                        <span v-else-if="scope.row.node_type==3">
                            {{ (scope.row.condition_rules && Array.isArray(scope.row.condition_rules)) ? scope.row.condition_rules.length + '个条件' : '-' }}
                        </span>
                        <!-- 并行网关节点 -->
                        <span v-else-if="scope.row.node_type==4">
                            {{ (scope.row.condition_rules && scope.row.condition_rules.branches) ? scope.row.condition_rules.branches.length + '个分支' : '-' }}
                        </span>
                        <!-- 结束节点 -->
                        <span v-else-if="scope.row.node_type==5">-</span>
                    </template>
                </el-table-column>
                <el-table-column label="审批模式" width="100" align="center" v-if="showApprovalModeColumn">
                    <template #default="scope">
                        <el-tag v-if="scope.row.sign_mode==1" type="primary" size="small">或签</el-tag>
                        <el-tag v-else-if="scope.row.sign_mode==2" type="success" size="small">会签</el-tag>
                        <el-tag v-else-if="scope.row.sign_mode==3" type="warning" size="small">顺序</el-tag>
                    </template>
                </el-table-column>
                <el-table-column label="允许退回" width="100" align="center">
                    <template #default="scope">
                        <el-tag v-if="scope.row.node_type===1 && scope.row.allow_return" type="success" size="small">是</el-tag>
                        <el-tag v-else-if="scope.row.node_type===1" type="info" size="small">否</el-tag>
                        <span v-else>-</span>
                    </template>
                </el-table-column>
                <el-table-column label="允许驳回" width="100" align="center">
                    <template #default="scope">
                        <el-tag v-if="scope.row.node_type===1 && scope.row.allow_reject" type="success" size="small">是</el-tag>
                        <el-tag v-else-if="scope.row.node_type===1" type="info" size="small">否</el-tag>
                        <span v-else>-</span>
                    </template>
                </el-table-column>
                <el-table-column label="超时设置" width="120" align="center">
                    <template #default="scope">
                        <span v-if="scope.row.node_type===1 && scope.row.timeout_hours">
                            {{ scope.row.timeout_hours }}小时
                            <el-tag v-if="scope.row.auto_action==1" type="success" size="small">自动通过</el-tag>
                            <el-tag v-else-if="scope.row.auto_action==2" type="warning" size="small">自动退回</el-tag>
                        </span>
                        <span v-else>-</span>
                    </template>
                </el-table-column>
                <el-table-column label="通知方式" width="150" align="center">
                    <template #default="scope">
                        <span v-if="scope.row.node_type===1">
                            <el-tag v-if="scope.row.notify_email" type="info" size="small">邮件</el-tag>
                            <el-tag v-if="scope.row.notify_message" type="info" size="small">站内信</el-tag>
                            <el-tag v-if="scope.row.notify_sms" type="info" size="small">短信</el-tag>
                        </span>
                        <span v-else>-</span>
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
        <el-dialog v-model="stepEditDialogVisible" :title="stepEditTitle" width="800px">
            <el-form :model="stepForm" label-width="120px">
                <el-form-item label="节点类型" required>
                    <el-select v-model="stepForm.node_type" placeholder="请选择" style="width: 100%" @change="handleNodeTypeChange">
                        <el-option label="普通审批节点" :value="1"></el-option>
                        <el-option label="抄送节点" :value="2"></el-option>
                        <el-option label="条件分支节点" :value="3"></el-option>
                        <el-option label="并行网关节点" :value="4"></el-option>
                        <el-option label="结束节点" :value="5"></el-option>
                    </el-select>
                </el-form-item>
                
                <!-- 基本信息（所有节点类型都需要） -->
                <el-divider content-position="left">基本信息</el-divider>
                <el-form-item label="步骤名称" required>
                    <el-input v-model="stepForm.step_name" placeholder="请输入步骤名称"></el-input>
                </el-form-item>
                <el-form-item label="步骤顺序" required>
                    <el-input-number v-model="stepForm.step_order" :min="1" :max="99"></el-input-number>
                </el-form-item>
                
                <!-- 普通审批节点配置 -->
                <template v-if="stepForm.node_type === 1">
                    <el-divider content-position="left">审批人配置</el-divider>
                    <el-form-item label="审批人类型" required>
                        <el-select v-model="stepForm.approver_type" placeholder="请选择" style="width: 100%">
                            <el-option label="指定角色" :value="1"></el-option>
                            <el-option label="指定部门" :value="2"></el-option>
                            <el-option label="部门负责人" :value="3"></el-option>
                            <el-option label="指定人员" :value="4"></el-option>
                            <el-option label="申请人自选" :value="5"></el-option>
                            <el-option label="多级审批（组合）" :value="6"></el-option>
                            <el-option label="发起人" :value="7"></el-option>
                            <el-option label="条件化审批人" :value="8"></el-option>
                            <el-option label="自定义审批组" :value="10"></el-option>
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
                    <el-form-item label="审批组" v-if="stepForm.approver_type==10" required>
                        <el-select v-model="stepForm.approver_group" placeholder="请选择审批组" style="width: 100%">
                            <el-option v-for="item in approvalGroups" :key="item.id" :label="item.product_line ? item.name + '（' + item.product_line + '）' : item.name" :value="item.id"></el-option>
                        </el-select>
                        <div style="margin-top: 5px; font-size: 12px; color: #909399;">
                            审批组成员可在“流程节点配置-管理审批组”中随时增删，审批人随审批组动态更新
                        </div>
                    </el-form-item>
                    
                    <!-- 多级审批配置 -->
                    <template v-if="stepForm.approver_type==6">
                        <el-alert
                            title="提示：多级审批支持设置多个审批层级，每个层级可独立配置审批人"
                            type="info"
                            :closable="false"
                            show-icon
                            style="margin-bottom: 15px;"
                        />
                        <div style="margin-bottom: 10px;">
                            <el-button type="primary" icon="Plus" @click="handleAddMultiLevel" size="small">添加层级</el-button>
                        </div>
                        <el-table :data="multiLevelData" border style="width: 100%; margin-bottom: 15px;">
                            <el-table-column prop="name" label="层级名称" width="150">
                                <template #default="scope">
                                    <el-input v-model="scope.row.name" placeholder="如：第一级审批" size="small"></el-input>
                                </template>
                            </el-table-column>
                            <el-table-column prop="approver_type" label="审批人类型" width="120">
                                <template #default="scope">
                                    <el-select v-model="scope.row.approver_type" placeholder="请选择" size="small" style="width: 100%">
                                        <el-option label="指定角色" :value="1"></el-option>
                                        <el-option label="指定部门" :value="2"></el-option>
                                        <el-option label="部门负责人" :value="3"></el-option>
                                        <el-option label="指定人员" :value="4"></el-option>
                                        <el-option label="发起人" :value="7"></el-option>
                                        <el-option label="条件化审批人" :value="8"></el-option>
                                    </el-select>
                                </template>
                            </el-table-column>
                            <el-table-column label="审批人配置" min-width="200">
                                <template #default="scope">
                                    <el-select v-if="scope.row.approver_type==1" v-model="scope.row.approver_role" placeholder="请选择角色" size="small" style="width: 100%">
                                        <el-option v-for="item in roles" :key="item.id" :label="item.name" :value="item.id"></el-option>
                                    </el-select>
                                    <el-select v-else-if="scope.row.approver_type==2 || scope.row.approver_type==3" v-model="scope.row.approver_dept" placeholder="请选择部门" size="small" style="width: 100%">
                                        <el-option v-for="item in depts" :key="item.id" :label="item.name" :value="item.id"></el-option>
                                    </el-select>
                                    <el-select v-else-if="scope.row.approver_type==4" v-model="scope.row.approver_users" multiple placeholder="请选择人员" size="small" style="width: 100%">
                                        <el-option v-for="item in users" :key="item.id" :label="item.name" :value="item.id"></el-option>
                                    </el-select>
                                    <span v-else>-</span>
                                </template>
                            </el-table-column>
                            <el-table-column label="操作" width="80" align="center">
                                <template #default="scope">
                                    <el-button type="danger" icon="Delete" size="small" circle @click="handleDeleteMultiLevel(scope.$index)"></el-button>
                                </template>
                            </el-table-column>
                        </el-table>
                    </template>
                    
                    <!-- 多人审批模式 -->
                    <el-form-item label="审批模式">
                        <el-radio-group v-model="stepForm.sign_mode">
                            <el-radio :label="1">或签（一人审批即可）</el-radio>
                            <el-radio :label="2">会签（所有人都需审批）</el-radio>
                            <el-radio :label="3">顺序审批（按顺序依次审批）</el-radio>
                        </el-radio-group>
                    </el-form-item>
                    
                    <!-- 退回设置 -->
                    <el-form-item label="允许退回">
                        <el-switch v-model="stepForm.allow_return"></el-switch>
                    </el-form-item>
                    <el-form-item label="允许驳回">
                        <el-switch v-model="stepForm.allow_reject"></el-switch>
                    </el-form-item>
                    
                    <!-- 自动跳过审批配置 -->
                    <el-divider content-position="left">自动跳过审批</el-divider>
                    <el-alert
                        title="提示：当发起人满足指定条件时，自动跳过当前审批节点，直接流转到目标步骤"
                        type="info"
                        :closable="false"
                        show-icon
                        style="margin-bottom: 15px;"
                    />
                    <el-form-item label="启用自动跳过">
                        <el-switch v-model="stepForm.skip_approval_enabled"></el-switch>
                    </el-form-item>
                    <template v-if="stepForm.skip_approval_enabled">
                        <el-form-item label="跳过条件">
                            <div style="width: 100%">
                                <el-checkbox v-model="stepForm.skip_is_dept_owner" style="margin-bottom: 8px; display: block;">
                                    发起人是部门负责人（部门owner）
                                </el-checkbox>
                                <el-checkbox v-model="stepForm.skip_specified_users_checked" style="margin-bottom: 8px; display: block;">
                                    发起人为指定人员
                                </el-checkbox>
                                <el-select v-if="stepForm.skip_specified_users_checked" v-model="stepForm.skip_specified_users" multiple placeholder="请选择指定人员" style="width: 100%; margin-bottom: 8px;">
                                    <el-option v-for="item in users" :key="item.id" :label="item.name" :value="item.id"></el-option>
                                </el-select>
                                <el-checkbox v-model="stepForm.skip_specified_roles_checked" style="margin-bottom: 8px; display: block;">
                                    发起人拥有指定角色
                                </el-checkbox>
                                <el-select v-if="stepForm.skip_specified_roles_checked" v-model="stepForm.skip_specified_roles" multiple placeholder="请选择指定角色" style="width: 100%;">
                                    <el-option v-for="item in roles" :key="item.id" :label="item.name" :value="item.id"></el-option>
                                </el-select>
                                <el-checkbox v-model="stepForm.skip_scan_status_pass" style="margin-bottom: 8px; display: block;">
                                    包扫描状态为PASS
                                </el-checkbox>
                            </div>
                        </el-form-item>
                        <el-form-item label="目标步骤" required>
                            <el-select v-model="stepForm.skip_target_step" placeholder="请选择跳过后的目标步骤" style="width: 100%" clearable>
                                <el-option v-for="item in stepsData.filter(s => s.id !== stepForm.id)" :key="item.id" :label="item.step_name" :value="item.id"></el-option>
                            </el-select>
                        </el-form-item>
                    </template>
                </template>
                
                <!-- 抄送节点配置 -->
                <template v-if="stepForm.node_type === 2">
                    <el-divider content-position="left">抄送人员配置</el-divider>
                    <el-alert
                        title="提示：抄送节点会自动通知指定人员查看流程信息，不需要审批操作"
                        type="info"
                        :closable="false"
                        show-icon
                        style="margin-bottom: 15px;"
                    />
                    <el-form-item label="抄送人类型" required>
                        <el-select v-model="ccTypeInStep" placeholder="请选择" style="width: 100%">
                            <el-option label="指定角色" :value="1"></el-option>
                            <el-option label="指定部门" :value="2"></el-option>
                            <el-option label="部门负责人" :value="3"></el-option>
                            <el-option label="指定人员" :value="4"></el-option>
                            <el-option label="自定义审批组" :value="6"></el-option>
                        </el-select>
                    </el-form-item>
                    <el-form-item label="抄送角色" v-if="ccTypeInStep==1" required>
                        <el-select v-model="ccRoleInStep" placeholder="请选择角色" style="width: 100%">
                            <el-option v-for="item in roles" :key="item.id" :label="item.name" :value="item.id"></el-option>
                        </el-select>
                    </el-form-item>
                    <el-form-item label="抄送部门" v-if="ccTypeInStep==2 || ccTypeInStep==3" required>
                        <el-select v-model="ccDeptInStep" placeholder="请选择部门" style="width: 100%">
                            <el-option v-for="item in depts" :key="item.id" :label="item.name" :value="item.id"></el-option>
                        </el-select>
                    </el-form-item>
                    <el-form-item label="抄送人员" v-if="ccTypeInStep==4" required>
                        <el-select v-model="ccUsersInStep" multiple placeholder="请选择人员" style="width: 100%">
                            <el-option v-for="item in users" :key="item.id" :label="item.name" :value="item.id"></el-option>
                        </el-select>
                    </el-form-item>
                    <el-form-item label="抄送审批组" v-if="ccTypeInStep==6" required>
                        <el-select v-model="ccGroupInStep" placeholder="请选择审批组" style="width: 100%">
                            <el-option v-for="item in approvalGroups" :key="item.id" :label="item.product_line ? item.name + '（' + item.product_line + '）' : item.name" :value="item.id"></el-option>
                        </el-select>
                        <div style="margin-top: 5px; font-size: 12px; color: #909399;">
                            抄送人为审批组成员，成员可在“流程节点配置-管理审批组”中随时增删，抄送人随审批组动态更新
                        </div>
                    </el-form-item>
                </template>
                
                <!-- 条件分支节点配置 -->
                <template v-if="stepForm.node_type === 3">
                    <el-divider content-position="left">条件分支配置</el-divider>
                    <el-alert
                        title="提示：根据表单字段值判断流程走向，支持多种比较操作符"
                        type="info"
                        :closable="false"
                        show-icon
                        style="margin-bottom: 15px;"
                    />
                    <el-form-item label="默认下一步骤">
                        <el-select v-model="stepForm.next_step_on_pass" placeholder="无匹配条件时的默认步骤" style="width: 100%" clearable>
                            <el-option v-for="item in stepsData.filter(s => s.id !== stepForm.id)" :key="item.id" :label="item.step_name" :value="item.id"></el-option>
                        </el-select>
                    </el-form-item>
                    
                    <div style="margin-bottom: 10px;">
                        <el-button type="primary" icon="Plus" @click="handleAddCondition" size="small">添加条件</el-button>
                    </div>
                    <el-table :data="conditionRulesData" border style="width: 100%; margin-bottom: 15px;">
                        <el-table-column prop="field" label="字段名" width="200">
                            <template #default="scope">
                                <el-select v-model="scope.row.field" placeholder="请选择字段" size="small" style="width: 100%" filterable>
                                    <el-option 
                                        v-for="item in formFields" 
                                        :key="item.value" 
                                        :label="item.label" 
                                        :value="item.value">
                                    </el-option>
                                </el-select>
                            </template>
                        </el-table-column>
                        <el-table-column prop="operator" label="操作符" width="120">
                            <template #default="scope">
                                <el-select v-model="scope.row.operator" placeholder="请选择" size="small" style="width: 100%">
                                    <el-option label="等于" value="=="></el-option>
                                    <el-option label="不等于" value="!="></el-option>
                                    <el-option label="大于" value=">"></el-option>
                                    <el-option label="小于" value="<"></el-option>
                                    <el-option label="大于等于" value=">="></el-option>
                                    <el-option label="小于等于" value="<="></el-option>
                                    <el-option label="包含" value="contains"></el-option>
                                    <el-option label="不包含" value="not_contains"></el-option>
                                    <el-option label="在列表中" value="in"></el-option>
                                    <el-option label="不在列表中" value="not_in"></el-option>
                                </el-select>
                            </template>
                        </el-table-column>
                        <el-table-column prop="value" label="比较值" min-width="150">
                            <template #default="scope">
                                <el-input v-model="scope.row.value" placeholder="如：10000 或 yes" size="small"></el-input>
                            </template>
                        </el-table-column>
                        <el-table-column prop="target_step" label="目标步骤" width="150">
                            <template #default="scope">
                                <el-select v-model="scope.row.target_step" placeholder="请选择" size="small" style="width: 100%">
                                    <el-option v-for="item in stepsData.filter(s => s.id !== stepForm.id)" :key="item.id" :label="item.step_name" :value="item.id"></el-option>
                                </el-select>
                            </template>
                        </el-table-column>
                        <el-table-column label="操作" width="80" align="center">
                            <template #default="scope">
                                <el-button type="danger" icon="Delete" size="small" circle @click="handleDeleteCondition(scope.$index)"></el-button>
                            </template>
                        </el-table-column>
                    </el-table>
                </template>
                
                <!-- 并行网关节点配置 -->
                <template v-if="stepForm.node_type === 4">
                    <el-divider content-position="left">并行分支配置</el-divider>
                    <el-alert
                        title="提示：同时创建多个分支任务，各分支并行执行"
                        type="info"
                        :closable="false"
                        show-icon
                        style="margin-bottom: 15px;"
                    />
                    <div style="margin-bottom: 10px;">
                        <el-button type="primary" icon="Plus" @click="handleAddBranch" size="small">添加分支</el-button>
                    </div>
                    <el-table :data="parallelBranchesData" border style="width: 100%; margin-bottom: 15px;">
                        <el-table-column prop="branch_name" label="分支名称" width="150">
                            <template #default="scope">
                                <el-input v-model="scope.row.branch_name" placeholder="如：技术部审批" size="small"></el-input>
                            </template>
                        </el-table-column>
                        <el-table-column prop="target_step" label="目标步骤" min-width="200">
                            <template #default="scope">
                                <el-select v-model="scope.row.target_step" placeholder="请选择" size="small" style="width: 100%">
                                    <el-option v-for="item in stepsData.filter(s => s.id !== stepForm.id)" :key="item.id" :label="item.step_name" :value="item.id"></el-option>
                                </el-select>
                            </template>
                        </el-table-column>
                        <el-table-column label="操作" width="80" align="center">
                            <template #default="scope">
                                <el-button type="danger" icon="Delete" size="small" circle @click="handleDeleteBranch(scope.$index)"></el-button>
                            </template>
                        </el-table-column>
                    </el-table>
                </template>
                
                <!-- 结束节点配置 -->
                <template v-if="stepForm.node_type === 5">
                    <el-divider content-position="left">结束节点说明</el-divider>
                    <el-alert
                        title="提示：结束节点标记流程完成，将流程状态设置为'已通过'"
                        type="success"
                        :closable="false"
                        show-icon
                        style="margin-bottom: 15px;"
                    />
                    <el-form-item label="节点说明">
                        <el-input v-model="stepForm.description" type="textarea" :rows="3" placeholder="可选：填写流程结束的说明信息"></el-input>
                    </el-form-item>
                </template>
                
                <!-- 超时设置（仅普通审批节点） -->
                <template v-if="stepForm.node_type === 1">
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
                </template>
                
                <!-- 通知设置（仅普通审批节点） -->
                <template v-if="stepForm.node_type === 1">
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
                </template>
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
                        <span v-else-if="scope.row.cc_type==6">审批组: {{ scope.row.cc_group_name || '-' }}</span>
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
                        <el-option label="自定义审批组" :value="6"></el-option>
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
                <el-form-item label="抄送审批组" v-if="ccForm.cc_type==6" required>
                    <el-select v-model="ccForm.cc_group" placeholder="请选择审批组" style="width: 100%">
                        <el-option v-for="item in approvalGroups" :key="item.id" :label="item.product_line ? item.name + '（' + item.product_line + '）' : item.name" :value="item.id"></el-option>
                    </el-select>
                    <div style="margin-top: 5px; font-size: 12px; color: #909399;">
                        抄送人为审批组成员，成员可在“流程节点配置-管理审批组”中随时增删，抄送人随审批组动态更新
                    </div>
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
                <!-- auto_fill 开关：开启后该字段由系统自动填写（打包管理发包时回填制品路径/版本名；手动发起时软件包存放路径按"共享路径 + 软件包名称"拼接并校验文件真实存在，不存在时由申请人确认实际路径），建议同时开启只读 -->
                <el-form-item label="自动回填">
                    <el-switch v-model="fieldForm.auto_fill"></el-switch>
                    <div style="font-size: 12px; color: #909399; line-height: 1.5; margin-top: 4px;">
                        开启后该字段由系统自动填写，用户无需手动输入；回填内容按字段类型确定（当前支持软件包存放路径类字段：打包管理发包时回填制品实际路径，手动发起时按配置文件 config.py 的 PACKAGE_SCAN_SHARED_PATH + 软件包名称拼接并校验文件是否真实存在，不存在时由申请人确认实际路径），建议同时开启只读；回填字段与回填内容的映射关系在 config.py 的 DELIVERY_AUTO_FILL_FIELDS 中维护，新增回填字段需在配置中添加一项并开启此开关
                    </div>
                </el-form-item>
                <!-- readonly 只读开关：开启后发起流程时该字段不可编辑 -->
                <el-form-item label="是否只读">
                    <el-switch v-model="fieldForm.readonly"></el-switch>
                    <div style="font-size: 12px; color: #909399; line-height: 1.5; margin-top: 4px;">
                        开启后用户在发起流程时不可编辑该字段
                    </div>
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
                <el-divider content-position="left">字段联动规则（可选）</el-divider>
                <el-form-item label="联动触发条件">
                    <el-alert 
                        title="设置当其他字段的值满足特定条件时，当前字段变为必填或隐藏" 
                        type="info" 
                        :closable="false"
                        style="margin-bottom: 10px;"
                    >
                    </el-alert>
                    <div v-for="(rule, index) in fieldForm.conditional_rules" :key="index" style="margin-bottom: 10px; padding: 10px; border: 1px solid #EBEEF5; border-radius: 4px;">
                        <el-row :gutter="10">
                            <el-col :span="6">
                                <el-select v-model="rule.trigger_field" placeholder="触发字段" size="small" style="width: 100%" filterable @change="onTriggerFieldChange(rule)">
                                    <el-option v-for="item in availableFieldsForLinkage" :key="item.value" :label="item.label" :value="item.value"></el-option>
                                </el-select>
                            </el-col>
                            <el-col :span="5">
                                <el-select v-model="rule.operator" placeholder="操作符" size="small" style="width: 100%">
                                    <el-option label="等于" value="=="></el-option>
                                    <el-option label="不等于" value="!="></el-option>
                                    <el-option label="包含" value="contains"></el-option>
                                    <el-option label="不包含" value="not_contains"></el-option>
                                </el-select>
                            </el-col>
                            <el-col :span="6">
                                <el-input v-model="rule.trigger_value" placeholder="触发值" size="small"></el-input>
                                <!-- 智能提示：显示可用选项 -->
                                <div v-if="getTriggerFieldOptions(rule.trigger_field).length > 0" style="margin-top: 5px; font-size: 12px; color: #909399;">
                                    <div>可用值：</div>
                                    <el-tag 
                                        v-for="opt in getTriggerFieldOptions(rule.trigger_field)" 
                                        :key="opt.value"
                                        size="small"
                                        style="margin: 2px; cursor: pointer;"
                                        @click="rule.trigger_value = opt.value"
                                    >
                                        {{ opt.label }} ({{ opt.value }})
                                    </el-tag>
                                </div>
                            </el-col>
                            <el-col :span="5">
                                <el-select v-model="rule.action" placeholder="执行动作" size="small" style="width: 100%">
                                    <el-option label="设为必填" value="required"></el-option>
                                    <el-option label="取消必填" value="not_required"></el-option>
                                    <el-option label="隐藏字段" value="hidden"></el-option>
                                    <el-option label="显示字段" value="visible"></el-option>
                                </el-select>
                            </el-col>
                            <el-col :span="2">
                                <el-button @click="removeConditionalRule(index)" type="danger" icon="Delete" size="small" circle></el-button>
                            </el-col>
                        </el-row>
                        <!-- 智能提示 -->
                        <el-alert 
                            v-if="getTriggerFieldType(rule.trigger_field) === 'checkbox' && rule.operator === '=='" 
                            :title="`提示：对于复选框类型，建议使用“包含”操作符而不是“等于”，这样更直观`" 
                            type="warning" 
                            :closable="false"
                            style="margin-top: 8px;"
                        >
                        </el-alert>
                    </div>
                    <el-button @click="addConditionalRule" type="primary" icon="Plus" size="small">添加联动规则</el-button>
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
    import {workflowType, workflowTypeAdd, workflowTypeUpdate, workflowTypeDelete, getWorkflowTypeFormFields, workflowStep, workflowStepAdd, workflowStepUpdate, workflowStepDelete, workflowCC, workflowCCAdd, workflowCCUpdate, workflowCCDelete, apiSystemRole, apiSystemDept, apiSystemAllUser, approvalGroup} from '@/api/api';
    
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
                conditionRulesData: [],  // 条件分支规则数据
                parallelBranchesData: [],  // 并行分支数据
                multiLevelData: [],  // 多级审批层级数据
                ccTypeInStep: 1,  // 抄送节点中的抄送人类型
                ccRoleInStep: '',  // 抄送节点中的抄送角色
                ccDeptInStep: '',  // 抄送节点中的抄送部门
                ccUsersInStep: [],  // 抄送节点中的抄送人员
                ccGroupInStep: '',  // 抄送节点中的抄送审批组（cc_type=6 时使用）
                roles: [],
                depts: [],
                users: [],
                approvalGroups: [],  // 自定义审批组列表
                formFields: [],  // 当前流程类型的表单字段列表
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
                    form_schema: null,  // 表单配置
                    allowed_initiator_depts: []  // 允许发起的部门
                },
                fieldForm: {
                    label: '',
                    field: '',
                    type: 'input',
                    required: false,
                    auto_fill: false,  // 自动回填开关（true 开启后该字段由系统自动填写：打包管理发包时回填制品路径/版本名，手动创建时软件包存放路径按共享路径+包名拼接并校验文件存在；回填字段清单见 config.DELIVERY_AUTO_FILL_FIELDS）
                    readonly: false,  // 只读开关（true 开启后发起流程时该字段不可编辑）
                    placeholder: '',
                    defaultValue: '',
                    options: '',  // 选项配置（用于 select/radio/checkbox）
                    conditional_rules: []  // 字段联动规则
                },
                stepForm: {
                    id: '',
                    workflow_type: '',
                    step_name: '',
                    step_order: 1,
                    node_type: 1,  // 节点类型：1=普通审批, 2=抄送, 3=条件分支, 4=并行网关, 5=结束
                    approval_mode: 1,  // 审批模式：1=自动流转, 2=手动配置
                    approver_type: 1,
                    approver_role: '',
                    approver_dept: '',
                    approver_users: [],
                    approver_group: null,  // 自定义审批组
                    sign_mode: 1,  // 默认为或签
                    allow_return: true,
                    allow_reject: false,
                    timeout_hours: null,  // 超时时间
                    auto_action: 0,  // 不自动处理
                    notify_email: true,  // 邮件通知
                    notify_message: true,  // 站内信通知
                    notify_sms: false,  // 短信通知
                    description: '',  // 节点说明
                    condition_rules: null,  // 条件规则（用于抄送、条件分支、并行网关）
                    next_step_on_pass: null,  // 通过后下一步骤
                    next_step_on_reject: null,  // 驳回后下一步骤
                    multi_level_config: null,  // 多级审批配置
                    // 自动跳过审批配置
                    skip_approval_enabled: false,
                    skip_is_dept_owner: false,
                    skip_specified_users: [],
                    skip_specified_roles: [],
                    skip_scan_status_pass: false,
                    skip_target_step: null
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
        computed: {
            // 是否显示审批模式列（只有普通审批节点才有）
            showApprovalModeColumn() {
                return this.stepsData.some(step => step.node_type === 1)
            },
            // 可用于联动配置的字段列表（排除当前正在编辑的字段）
            availableFieldsForLinkage() {
                const fields = this.formFieldsData
                    .filter(field => field.field !== this.fieldForm.field)  // 排除自己
                    .map(field => ({
                        value: field.field,
                        label: `${field.label} (${field.field})`
                    }))
                return fields
            },
            // 自动跳过审批：是否选择了指定人员
            skip_specified_users_checked: {
                get() { return this.stepForm.skip_specified_users && this.stepForm.skip_specified_users.length > 0 },
                set(val) { if (!val) this.stepForm.skip_specified_users = [] }
            },
            // 自动跳过审批：是否选择了指定角色
            skip_specified_roles_checked: {
                get() { return this.stepForm.skip_specified_roles && this.stepForm.skip_specified_roles.length > 0 },
                set(val) { if (!val) this.stepForm.skip_specified_roles = [] }
            }
        },
        created() {
            this.getData()
            this.getRoles()
            this.getDepts()
            this.getUsers()
            this.getApprovalGroups()
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
                apiSystemAllUser({page: 1, limit: 1000}).then(res => {
                    if(res.code === 2000) {
                        vm.users = res.data.data || []
                    }
                })
            },
            getApprovalGroups(){
                let vm = this
                approvalGroup({page: 1, limit: 1000}).then(res => {
                    if(res.code === 2000) {
                        vm.approvalGroups = res.data.data || []
                    }
                })
            },
            // 根据审批组ID获取审批组名称（抄送审批组显示用）
            getApprovalGroupName(groupId){
                if(!groupId) return '-'
                const group = this.approvalGroups.find(g => g.id === groupId)
                return group ? group.name : '-'
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
                    form_schema: null,
                    allowed_initiator_depts: []  // 允许发起的部门
                }
                this.formFieldsData = []  // 清空字段数据
                this.editTitle = '新增流程类型'
                this.editDialogVisible = true
            },
            handleEdit(row){
                this.editForm = {...row}
                // 确保 allowed_initiator_depts 是数组
                if(!this.editForm.allowed_initiator_depts) {
                    this.editForm.allowed_initiator_depts = []
                }
                // 解析表单配置
                if(row.form_schema) {
                    try {
                        let schema = typeof row.form_schema === 'string' ? JSON.parse(row.form_schema) : row.form_schema
                        
                        // 兼容两种格式：{fields: [...]} 或直接 [...]
                        if (schema.fields && Array.isArray(schema.fields)) {
                            this.formFieldsData = schema.fields
                        } else if (Array.isArray(schema)) {
                            this.formFieldsData = schema
                        } else {
                            console.error('form_schema 格式不正确:', schema)
                            this.formFieldsData = []
                        }
                    } catch(e) {
                        console.error('解析 form_schema 失败:', e)
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
            // 获取流程类型的表单字段列表
            getFormFields(workflowTypeId) {
                if (!workflowTypeId) {
                    console.log('警告: workflowTypeId 为空')
                    return
                }
                
                console.log(`正在获取流程类型 ${workflowTypeId} 的表单字段`)
                
                getWorkflowTypeFormFields(workflowTypeId).then(res => {
                    console.log('API响应:', res)
                    if (res.code === 2000 && res.data) {
                        this.formFields = res.data || []
                        console.log(`获取到 ${this.formFields.length} 个字段:`, this.formFields)
                    } else {
                        console.log('未获取到字段数据，res.code:', res.code, 'res.data:', res.data)
                        this.formFields = []
                    }
                }).catch(err => {
                    console.error('获取表单字段失败:', err)
                    this.formFields = []
                })
            },
            handleAddStep(){
                // 获取当前流程类型的表单字段
                this.getFormFields(this.currentWorkflowType.id)
                
                this.stepForm = {
                    id: '',
                    workflow_type: this.currentWorkflowType.id,
                    step_name: '',
                    step_order: this.stepsData.length + 1,
                    node_type: 1,  // 默认为普通审批节点
                    approval_mode: 1,
                    approver_type: 1,
                    approver_role: '',
                    approver_dept: '',
                    approver_users: [],
                    approver_group: null,  // 自定义审批组
                    sign_mode: 1,  // 默认为或签
                    allow_return: true,
                    allow_reject: false,
                    timeout_hours: null,
                    auto_action: 0,
                    notify_email: true,
                    notify_message: true,
                    notify_sms: false,
                    description: '',
                    condition_rules: null,
                    next_step_on_pass: null,
                    next_step_on_reject: null,
                    multi_level_config: null,
                    skip_approval_enabled: false,
                    skip_is_dept_owner: false,
                    skip_specified_users: [],
                    skip_specified_roles: [],
                    skip_target_step: null
                }
                // 重置抄送节点相关字段
                this.ccTypeInStep = 1
                this.ccRoleInStep = ''
                this.ccDeptInStep = ''
                this.ccUsersInStep = []
                this.ccGroupInStep = ''
                // 重置条件和分支数据
                this.conditionRulesData = []
                this.parallelBranchesData = []
                this.multiLevelData = []
                this.stepEditTitle = '新增步骤'
                this.stepEditDialogVisible = true
            },
            handleEditStep(row){
                // 获取当前流程类型的表单字段
                this.getFormFields(this.currentWorkflowType.id)
                
                this.stepForm = {...row}
                
                // 解析 condition_rules
                if(row.condition_rules) {
                    try {
                        const rules = typeof row.condition_rules === 'string' ? JSON.parse(row.condition_rules) : row.condition_rules
                        
                        // 根据节点类型解析不同的配置
                        if(row.node_type === 2) {  // 抄送节点
                            // condition_rules 格式: {cc_type, cc_role, cc_dept, cc_users, cc_group}
                            this.ccTypeInStep = rules.cc_type || 1
                            this.ccRoleInStep = rules.cc_role || ''
                            this.ccDeptInStep = rules.cc_dept || ''
                            this.ccUsersInStep = rules.cc_users || []
                            this.ccGroupInStep = rules.cc_group || ''
                        } else if(row.node_type === 3) {  // 条件分支节点
                            // condition_rules 格式: [{field, operator, value, target_step}, ...]
                            this.conditionRulesData = Array.isArray(rules) ? rules : []
                        } else if(row.node_type === 4) {  // 并行网关节点
                            // condition_rules 格式: {branches: [{target_step}, ...]}
                            this.parallelBranchesData = rules.branches || []
                        }
                    } catch(e) {
                        console.error('解析 condition_rules 失败:', e)
                        this.conditionRulesData = []
                        this.parallelBranchesData = []
                    }
                } else {
                    this.conditionRulesData = []
                    this.parallelBranchesData = []
                }
                
                // 解析 multi_level_config（多级审批配置）
                if(row.multi_level_config) {
                    try {
                        const config = typeof row.multi_level_config === 'string' ? JSON.parse(row.multi_level_config) : row.multi_level_config
                        this.multiLevelData = Array.isArray(config) ? config : []
                    } catch(e) {
                        console.error('解析 multi_level_config 失败:', e)
                        this.multiLevelData = []
                    }
                } else {
                    this.multiLevelData = []
                }
                
                // 解析 skip_approval_config（自动跳过审批配置）
                if(row.skip_approval_config) {
                    try {
                        const skipConfig = typeof row.skip_approval_config === 'string' ? JSON.parse(row.skip_approval_config) : row.skip_approval_config
                        this.stepForm.skip_approval_enabled = skipConfig.enabled || false
                        const conditions = skipConfig.skip_conditions || {}
                        this.stepForm.skip_is_dept_owner = conditions.is_dept_owner || false
                        this.stepForm.skip_specified_users = conditions.specified_users || []
                        this.stepForm.skip_specified_roles = conditions.specified_roles || []
                        this.stepForm.skip_scan_status_pass = conditions.scan_status_pass || false
                        this.stepForm.skip_target_step = skipConfig.target_step_id || null
                    } catch(e) {
                        console.error('解析 skip_approval_config 失败:', e)
                        this.stepForm.skip_approval_enabled = false
                        this.stepForm.skip_is_dept_owner = false
                        this.stepForm.skip_specified_users = []
                        this.stepForm.skip_specified_roles = []
                        this.stepForm.skip_scan_status_pass = false
                        this.stepForm.skip_target_step = null
                    }
                } else {
                    this.stepForm.skip_approval_enabled = false
                    this.stepForm.skip_is_dept_owner = false
                    this.stepForm.skip_specified_users = []
                    this.stepForm.skip_specified_roles = []
                    this.stepForm.skip_scan_status_pass = false
                    this.stepForm.skip_target_step = null
                }
                
                this.stepEditTitle = '编辑步骤'
                this.stepEditDialogVisible = true
            },
            handleStepSubmit(){
                if(!this.stepForm.step_name) {
                    this.$message.warning('请填写步骤名称')
                    return
                }
                
                let vm = this
                
                // 根据节点类型构建 condition_rules
                if(vm.stepForm.node_type === 2) {  // 抄送节点
                    vm.stepForm.condition_rules = {
                        cc_type: vm.ccTypeInStep,
                        cc_role: vm.ccTypeInStep === 1 ? vm.ccRoleInStep : null,
                        cc_dept: (vm.ccTypeInStep === 2 || vm.ccTypeInStep === 3) ? vm.ccDeptInStep : null,
                        cc_users: vm.ccTypeInStep === 4 ? vm.ccUsersInStep : null,
                        cc_group: vm.ccTypeInStep === 6 ? vm.ccGroupInStep : null
                    }
                    // 验证抄送节点配置
                    if(vm.ccTypeInStep === 1 && !vm.ccRoleInStep) {
                        vm.$message.warning('请选择抄送角色')
                        return
                    } else if((vm.ccTypeInStep === 2 || vm.ccTypeInStep === 3) && !vm.ccDeptInStep) {
                        vm.$message.warning('请选择抄送部门')
                        return
                    } else if(vm.ccTypeInStep === 4 && (!vm.ccUsersInStep || vm.ccUsersInStep.length === 0)) {
                        vm.$message.warning('请选择抄送人员')
                        return
                    } else if(vm.ccTypeInStep === 6 && !vm.ccGroupInStep) {
                        vm.$message.warning('请选择抄送审批组')
                        return
                    }
                } else if(vm.stepForm.node_type === 3) {  // 条件分支节点
                    vm.stepForm.condition_rules = vm.conditionRulesData
                    // 验证条件分支配置
                    if(!vm.conditionRulesData || vm.conditionRulesData.length === 0) {
                        vm.$message.warning('请至少添加一个条件分支')
                        return
                    }
                    // 验证每个条件的完整性
                    for(let i = 0; i < vm.conditionRulesData.length; i++) {
                        const cond = vm.conditionRulesData[i]
                        if(!cond.field || !cond.operator || !cond.value || !cond.target_step) {
                            vm.$message.warning(`请完整填写第${i+1}个条件的信息`)
                            return
                        }
                    }
                } else if(vm.stepForm.node_type === 4) {  // 并行网关节点
                    vm.stepForm.condition_rules = {
                        branches: vm.parallelBranchesData
                    }
                    // 验证并行分支配置
                    if(!vm.parallelBranchesData || vm.parallelBranchesData.length === 0) {
                        vm.$message.warning('请至少添加一个并行分支')
                        return
                    }
                    // 验证每个分支的完整性
                    for(let i = 0; i < vm.parallelBranchesData.length; i++) {
                        const branch = vm.parallelBranchesData[i]
                        if(!branch.target_step) {
                            vm.$message.warning(`请为第${i+1}个分支选择目标步骤`)
                            return
                        }
                    }
                } else if(vm.stepForm.node_type === 1) {  // 普通审批节点
                    // 如果是多级审批，保存层级配置
                    if(vm.stepForm.approver_type === 6) {
                        vm.stepForm.multi_level_config = vm.multiLevelData
                        // 验证多级审批配置
                        if(!vm.multiLevelData || vm.multiLevelData.length === 0) {
                            vm.$message.warning('多级审批至少需要配置一个层级')
                            return
                        }
                        // 验证每个层级的配置
                        for(let i = 0; i < vm.multiLevelData.length; i++) {
                            const level = vm.multiLevelData[i]
                            const levelApproverType = level.approver_type
                            if(levelApproverType === 1 && !level.approver_role) {
                                vm.$message.warning(`第${i+1}级指定角色类型必须选择审批角色`)
                                return
                            } else if(levelApproverType === 2 && !level.approver_dept) {
                                vm.$message.warning(`第${i+1}级指定部门类型必须选择审批部门`)
                                return
                            } else if(levelApproverType === 4 && (!level.approver_users || level.approver_users.length === 0)) {
                                vm.$message.warning(`第${i+1}级指定人员类型必须选择审批人员`)
                                return
                            }
                        }
                    } else {
                        vm.stepForm.multi_level_config = null
                    }
                    
                    // 验证审批人配置（非多级审批）
                    if(vm.stepForm.approver_type !== 6) {
                        if(vm.stepForm.approver_type === 1 && !vm.stepForm.approver_role) {
                            vm.$message.warning('请选择审批角色')
                            return
                        } else if((vm.stepForm.approver_type === 2 || vm.stepForm.approver_type === 3) && !vm.stepForm.approver_dept) {
                            vm.$message.warning('请选择审批部门')
                            return
                        } else if(vm.stepForm.approver_type === 4 && (!vm.stepForm.approver_users || vm.stepForm.approver_users.length === 0)) {
                            vm.$message.warning('请选择审批人员')
                            return
                        } else if(vm.stepForm.approver_type === 10 && !vm.stepForm.approver_group) {
                            vm.$message.warning('请选择审批组')
                            return
                        }
                    }
                } else if(vm.stepForm.node_type === 5) {
                    // 结束节点不需要特殊验证
                }
                
                // 构建自动跳过审批配置
                if(vm.stepForm.node_type === 1 && vm.stepForm.skip_approval_enabled) {
                    // 验证：启用跳过时必须选择至少一个条件和目标步骤
                    if(!vm.stepForm.skip_is_dept_owner && 
                       (!vm.stepForm.skip_specified_users || vm.stepForm.skip_specified_users.length === 0) && 
                       (!vm.stepForm.skip_specified_roles || vm.stepForm.skip_specified_roles.length === 0) &&
                       !vm.stepForm.skip_scan_status_pass) {
                        vm.$message.warning('请至少选择一个跳过条件')
                        return
                    }
                    if(!vm.stepForm.skip_target_step) {
                        vm.$message.warning('请选择目标步骤')
                        return
                    }
                    vm.stepForm.skip_approval_config = {
                        enabled: true,
                        skip_conditions: {
                            is_dept_owner: vm.stepForm.skip_is_dept_owner,
                            specified_users: vm.stepForm.skip_specified_users || [],
                            specified_roles: vm.stepForm.skip_specified_roles || [],
                            scan_status_pass: vm.stepForm.skip_scan_status_pass
                        },
                        target_step_id: vm.stepForm.skip_target_step
                    }
                } else {
                    vm.stepForm.skip_approval_config = null
                }
                
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
                    cc_group: '',
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
                // 校验：自定义审批组类型必须选择审批组
                if(vm.ccForm.cc_type === 6 && !vm.ccForm.cc_group) {
                    vm.$message.warning('请选择抄送审批组')
                    return
                }
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
                    auto_fill: false,
                    readonly: false,
                    placeholder: '',
                    defaultValue: '',
                    options: '',
                    conditional_rules: []
                }
                this.fieldEditTitle = '新增字段'
                this.fieldEditDialogVisible = true
            },
            handleEditFormField(row, index) {
                this.fieldForm = {...row}
                // auto_fill 兼容旧数据：旧版标记为角色字符串（package_path/package_version_name），统一转为布尔开关
                this.fieldForm.auto_fill = !!this.fieldForm.auto_fill
                // readonly 兼容旧数据：旧版无此字段，统一转为布尔开关
                this.fieldForm.readonly = !!this.fieldForm.readonly
                // 如果是选项类型，将 options 数组转为字符串
                if(row.options && Array.isArray(row.options)) {
                    this.fieldForm.options = row.options.map(opt => `${opt.label}:${opt.value}`).join('\n')
                }
                // 确保 conditional_rules 存在
                if(!this.fieldForm.conditional_rules) {
                    this.fieldForm.conditional_rules = []
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
                // auto_fill 空值统一存 null，避免冗余空字符串（false/undefined/null 均归一为 null，true 保持 true）
                if(!fieldData.auto_fill) {
                    fieldData.auto_fill = null
                }
                // readonly 空值统一存 null，与 auto_fill 保持一致（false/undefined/null 均归一为 null，true 保持 true）
                if(!fieldData.readonly) {
                    fieldData.readonly = null
                }
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
                
                console.log('[handleFieldSubmit] 保存字段:', fieldData)
                console.log('[handleFieldSubmit] 联动规则:', fieldData.conditional_rules)
                
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
            },
            // 添加联动规则
            addConditionalRule() {
                if(!this.fieldForm.conditional_rules) {
                    this.fieldForm.conditional_rules = []
                }
                this.fieldForm.conditional_rules.push({
                    trigger_field: '',
                    operator: '==',
                    trigger_value: '',
                    action: 'required'
                })
            },
            // 删除联动规则
            removeConditionalRule(index) {
                this.fieldForm.conditional_rules.splice(index, 1)
            },
            // 获取触发字段的类型
            getTriggerFieldType(fieldName) {
                const field = this.formFieldsData.find(f => f.field === fieldName)
                return field ? field.type : ''
            },
            // 当触发字段改变时，智能推荐操作符
            onTriggerFieldChange(rule) {
                const fieldType = this.getTriggerFieldType(rule.trigger_field)
                // 如果是复选框，自动切换为"包含"操作符
                if (fieldType === 'checkbox' && rule.operator === '==') {
                    rule.operator = 'contains'
                }
            },
            // 获取触发字段的可用选项列表
            getTriggerFieldOptions(fieldName) {
                const field = this.formFieldsData.find(f => f.field === fieldName)
                if (!field || !field.options) {
                    return []
                }
                
                // 如果 options 是字符串，解析它
                let options = field.options
                if (typeof options === 'string') {
                    try {
                        options = JSON.parse(options)
                    } catch (e) {
                        // 如果不是 JSON，尝试解析 label:value 格式
                        options = options.split('\n').map(line => {
                            const parts = line.split(':')
                            if (parts.length >= 2) {
                                return {
                                    label: parts[0].trim(),
                                    value: parts.slice(1).join(':').trim()
                                }
                            }
                            return null
                        }).filter(opt => opt !== null)
                    }
                }
                
                // 如果已经是数组，直接返回
                if (Array.isArray(options)) {
                    return options.map(opt => ({
                        label: typeof opt === 'object' ? opt.label : opt,
                        value: typeof opt === 'object' ? opt.value : opt
                    }))
                }
                
                return []
            },
            // ========== 节点配置相关方法 ==========
            handleNodeTypeChange() {
                // 当节点类型改变时，重置相关数据
                if(this.stepForm.node_type === 2) {  // 抄送节点
                    this.ccTypeInStep = 1
                    this.ccRoleInStep = ''
                    this.ccDeptInStep = ''
                    this.ccUsersInStep = []
                } else if(this.stepForm.node_type === 3) {  // 条件分支节点
                    this.conditionRulesData = []
                } else if(this.stepForm.node_type === 4) {  // 并行网关节点
                    this.parallelBranchesData = []
                }
            },
            // 条件分支相关方法
            handleAddCondition() {
                this.conditionRulesData.push({
                    field: '',
                    operator: '==',
                    value: '',
                    target_step: null
                })
            },
            handleDeleteCondition(index) {
                this.conditionRulesData.splice(index, 1)
            },
            // 并行分支相关方法
            handleAddBranch() {
                this.parallelBranchesData.push({
                    branch_name: `分支${this.parallelBranchesData.length + 1}`,
                    target_step: null
                })
            },
            handleDeleteBranch(index) {
                this.parallelBranchesData.splice(index, 1)
            },
            // 多级审批相关方法
            handleAddMultiLevel() {
                this.multiLevelData.push({
                    name: `第${this.multiLevelData.length + 1}级`,
                    approver_type: 1,
                    approver_role: '',
                    approver_dept: '',
                    approver_users: []
                })
            },
            handleDeleteMultiLevel(index) {
                this.multiLevelData.splice(index, 1)
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
