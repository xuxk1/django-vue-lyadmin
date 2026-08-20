<template>
    <div :class="{'ly-is-full':isFull}">
        <!-- 搜索区域 -->
        <div class="tableSelect" ref="tableSelect">
            <el-form :inline="true" :model="formInline" label-position="left">
                <el-form-item label="流程类型">
                    <el-select v-model="formInline.workflow_type" placeholder="请选择流程类型" clearable @change="search" size="default" style="width:200px">
                        <el-option v-for="item in workflowTypes" :key="item.id" :label="item.name" :value="item.id"></el-option>
                    </el-select>
                </el-form-item>
                <el-form-item label="步骤名称">
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
                                <span v-else-if="level.approver_type==3">{{ level.approver_dept && level.approver_dept.length > 0 ? getDeptName(level.approver_dept) + '负责人' : '申请人部门负责人' }}</span>
                                <span v-else-if="level.approver_type==4">人员: {{ getUserNames(level.approver_users) }}</span>
                                <span v-else-if="level.approver_type==5">申请人自选</span>
                                <span v-else-if="level.approver_type==7">发起人</span>
                                <span v-else>未配置</span>
                            </div>
                        </div>
                        <!-- 普通审批 -->
                        <span v-else-if="scope.row.approver_type==1">{{ scope.row.approver_role_name || '-' }}</span>
                        <span v-else-if="scope.row.approver_type==2">{{ scope.row.approver_dept_name || '-' }}</span>
                        <span v-else-if="scope.row.approver_type==3">{{ scope.row.approver_dept_name ? scope.row.approver_dept_name + '负责人' : '申请人部门负责人' }}</span>
                        <span v-else-if="scope.row.approver_type==4">
                            <span v-for="(user, index) in scope.row.approver_users_info" :key="index">
                                {{ user.name }}<span v-if="index < scope.row.approver_users_info.length - 1">, </span>
                            </span>
                        </span>
                        <span v-else-if="scope.row.approver_type==5">申请人自选</span>
                        <span v-else-if="scope.row.approver_type==7">发起人</span>
                        <span v-else-if="scope.row.approver_type==10">审批组: {{ scope.row.approver_group_name || '-' }}</span>
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
                    <el-select v-model="editForm.workflow_type" placeholder="请选择流程类型" style="width: 100%" :disabled="!!editForm.id" @change="handleEditWorkflowTypeChange">
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
                
                <!-- 产品线标识（用于区分不同产品线的确认节点） -->
                <el-form-item label="产品线">
                    <el-input v-model="editForm.product_line" placeholder="如：RC、EMIR&Grid、STA、Phybolt" style="width: 100%"></el-input>
                    <div style="margin-top: 5px; font-size: 12px; color: #909399;">
                        标识该节点所属的产品线，用于发起人确认时根据产品线判断抄送人
                    </div>
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
                            <el-option label="发起人" :value="7"></el-option>
                            <el-option label="条件化审批人" :value="8"></el-option>
                            <el-option label="自定义审批组" :value="10"></el-option>
                        </el-select>
                    </el-form-item>
                    <el-form-item label="审批角色" v-if="editForm.approver_type==1" required>
                        <el-select v-model="editForm.approver_role" placeholder="请选择角色" style="width: 100%">
                            <el-option v-for="item in roles" :key="item.id" :label="item.name" :value="item.id"></el-option>
                        </el-select>
                    </el-form-item>
                    <el-form-item label="审批部门" v-if="editForm.approver_type==2" required>
                        <el-select v-model="editForm.approver_dept" multiple placeholder="请选择部门（可多选）" style="width: 100%">
                            <el-option v-for="item in depts" :key="item.id" :label="item.name" :value="item.id"></el-option>
                        </el-select>
                    </el-form-item>
                    <el-form-item label="审批部门" v-if="editForm.approver_type==3">
                        <el-select v-model="editForm.approver_dept" multiple placeholder="不选则自动使用申请人部门" clearable style="width: 100%">
                            <el-option v-for="item in depts" :key="item.id" :label="item.name" :value="item.id"></el-option>
                        </el-select>
                        <div style="margin-top: 5px; font-size: 12px; color: #909399;">
                            未选择部门时，系统将自动根据申请人的实际部门查找负责人
                        </div>
                    </el-form-item>
                    <el-form-item label="审批人员" v-if="editForm.approver_type==4" required>
                        <el-select v-model="editForm.approver_users" multiple placeholder="请选择人员" style="width: 100%">
                            <el-option v-for="item in users" :key="item.id" :label="item.name" :value="item.id"></el-option>
                        </el-select>
                    </el-form-item>
                    <el-form-item label="审批组" v-if="editForm.approver_type==10" required>
                        <div style="display: flex; gap: 8px; width: 100%;">
                            <el-select v-model="editForm.approver_group" placeholder="请选择审批组" style="flex: 1;">
                                <el-option v-for="item in approvalGroups" :key="item.id" :label="item.product_line ? item.name + '（' + item.product_line + '）' : item.name" :value="item.id"></el-option>
                            </el-select>
                            <el-button type="primary" plain @click="openGroupManage">管理审批组</el-button>
                        </div>
                        <div style="margin-top: 5px; font-size: 12px; color: #909399;">
                            当前组成员：{{ getGroupMembersDisplay(editForm.approver_group) }}。组成员可随时增删，审批人随审批组动态更新
                        </div>
                    </el-form-item>
                    
                    <!-- 发起人 -->
                    <el-alert 
                        v-if="editForm.approver_type==7"
                        title="审批人为流程发起人（申请人），无需额外配置"
                        type="info"
                        :closable="false"
                        show-icon
                        style="margin-bottom: 15px;"
                    />
                    
                    <!-- 产品线抄送规则配置（仅发起人类型显示） -->
                    <template v-if="editForm.approver_type==7">
                        <el-divider content-position="left">产品线抄送规则配置</el-divider>
                        <el-alert
                            title="提示：配置产品线抄送规则后，当发起人确认时，系统会根据已完成的产品线节点自动确定抄送人"
                            type="info"
                            :closable="false"
                            show-icon
                            style="margin-bottom: 15px;"
                        />
                        
                        <div style="margin-bottom: 10px;">
                            <el-button type="primary" icon="Plus" @click="addProductLineCcRule" size="small">添加产品线抄送规则</el-button>
                        </div>
                        
                        <div v-for="(rule, ruleIndex) in editForm.product_line_cc_rules" :key="ruleIndex" 
                             style="margin-bottom: 15px; padding: 15px; border: 1px solid #dcdfe6; border-radius: 4px; background-color: #fafafa;">
                            
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                                <strong style="color: #409EFF;">产品线抄送规则 {{ ruleIndex + 1 }}</strong>
                                <el-button type="danger" size="small" icon="Delete" circle @click="removeProductLineCcRule(ruleIndex)"></el-button>
                            </div>
                            
                            <!-- 产品线标识 -->
                            <el-form-item label="产品线" label-width="100px" required>
                                <el-input v-model="rule.product_line" placeholder="如：RC、EMIR&Grid、STA、Phybolt" size="small" style="width: 100%"></el-input>
                                <div style="margin-top: 5px; font-size: 12px; color: #909399;">
                                    必须与产品线确认节点的“产品线”字段值完全一致
                                </div>
                            </el-form-item>
                            
                            <!-- 抄送人类型 -->
                            <el-form-item label="抄送人类型" label-width="100px" required>
                                <el-select v-model="rule.cc_type" placeholder="请选择" size="small" style="width: 100%">
                                    <el-option label="指定角色" :value="1"></el-option>
                                    <el-option label="指定部门" :value="2"></el-option>
                                    <el-option label="部门负责人" :value="3"></el-option>
                                    <el-option label="指定人员" :value="4"></el-option>
                                    <el-option label="发起人" :value="5"></el-option>
                                    <el-option label="自定义审批组" :value="6"></el-option>
                                </el-select>
                            </el-form-item>
                            
                            <!-- 指定角色 -->
                            <el-form-item label="抄送角色" v-if="rule.cc_type==1" label-width="100px" required>
                                <el-select v-model="rule.cc_role" placeholder="请选择角色" size="small" style="width: 100%">
                                    <el-option v-for="item in roles" :key="item.id" :label="item.name" :value="item.id"></el-option>
                                </el-select>
                            </el-form-item>
                            
                            <!-- 指定部门/部门负责人 -->
                            <el-form-item label="抄送部门" v-if="rule.cc_type==2 || rule.cc_type==3" label-width="100px" required>
                                <el-select v-model="rule.cc_dept" multiple placeholder="请选择部门" size="small" style="width: 100%">
                                    <el-option v-for="item in depts" :key="item.id" :label="item.name" :value="item.id"></el-option>
                                </el-select>
                            </el-form-item>
                            
                            <!-- 指定人员 -->
                            <el-form-item label="抄送人员" v-if="rule.cc_type==4" label-width="100px" required>
                                <el-select v-model="rule.cc_users" multiple placeholder="请选择人员" size="small" style="width: 100%">
                                    <el-option v-for="item in users" :key="item.id" :label="item.name" :value="item.id"></el-option>
                                </el-select>
                            </el-form-item>
                            
                            <!-- 发起人 -->
                            <el-alert 
                                v-if="rule.cc_type==5"
                                title="抄送人为流程发起人（申请人）"
                                type="info"
                                :closable="false"
                                show-icon
                            />

                            <!-- 自定义审批组 -->
                            <el-form-item label="抄送审批组" v-if="rule.cc_type==6" label-width="100px" required>
                                <el-select v-model="rule.cc_group" placeholder="请选择审批组" size="small" style="width: 100%">
                                    <el-option v-for="item in approvalGroups" :key="item.id" :label="item.product_line ? item.name + '（' + item.product_line + '）' : item.name" :value="item.id"></el-option>
                                </el-select>
                                <div style="margin-top: 5px; font-size: 12px; color: #909399;">
                                    抄送人为审批组成员，成员可在“管理审批组”中动态增删
                                </div>
                            </el-form-item>
                        </div>
                        
                        <div v-if="!editForm.product_line_cc_rules || editForm.product_line_cc_rules.length === 0" 
                             style="color: #909399; font-size: 13px; padding: 10px; background-color: #f5f7fa; border-radius: 4px;">
                            <i class="el-icon-info"></i> 请添加至少一个产品线抄送规则
                        </div>
                    </template>
                    
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
                                            icon="Delete"
                                            circle
                                            @click="removeApprovalLevel(index)"
                                        ></el-button>
                                    </div>
                                    
                                    <!-- 层级名称 -->
                                    <el-form-item label="层级名称" required>
                                        <el-input v-model="level.name" placeholder="如：直接上级审批" size="small"></el-input>
                                    </el-form-item>
                                    
                                    <!-- 审批人类型 -->
                                    <el-form-item label="审批人类型" required>
                                        <el-select v-model="level.approver_type" placeholder="请选择" size="small" style="width: 100%" @change="handleLevelTypeChange(level)">
                                            <el-option label="指定角色" :value="1"></el-option>
                                            <el-option label="指定部门" :value="2"></el-option>
                                            <el-option label="部门负责人" :value="3"></el-option>
                                            <el-option label="指定人员" :value="4"></el-option>
                                            <el-option label="申请人自选" :value="5"></el-option>
                                            <el-option label="发起人" :value="7"></el-option>
                                        </el-select>
                                    </el-form-item>
                                    
                                    <!-- 指定角色 -->
                                    <el-form-item label="审批角色" v-if="level.approver_type==1" required>
                                        <el-select v-model="level.approver_role" placeholder="请选择角色" size="small" style="width: 100%">
                                            <el-option v-for="item in roles" :key="item.id" :label="item.name" :value="item.id"></el-option>
                                        </el-select>
                                    </el-form-item>
                                    
                                    <!-- 指定部门/部门负责人 -->
                                    <el-form-item label="审批部门" v-if="level.approver_type==2" required>
                                        <el-select v-model="level.approver_dept" multiple placeholder="请选择部门（可多选）" size="small" style="width: 100%">
                                            <el-option v-for="item in depts" :key="item.id" :label="item.name" :value="item.id"></el-option>
                                        </el-select>
                                    </el-form-item>
                                    <el-form-item label="审批部门" v-if="level.approver_type==3">
                                        <el-select v-model="level.approver_dept" multiple placeholder="不选则自动使用申请人部门" clearable size="small" style="width: 100%">
                                            <el-option v-for="item in depts" :key="item.id" :label="item.name" :value="item.id"></el-option>
                                        </el-select>
                                        <div style="margin-top: 5px; font-size: 12px; color: #909399;">
                                            未选择部门时，系统将自动根据申请人的实际部门查找负责人
                                        </div>
                                    </el-form-item>
                                    
                                    <!-- 指定人员 -->
                                    <el-form-item label="审批人员" v-if="level.approver_type==4" required>
                                        <el-select v-model="level.approver_users" multiple placeholder="请选择人员" size="small" style="width: 100%">
                                            <el-option v-for="item in users" :key="item.id" :label="item.name" :value="item.id"></el-option>
                                        </el-select>
                                    </el-form-item>
                                    
                                    <!-- 申请人自选 -->
                                    <el-alert 
                                        v-if="level.approver_type==5"
                                        title="申请人将在发起流程时自行选择审批人"
                                        type="info"
                                        :closable="false"
                                        show-icon
                                        style="margin-top: 10px;"
                                    />
                                    
                                    <!-- 发起人 -->
                                    <el-alert 
                                        v-if="level.approver_type==7"
                                        title="审批人为流程发起人（申请人）"
                                        type="info"
                                        :closable="false"
                                        show-icon
                                        style="margin-top: 10px;"
                                    />
                                    
                                    <!-- 层级条件配置 -->
                                    <el-divider content-position="left">层级执行条件（可选）</el-divider>
                                    <el-alert 
                                        title="提示：如果配置了条件，只有满足条件时才会执行该层级审批。不配置条件则始终执行。" 
                                        type="info" 
                                        :closable="false"
                                        style="margin-bottom: 10px;"
                                    />
                                    
                                    <!-- 条件关系 -->
                                    <el-form-item label="条件关系">
                                        <el-radio-group v-model="level.condition_relation" size="small">
                                            <el-radio label="and">并且</el-radio>
                                            <el-radio label="or">或者</el-radio>
                                        </el-radio-group>
                                        <span style="margin-left: 10px; color: #909399; font-size: 12px;">
                                            （如果设置了多个条件，{{ level.condition_relation == 'and' ? '需要同时满足所有条件' : '任何一个条件满足即可' }}）
                                        </span>
                                    </el-form-item>
                                    
                                    <!-- 条件列表 -->
                                    <el-table :data="level.conditions || []" border style="width: 100%; margin-bottom: 10px;">
                                        <el-table-column prop="field" label="字段名" width="200">
                                            <template #default="scope">
                                                <el-select v-model="scope.row.field" placeholder="请选择字段" size="small" style="width: 100%" filterable>
                                                    <el-option v-for="item in formFields" :key="item.value" :label="item.label" :value="item.value"></el-option>
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
                                                </el-select>
                                            </template>
                                        </el-table-column>
                                        <el-table-column prop="value" label="比较值" min-width="150">
                                            <template #default="scope">
                                                <el-input v-model="scope.row.value" placeholder="如：EMIR" size="small"></el-input>
                                            </template>
                                        </el-table-column>
                                        <el-table-column label="操作" width="80" align="center">
                                            <template #default="scope">
                                                <el-button type="danger" icon="Delete" size="small" circle @click="removeLevelCondition(index, scope.$index)"></el-button>
                                            </template>
                                        </el-table-column>
                                    </el-table>
                                    
                                    <el-button type="primary" icon="Plus" @click="addLevelCondition(index)" size="small">添加条件</el-button>
                                </div>
                            </div>
                        </el-form-item>
                    </template>
                    
                    <!-- 节点内部条件配置（仅普通审批节点显示） -->
                    <template v-if="editForm.node_type==1">
                        <el-divider content-position="left">条件化审批人配置</el-divider>
                        <el-alert
                            title="提示：根据表单字段值动态决定审批人。如果配置了条件，则只有满足条件的情况下才会创建该节点的审批任务。"
                            type="info"
                            :closable="false"
                            show-icon
                            style="margin-bottom: 15px;"
                        />
                        
                        <!-- 条件组列表 -->
                        <div v-for="(group, groupIndex) in editForm.internal_conditions" :key="groupIndex" 
                             style="margin-bottom: 20px; padding: 15px; border: 1px solid #dcdfe6; border-radius: 4px; background-color: #fafafa;">
                            
                            <!-- 条件组名称 -->
                            <el-form-item :label="'条件组' + (groupIndex + 1)">
                                <el-input v-model="group.condition_group" placeholder="如：EMIR&Grid" size="small"></el-input>
                            </el-form-item>
                            
                            <!-- 条件关系 -->
                            <el-form-item label="条件关系">
                                <el-radio-group v-model="group.condition_relation" size="small">
                                    <el-radio label="and">并且</el-radio>
                                    <el-radio label="or">或者</el-radio>
                                </el-radio-group>
                                <span style="margin-left: 10px; color: #909399; font-size: 12px;">
                                    （如果设置了多个条件，{{ group.condition_relation == 'and' ? '需要同时满足所有条件' : '任何一个条件满足即可' }}）
                                </span>
                            </el-form-item>
                            
                            <!-- 条件列表 -->
                            <el-table :data="group.conditions" border style="width: 100%; margin-bottom: 10px;">
                                <el-table-column prop="field" label="字段名" width="200">
                                    <template #default="scope">
                                        <el-select v-model="scope.row.field" placeholder="请选择字段" size="small" style="width: 100%" filterable>
                                            <el-option v-for="item in formFields" :key="item.value" :label="item.label" :value="item.value"></el-option>
                                        </el-select>
                                    </template>
                                </el-table-column>
                                <el-table-column prop="operator" label="操作符" width="120">
                                    <template #default="scope">
                                        <el-select v-model="scope.row.operator" placeholder="请选择" size="small" style="width: 100%">
                                            <el-option label="等于" value="=="></el-option>
                                            <el-option label="不等于" value="!="></el-option>
                                            <el-option label="大于" value="&gt;"></el-option>
                                            <el-option label="小于" value="<"></el-option>
                                            <el-option label="大于等于" value=">="></el-option>
                                            <el-option label="小于等于" value="<="></el-option>
                                            <el-option label="包含" value="contains"></el-option>
                                            <el-option label="不包含" value="not_contains"></el-option>
                                        </el-select>
                                    </template>
                                </el-table-column>
                                <el-table-column prop="value" label="比较值" min-width="150">
                                    <template #default="scope">
                                        <el-input v-model="scope.row.value" placeholder="如：EMIR" size="small"></el-input>
                                    </template>
                                </el-table-column>
                                <el-table-column label="操作" width="80" align="center">
                                    <template #default="scope">
                                        <el-button type="danger" icon="Delete" size="small" circle @click="removeCondition(groupIndex, scope.$index)"></el-button>
                                    </template>
                                </el-table-column>
                            </el-table>
                            
                            <el-button type="primary" icon="Plus" @click="addCondition(groupIndex)" size="small">添加条件</el-button>
                            
                            <!-- 审批人配置 -->
                            <el-divider>审批人配置</el-divider>
                            <div style="margin-bottom: 10px;">
                                <div v-for="(approver, approverIndex) in group.approvers_config" :key="approverIndex" 
                                     style="display: flex; align-items: center; margin-bottom: 8px; padding: 8px; background-color: #f5f7fa; border-radius: 4px;">
                                    
                                    <!-- 审批人标签显示 -->
                                    <div style="flex: 1; display: flex; align-items: center; gap: 8px;">
                                        <el-tag v-if="approver.approver_type==1" type="primary" size="medium">
                                            指定角色: {{ getRoleName(approver.approver_role) }}
                                        </el-tag>
                                        <el-tag v-else-if="approver.approver_type==2" type="success" size="medium">
                                            指定部门: {{ getDeptName(approver.approver_dept) }}
                                        </el-tag>
                                        <el-tag v-else-if="approver.approver_type==3" type="warning" size="medium">
                                            {{ approver.approver_dept && approver.approver_dept.length > 0 ? getDeptName(approver.approver_dept) + '负责人' : '申请人部门负责人' }}
                                        </el-tag>
                                        <el-tag v-else-if="approver.approver_type==4" type="info" size="medium">
                                            指定人员: {{ getUserNames(approver.approver_users) }}
                                        </el-tag>
                                        <el-tag v-else-if="approver.approver_type==5" type="danger" size="medium">
                                            申请人自选
                                        </el-tag>
                                        <el-tag v-else-if="approver.approver_type==6" type="primary" size="medium">
                                            多级审批（组合）
                                        </el-tag>
                                        <el-tag v-else-if="approver.approver_type==7" type="success" size="medium">
                                            发起人
                                        </el-tag>
                                        <el-tag v-else-if="approver.approver_type==9" type="warning" size="medium">
                                            直接上级
                                        </el-tag>
                                        <el-tag v-else-if="approver.approver_type==10" type="danger" size="medium">
                                            自定义审批组: {{ getGroupName(approver.approver_group) }}
                                        </el-tag>
                                        <span v-else style="color: #909399;">未配置</span>
                                    </div>
                                    
                                    <!-- 删除按钮 -->
                                    <el-button 
                                        type="danger" 
                                        icon="Delete" 
                                        size="small" 
                                        circle 
                                        @click="removeApprover(groupIndex, approverIndex)"
                                        title="删除此审批人"
                                    ></el-button>
                                </div>
                                
                                <!-- 添加审批人按钮 -->
                                <el-dropdown @command="handleAddApprover($event, groupIndex)" trigger="click" style="margin-top: 5px;">
                                    <el-button type="primary" icon="Plus" size="small">
                                        + 追加选择
                                        <el-icon class="el-icon--right"><arrow-down /></el-icon>
                                    </el-button>
                                    <template #dropdown>
                                        <el-dropdown-menu>
                                            <el-dropdown-item :command="1">指定角色</el-dropdown-item>
                                            <el-dropdown-item :command="2">指定部门</el-dropdown-item>
                                            <el-dropdown-item :command="3">部门负责人</el-dropdown-item>
                                            <el-dropdown-item :command="4">指定人员</el-dropdown-item>
                                            <el-dropdown-item :command="5">申请人自选</el-dropdown-item>
                                            <el-dropdown-item :command="6">多级审批（组合）</el-dropdown-item>
                                            <el-dropdown-item :command="7">发起人</el-dropdown-item>
                                            <el-dropdown-item :command="9">直接上级</el-dropdown-item>
                                            <el-dropdown-item :command="10">自定义审批组</el-dropdown-item>
                                        </el-dropdown-menu>
                                    </template>
                                </el-dropdown>
                            </div>
                            
                            <!-- 当前编辑的审批人配置区域 -->
                            <div v-if="group.editing_approver_index !== undefined && group.editing_approver_index !== null" 
                                 style="margin-top: 15px; padding: 15px; border: 1px dashed #409EFF; border-radius: 4px; background-color: #ecf5ff;">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                                    <strong style="color: #409EFF;">配置审批人</strong>
                                    <el-button type="text" size="small" @click="cancelEditApprover(groupIndex)">取消</el-button>
                                </div>
                                
                                <el-form-item label="审批人类型" label-width="100px">
                                    <el-select v-model="group.approvers_config[group.editing_approver_index].approver_type" 
                                               placeholder="请选择" size="small" style="width: 100%">
                                        <el-option label="指定角色" :value="1"></el-option>
                                        <el-option label="指定部门" :value="2"></el-option>
                                        <el-option label="部门负责人" :value="3"></el-option>
                                        <el-option label="指定人员" :value="4"></el-option>
                                        <el-option label="申请人自选" :value="5"></el-option>
                                        <el-option label="多级审批（组合）" :value="6"></el-option>
                                        <el-option label="发起人" :value="7"></el-option>
                                        <el-option label="直接上级" :value="9"></el-option>
                                        <el-option label="自定义审批组" :value="10"></el-option>
                                    </el-select>
                                </el-form-item>
                                
                                <el-form-item label="审批角色" 
                                              v-if="group.approvers_config[group.editing_approver_index].approver_type==1" 
                                              label-width="100px">
                                    <el-select v-model="group.approvers_config[group.editing_approver_index].approver_role" 
                                               placeholder="请选择角色" size="small" style="width: 100%">
                                        <el-option v-for="item in roles" :key="item.id" :label="item.name" :value="item.id"></el-option>
                                    </el-select>
                                </el-form-item>
                                
                                <el-form-item label="审批部门" 
                                              v-if="group.approvers_config[group.editing_approver_index].approver_type==2" 
                                              label-width="100px" required>
                                    <el-select v-model="group.approvers_config[group.editing_approver_index].approver_dept" 
                                               multiple placeholder="请选择部门（可多选）" size="small" style="width: 100%">
                                        <el-option v-for="item in depts" :key="item.id" :label="item.name" :value="item.id"></el-option>
                                    </el-select>
                                </el-form-item>
                                <el-form-item label="审批部门" 
                                              v-if="group.approvers_config[group.editing_approver_index].approver_type==3" 
                                              label-width="100px">
                                    <el-select v-model="group.approvers_config[group.editing_approver_index].approver_dept" 
                                               multiple placeholder="不选则自动使用申请人部门" clearable size="small" style="width: 100%">
                                        <el-option v-for="item in depts" :key="item.id" :label="item.name" :value="item.id"></el-option>
                                    </el-select>
                                    <div style="margin-top: 5px; font-size: 12px; color: #909399;">
                                        未选择部门时，自动根据申请人实际部门查找负责人
                                    </div>
                                </el-form-item>
                                
                                <el-form-item label="审批人员" 
                                              v-if="group.approvers_config[group.editing_approver_index].approver_type==4" 
                                              label-width="100px">
                                    <el-select v-model="group.approvers_config[group.editing_approver_index].approver_users" 
                                               multiple placeholder="请选择人员" size="small" style="width: 100%">
                                        <el-option v-for="item in users" :key="item.id" :label="item.name" :value="item.id"></el-option>
                                    </el-select>
                                </el-form-item>
                                
                                <el-form-item label="审批组" 
                                              v-if="group.approvers_config[group.editing_approver_index].approver_type==10" 
                                              label-width="100px">
                                    <div style="display: flex; gap: 8px; width: 100%;">
                                        <el-select v-model="group.approvers_config[group.editing_approver_index].approver_group" 
                                                   placeholder="请选择审批组" size="small" style="flex: 1;">
                                            <el-option v-for="item in approvalGroups" :key="item.id" :label="item.product_line ? item.name + '（' + item.product_line + '）' : item.name" :value="item.id"></el-option>
                                        </el-select>
                                        <el-button type="primary" plain size="small" @click="openGroupManage">管理审批组</el-button>
                                    </div>
                                    <div style="margin-top: 5px; font-size: 12px; color: #909399;">
                                        当前组成员：{{ getGroupMembersDisplay(group.approvers_config[group.editing_approver_index].approver_group) }}。组成员可随时增删，审批人随审批组动态更新
                                    </div>
                                </el-form-item>
                                
                                <!-- 直接上级提示 -->
                                <el-alert 
                                    v-if="group.approvers_config[group.editing_approver_index].approver_type==9"
                                    title="审批人为当前申请人的直接上级（优先取申请人部门 owner，其次部门内角色含“负责人”的人员），无需额外配置"
                                    type="info" 
                                    :closable="false"
                                    style="margin-bottom: 10px;"
                                />
                                
                                <!-- 多级审批配置 -->
                                <template v-if="group.approvers_config[group.editing_approver_index].approver_type==6">
                                    <el-alert 
                                        title="注意：内部条件中的多级审批只支持单级配置，如需多级请使用独立的多级审批节点" 
                                        type="warning" 
                                        :closable="false"
                                        style="margin-bottom: 10px;"
                                    />
                                    <el-form-item label="审批人类型" label-width="100px">
                                        <el-select v-model="group.approvers_config[group.editing_approver_index].multi_level_config[0].approver_type" 
                                                   placeholder="请选择" size="small" style="width: 100%">
                                            <el-option label="指定角色" :value="1"></el-option>
                                            <el-option label="指定部门" :value="2"></el-option>
                                            <el-option label="部门负责人" :value="3"></el-option>
                                            <el-option label="指定人员" :value="4"></el-option>
                                            <el-option label="申请人自选" :value="5"></el-option>
                                            <el-option label="直接上级" :value="9"></el-option>
                                        </el-select>
                                    </el-form-item>
                                    
                                    <el-form-item label="审批角色" 
                                                  v-if="group.approvers_config[group.editing_approver_index].multi_level_config[0].approver_type==1" 
                                                  label-width="100px">
                                        <el-select v-model="group.approvers_config[group.editing_approver_index].multi_level_config[0].approver_role" 
                                                   placeholder="请选择角色" size="small" style="width: 100%">
                                            <el-option v-for="item in roles" :key="item.id" :label="item.name" :value="item.id"></el-option>
                                        </el-select>
                                    </el-form-item>
                                    
                                    <el-form-item label="审批部门" 
                                                  v-if="group.approvers_config[group.editing_approver_index].multi_level_config[0].approver_type==2" 
                                                  label-width="100px" required>
                                        <el-select v-model="group.approvers_config[group.editing_approver_index].multi_level_config[0].approver_dept" 
                                                   multiple placeholder="请选择部门（可多选）" size="small" style="width: 100%">
                                            <el-option v-for="item in depts" :key="item.id" :label="item.name" :value="item.id"></el-option>
                                        </el-select>
                                    </el-form-item>
                                    <el-form-item label="审批部门" 
                                                  v-if="group.approvers_config[group.editing_approver_index].multi_level_config[0].approver_type==3" 
                                                  label-width="100px">
                                        <el-select v-model="group.approvers_config[group.editing_approver_index].multi_level_config[0].approver_dept" 
                                                   multiple placeholder="不选则自动使用申请人部门" clearable size="small" style="width: 100%">
                                            <el-option v-for="item in depts" :key="item.id" :label="item.name" :value="item.id"></el-option>
                                        </el-select>
                                        <div style="margin-top: 5px; font-size: 12px; color: #909399;">
                                            未选择部门时，自动根据申请人实际部门查找负责人
                                        </div>
                                    </el-form-item>
                                    
                                    <el-form-item label="审批人员" 
                                                  v-if="group.approvers_config[group.editing_approver_index].multi_level_config[0].approver_type==4" 
                                                  label-width="100px">
                                        <el-select v-model="group.approvers_config[group.editing_approver_index].multi_level_config[0].approver_users" 
                                                   multiple placeholder="请选择人员" size="small" style="width: 100%">
                                            <el-option v-for="item in users" :key="item.id" :label="item.name" :value="item.id"></el-option>
                                        </el-select>
                                    </el-form-item>
                                </template>
                                
                                <div style="text-align: right; margin-top: 10px;">
                                    <el-button type="primary" size="small" @click="confirmEditApprover(groupIndex)">确认</el-button>
                                </div>
                            </div>
                            
                            <el-button type="danger" icon="Delete" @click="removeConditionGroup(groupIndex)" size="small" style="margin-top: 10px;">删除条件组</el-button>
                        </div>
                        
                        <el-button type="primary" icon="Plus" @click="addConditionGroup" size="small">添加条件组</el-button>
                    </template>
                </template>
                
                <!-- 抄送节点配置 -->
                <template v-if="editForm.node_type==2">
                    <el-divider content-position="left">抄送人配置</el-divider>
                    <el-alert
                        title="提示：抄送节点会将流程信息发送给指定人员，抄送人员可以查看但不能审批"
                        type="info"
                        :closable="false"
                        show-icon
                        style="margin-bottom: 15px;"
                    />
                    <el-form-item label="抄送人类型" required>
                        <el-select v-model="editForm.cc_type" placeholder="请选择" style="width: 100%">
                            <el-option label="指定角色" :value="1"></el-option>
                            <el-option label="指定部门" :value="2"></el-option>
                            <el-option label="部门负责人" :value="3"></el-option>
                            <el-option label="指定人员" :value="4"></el-option>
                            <el-option label="自定义审批组" :value="6"></el-option>
                        </el-select>
                    </el-form-item>
                    <el-form-item label="抄送角色" v-if="editForm.cc_type==1" required>
                        <el-select v-model="editForm.cc_role" placeholder="请选择角色" style="width: 100%">
                            <el-option v-for="item in roles" :key="item.id" :label="item.name" :value="item.id"></el-option>
                        </el-select>
                    </el-form-item>
                    <el-form-item label="抄送部门" v-if="editForm.cc_type==2 || editForm.cc_type==3" required>
                        <el-select v-model="editForm.cc_dept" placeholder="请选择部门" style="width: 100%">
                            <el-option v-for="item in depts" :key="item.id" :label="item.name" :value="item.id"></el-option>
                        </el-select>
                    </el-form-item>
                    <el-form-item label="抄送人员" v-if="editForm.cc_type==4" required>
                        <el-select v-model="editForm.cc_users" multiple placeholder="请选择人员" style="width: 100%">
                            <el-option v-for="item in users" :key="item.id" :label="item.name" :value="item.id"></el-option>
                        </el-select>
                    </el-form-item>
                    <el-form-item label="抄送审批组" v-if="editForm.cc_type==6" required>
                        <el-select v-model="editForm.cc_group" placeholder="请选择审批组" style="width: 100%">
                            <el-option v-for="item in approvalGroups" :key="item.id" :label="item.product_line ? item.name + '（' + item.product_line + '）' : item.name" :value="item.id"></el-option>
                        </el-select>
                    </el-form-item>
                </template>
                
                <!-- 条件分支节点配置 -->
                <template v-if="editForm.node_type==3">
                    <el-divider content-position="left">条件分支配置</el-divider>
                    <el-alert
                        title="提示：根据表单字段值判断流程走向，支持多种比较操作。"
                        type="info"
                        :closable="false"
                        show-icon
                        style="margin-bottom: 15px;"
                    />
                    <el-form-item label="默认下一步骤">
                        <el-select v-model="editForm.next_step_on_pass" placeholder="无匹配条件时的默认步骤" style="width: 100%" clearable>
                            <el-option v-for="item in tableData.filter(s => s.id !== editForm.id)" :key="item.id" :label="item.step_name" :value="item.id"></el-option>
                        </el-select>
                    </el-form-item>
                    
                    <div style="margin-bottom: 10px;">
                        <el-button type="primary" icon="Plus" @click="addConditionRule" size="small">添加条件</el-button>
                    </div>
                    <el-table :data="editForm.condition_rules" border style="width: 100%; margin-bottom: 15px;">
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
                                    <el-option label="大于" value="&gt;"></el-option>
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
                                    <el-option v-for="item in getAvailableTargetSteps()" :key="item.id" :label="item.step_name" :value="item.id"></el-option>
                                </el-select>
                            </template>
                        </el-table-column>
                        <el-table-column label="操作" width="80" align="center">
                            <template #default="scope">
                                <el-button type="danger" icon="Delete" size="small" circle @click="removeConditionRule(scope.$index)"></el-button>
                            </template>
                        </el-table-column>
                    </el-table>
                </template>
                
                <!-- 并行网关节点配置 -->
                <template v-if="editForm.node_type==4">
                    <el-divider content-position="left">并行分支配置</el-divider>
                    <el-alert
                        title="提示：同时创建多个分支任务，各分支并行执行。"
                        type="info"
                        :closable="false"
                        show-icon
                        style="margin-bottom: 15px;"
                    />
                    <div style="margin-bottom: 10px;">
                        <el-button type="primary" icon="Plus" @click="addParallelBranch" size="small">添加分支</el-button>
                    </div>
                    <el-table :data="editForm.parallel_branches" border style="width: 100%; margin-bottom: 15px;">
                        <el-table-column prop="branch_name" label="分支名称" width="150">
                            <template #default="scope">
                                <el-input v-model="scope.row.branch_name" placeholder="如：技术部审批" size="small"></el-input>
                            </template>
                        </el-table-column>
                        <el-table-column prop="target_step" label="目标步骤" min-width="200">
                            <template #default="scope">
                                <el-select v-model="scope.row.target_step" placeholder="请选择" size="small" style="width: 100%">
                                    <el-option v-for="item in tableData.filter(s => s.id !== editForm.id)" :key="item.id" :label="item.step_name" :value="item.id"></el-option>
                                </el-select>
                            </template>
                        </el-table-column>
                        <el-table-column label="操作" width="80" align="center">
                            <template #default="scope">
                                <el-button type="danger" icon="Delete" size="small" circle @click="removeParallelBranch(scope.$index)"></el-button>
                            </template>
                        </el-table-column>
                    </el-table>
                </template>
                
                <!-- 结束节点配置 -->
                <template v-if="editForm.node_type==5">
                    <el-divider content-position="left">结束节点说明</el-divider>
                    <el-alert
                        title="提示：结束节点标记流程完成，将流程状态设置为'已通过'，无需配置审批人"
                        type="success"
                        :closable="false"
                        show-icon
                        style="margin-bottom: 15px;"
                    />
                </template>
                
                <!-- 节点级抄送人配置（普通审批节点和结束节点均可配置） -->
                <template v-if="editForm.node_type==1 || editForm.node_type==5">
                    <el-divider content-position="left">抄送人配置（可选）</el-divider>
                    <el-alert
                        title="提示：配置抄送人后，流程到达该节点时会同时通知抄送人员"
                        type="info"
                        :closable="false"
                        show-icon
                        style="margin-bottom: 15px;"
                    />
                    <el-form-item label="抄送人类型">
                        <el-select v-model="editForm.cc_type" placeholder="不配置则无抄送人" style="width: 100%" clearable>
                            <el-option label="指定角色" :value="1"></el-option>
                            <el-option label="指定部门" :value="2"></el-option>
                            <el-option label="部门负责人" :value="3"></el-option>
                            <el-option label="指定人员" :value="4"></el-option>
                            <el-option label="发起人" :value="5"></el-option>
                            <el-option label="自定义审批组" :value="6"></el-option>
                        </el-select>
                    </el-form-item>
                    <el-form-item label="抄送角色" v-if="editForm.cc_type==1">
                        <el-select v-model="editForm.cc_role" placeholder="请选择角色" style="width: 100%">
                            <el-option v-for="item in roles" :key="item.id" :label="item.name" :value="item.id"></el-option>
                        </el-select>
                    </el-form-item>
                    <el-form-item label="抄送部门" v-if="editForm.cc_type==2 || editForm.cc_type==3">
                        <el-select v-model="editForm.cc_dept" multiple placeholder="请选择部门" style="width: 100%">
                            <el-option v-for="item in depts" :key="item.id" :label="item.name" :value="item.id"></el-option>
                        </el-select>
                    </el-form-item>
                    <el-form-item label="抄送人员" v-if="editForm.cc_type==4">
                        <el-select v-model="editForm.cc_users" multiple placeholder="请选择人员" style="width: 100%">
                            <el-option v-for="item in users" :key="item.id" :label="item.name" :value="item.id"></el-option>
                        </el-select>
                    </el-form-item>
                    <el-form-item label="抄送审批组" v-if="editForm.cc_type==6">
                        <el-select v-model="editForm.cc_group" placeholder="请选择审批组" style="width: 100%">
                            <el-option v-for="item in approvalGroups" :key="item.id" :label="item.product_line ? item.name + '（' + item.product_line + '）' : item.name" :value="item.id"></el-option>
                        </el-select>
                        <div style="margin-top: 5px; font-size: 12px; color: #909399;">
                            抄送人为审批组成员，成员可在“管理审批组”中动态增删
                        </div>
                    </el-form-item>
                    <el-alert 
                        v-if="editForm.cc_type==5"
                        title="抄送人为流程发起人（申请人）"
                        type="info"
                        :closable="false"
                        show-icon
                    />
                </template>
                
                <!-- 退回设置 -->
                <el-divider content-position="left">退回设置</el-divider>
                <el-form-item label="允许退回">
                    <el-switch v-model="editForm.allow_return"></el-switch>
                </el-form-item>
                <el-form-item label="允许驳回">
                    <el-switch v-model="editForm.allow_reject"></el-switch>
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
                    <el-switch v-model="editForm.skip_approval_enabled"></el-switch>
                </el-form-item>
                <template v-if="editForm.skip_approval_enabled">
                    <el-form-item label="跳过条件">
                        <div style="width: 100%">
                            <el-checkbox v-model="editForm.skip_is_dept_owner" style="margin-bottom: 8px; display: block;">
                                发起人是部门负责人（部门owner）
                            </el-checkbox>
                            <el-checkbox v-model="skip_specified_users_checked" style="margin-bottom: 8px; display: block;">
                                发起人为指定人员
                            </el-checkbox>
                            <el-select v-if="skip_specified_users_checked" v-model="editForm.skip_specified_users" multiple placeholder="请选择指定人员" style="width: 100%; margin-bottom: 8px;">
                                <el-option v-for="item in users" :key="item.id" :label="item.name" :value="item.id"></el-option>
                            </el-select>
                            <el-checkbox v-model="skip_specified_roles_checked" style="margin-bottom: 8px; display: block;">
                                发起人拥有指定角色
                            </el-checkbox>
                            <el-select v-if="skip_specified_roles_checked" v-model="editForm.skip_specified_roles" multiple placeholder="请选择指定角色" style="width: 100%;">
                                <el-option v-for="item in roles" :key="item.id" :label="item.name" :value="item.id"></el-option>
                            </el-select>
                            <el-checkbox v-model="editForm.skip_scan_status_pass" style="margin-bottom: 8px; display: block;">
                                包扫描状态为PASS
                            </el-checkbox>
                        </div>
                    </el-form-item>
                    <el-form-item label="目标步骤" required>
                        <el-select v-model="editForm.skip_target_step" placeholder="请选择跳过后的目标步骤" style="width: 100%" clearable>
                            <el-option v-for="item in getAvailableTargetSteps(true)" :key="item.id" :label="item.step_name" :value="item.id"></el-option>
                        </el-select>
                    </el-form-item>
                </template>
                
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

        <!-- 审批组管理对话框 -->
        <el-dialog v-model="groupDialogVisible" title="自定义审批组管理" width="800px" append-to-body>
            <el-alert
                title="提示：审批组用于按产品线等维度维护一组可动态调整的审批人（如“RC产品负责人”）。增删组成员后，所有引用该审批组的流程节点审批人自动更新，无需修改流程配置。"
                type="info"
                :closable="false"
                show-icon
                style="margin-bottom: 15px;"
            />
            <div style="margin-bottom: 10px; text-align: right;">
                <el-button type="primary" icon="Plus" @click="handleAddGroup">新建审批组</el-button>
            </div>
            <el-table :data="approvalGroups" border style="width: 100%;">
                <el-table-column prop="name" label="审批组名称" min-width="150"></el-table-column>
                <el-table-column prop="product_line" label="产品线" width="120">
                    <template #default="scope">
                        <span>{{ scope.row.product_line || '-' }}</span>
                    </template>
                </el-table-column>
                <el-table-column label="组成员" min-width="200">
                    <template #default="scope">
                        <el-tag v-for="member in scope.row.members_info" :key="member.id" size="small" style="margin: 2px;">
                            {{ member.name }}
                        </el-tag>
                        <span v-if="!scope.row.members_info || scope.row.members_info.length === 0" style="color: #909399;">未配置成员</span>
                    </template>
                </el-table-column>
                <el-table-column label="操作" width="160" align="center">
                    <template #default="scope">
                        <el-button type="primary" link size="small" @click="handleEditGroup(scope.row)">编辑</el-button>
                        <el-button type="danger" link size="small" @click="handleDeleteGroup(scope.row)">删除</el-button>
                    </template>
                </el-table-column>
            </el-table>
        </el-dialog>

        <!-- 审批组新建/编辑对话框 -->
        <el-dialog v-model="groupEditVisible" :title="groupForm.id ? '编辑审批组' : '新建审批组'" width="600px" append-to-body>
            <el-form :model="groupForm" label-width="100px">
                <el-form-item label="审批组名称" required>
                    <el-input v-model="groupForm.name" placeholder="如：RC产品负责人"></el-input>
                </el-form-item>
                <el-form-item label="产品线">
                    <el-input v-model="groupForm.product_line" placeholder="如：RC、GloryBolt、GloryGrid（可留空）"></el-input>
                    <div style="margin-top: 5px; font-size: 12px; color: #909399;">
                        可选：标识该审批组对应的产品线，便于按产品线组织审批人
                    </div>
                </el-form-item>
                <el-form-item label="组成员" required>
                    <el-select v-model="groupForm.members" multiple filterable placeholder="请选择组成员（可随时增删）" style="width: 100%">
                        <el-option v-for="item in users" :key="item.id" :label="item.name" :value="item.id"></el-option>
                    </el-select>
                </el-form-item>
                <el-form-item label="审批组说明">
                    <el-input v-model="groupForm.description" type="textarea" :rows="2" placeholder="请输入审批组说明"></el-input>
                </el-form-item>
            </el-form>
            <template #footer>
                <el-button @click="groupEditVisible = false">取消</el-button>
                <el-button type="primary" @click="handleGroupSubmit" :loading="groupSubmitLoading">保存</el-button>
            </template>
        </el-dialog>
    </div>
</template>

<script>
    import Pagination from "@/components/Pagination";
    import {getTableHeight} from "@/utils/util";
    import {workflowStep, workflowStepAdd, workflowStepUpdate, workflowStepDelete, getWorkflowTypeFormFields, workflowType, apiSystemRole, apiSystemDept, apiSystemAllUser, approvalGroup, approvalGroupAdd, approvalGroupUpdate, approvalGroupDelete} from '@/api/api';
    
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
                approvalGroups: [],  // 自定义审批组列表
                // 审批组管理对话框状态
                groupDialogVisible: false,
                groupEditVisible: false,
                groupSubmitLoading: false,
                groupForm: {
                    id: '',
                    name: '',
                    product_line: '',
                    description: '',
                    members: []
                },
                formFields: [],  // 当前流程类型的表单字段列表
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
                    approver_dept: [],  // 改为数组，支持多部门
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
                    multi_level_config: [],  // 多级审批配置
                    internal_conditions: [],  // 节点内部条件配置
                    // 抄送节点配置
                    cc_type: null,  // 默认为空，表示不配置抄送人
                    cc_role: null,
                    cc_dept: [],  // 改为数组
                    cc_users: [],
                    cc_group: null,  // 抄送审批组（cc_type=6 时使用）
                    // 产品线标识
                    product_line: '',  // 产品线标识，如 RC、EMIR&Grid、STA、Phybolt
                    product_line_cc_rules: [],  // 产品线抄送规则
                    // 条件分支和并行网关配置
                    next_step_on_pass: null,
                    next_step_on_reject: null,
                    condition_rules: [],  // 条件分支规则
                    parallel_branches: [],  // 并行分支
                    // 自动跳过审批配置
                    skip_approval_config: null,  // JSON格式的配置
                    skip_approval_enabled: false,  // 是否启用自动跳过
                    skip_is_dept_owner: false,  // 是否是部门负责人
                    skip_specified_users: [],  // 指定人员
                    skip_specified_roles: [],  // 指定角色
                    skip_scan_status_pass: false,  // 包扫描状态为PASS
                    skip_target_step: null  // 目标步骤
                },
                skipTargetStepOptions: [],  // 自动跳过目标步骤选项（当前流程类型下的全部步骤）
                currentNodePlaceholder: '__CURRENT_NODE_PLACEHOLDER__',  // “当前编辑节点”占位符值（新增模式下节点尚未生成ID时使用）
                tableData:[]
            }
        },
        computed: {
            // 自动跳过审批：是否选择了指定人员
            skip_specified_users_checked: {
                get() { return this.editForm.skip_specified_users && this.editForm.skip_specified_users.length > 0 },
                set(val) { if (!val) this.editForm.skip_specified_users = [] }
            },
            // 自动跳过审批：是否选择了指定角色
            skip_specified_roles_checked: {
                get() { return this.editForm.skip_specified_roles && this.editForm.skip_specified_roles.length > 0 },
                set(val) { if (!val) this.editForm.skip_specified_roles = [] }
            }
        },
        created() {
            this.getWorkflowTypes()
            this.getRoles()
            this.getDepts()
            this.getUsers()
            this.getApprovalGroups()
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
            // 获取可用的目标步骤（同流程类型）
            // includeCurrentNode=true 时追加“当前编辑节点”占位选项：
            // 解决首次创建流程、尚无任何其他步骤时，目标步骤必填却无数据可选的死胡同问题；
            // 提交后占位符会被替换为当前节点的真实ID，下拉框自然显示真实名称
            getAvailableTargetSteps(includeCurrentNode) {
                if(!this.editForm.workflow_type) {
                    return []
                }
                const options = this.skipTargetStepOptions.filter(s =>
                    String(s.id) !== String(this.editForm.id)
                )
                if(includeCurrentNode) {
                    const isEdit = !!this.editForm.id
                    options.unshift({
                        id: isEdit ? this.editForm.id : this.currentNodePlaceholder,
                        step_name: isEdit
                            ? (this.editForm.step_name || '当前编辑节点')
                            : '当前编辑节点（保存后显示真实名称）'
                    })
                }
                return options
            },
            // 加载当前流程类型下的全部步骤，作为自动跳过的目标步骤选项
            // 不依赖分页的 tableData，避免当前页没有同流程步骤导致下拉框无数据
            loadSkipTargetSteps(workflowTypeId) {
                this.skipTargetStepOptions = []
                const typeId = workflowTypeId || this.editForm.workflow_type
                if(!typeId) {
                    return
                }
                workflowStep({workflow_type: typeId, page: 1, limit: 1000}).then(res => {
                    if(res.code === 2000) {
                        this.skipTargetStepOptions = res.data.data || []
                    }
                })
            },
            getIndex($index){
                return (this.formInline.page - 1) * this.formInline.limit + $index + 1
            },
            // 新增模式下切换流程类型时，重新加载目标步骤选项并清空已选目标
            handleEditWorkflowTypeChange(val) {
                this.editForm.skip_target_step = null
                this.loadSkipTargetSteps(val)
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
                apiSystemAllUser({page: 1, limit: 1000}).then(res => {
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
                // 获取当前流程类型的表单字段
                this.getFormFields(this.formInline.workflow_type)
                
                this.editForm = {
                    id: '',
                    workflow_type: this.formInline.workflow_type,
                    step_name: '',
                    step_order: this.tableData.length + 1,
                    node_type: 1,  // 默认为普通审批节点
                    approver_type: 1,
                    approver_role: '',
                    approver_dept: [],  // 改为数组，支持多部门
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
                    multi_level_config: [],  // 多级审批配置
                    internal_conditions: [],  // 节点内部条件配置
                    // 抄送节点配置
                    cc_type: null,  // 默认为空，表示不配置抄送人
                    cc_role: null,
                    cc_dept: [],  // 改为数组
                    cc_users: [],
                    cc_group: null,  // 抄送审批组（cc_type=6 时使用）
                    // 产品线标识
                    product_line: '',  // 产品线标识
                    product_line_cc_rules: [],  // 产品线抄送规则
                    // 自动跳过审批配置
                    skip_approval_config: null,  // 原始的跳过配置(JSON)
                    skip_approval_enabled: false,  // 是否启用跳过(临时)
                    skip_is_dept_owner: false,  // 是否是部门负责人(临时)
                    skip_specified_users: [],  // 指定人员(临时)
                    skip_specified_roles: [],  // 指定角色(临时)
                    skip_scan_status_pass: false,  // 包扫描状态为PASS(临时)
                    skip_target_step: null,  // 目标步骤(临时)
                    // 条件分支和并行网关配置
                    next_step_on_pass: null,
                    next_step_on_reject: null,
                    condition_rules: [],  // 条件分支规则
                    parallel_branches: []  // 并行分支
                }
                // 加载当前流程类型的全部步骤，供自动跳过目标步骤选择
                this.loadSkipTargetSteps(this.formInline.workflow_type)
                this.editTitle = '新增节点'
                this.editDialogVisible = true
            },
            handleEdit(row){
                // 获取当前流程类型的表单字段
                this.getFormFields(row.workflow_type)
                // 加载当前流程类型的全部步骤，供自动跳过目标步骤选择
                this.loadSkipTargetSteps(row.workflow_type)
                
                this.editForm = {...row}
                // 确保数组字段正确复制
                if(row.approver_users && Array.isArray(row.approver_users)) {
                    this.editForm.approver_users = [...row.approver_users]
                }
                // 处理 approver_dept：兼容单个ID和数组格式，统一转为数组
                if(row.approver_dept !== null && row.approver_dept !== undefined) {
                    if(Array.isArray(row.approver_dept)) {
                        this.editForm.approver_dept = [...row.approver_dept]
                    } else {
                        // 单个ID，转为数组
                        this.editForm.approver_dept = [row.approver_dept]
                    }
                } else {
                    this.editForm.approver_dept = []
                }
                // 确保多级审批配置正确复制
                if(row.multi_level_config && Array.isArray(row.multi_level_config)) {
                    this.editForm.multi_level_config = JSON.parse(JSON.stringify(row.multi_level_config))
                    // 处理每个层级的 approver_dept，统一转为数组
                    this.editForm.multi_level_config.forEach(level => {
                        if(level.approver_dept !== null && level.approver_dept !== undefined) {
                            if(!Array.isArray(level.approver_dept)) {
                                level.approver_dept = [level.approver_dept]
                            }
                        } else {
                            level.approver_dept = []
                        }
                    })
                    console.log('加载多级审批配置:', this.editForm.multi_level_config)
                } else {
                    this.editForm.multi_level_config = []
                }
                // 确保抄送人员正确复制
                if(row.cc_users && Array.isArray(row.cc_users)) {
                    this.editForm.cc_users = [...row.cc_users]
                } else {
                    this.editForm.cc_users = []
                }
                // 处理抄送部门：兼容单个ID和数组格式
                if(row.cc_dept !== null && row.cc_dept !== undefined) {
                    if(Array.isArray(row.cc_dept)) {
                        this.editForm.cc_dept = [...row.cc_dept]
                    } else {
                        this.editForm.cc_dept = [row.cc_dept]
                    }
                } else {
                    this.editForm.cc_dept = []
                }
                // 确保条件分支规则正确复制
                if(row.condition_rules && Array.isArray(row.condition_rules)) {
                    this.editForm.condition_rules = JSON.parse(JSON.stringify(row.condition_rules))
                } else {
                    this.editForm.condition_rules = []
                }
                // 抄送节点：condition_rules 为对象格式，解析到 editForm 的抄送字段
                if(row.node_type === 2 && row.condition_rules && !Array.isArray(row.condition_rules)) {
                    const ccConfig = typeof row.condition_rules === 'string' ? JSON.parse(row.condition_rules) : row.condition_rules
                    this.editForm.cc_type = ccConfig.cc_type || null
                    this.editForm.cc_role = ccConfig.cc_role || null
                    this.editForm.cc_dept = ccConfig.cc_dept || []
                    if(this.editForm.cc_dept !== null && !Array.isArray(this.editForm.cc_dept)) {
                        this.editForm.cc_dept = [this.editForm.cc_dept]
                    }
                    this.editForm.cc_users = ccConfig.cc_users || []
                    this.editForm.cc_group = ccConfig.cc_group || null
                }
                // 确保并行分支正确复制
                if(row.parallel_branches && Array.isArray(row.parallel_branches)) {
                    this.editForm.parallel_branches = JSON.parse(JSON.stringify(row.parallel_branches))
                } else {
                    this.editForm.parallel_branches = []
                }
                // 确保产品线抄送规则正确复制
                if(row.product_line_cc_rules && Array.isArray(row.product_line_cc_rules)) {
                    this.editForm.product_line_cc_rules = JSON.parse(JSON.stringify(row.product_line_cc_rules))
                    // 处理每个规则的 cc_dept 和 cc_users，统一转为数组
                    this.editForm.product_line_cc_rules.forEach(rule => {
                        if(rule.cc_dept !== null && rule.cc_dept !== undefined) {
                            if(!Array.isArray(rule.cc_dept)) {
                                rule.cc_dept = [rule.cc_dept]
                            }
                        } else {
                            rule.cc_dept = []
                        }
                        if(rule.cc_users !== null && rule.cc_users !== undefined) {
                            if(!Array.isArray(rule.cc_users)) {
                                rule.cc_users = [rule.cc_users]
                            }
                        } else {
                            rule.cc_users = []
                        }
                    })
                } else {
                    this.editForm.product_line_cc_rules = []
                }
                // 解析自动跳过审批配置
                if(row.skip_approval_config) {
                    try {
                        const skipConfig = typeof row.skip_approval_config === 'string' ? JSON.parse(row.skip_approval_config) : row.skip_approval_config
                        this.editForm.skip_approval_enabled = skipConfig.enabled || false
                        const conditions = skipConfig.skip_conditions || {}
                        this.editForm.skip_is_dept_owner = conditions.is_dept_owner || false
                        this.editForm.skip_specified_users = conditions.specified_users || []
                        this.editForm.skip_specified_roles = conditions.specified_roles || []
                        this.editForm.skip_scan_status_pass = conditions.scan_status_pass || false
                        this.editForm.skip_target_step = skipConfig.target_step_id || null
                    } catch(e) {
                        console.error('解析 skip_approval_config 失败:', e)
                        this.editForm.skip_approval_enabled = false
                        this.editForm.skip_is_dept_owner = false
                        this.editForm.skip_specified_users = []
                        this.editForm.skip_specified_roles = []
                        this.editForm.skip_scan_status_pass = false
                        this.editForm.skip_target_step = null
                    }
                } else {
                    this.editForm.skip_approval_enabled = false
                    this.editForm.skip_is_dept_owner = false
                    this.editForm.skip_specified_users = []
                    this.editForm.skip_specified_roles = []
                    this.editForm.skip_scan_status_pass = false
                    this.editForm.skip_target_step = null
                }
                // 确保内部条件配置正确复制
                if(row.internal_conditions && Array.isArray(row.internal_conditions)) {
                    this.editForm.internal_conditions = JSON.parse(JSON.stringify(row.internal_conditions))
                    // 向后兼容：将旧格式（单个对象）转换为新格式（数组）
                    this.editForm.internal_conditions.forEach(group => {
                        if (group.approvers_config && !Array.isArray(group.approvers_config)) {
                            // 旧格式：单个对象，转换为数组
                            group.approvers_config = [group.approvers_config]
                        }
                        if (!Array.isArray(group.approvers_config)) {
                            group.approvers_config = []
                        }
                        // 处理每个审批人配置中的 approver_dept，统一转为数组
                        group.approvers_config.forEach(approver => {
                            if(approver.approver_dept !== null && approver.approver_dept !== undefined) {
                                if(!Array.isArray(approver.approver_dept)) {
                                    approver.approver_dept = [approver.approver_dept]
                                }
                            } else {
                                approver.approver_dept = []
                            }
                            // 处理多级审批配置中的 approver_dept
                            if(approver.multi_level_config && Array.isArray(approver.multi_level_config)) {
                                approver.multi_level_config.forEach(ml => {
                                    if(ml.approver_dept !== null && ml.approver_dept !== undefined) {
                                        if(!Array.isArray(ml.approver_dept)) {
                                            ml.approver_dept = [ml.approver_dept]
                                        }
                                    } else {
                                        ml.approver_dept = []
                                    }
                                })
                            }
                        })
                        // 添加编辑状态字段
                        group.editing_approver_index = null
                    })
                } else {
                    this.editForm.internal_conditions = []
                }
                this.editTitle = '编辑节点'
                this.editDialogVisible = true
            },
            handleEditSubmit(){
                if(!this.editForm.step_name) {
                    this.$message.warning('请填写节点名称')
                    return
                }
                
                // 结束节点不需要验证审批人配置
                if(this.editForm.node_type !== 5) {
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
                            if(level.approver_type == 2 && (!level.approver_dept || level.approver_dept.length === 0)) {
                                this.$message.warning(`请选择第 ${i + 1} 级的审批部门`)
                                return
                            }
                            // 注意：type=3（部门负责人）不再强制要求选择部门，未选择时自动使用申请人部门
                            // type=5（申请人自选）和 type=7（发起人）不需要额外验证
                            if(level.approver_type == 4 && (!level.approver_users || level.approver_users.length === 0)) {
                                this.$message.warning(`请选择第 ${i + 1} 级的审批人员`)
                                return
                            }
                        }
                    } else if(this.editForm.approver_type == 1 && !this.editForm.approver_role) {
                        this.$message.warning('请选择审批角色')
                        return
                    } else if(this.editForm.approver_type == 2 && (!this.editForm.approver_dept || this.editForm.approver_dept.length === 0)) {
                        this.$message.warning('请选择审批部门')
                        return
                    } else if(this.editForm.approver_type == 4 && (!this.editForm.approver_users || this.editForm.approver_users.length === 0)) {
                        this.$message.warning('请选择审批人员')
                        return
                    } else if(this.editForm.approver_type == 10 && !this.editForm.approver_group) {
                        this.$message.warning('请选择审批组')
                        return
                    }
                    // type=3（部门负责人）、type=5（申请人自选）、type=7（发起人）不需要额外验证
                }
                
                // 抄送节点：校验抄送配置并构建 condition_rules
                if(this.editForm.node_type === 2) {
                    if(!this.editForm.cc_type) {
                        this.$message.warning('请选择抄送人类型')
                        return
                    }
                    if(this.editForm.cc_type === 1 && !this.editForm.cc_role) {
                        this.$message.warning('请选择抄送角色')
                        return
                    } else if((this.editForm.cc_type === 2 || this.editForm.cc_type === 3) && (!this.editForm.cc_dept || this.editForm.cc_dept.length === 0)) {
                        this.$message.warning('请选择抄送部门')
                        return
                    } else if(this.editForm.cc_type === 4 && (!this.editForm.cc_users || this.editForm.cc_users.length === 0)) {
                        this.$message.warning('请选择抄送人员')
                        return
                    } else if(this.editForm.cc_type === 6 && !this.editForm.cc_group) {
                        this.$message.warning('请选择抄送审批组')
                        return
                    }
                    this.editForm.condition_rules = {
                        cc_type: this.editForm.cc_type,
                        cc_role: this.editForm.cc_type === 1 ? this.editForm.cc_role : null,
                        cc_dept: (this.editForm.cc_type === 2 || this.editForm.cc_type === 3) ? this.editForm.cc_dept : null,
                        cc_users: this.editForm.cc_type === 4 ? this.editForm.cc_users : null,
                        cc_group: this.editForm.cc_type === 6 ? this.editForm.cc_group : null
                    }
                }
                
                // 节点级抄送配置校验：自定义审批组类型必须选择审批组
                if(this.editForm.node_type !== 2 && this.editForm.cc_type === 6 && !this.editForm.cc_group) {
                    this.$message.warning('请选择抄送审批组')
                    return
                }
                
                // 产品线抄送规则校验：自定义审批组类型必须选择审批组
                if(this.editForm.product_line_cc_rules && this.editForm.product_line_cc_rules.length > 0) {
                    for(let i = 0; i < this.editForm.product_line_cc_rules.length; i++) {
                        const rule = this.editForm.product_line_cc_rules[i]
                        if(rule.cc_type === 6 && !rule.cc_group) {
                            this.$message.warning(`产品线抄送规则 ${i + 1}：请选择抄送审批组`)
                            return
                        }
                    }
                }
                
                // 构建自动跳过审批配置
                let pendingSelfTarget = false  // 新增模式下目标步骤选了“当前编辑节点”占位符，需创建后回写真实ID
                if(this.editForm.node_type === 1 && this.editForm.skip_approval_enabled) {
                    // 验证：启用跳过时必须选择至少一个条件和目标步骤
                    if(!this.editForm.skip_is_dept_owner &&
                       (!this.editForm.skip_specified_users || this.editForm.skip_specified_users.length === 0) && 
                       (!this.editForm.skip_specified_roles || this.editForm.skip_specified_roles.length === 0) &&
                       !this.editForm.skip_scan_status_pass) {
                        this.$message.warning('请至少选择一个跳过条件')
                        return
                    }
                    if(!this.editForm.skip_target_step) {
                        this.$message.warning('请选择目标步骤')
                        return
                    }
                    const skipConfig = {
                        enabled: true,
                        skip_conditions: {
                            is_dept_owner: this.editForm.skip_is_dept_owner,
                            specified_users: this.editForm.skip_specified_users || [],
                            specified_roles: this.editForm.skip_specified_roles || [],
                            scan_status_pass: this.editForm.skip_scan_status_pass
                        },
                        target_step_id: this.editForm.skip_target_step
                    }
                    if(!this.editForm.id && this.editForm.skip_target_step === this.currentNodePlaceholder) {
                        // 新增模式下节点ID尚未生成，先以空配置创建，拿到新ID后再回写真实配置
                        pendingSelfTarget = true
                        this.editForm.skip_approval_config = null
                    } else {
                        this.editForm.skip_approval_config = skipConfig
                    }
                } else {
                    this.editForm.skip_approval_config = null
                }
                
                let vm = this
                vm.submitLoading = true
                let apiCall = vm.editForm.id ? workflowStepUpdate(vm.editForm) : workflowStepAdd(vm.editForm)
                apiCall.then(res => {
                    if(res.code === 2000 && pendingSelfTarget) {
                        // 创建成功，将“当前编辑节点”占位符替换为新节点的真实ID并回写跳过配置
                        const newId = res.data ? res.data.id : null
                        if(newId) {
                            const updateForm = {...vm.editForm, id: newId}
                            updateForm.skip_target_step = newId
                            updateForm.skip_approval_config = {
                                enabled: true,
                                skip_conditions: {
                                    is_dept_owner: vm.editForm.skip_is_dept_owner,
                                    specified_users: vm.editForm.skip_specified_users || [],
                                    specified_roles: vm.editForm.skip_specified_roles || [],
                                    scan_status_pass: vm.editForm.skip_scan_status_pass
                                },
                                target_step_id: newId
                            }
                            workflowStepUpdate(updateForm).then(updRes => {
                                vm.submitLoading = false
                                if(updRes.code === 2000) {
                                    vm.$message.success('新增成功')
                                    vm.editDialogVisible = false
                                    vm.getData()
                                } else {
                                    vm.$message.warning('节点已创建，但自动跳过配置回写失败，请编辑该节点重新保存')
                                    vm.editDialogVisible = false
                                    vm.getData()
                                }
                            }).catch(() => {
                                vm.submitLoading = false
                                vm.$message.warning('节点已创建，但自动跳过配置回写失败，请编辑该节点重新保存')
                                vm.editDialogVisible = false
                                vm.getData()
                            })
                            return
                        }
                    }
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
                    name: '',  // 层级名称由用户自定义
                    approver_type: 1,
                    approver_role: null,  // 使用null而不是空字符串
                    approver_dept: [],  // 改为数组，支持多部门
                    approver_users: [],
                    condition_relation: 'and',  // 条件关系：and/or
                    conditions: []  // 条件列表
                })
                console.log('添加审批层级:', this.editForm.multi_level_config)
            },
            // 删除审批层级
            removeApprovalLevel(index) {
                if(this.editForm.multi_level_config && this.editForm.multi_level_config.length > 1) {
                    this.editForm.multi_level_config.splice(index, 1)
                }
            },
            // 处理层级类型变化，清空不相关的字段
            handleLevelTypeChange(level) {
                console.log('层级类型变化:', level.approver_type)
                // 根据类型清空不相关的字段
                if (level.approver_type !== 1) {
                    level.approver_role = null
                }
                if (level.approver_type !== 2 && level.approver_type !== 3) {
                    level.approver_dept = []  // 改为数组
                }
                if (level.approver_type !== 4) {
                    level.approver_users = []
                }
            },
            
            // ========== 多级审批层级条件配置方法 ==========
            // 添加层级条件
            addLevelCondition(levelIndex) {
                const level = this.editForm.multi_level_config[levelIndex]
                if (!level.conditions) {
                    level.conditions = []
                }
                level.conditions.push({
                    field: '',
                    operator: '==',
                    value: ''
                })
            },
            
            // 删除层级条件
            removeLevelCondition(levelIndex, conditionIndex) {
                const level = this.editForm.multi_level_config[levelIndex]
                if (level.conditions) {
                    level.conditions.splice(conditionIndex, 1)
                }
            },
            
            // ========== 内部条件配置方法 ==========
            // 添加条件组
            addConditionGroup() {
                if(!this.editForm.internal_conditions) {
                    this.editForm.internal_conditions = []
                }
                this.editForm.internal_conditions.push({
                    condition_group: '',
                    condition_relation: 'and',
                    conditions: [],
                    approvers_config: [],  // 改为数组，支持多个审批人
                    editing_approver_index: null
                })
            },
            
            // 删除条件组
            removeConditionGroup(groupIndex) {
                if(this.editForm.internal_conditions) {
                    this.editForm.internal_conditions.splice(groupIndex, 1)
                }
            },
            
            // 添加条件
            addCondition(groupIndex) {
                const group = this.editForm.internal_conditions[groupIndex]
                if (!group.conditions) {
                    group.conditions = []
                }
                group.conditions.push({
                    field: '',
                    operator: '==',
                    value: ''
                })
            },
            
            // 删除条件
            removeCondition(groupIndex, conditionIndex) {
                const group = this.editForm.internal_conditions[groupIndex]
                if (group.conditions) {
                    group.conditions.splice(conditionIndex, 1)
                }
            },
            
            // ========== 审批人管理方法 ==========
            // 添加审批人（从下拉菜单选择类型）
            handleAddApprover(approverType, groupIndex) {
                const group = this.editForm.internal_conditions[groupIndex]
                if (!group.approvers_config) {
                    group.approvers_config = []
                }
                
                // 创建新的审批人配置
                const newApprover = {
                    approver_type: approverType,
                    approver_role: null,
                    approver_dept: [],  // 改为数组，支持多部门
                    approver_users: [],
                    approver_group: null,  // 自定义审批组
                    multi_level_config: [{
                        approver_type: 1,
                        approver_role: null,
                        approver_dept: [],  // 改为数组
                        approver_users: []
                    }]
                }
                
                group.approvers_config.push(newApprover)
                // 设置当前编辑的索引
                group.editing_approver_index = group.approvers_config.length - 1
            },
            
            // 删除审批人
            removeApprover(groupIndex, approverIndex) {
                const group = this.editForm.internal_conditions[groupIndex]
                if (group.approvers_config) {
                    group.approvers_config.splice(approverIndex, 1)
                    // 如果删除的是当前正在编辑的，清除编辑状态
                    if (group.editing_approver_index === approverIndex) {
                        group.editing_approver_index = null
                    } else if (group.editing_approver_index > approverIndex) {
                        group.editing_approver_index--
                    }
                }
            },
            
            // 确认编辑审批人
            confirmEditApprover(groupIndex) {
                const group = this.editForm.internal_conditions[groupIndex]
                group.editing_approver_index = null
            },
            
            // 取消编辑审批人
            cancelEditApprover(groupIndex) {
                const group = this.editForm.internal_conditions[groupIndex]
                // 如果审批人配置为空，则删除刚添加的
                if (group.approvers_config && group.approvers_config.length > 0) {
                    const editingIndex = group.editing_approver_index
                    // 检查是否是刚添加的空配置
                    const approver = group.approvers_config[editingIndex]
                    if (approver && !approver.approver_role && (!approver.approver_dept || approver.approver_dept.length === 0) && 
                        (!approver.approver_users || approver.approver_users.length === 0) && !approver.approver_group) {
                        group.approvers_config.splice(editingIndex, 1)
                    }
                }
                group.editing_approver_index = null
            },
            // 辅助方法：根据ID获取角色名称
            getRoleName(roleId) {
                if(!roleId) return '未配置'
                const role = this.roles.find(r => r.id === roleId)
                return role ? role.name : '角色'
            },
            // 辅助方法：根据ID获取部门名称（支持单个ID或ID数组）
            getDeptName(deptId) {
                if(!deptId) return '未配置'
                // 支持数组格式
                if(Array.isArray(deptId)) {
                    if(deptId.length === 0) return '未配置'
                    const names = deptId.map(id => {
                        const dept = this.depts.find(d => d.id === id)
                        return dept ? dept.name : ''
                    }).filter(name => name !== '')
                    return names.join(', ') || '部门'
                }
                // 单个ID
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
            },
            // ========== 自定义审批组相关方法 ==========
            // 获取审批组列表
            getApprovalGroups() {
                approvalGroup({page: 1, limit: 1000}).then(res => {
                    if(res.code === 2000) {
                        this.approvalGroups = res.data.data || []
                    }
                })
            },
            // 根据ID获取审批组名称
            getGroupName(groupId) {
                if(!groupId) return '未配置'
                const group = this.approvalGroups.find(g => g.id === groupId)
                return group ? group.name : '审批组'
            },
            // 根据ID获取审批组成员显示文本
            getGroupMembersDisplay(groupId) {
                if(!groupId) return '未选择审批组'
                const group = this.approvalGroups.find(g => g.id === groupId)
                if(!group) return '未选择审批组'
                if(!group.members_info || group.members_info.length === 0) return '暂无成员'
                return group.members_info.map(m => m.name).join(', ')
            },
            // 打开审批组管理对话框
            openGroupManage() {
                this.getApprovalGroups()
                this.groupDialogVisible = true
            },
            // 新建审批组
            handleAddGroup() {
                this.groupForm = {
                    id: '',
                    name: '',
                    product_line: '',
                    description: '',
                    members: []
                }
                this.groupEditVisible = true
            },
            // 编辑审批组
            handleEditGroup(row) {
                this.groupForm = {
                    id: row.id,
                    name: row.name,
                    product_line: row.product_line || '',
                    description: row.description || '',
                    members: row.members ? [...row.members] : []
                }
                this.groupEditVisible = true
            },
            // 保存审批组（新建/编辑）
            handleGroupSubmit() {
                if(!this.groupForm.name) {
                    this.$message.warning('请填写审批组名称')
                    return
                }
                if(!this.groupForm.members || this.groupForm.members.length === 0) {
                    this.$message.warning('请至少选择一名组成员')
                    return
                }
                let vm = this
                vm.groupSubmitLoading = true
                let apiCall = vm.groupForm.id ? approvalGroupUpdate(vm.groupForm) : approvalGroupAdd(vm.groupForm)
                apiCall.then(res => {
                    vm.groupSubmitLoading = false
                    if(res.code === 2000) {
                        vm.$message.success(vm.groupForm.id ? '编辑成功' : '新建成功')
                        vm.groupEditVisible = false
                        vm.getApprovalGroups()
                    } else {
                        vm.$message.error(res.msg || '操作失败')
                    }
                }).catch(() => {
                    vm.groupSubmitLoading = false
                    vm.$message.error('操作失败')
                })
            },
            // 删除审批组
            handleDeleteGroup(row) {
                let vm = this
                vm.$confirm(`确认要删除审批组「${row.name}」吗？删除后引用该审批组的流程节点将无法获取审批人。`, '提示', {
                    confirmButtonText: '确定',
                    cancelButtonText: '取消',
                    type: 'warning'
                }).then(() => {
                    approvalGroupDelete({id: row.id}).then(res => {
                        if(res.code === 2000) {
                            vm.$message.success('删除成功')
                            vm.getApprovalGroups()
                        } else {
                            vm.$message.error(res.msg || '删除失败')
                        }
                    }).catch(() => {
                        vm.$message.error('删除失败')
                    })
                }).catch(() => {})
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
                        console.log(`获取到 ${this.formFields.length} 个字段`, this.formFields)
                    } else {
                        console.log('未获取到字段数据，res.code:', res.code, 'res.data:', res.data)
                        this.formFields = []
                    }
                }).catch(err => {
                    console.error('获取表单字段失败:', err)
                    this.formFields = []
                })
            },
            // 添加条件分支规则
            addConditionRule() {
                if(!this.editForm.condition_rules) {
                    this.editForm.condition_rules = []
                }
                this.editForm.condition_rules.push({
                    field: '',
                    operator: '==',
                    value: '',
                    target_step: null
                })
            },
            // 删除条件分支规则
            removeConditionRule(index) {
                if(this.editForm.condition_rules && this.editForm.condition_rules.length > 0) {
                    this.editForm.condition_rules.splice(index, 1)
                }
            },
            // 添加并行分支
            addParallelBranch() {
                if(!this.editForm.parallel_branches) {
                    this.editForm.parallel_branches = []
                }
                this.editForm.parallel_branches.push({
                    branch_name: '',
                    target_step: null
                })
            },
            // 删除并行分支
            removeParallelBranch(index) {
                if(this.editForm.parallel_branches && this.editForm.parallel_branches.length > 0) {
                    this.editForm.parallel_branches.splice(index, 1)
                }
            },
            // 添加产品线抄送规则
            addProductLineCcRule() {
                if(!this.editForm.product_line_cc_rules) {
                    this.editForm.product_line_cc_rules = []
                }
                this.editForm.product_line_cc_rules.push({
                    product_line: '',
                    cc_type: 1,
                    cc_role: null,
                    cc_dept: [],
                    cc_users: [],
                    cc_group: null
                })
            },
            // 删除产品线抄送规则
            removeProductLineCcRule(index) {
                if(this.editForm.product_line_cc_rules && this.editForm.product_line_cc_rules.length > 0) {
                    this.editForm.product_line_cc_rules.splice(index, 1)
                }
            }
        }
    }
</script>

<style scoped>
</style>
