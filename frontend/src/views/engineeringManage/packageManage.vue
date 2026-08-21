<template>
    <div :class="{'ly-is-full':isFull}">
        <div class="tableSelect" ref="tableSelect">
            <el-form :inline="true" :model="formInline" label-position="left">
                <el-form-item label="项目名称：">
                    <el-input size="default" v-model.trim="formInline.project_name" maxlength="60" clearable placeholder="项目名称" @change="search" style="width:200px"></el-input>
                </el-form-item>
                <el-form-item label="构建状态：">
                    <el-select v-model="formInline.build_status" placeholder="请选择" clearable @change="search" size="default" style="width:120px">
                        <el-option
                            v-for="item in statusList"
                            :key="item.id"
                            :label="item.name"
                            :value="item.id">
                        </el-option>
                    </el-select>
                </el-form-item>
                <el-form-item label="扫描状态：">
                    <el-select v-model="formInline.scan_status" placeholder="请选择" clearable @change="search" size="default" style="width:120px">
                        <el-option
                            v-for="item in scanStatusList"
                            :key="item.id"
                            :label="item.name"
                            :value="item.id">
                        </el-option>
                    </el-select>
                </el-form-item>
                <el-form-item label=""><el-button @click="search" type="primary" icon="Search" v-show="hasPermission(this.$route.name,'Search')">查询</el-button></el-form-item>
                <el-form-item label=""><el-button @click="handleEdit('','reset')" icon="Refresh">重置</el-button></el-form-item>
                <el-form-item label="" v-show="hasPermission(this.$route.name,'Create')">
                    <el-button icon="Refresh" type="primary" @click="syncProjects" :loading="syncLoading">同步</el-button>
                </el-form-item>
                <el-form-item label="" v-if="isAdmin">
                    <el-button icon="Setting" @click="openPermDialog">可见性配置</el-button>
                </el-form-item>
            </el-form>
        </div>
        <div class="table">
            <el-table :height="'calc('+(tableHeight)+'px)'" border :data="tableData" ref="tableref" v-loading="loadingPage" style="width: 100%">
                <el-table-column type="index" width="60" align="center" label="序号">
                    <template #default="scope">
                        <span v-text="getIndex(scope.$index)"></span>
                    </template>
                </el-table-column>
                <el-table-column min-width="150" prop="project_name" label="项目名称" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="100" prop="build_type" label="构建类型" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="100" prop="jenkins_build_number" label="构建编号" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="100" label="构建人" show-overflow-tooltip>
                    <template #default="scope">
                        <span>{{ scope.row.creator_name || '系统同步' }}</span>
                    </template>
                </el-table-column>
                <el-table-column min-width="100" label="构建状态">
                    <template #default="scope">
                        <el-tag v-if="scope.row.build_status==1" type="success">成功</el-tag>
                        <el-tag v-else-if="scope.row.build_status==2" type="danger">失败</el-tag>
                        <el-tag v-else-if="scope.row.build_status==3" type="info">未构建</el-tag>
                        <el-tag v-else type="warning">构建中</el-tag>
                    </template>
                </el-table-column>
                <el-table-column min-width="110" label="包扫描状态">
                    <template #default="scope">
                        <!-- 构建未成功（构建中/失败/未构建）时扫描尚未开始，统一显示未扫描；
                             业务扫描状态无 FAIL，只有 PASS/REJECT/WARN/ERROR/SCANNING/未扫描 -->
                        <span v-if="scope.row.build_status !== 1" style="color: #C0C4CC;">未扫描</span>
                        <el-tag v-else-if="scope.row.scan_status === 'PASS'" type="success">PASS</el-tag>
                        <el-tag v-else-if="scope.row.scan_status === 'REJECT'" type="danger">REJECT</el-tag>
                        <el-tag v-else-if="scope.row.scan_status === 'WARN'" type="warning">WARN</el-tag>
                        <el-tag v-else-if="scope.row.scan_status === 'ERROR'" type="danger">ERROR</el-tag>
                        <el-tag v-else-if="scope.row.scan_status === 'SCANNING'" type="warning">扫描中</el-tag>
                        <span v-else style="color: #C0C4CC;">未扫描</span>
                    </template>
                </el-table-column>
                <el-table-column min-width="80" label="是否传包" align="center">
                    <template #default="scope">
                        <span v-if="scope.row.need_delivery" style="color: #67C23A;">是</span>
                        <span v-else style="color: #C0C4CC;">否</span>
                    </template>
                </el-table-column>
                <el-table-column min-width="150" prop="build_log_snippet" label="构建日志" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="150" prop="create_datetime" label="创建时间"></el-table-column>
                <el-table-column label="操作" fixed="right" width="250">
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
                        <span class="table-operate-btn" @click="handleEdit(scope.row,'build')" v-show="hasPermission(this.$route.name,'Create')">构建</span>
                        <span class="table-operate-btn" @click="handleEdit(scope.row,'deliver')" v-if="scope.row.build_status==1 && !(scope.row.need_delivery || !scope.row.creator_name)" v-show="hasPermission(this.$route.name,'SendPackage')">发包</span>
                        <span class="table-operate-btn" @click="handleEdit(scope.row,'detail')" v-show="hasPermission(this.$route.name,'Retrieve')">详情</span>
                        <span class="table-operate-btn" @click="handleEdit(scope.row,'delete')" v-show="hasPermission(this.$route.name,'Delete')">删除</span>
                    </template>
                </el-table-column>
            </el-table>
        </div>
        <Pagination v-bind:child-msg="pageparm" @callFather="callFather"></Pagination>

        <!-- 构建参数输入弹窗 -->
        <el-dialog v-model="buildDialogVisible" title="构建参数" width="700px" destroy-on-close>
            <el-form :model="buildFormData" label-width="150px">
                <el-form-item label="项目名称">
                    <span>{{ currentBuildRow.project_name }}</span>
                </el-form-item>
                <el-form-item label="Jenkins 任务">
                    <span>{{ currentBuildRow.jenkins_job_name }}</span>
                </el-form-item>

                <!-- 构建参数：根据当前 Jenkins 任务实际参数动态渲染，左侧展示参数名称 -->
                <el-form-item v-for="param in jobParameters" :key="param.name">
                    <template #label>
                        <el-tooltip :content="param.description || ''" placement="top" :disabled="!param.description">
                            <span>{{ param.name }}</span>
                        </el-tooltip>
                    </template>
                    <!-- Choice 类型：下拉选择 -->
                    <el-select v-if="param.type === 'ChoiceParameterDefinition'" v-model="buildFormData[param.name]" placeholder="请选择" style="width: 100%">
                        <el-option
                            v-for="choice in param.choices"
                            :key="choice"
                            :label="choice"
                            :value="choice">
                        </el-option>
                    </el-select>
                    <!-- Boolean 类型：开关 -->
                    <el-switch v-else-if="param.type === 'BooleanParameterDefinition'" v-model="buildFormData[param.name]" active-text="是" inactive-text="否"></el-switch>
                    <!-- Password 类型：密码输入 -->
                    <el-input v-else-if="param.type === 'PasswordParameterDefinition'" v-model="buildFormData[param.name]" type="password" show-password placeholder="请输入" style="width: 100%" clearable></el-input>
                    <!-- Text 类型：多行文本 -->
                    <el-input v-else-if="param.type === 'TextParameterDefinition'" v-model="buildFormData[param.name]" type="textarea" :rows="3" placeholder="请输入" style="width: 100%"></el-input>
                    <!-- 其他类型：单行文本输入 -->
                    <el-input v-else v-model="buildFormData[param.name]" placeholder="请输入" style="width: 100%" clearable></el-input>
                </el-form-item>

                <!-- 参数加载状态 -->
                <div v-if="paramsLoading" v-loading="true" element-loading-text="正在获取构建参数..." style="height: 60px;"></div>
                <!-- 参数为空 -->
                <el-empty v-else-if="jobParameters.length === 0" description="暂无构建参数" :image-size="60"></el-empty>

                <!-- 是否需要传包 -->
                <el-form-item label="是否需要传包">
                    <el-switch v-model="buildFormData.need_delivery" active-text="是" inactive-text="否"></el-switch>
                </el-form-item>

                <!-- 勾选传包后：填写"软件包(D包)发包流程"申请表单，构建成功后自动发起审批流 -->
                <template v-if="buildFormData.need_delivery">
                    <el-divider content-position="left">发包审批流申请信息</el-divider>
                    <el-alert
                        title="构建成功后系统将自动获取制品路径并回填「软件包存放路径」，自动发起发包审批流，请先完善以下申请信息"
                        type="info"
                        :closable="false"
                        show-icon
                        style="margin-bottom: 15px;"
                    />
                    <div v-if="deliverySchemaLoading" v-loading="true" element-loading-text="正在获取申请表单..." style="height: 60px;"></div>
                    <el-empty v-else-if="deliveryFormFields.length === 0" description="未获取到发包申请表单" :image-size="60"></el-empty>
                    <el-form-item v-for="field in visibleDeliveryFormFields" :key="field.field" :label="field.label" :required="isDeliveryFieldRequired(field)">
                        <!-- auto_fill 字段（如软件包存放路径/软件包版本名称）：构建成功后自动回填，不允许手动填写 -->
                        <el-input v-if="field.auto_fill" model-value="构建成功后自动填写" disabled></el-input>
                        <!-- 单行文本 -->
                        <el-input v-else-if="field.type === 'input'" v-model="deliveryFormData[field.field]" :placeholder="field.placeholder || '请输入' + field.label"></el-input>
                        <!-- 多行文本 -->
                        <el-input v-else-if="field.type === 'textarea'" v-model="deliveryFormData[field.field]" type="textarea" :rows="3" :placeholder="field.placeholder || '请输入' + field.label"></el-input>
                        <!-- 数字 -->
                        <el-input-number v-else-if="field.type === 'number'" v-model="deliveryFormData[field.field]" :placeholder="field.placeholder" style="width: 100%"></el-input-number>
                        <!-- 下拉选择 -->
                        <el-select v-else-if="field.type === 'select'" v-model="deliveryFormData[field.field]" :placeholder="field.placeholder || '请选择' + field.label" style="width: 100%">
                            <el-option v-for="opt in field.options" :key="opt.value" :label="opt.label" :value="opt.value"></el-option>
                        </el-select>
                        <!-- 单选框 -->
                        <el-radio-group v-else-if="field.type === 'radio'" v-model="deliveryFormData[field.field]">
                            <el-radio v-for="opt in field.options" :key="opt.value" :label="opt.value">{{ opt.label }}</el-radio>
                        </el-radio-group>
                        <!-- 复选框 -->
                        <el-checkbox-group v-else-if="field.type === 'checkbox'" v-model="deliveryFormData[field.field]">
                            <el-checkbox v-for="opt in field.options" :key="opt.value" :label="opt.value">{{ opt.label }}</el-checkbox>
                        </el-checkbox-group>
                        <!-- 日期 -->
                        <el-date-picker v-else-if="field.type === 'date'" v-model="deliveryFormData[field.field]" type="date" :placeholder="field.placeholder || '请选择' + field.label" style="width: 100%" value-format="YYYY-MM-DD"></el-date-picker>
                        <!-- 日期时间 -->
                        <el-date-picker v-else-if="field.type === 'datetime'" v-model="deliveryFormData[field.field]" type="datetime" :placeholder="field.placeholder || '请选择' + field.label" style="width: 100%" value-format="YYYY-MM-DD HH:mm:ss"></el-date-picker>
                    </el-form-item>
                </template>
            </el-form>
            <template #footer>
                <el-button @click="buildDialogVisible = false">取消</el-button>
                <el-button type="primary" @click="confirmBuild" :loading="buildLoading">确认构建</el-button>
            </template>
        </el-dialog>

        <!-- 详情弹窗 -->
        <el-dialog v-model="detailDialogVisible" title="构建详情" width="860px" destroy-on-close>
            <el-descriptions :column="2" border v-if="detailData">
                <el-descriptions-item label="项目名称">{{ detailData.project_name }}</el-descriptions-item>
                <el-descriptions-item label="项目版本">{{ detailData.project_version }}</el-descriptions-item>
                <el-descriptions-item label="构建类型">{{ detailData.build_type }}</el-descriptions-item>
                <el-descriptions-item label="构建状态">
                    <el-tag v-if="detailData.build_status==1" type="success">成功</el-tag>
                    <el-tag v-else-if="detailData.build_status==2" type="danger">失败</el-tag>
                    <el-tag v-else-if="detailData.build_status==3" type="info">未构建</el-tag>
                    <el-tag v-else type="warning">构建中</el-tag>
                </el-descriptions-item>
                <el-descriptions-item label="Jenkins 任务">{{ detailData.jenkins_job_name }}</el-descriptions-item>
                <el-descriptions-item label="构建编号">{{ detailData.jenkins_build_number || '-' }}</el-descriptions-item>
                <el-descriptions-item label="构建人">{{ detailData.creator_name || '系统同步' }}</el-descriptions-item>
                <el-descriptions-item label="是否需要传包">
                    <el-tag :type="detailData.need_delivery ? 'success' : 'info'">
                        {{ detailData.need_delivery ? '是' : '否' }}
                    </el-tag>
                </el-descriptions-item>
                <el-descriptions-item label="创建时间">{{ detailData.create_datetime }}</el-descriptions-item>
            </el-descriptions>

            <!-- 构建日志：终端风格独立面板，支持滚动 / 着色 / 复制 / 刷新 -->
            <div class="log-panel" v-if="detailData">
                <div class="log-panel-header">
                    <span class="log-panel-title">
                        构建日志
                        <el-tag v-if="detailData.build_status==1" type="success" size="small">成功</el-tag>
                        <el-tag v-else-if="detailData.build_status==2" type="danger" size="small">失败</el-tag>
                        <el-tag v-else-if="detailData.build_status==3" type="info" size="small">未构建</el-tag>
                        <el-tag v-else type="warning" size="small">构建中</el-tag>
                    </span>
                    <span class="log-panel-actions">
                        <el-button size="small" @click="refreshDetailLog">刷新</el-button>
                        <el-button size="small" type="primary" plain @click="copyBuildLog">复制</el-button>
                    </span>
                </div>
                <div class="log-body" ref="logBody" v-loading="logLoading" element-loading-text="正在加载日志...">
                    <div v-if="logLines.length === 0" class="log-empty">暂无日志</div>
                    <template v-else>
                        <div v-for="(line, index) in logLines" :key="index" class="log-line">
                            <span class="log-line-num">{{ index + 1 }}</span>
                            <span class="log-line-content" v-html="highlightLogLine(line)"></span>
                        </div>
                    </template>
                </div>
            </div>

            <template #footer>
                <el-button @click="detailDialogVisible = false">关闭</el-button>
            </template>
        </el-dialog>

        <!-- 发包确认弹窗：预览制品路径供用户确认（路径只读，不允许手动修改），确认后才创建发包流程 -->
        <el-dialog v-model="deliverDialogVisible" title="发包确认" width="680px" destroy-on-close>
            <div class="deliver-tip">
                将获取项目 <b>{{ deliverRow ? deliverRow.project_name : '' }}</b> 构建成功的制品，自动创建“{{ deliverSchemaName || '软件包(D包)发包流程' }}”，并将确认后的制品路径填写至“{{ deliverPathLabel }}”字段，路径文件名自动填写至“{{ deliverVersionLabel }}”字段。
            </div>
            <el-descriptions :column="1" border style="margin-bottom: 15px;">
                <el-descriptions-item label="项目名称">{{ deliverRow ? deliverRow.project_name : '-' }}</el-descriptions-item>
                <el-descriptions-item label="Jenkins 任务">{{ deliverRow ? deliverRow.jenkins_job_name : '-' }}</el-descriptions-item>
                <el-descriptions-item label="构建编号">{{ deliverRow ? (deliverRow.jenkins_build_number || '-') : '-' }}</el-descriptions-item>
                <el-descriptions-item label="包扫描状态">
                    <el-tag v-if="deliverScanStatus" :type="getScanStatusTagType(deliverScanStatus)" size="small">{{ deliverScanStatus }}</el-tag>
                    <span v-else style="color: #C0C4CC;">-</span>
                </el-descriptions-item>
            </el-descriptions>
            <el-form label-width="100px" label-position="left">
                <!-- 扫描报告路径：构建扫描自动获取，只读展示，不允许手动修改（与制品路径一致，自动换行） -->
                <el-form-item label="扫描报告路径">
                    <el-input
                        :model-value="deliverScanReport || '未获取到扫描报告'"
                        type="textarea"
                        :rows="3"
                        placeholder="构建成功后自动获取"
                        disabled
                        resize="none"
                    ></el-input>
                </el-form-item>
                <el-form-item :label="deliverPathLabel" required>
                    <el-input
                        v-model="deliverPath"
                        type="textarea"
                        :rows="3"
                        placeholder="构建成功后自动获取"
                        disabled
                        resize="none"
                    ></el-input>
                </el-form-item>
                <!-- 软件包版本名称：自动从制品路径提取文件名 -->
                <el-form-item :label="deliverVersionLabel">
                    <el-input :model-value="deliverVersionName || '自动从制品路径文件名提取'" disabled></el-input>
                </el-form-item>
            </el-form>
            <div class="deliver-tip-sub" v-loading="deliverPreviewLoading" element-loading-text="正在获取制品路径...">制品路径由构建制品自动获取且不可修改；确认后将以此路径发起发包流程。</div>
            <template #footer>
                <el-button @click="deliverDialogVisible = false">取消</el-button>
                <el-button type="primary" :loading="deliverConfirmLoading" @click="confirmDeliver">确定</el-button>
            </template>
        </el-dialog>

        <!-- 项目可见性配置弹窗：管理员按项目配置可见范围（公共/部门/角色/用户），未授权项目默认仅管理员可见 -->
        <el-dialog v-model="permDialogVisible" title="项目可见性配置" width="1250px" destroy-on-close>
            <el-alert
                title="未授权项目默认仅管理员可见；配置后对应部门/角色/用户即可在打包列表中看到该项目并发起构建。勾选「公共可见」则所有用户可见。"
                type="info"
                :closable="false"
                show-icon
                style="margin-bottom: 15px;"
            />
            <el-table :data="permList" border height="60vh" v-loading="permLoading" style="width: 100%">
                <el-table-column min-width="220" prop="job_name" label="Jenkins 项目" show-overflow-tooltip></el-table-column>
                <el-table-column width="100" label="公共可见" align="center">
                    <template #default="scope">
                        <el-switch v-model="scope.row.is_public" />
                    </template>
                </el-table-column>
                <el-table-column min-width="230" label="可见部门">
                    <template #default="scope">
                        <el-select v-model="scope.row.dept_ids" multiple filterable collapse-tags :reserve-keyword="false" placeholder="选择部门" style="width: 100%">
                            <el-option v-for="d in deptOptions" :key="d.id" :label="d.label" :value="d.id"></el-option>
                        </el-select>
                    </template>
                </el-table-column>
                <el-table-column min-width="200" label="可见角色">
                    <template #default="scope">
                        <el-select v-model="scope.row.role_ids" multiple filterable collapse-tags :reserve-keyword="false" placeholder="选择角色" style="width: 100%">
                            <el-option v-for="r in roleOptions" :key="r.id" :label="r.label" :value="r.id"></el-option>
                        </el-select>
                    </template>
                </el-table-column>
                <el-table-column min-width="230" label="可见用户">
                    <template #default="scope">
                        <el-select v-model="scope.row.user_ids" multiple filterable remote collapse-tags
                                   :remote-method="searchUsers" :reserve-keyword="false" placeholder="输入姓名/账号搜索选择用户" style="width: 100%">
                            <el-option v-for="u in userOptions" :key="u.id" :label="u.label" :value="u.id"></el-option>
                        </el-select>
                    </template>
                </el-table-column>
                <el-table-column width="90" label="操作" align="center" fixed="right">
                    <template #default="scope">
                        <el-button size="small" type="primary" :loading="scope.row.saving" @click="savePermRow(scope.row)">保存</el-button>
                    </template>
                </el-table-column>
            </el-table>
            <template #footer>
                <el-button @click="permDialogVisible = false">关闭</el-button>
            </template>
        </el-dialog>
    </div>
</template>

<script>
    import Pagination from "@/components/Pagination";
    import {getTableHeight} from "@/utils/util";
    import {
        packageBuildList, packageBuildDelete,
        jenkinsJobParams, packageBuildTrigger, packageBuildStatus, packageBuildLog, syncProjects,
        packageBuildDeliver, packageBuildDeliverPreview, packageBuildDeliveryFormSchema,
        packageProjectPermissions, packageProjectPermissionSave,
        apiSystemDept, apiSystemRole, apiSystemAllUser, systemUserUserInfo
    } from '@/api/api';

    export default {
        name: "packageManage",
        components:{
            Pagination,
        },
        data() {
            return {
                isFull:false,
                tableHeight:500,
                loadingPage:false,
                formInline:{
                    page: 1,
                    limit: 10,
                    project_name:'',
                    build_status:'',
                    scan_status:''
                },
                pageparm: {
                    page: 1,
                    limit: 10,
                    total: 0
                },
                tableData:[],
                statusList:[
                    {id:0,name:'构建中'},
                    {id:1,name:'成功'},
                    {id:2,name:'失败'},
                    {id:3,name:'未构建'},
                ],
                // 包扫描状态筛选（__empty__ 表示未扫描，后端按 scan_status 为空过滤）
                scanStatusList:[
                    {id:'PASS',name:'PASS'},
                    {id:'REJECT',name:'REJECT'},
                    {id:'WARN',name:'WARN'},
                    {id:'ERROR',name:'ERROR'},
                    {id:'SCANNING',name:'扫描中'},
                    {id:'__empty__',name:'未扫描'},
                ],
                // 同步按钮
                syncLoading: false,
                // 上次同步时间戳（冷却防抖：30s 内不允许重复点击，与后端限流一致）
                lastSyncTime: 0,
                // Jenkins 任务参数
                jobParameters: [],
                // 构建参数加载中
                paramsLoading: false,
                // 构建状态轮询定时器
                statusTimer: null,
                // 构建参数输入弹窗
                buildDialogVisible: false,
                buildLoading: false,
                currentBuildRow: null,
                buildFormData: {},
                // 发包审批流申请表单（勾选自动传包时填写，构建成功后自动发起审批流）
                deliveryFormFields: [],
                deliveryFormData: {},
                deliverySchemaLoading: false,
                // 详情弹窗
                detailDialogVisible: false,
                detailData: null,
                // 详情日志加载中
                logLoading: false,
                // 详情日志后台拉取轮询定时器（构建已结束但完整日志后台加载中时启用）
                logPollTimer: null,
                // 发包确认弹窗
                deliverDialogVisible: false,
                deliverPreviewLoading: false,
                deliverConfirmLoading: false,
                deliverRow: null,
                deliverPath: '',
                // 当前构建的包扫描状态（deliver_package_preview 返回 package_info 中的 ScanStatus）
                deliverScanStatus: '',
                // 当前构建的扫描报告路径（deliver_package_preview 返回 package_info 中的 ScanReport）
                deliverScanReport: '',
                // 发包确认弹窗字段配置（从 delivery_form_schema 接口解析）
                deliverSchemaFields: [],
                deliverSchemaName: '',
                // 自动回填字段列表 [{field, label, source}]（后端直接返回流程表单中开启自动回填的字段，前端按 source 消费）
                deliverAutoFillFields: [],
                // 当前用户是否管理员（控制"可见性配置"入口显示）
                isAdmin: false,
                // 项目可见性配置弹窗
                permDialogVisible: false,
                permLoading: false,
                permList: [],
                // 可见范围下拉选项
                deptOptions: [],
                roleOptions: [],
                userOptions: [],
            }
        },
        computed: {
            // 构建日志按行拆分（只展示最新 50 行，避免超长日志渲染卡顿）
            logLines() {
                const log = (this.detailData && this.detailData.build_log) || ''
                if (!log) return []
                // 去除行尾回车符（Jenkins 控制台输出可能带 \r）
                return log.split('\n').map(line => line.replace(/\r$/, '')).slice(-50)
            },
            // 根据联动规则过滤可见的发包申请表单字段（action=hidden 且条件满足时隐藏）
            visibleDeliveryFormFields() {
                return this.deliveryFormFields.filter(field => {
                    if (field.conditional_rules) {
                        for (let rule of field.conditional_rules) {
                            if (rule.action === 'hidden' && this.checkDeliveryCondition(rule)) {
                                return false
                            }
                        }
                    }
                    return true
                })
            },
            // 发包确认弹窗：从制品路径提取文件名（保留文件后缀），回填"软件包版本名称"（与后端 _extract_version_name 逻辑对齐）
            deliverVersionName() {
                const path = (this.deliverPath || '').trim().replace(/\\/g, '/').replace(/\/+$/, '')
                if (!path) return ''
                const idx = path.lastIndexOf('/')
                return idx === -1 ? path : path.substring(idx + 1)
            },
            // 发包确认弹窗：路径字段（后端按配置映射标注 source，前端按回填来源标识 package_path 匹配）
            deliverPathField() {
                return (this.deliverAutoFillFields || []).find(f => f.source === 'package_path') || null
            },
            // 发包确认弹窗：版本名称字段（回填来源标识 package_version_name 与后端 config.DELIVERY_AUTO_FILL_FIELDS 配置值对应）
            deliverVersionField() {
                return (this.deliverAutoFillFields || []).find(f => f.source === 'package_version_name') || null
            },
            // 发包确认弹窗：路径字段 label（未解析到时回退默认文案）
            deliverPathLabel() {
                return this.deliverPathField ? this.deliverPathField.label : '制品路径'
            },
            // 发包确认弹窗：版本名称字段 label（未解析到时回退默认文案）
            deliverVersionLabel() {
                return this.deliverVersionField ? this.deliverVersionField.label : '软件包版本名称'
            }
        },
        created() {
            this.getData()
            this.checkIsAdmin()
        },
        methods:{
            // 获取当前用户是否管理员（控制"可见性配置"入口显示；后端接口另有 is_superuser 双重校验）
            async checkIsAdmin() {
                try {
                    const res = await systemUserUserInfo()
                    this.isAdmin = !!(res.data && res.data.data.is_superuser)
                } catch (e) {
                    this.isAdmin = false
                }
            },
            // 打开项目可见性配置弹窗：加载授权清单 + 部门/角色下拉选项，用户通过远程搜索加载
            async openPermDialog() {
                this.permDialogVisible = true
                this.permLoading = true
                try {
                    const [permRes, deptRes, roleRes] = await Promise.all([
                        packageProjectPermissions(),
                        apiSystemDept({page: 1, limit: 1000}),
                        apiSystemRole({limit: 1000})
                    ])
                    if (permRes.code === 2000 && deptRes.code === 2000 && roleRes.code === 2000) {
                        this.deptOptions = this.flattenDepts(deptRes.data.data || [])
                        this.roleOptions = (roleRes.data.data || []).map(r => ({id: r.id, label: r.name}))
                        this.permList = (permRes.data || []).map(p => ({
                            job_name: p.job_name,
                            is_public: !!p.is_public,
                            dept_ids: p.depts.map(d => d.id),
                            role_ids: p.roles.map(r => r.id),
                            user_ids: p.users.map(u => u.id),
                            saving: false,
                        }))
                        // 预置已授权用户到远程搜索选项缓存（保证已选值能正常显示名称）
                        const cachedUsers = (permRes.data || []).reduce((acc, p) => acc.concat(p.users || []), [])
                        cachedUsers.forEach(u => {
                            const label = u.name || u.username
                            if (!this.userOptions.find(o => o.id === u.id)) {
                                this.userOptions.push({id: u.id, label})
                            }
                        })
                    } else {
                        this.$message.error(permRes.msg || '获取配置失败')
                    }
                } catch (e) {
                    this.$message.error('获取配置失败')
                } finally {
                    this.permLoading = false
                }
            },
            // 部门列表按父子关系展平为带层级缩进的下拉选项（父级在前，子级缩进）
            // 注意：后端根部门 parent 可能为 null/''/"False"/"0"（模型 default=False 导致数据库存 0），统一归一化为空字符串
            flattenDepts(list) {
                const childrenMap = {}
                const normKey = pid => (!pid || pid === 'False' || pid === 'false' || pid === '0') ? '' : String(pid)
                ;(list || []).forEach(d => {
                    const pid = normKey(d.parent)
                    if (!childrenMap[pid]) childrenMap[pid] = []
                    childrenMap[pid].push(d)
                })
                const result = []
                const walk = (pid, level) => {
                    ;(childrenMap[pid] || []).forEach(d => {
                        result.push({id: d.id, label: `${'　'.repeat(level)}${d.name}`})
                        walk(normKey(d.id), level + 1)
                    })
                }
                walk('', 0)
                return result
            },
            // 远程搜索用户（姓名/账号），结果合并进选项缓存避免重复
            searchUsers(query) {
                if (!query) return
                apiSystemAllUser({search: query, page: 1, limit: 20}).then(res => {
                    if (res.code === 2000) {
                        const list = (res.data.data || []).map(u => ({id: u.id, label: u.name || u.username}))
                        list.forEach(u => {
                            if (!this.userOptions.find(o => o.id === u.id)) {
                                this.userOptions.push(u)
                            }
                        })
                    }
                }).catch(() => {})
            },
            // 保存单行项目授权（公共开关 + 部门/角色/用户 id 列表）
            async savePermRow(row) {
                row.saving = true
                try {
                    const res = await packageProjectPermissionSave({
                        job_name: row.job_name,
                        is_public: row.is_public,
                        visible_depts: row.dept_ids || [],
                        visible_roles: row.role_ids || [],
                        visible_users: row.user_ids || [],
                    })
                    if (res.code === 2000) {
                        this.$message.success('保存成功')
                    } else {
                        this.$message.error(res.msg || '保存失败')
                    }
                } catch (e) {
                    this.$message.error('保存失败')
                } finally {
                    row.saving = false
                }
            },
            // 包扫描状态对应的标签类型（PASS绿色/REJECT红色/FAIL红色/SCANNING黄色/WARN黄色）
            getScanStatusTagType(value) {
                const v = String(value || '').trim().toUpperCase()
                if (v === 'PASS') return 'success'
                if (v === 'SCANNING' || v === 'WARN') return 'warning'
                if (v === 'REJECT' || v === 'FAIL' || v === 'ERROR') return 'danger'
                return 'info'
            },
            // 表格序列号
            getIndex($index) {
                return (this.pageparm.page-1)*this.pageparm.limit + $index +1
            },
            setFull(){
                this.isFull=!this.isFull
                window.dispatchEvent(new Event('resize'))
            },
            // 同步 Jenkins 项目
            async syncProjects() {
                // 前端冷却：防止快速连点叠加后端限流，同步刚结束/失败后 30s 内不可重复触发
                if (Date.now() - this.lastSyncTime < 30000) {
                    this.$message.warning('同步过于频繁，请稍后再试')
                    return
                }
                this.lastSyncTime = Date.now()
                this.syncLoading = true
                try {
                    const res = await syncProjects()
                    if (res.code === 2000) {
                        this.$message.success(res.msg)
                        this.getData()
                    } else {
                        // 后端互斥/限流提示（同步进行中、冷却期内）直接透传，避免误判为同步失败
                        this.$message.error(res.msg || '同步失败')
                    }
                } catch (e) {
                    this.$message.error('同步失败，请稍后重试')
                } finally {
                    this.syncLoading = false
                }
            },
            // 获取 Jenkins 任务参数（根据任务名称获取实际需要的构建参数）
            async loadJobParameters(jobName) {
                if (!jobName) return
                this.paramsLoading = true
                this.jobParameters = []
                try {
                    const res = await jenkinsJobParams({ job_name: jobName })
                    if (res.code === 2000 && res.data) {
                        // 兼容不同响应结构：直接数组 / 分页包装 data.data / JSON 字符串
                        let params = res.data
                        if (typeof params === 'string') {
                            try {
                                params = JSON.parse(params)
                            } catch (e) {
                                params = null
                            }
                        }
                        if (params && !Array.isArray(params) && Array.isArray(params.data)) {
                            params = params.data
                        }
                        if (!Array.isArray(params)) {
                            this.$message.error('构建参数数据格式异常')
                            return
                        }
                        this.jobParameters = params
                        // 初始化参数默认值
                        params.forEach(param => {
                            let defaultValue = param.default_value
                            // 布尔参数默认值转为布尔类型
                            if (param.type === 'BooleanParameterDefinition') {
                                defaultValue = !!defaultValue
                            }
                            // Vue 3 响应式对象直接赋值即可，无需 $set
                            this.buildFormData[param.name] = defaultValue ?? ''
                        })
                    } else {
                        this.$message.error(res.msg || '获取构建参数失败')
                    }
                } catch (e) {
                    console.error('获取 Jenkins 任务参数失败:', e)
                    this.$message.error('获取构建参数失败，请检查 Jenkins 服务是否可用')
                } finally {
                    this.paramsLoading = false
                }
            },
            // 获取"软件包(D包)发包流程"申请表单定义（勾选自动传包时动态渲染，预填项目名/版本）
            async loadDeliveryFormSchema(row) {
                this.deliverySchemaLoading = true
                try {
                    const res = await packageBuildDeliveryFormSchema()
                    if (res.code === 2000 && res.data) {
                        let schema = res.data.form_schema || []
                        if (typeof schema === 'string') {
                            try {
                                schema = JSON.parse(schema)
                            } catch (e) {
                                schema = []
                            }
                        }
                        if (!Array.isArray(schema)) {
                            schema = []
                        }
                        this.deliveryFormFields = schema
                        // 初始化表单数据：预填项目名与版本号，checkbox 初始化为空数组
                        this.deliveryFormData = {}
                        schema.forEach(field => {
                            if (field.field === 'project_name') {
                                this.deliveryFormData[field.field] = row.project_name || ''
                            } else if (field.type === 'checkbox') {
                                this.deliveryFormData[field.field] = []
                            } else if (field.defaultValue !== '' && field.defaultValue !== undefined && field.defaultValue !== null) {
                                this.deliveryFormData[field.field] = field.defaultValue
                            } else {
                                this.deliveryFormData[field.field] = ''
                            }
                        })
                    } else {
                        this.$message.error(res.msg || '获取发包申请表单失败')
                        this.deliveryFormFields = []
                        this.deliveryFormData = {}
                    }
                } catch (e) {
                    console.error('获取发包申请表单失败:', e)
                    this.deliveryFormFields = []
                    this.deliveryFormData = {}
                } finally {
                    this.deliverySchemaLoading = false
                }
            },
            // 判断联动规则是否满足（与流程发起弹窗 checkCondition 逻辑对齐）
            checkDeliveryCondition(rule) {
                if (!rule || !rule.trigger_field || !rule.operator) return false
                const triggerValue = this.deliveryFormData[rule.trigger_field]
                const conditionValue = rule.trigger_value
                let result = false
                switch (rule.operator) {
                    case '==':
                        if (Array.isArray(triggerValue)) {
                            result = triggerValue.includes(conditionValue)
                        } else {
                            result = String(triggerValue || '') === String(conditionValue)
                        }
                        break
                    case 'contains':
                        if (Array.isArray(triggerValue)) {
                            result = triggerValue.includes(conditionValue)
                        } else {
                            result = String(triggerValue || '').includes(conditionValue)
                        }
                        break
                    case 'not_contains':
                        if (Array.isArray(triggerValue)) {
                            result = !triggerValue.includes(conditionValue)
                        } else {
                            result = !String(triggerValue || '').includes(conditionValue)
                        }
                        break
                    default:
                        result = false
                }
                return result
            },
            // 判断字段是否必填（基础必填 + 联动规则必填；auto_fill 字段由系统自动回填）
            isDeliveryFieldRequired(field) {
                if (field.auto_fill) return false
                if (field.required) return true
                if (field.conditional_rules && field.conditional_rules.length > 0) {
                    for (let rule of field.conditional_rules) {
                        if (rule.action === 'required' && this.checkDeliveryCondition(rule)) {
                            return true
                        }
                    }
                }
                return false
            },
            // 校验发包申请表单（必填 + 联动必填，仅校验当前可见字段）
            validateDeliveryForm() {
                for (const field of this.visibleDeliveryFormFields) {
                    if (field.auto_fill) continue  // auto_fill 字段由系统自动回填
                    if (this.isDeliveryFieldRequired(field)) {
                        const value = this.deliveryFormData[field.field]
                        if (value === '' || value === null || value === undefined || (Array.isArray(value) && value.length === 0)) {
                            this.$message.warning('请填写必填项：' + field.label)
                            return false
                        }
                    }
                }
                return true
            },
            handleEdit(row,flag) {
                if(flag=='build') {
                    this.currentBuildRow = row
                    this.buildFormData = {
                        need_delivery: false
                    }
                    this.jobParameters = []
                    this.deliveryFormFields = []
                    this.deliveryFormData = {}
                    this.buildDialogVisible = true

                    // 获取 Jenkins 任务参数
                    this.loadJobParameters(row.jenkins_job_name)
                    // 预取发包审批流申请表单定义（勾选自动传包时动态展示）
                    this.loadDeliveryFormSchema(row)
                }
                else if(flag=='detail') {
                    this.showDetail(row)
                }
                else if(flag=='deliver') {
                    this.handleDeliver(row)
                }
                else if(flag=='delete') {
                    let vm = this
                    vm.$confirm('您确定要删除选中的数据吗？',{
                        closeOnClickModal:false
                    }).then(async res=>{
                        try {
                            const deleteRes = await packageBuildDelete(row.id)
                            if (deleteRes.code === 2000) {
                                vm.$message.success('删除成功')
                                vm.getData()
                            } else {
                                vm.$message.error(deleteRes.msg || '删除失败')
                            }
                        } catch (e) {
                            vm.$message.error('删除失败')
                        }
                    }).catch(()=>{
                    })
                }
                else if(flag=="reset"){
                    this.formInline = {
                        page:1,
                        limit: 10,
                        project_name:'',
                        build_status:'',
                        scan_status:''
                    }
                    this.pageparm={
                        page: 1,
                        limit: 10,
                        total: 0
                    }
                    this.getData()
                }
            },
            // 发包：打开确认弹窗，先通过预览接口获取制品路径供用户确认/手动修改，确认后才创建流程
            async handleDeliver(row) {
                this.deliverRow = row
                this.deliverPath = ''
                this.deliverScanStatus = ''
                this.deliverScanReport = ''
                this.deliverDialogVisible = true
                this.deliverPreviewLoading = true
                                // 加载发包流程表单定义（解析自动回填映射，动态获取路径/版本字段的 key 与 label）
                try {
                    if (this.deliverSchemaFields.length === 0) {
                        const schemaRes = await packageBuildDeliveryFormSchema()
                        if (schemaRes.code === 2000 && schemaRes.data && Array.isArray(schemaRes.data.form_schema)) {
                            this.deliverSchemaFields = schemaRes.data.form_schema
                            this.deliverSchemaName = schemaRes.data.workflow_type_name || ''
                            this.deliverAutoFillFields = schemaRes.data.auto_fill_fields || []
                        } else {
                            this.deliverSchemaFields = []
                            this.deliverSchemaName = ''
                        }
                    }
                } catch (e) {
                    console.error('获取发包流程表单定义失败:', e)
                    this.deliverSchemaFields = []
                    this.deliverSchemaName = ''
                }
                try {
                    const res = await packageBuildDeliverPreview(row.id)
                    if (res.code === 2000 && res.data) {
                        this.deliverPath = res.data.package_path || ''
                        this.deliverScanStatus = res.data.scan_status || ''
                        this.deliverScanReport = res.data.scan_report || ''
                        if (!this.deliverPath) {
                            // 路径只读不可手动填写：未获取到制品路径时不允许继续发包
                            this.$message.error('未获取到制品路径，无法发包，请检查 Jenkins 构建制品')
                            this.deliverDialogVisible = false
                        }
                    } else {
                        // 预览失败：无法确认制品路径时不允许继续发包，避免误建流程
                        this.$message.error(res.msg || '获取制品路径失败')
                        this.deliverDialogVisible = false
                    }
                } catch (e) {
                    console.error('获取制品路径失败:', e)
                    this.$message.error('获取制品路径失败，请检查 Jenkins 服务是否可用')
                    this.deliverDialogVisible = false
                } finally {
                    this.deliverPreviewLoading = false
                }
            },
            // 确认发包：校验制品路径非空后，按自动回填映射动态解析字段 key 提交（路径 + 版本名称）创建发包流程
            async confirmDeliver() {
                const path = (this.deliverPath || '').trim()
                if (!path) {
                    this.$message.warning('请填写制品路径')
                    return
                }
                // 路径/版本字段由后端按配置映射解析；缺失时阻止发包，避免静默失败
                if (!this.deliverPathField || !this.deliverVersionField) {
                    this.$message.error('发包流程表单自动回填字段配置异常，请在流程配置中为路径/版本名称字段开启"自动回填"开关')
                    return
                }
                const payload = {}
                payload[this.deliverPathField.field] = path
                payload[this.deliverVersionField.field] = this.deliverVersionName
                this.deliverConfirmLoading = true
                try {
                    const res = await packageBuildDeliver(this.deliverRow.id, payload)
                    if (res.code === 2000 && res.data) {
                        this.$message.success(res.data.instance_no ? `已创建发包流程：${res.data.instance_no}` : (res.msg || '发包成功'))
                        this.deliverDialogVisible = false
                        this.getData()
                        this.$confirm(
                            `发包流程已创建（${res.data.title}），\n软件包存放路径已自动填写，其余申请字段请按提示填写。\n\n是否前往流程管理补全申请信息并提交？`,
                            '创建成功',
                            { closeOnClickModal: false, showCancelButton: true, confirmButtonText: '前往补全', cancelButtonText: '稍后处理' }
                        ).then(() => {
                            // 跳转流程管理并自动打开该流程的发起弹窗，便于直接补全申请信息后提交
                            this.$router.push({ path: '/workflowList', query: { initiate_instance: res.data.workflow_instance_id } })
                        }).catch(() => {})
                    } else {
                        this.$message.error(res.msg || '发包失败')
                    }
                } catch (e) {
                    console.error('发包失败:', e)
                    this.$message.error('发包失败，请检查 Jenkins 服务或流程配置')
                } finally {
                    this.deliverConfirmLoading = false
                }
            },
            // 确认构建
            async confirmBuild() {
                if (!this.currentBuildRow) return

                // 校验选择型参数必须已选择
                for (const param of this.jobParameters) {
                    if (param.type === 'ChoiceParameterDefinition' && !this.buildFormData[param.name]) {
                        this.$message.warning(`请选择参数：${param.name}`)
                        return
                    }
                }

                // 勾选自动传包：先校验发包审批流申请表单必填项
                if (this.buildFormData.need_delivery && !this.validateDeliveryForm()) {
                    return
                }

                this.buildLoading = true
                try {
                    // 构建参数（排除 need_delivery）
                    const buildParams = {}
                    for (const key in this.buildFormData) {
                        if (key !== 'need_delivery') {
                            buildParams[key] = this.buildFormData[key]
                        }
                    }

                    // 发包审批流申请表单数据（auto_fill 字段由构建成功后自动回填，不随请求提交）
                    const deliveryFormData = {}
                    if (this.buildFormData.need_delivery) {
                        for (const key in this.deliveryFormData) {
                            const schemaField = this.deliveryFormFields.find(f => f.field === key)
                            if (schemaField && schemaField.auto_fill) continue
                            deliveryFormData[key] = this.deliveryFormData[key]
                        }
                    }

                    const res = await packageBuildTrigger(this.currentBuildRow.id, {
                        build_params: buildParams,
                        need_delivery: this.buildFormData.need_delivery,
                        delivery_form_data: deliveryFormData
                    })
                    if (res.code === 2000) {
                        this.$message.success(res.msg || '构建已触发')
                        this.buildDialogVisible = false

                        // 如果需要传包，提示用户
                        if (this.buildFormData.need_delivery) {
                            this.$message.info('构建完成后将自动获取制品路径并自动发起发包审批流程')
                        }

                        this.getData()
                        // 轮询新构建记录状态（每次触发创建独立记录，后端返回的 id 才是本次构建），构建结束后自动刷新结果
                        this.startStatusPolling(res.data.id)
                    } else {
                        this.$message.error(res.msg || '构建触发失败')
                    }
                } catch (e) {
                    this.$message.error('构建触发失败')
                } finally {
                    this.buildLoading = false
                }
            },
            // 轮询 Jenkins 构建状态，构建结束后自动更新列表并提示结果；构建中实时同步编号到列表行
            startStatusPolling(id) {
                if (this.statusTimer) {
                    clearInterval(this.statusTimer)
                }
                this.statusTimer = setInterval(async () => {
                    try {
                        const res = await packageBuildStatus(id)
                        if (res.code === 2000 && res.data) {
                            if (res.data.building) {
                                // 构建中：后端已解析出构建编号时实时更新列表行展示，避免构建期间编号一直显示“—”
                                if (res.data.build_number && !res.data.queued) {
                                    const row = this.tableData.find(item => item.id === id)
                                    if (row && row.jenkins_build_number !== res.data.build_number) {
                                        row.jenkins_build_number = res.data.build_number
                                    }
                                }
                                return
                            }
                            clearInterval(this.statusTimer)
                            this.statusTimer = null
                            // 构建结束后的收尾：刷新列表 + 结果提示（等日志就绪后再一次性执行，保证列表编号/状态/日志摘要同时到位）
                            const showResult = () => {
                                this.getData()
                                if (res.data.result === 'SUCCESS') {
                                    this.$message.success('构建成功')
                                    // 勾选了自动传包：提示审批流已自动发起（以本次触发表单为准，模板行可能不同）
                                    if (this.buildFormData.need_delivery) {
                                        this.$message.info('构建成功，已自动发起"软件包(D包)发包流程"，可前往流程管理查看')
                                    }
                                } else {
                                    this.$message.error(`构建失败：${res.data.result || '未知原因'}`)
                                }
                            }
                            // 触发后台拉取完整日志（接口立即返回，log_ready=false 表示后台任务拉取中）：
                            // 等待日志就绪后刷新列表；超时（约 30 秒）也先刷新，避免状态/编号迟迟不更新
                            try {
                                const logRes = await packageBuildLog(id)
                                if (logRes.code === 2000 && logRes.data && logRes.data.log_ready === false) {
                                    this.startLogPolling(id, { requireDialog: false, onReady: showResult, onTimeout: showResult })
                                } else {
                                    showResult()
                                }
                            } catch (e) {
                                // 日志获取失败不影响状态更新
                                showResult()
                            }
                        }
                    } catch (e) {
                        // 构建排队中或临时错误，继续轮询
                        console.error('轮询构建状态失败:', e)
                    }
                }, 5000)
            },
            // 显示详情（日志接口已异步化：立即返回数据库缓存，完整日志由后台任务拉取后轮询补齐，不阻塞弹窗展示）
            async showDetail(row) {
                // 先用行数据填充基本信息（列表接口不再返回完整日志）
                this.detailData = { ...row, build_log: '', logOffset: 0 }
                this.detailDialogVisible = true
                this.logLoading = true
                // 本地状态为“构建中”时向 Jenkins 确认一次真实状态（并行执行不阻塞日志加载；轮询可能已中断，纠正滞后显示）
                if (this.detailData.build_status === 0) {
                    packageBuildStatus(row.id).then(st => {
                        if (st.code === 2000 && st.data && !st.data.building) {
                            this.detailData.build_status = st.data.result === 'SUCCESS' ? 1 : 2
                        }
                    }).catch(() => {
                        // 状态确认失败不影响详情展示
                    })
                }
                // 加载日志：接口立即返回缓存内容（无缓存时投递后台任务拉取，log_ready=false）
                try {
                    const res = await packageBuildLog(row.id)
                    if (res.code === 2000 && res.data) {
                        this.detailData = {
                            ...this.detailData,
                            build_log: res.data.log || '',
                            logOffset: res.data.offset || 0
                        }
                        // 构建已结束但完整日志后台加载中：轮询等待后台任务完成（构建中由“刷新”按钮增量拉取）
                        if (res.data.log_ready === false && !res.data.building) {
                            this.startLogPolling(row.id)
                        }
                    }
                } catch (e) {
                    // 日志获取失败不影响详情显示
                } finally {
                    this.logLoading = false
                }
                // 刷新列表同步更新状态/扫描信息展示（不阻塞弹窗；日志内容保留在详情中）
                this.getData().then(() => {
                    const updated = this.tableData.find(item => item.id === row.id)
                    if (updated) {
                        this.detailData = { ...updated, build_log: this.detailData.build_log, logOffset: this.detailData.logOffset }
                    }
                })
                // 打开后滚动到日志底部，便于查看最新输出
                this.scrollLogToBottom()
            },
            // 轮询等待后台任务拉取完整日志（构建已结束但数据库无完整缓存时启用；log_ready=true 或超时/关闭弹窗后停止）
            // options: { requireDialog: 弹窗关闭时是否停止（列表场景传 false）, onReady: 日志就绪回调, onTimeout: 超时/停止回调 }
            startLogPolling(id, options = {}) {
                this.stopLogPolling()
                const { requireDialog = true, onReady = null, onTimeout = null } = options
                let count = 0
                this.logPollTimer = setInterval(async () => {
                    count++
                    // 弹窗已关闭（详情场景）或超过轮询上限（约 30 秒）时停止
                    if ((requireDialog && !this.detailDialogVisible) || count > 15) {
                        this.stopLogPolling()
                        if (onTimeout) onTimeout()
                        return
                    }
                    try {
                        const res = await packageBuildLog(id)
                        if (res.code === 2000 && res.data) {
                            // 后台拉取中已有部分缓存时先展示（仅详情弹窗场景），完整日志就绪后停止轮询
                            if (requireDialog && (res.data.log_ready !== false || res.data.log)) {
                                this.detailData = {
                                    ...this.detailData,
                                    build_log: res.data.log || this.detailData.build_log,
                                    logOffset: res.data.offset || 0
                                }
                            }
                            if (res.data.log_ready === true) {
                                this.stopLogPolling()
                                this.scrollLogToBottom()
                                if (onReady) onReady()
                            }
                        }
                    } catch (e) {
                        // 单次轮询失败不中断，继续等待下次
                    }
                }, 2000)
            },
            stopLogPolling() {
                if (this.logPollTimer) {
                    clearInterval(this.logPollTimer)
                    this.logPollTimer = null
                }
            },
            // 日志面板滚动到底部（打开/刷新/轮询就绪后调用）
            scrollLogToBottom() {
                this.$nextTick(() => {
                    const body = this.$refs.logBody
                    if (body) {
                        body.scrollTop = body.scrollHeight
                    }
                })
            },
            // 刷新详情日志：构建已结束后全量替换为最新完整日志；构建中增量追加新增内容
            async refreshDetailLog() {
                if (!this.detailData) return
                this.logLoading = true
                try {
                    // 先获取最新构建状态，决定刷新模式（避免本地状态滞后导致刷新方式错误）
                    let isFinished = !!(this.detailData.build_status && this.detailData.build_status !== 0)
                    try {
                        const st = await packageBuildStatus(this.detailData.id)
                        if (st.code === 2000 && st.data) {
                            isFinished = !st.data.building
                        }
                    } catch (e) {
                        // 状态获取失败时沿用本地状态
                    }

                    // 构建结束：全量请求并替换（后端优先返回完整日志，避免增量拼接错位）；
                    // 构建中：仅请求上次之后的增量并追加，避免全量传输
                    const offset = isFinished ? 0 : (this.detailData.logOffset || 0)
                    const res = await packageBuildLog(this.detailData.id, { offset })
                    if (res.code === 2000 && res.data) {
                        if (isFinished) {
                            // 完整日志就绪（log_ready=true）或为后台加载中的缓存：先替换展示，
                            // 后台任务拉取完成后由轮询补齐（log_ready=false 时启动）
                            this.detailData = {
                                ...this.detailData,
                                build_log: res.data.log || '',
                                logOffset: res.data.offset || 0
                            }
                            if (res.data.log_ready === false) {
                                this.startLogPolling(this.detailData.id)
                            }
                        } else {
                            const newLog = res.data.log || ''
                            if (newLog) {
                                // 增量追加，并仅在内存保留最近 2000 行，避免多次刷新后内存无限增长
                                let merged = (this.detailData.build_log || '') + newLog
                                const lines = merged.split('\n')
                                if (lines.length > 2000) {
                                    merged = lines.slice(-2000).join('\n')
                                }
                                this.detailData = {
                                    ...this.detailData,
                                    build_log: merged,
                                    logOffset: res.data.offset || 0
                                }
                            }
                        }
                    }
                    // 同步刷新列表中的状态等基础信息（不包含完整日志）
                    await this.getData()
                    const updated = this.tableData.find(item => item.id === this.detailData.id)
                    if (updated) {
                        this.detailData = { ...updated, build_log: this.detailData.build_log, logOffset: this.detailData.logOffset }
                    }
                    // 刷新后滚动到底部，便于查看最新日志
                    this.scrollLogToBottom()
                } catch (e) {
                    this.$message.error('刷新日志失败')
                } finally {
                    this.logLoading = false
                }
            },
            // 复制构建日志到剪贴板
            async copyBuildLog() {
                const log = (this.detailData && this.detailData.build_log) || ''
                if (!log) {
                    this.$message.warning('暂无日志可复制')
                    return
                }
                try {
                    await navigator.clipboard.writeText(log)
                    this.$message.success('日志已复制到剪贴板')
                } catch (e) {
                    this.$message.error('复制失败，请手动选择复制')
                }
            },
            // 日志行 HTML 转义（防 XSS）
            escapeHtml(str) {
                return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
            },
            // 时间戳转换：UTC（Z 后缀）→ 浏览器本地时区（中国为 UTC+8），避免日志时间比实际少 8 小时
            convertLogTimestamp(line) {
                return line.replace(/\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)\]/g, (match, ts) => {
                    const date = new Date(ts)
                    if (isNaN(date.getTime())) return match
                    const pad = (n) => String(n).padStart(2, '0')
                    return `[${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}]`
                })
            },
            // 日志行着色：先转 UTC 时间为本地时间，再转义，最后按级别高亮关键词
            highlightLogLine(line) {
                let html = this.escapeHtml(this.convertLogTimestamp(line))
                // 错误 / 失败
                html = html.replace(/(ERROR|FATAL|FAILED|FAILURE|Exception|Traceback|error:|fatal:)/g, '<span class="log-err">$1</span>')
                // 警告
                html = html.replace(/(WARNING|WARN)/g, '<span class="log-warn">$1</span>')
                // 成功
                html = html.replace(/(SUCCESS|SUCCESSFUL|BUILD SUCCESSFUL|finished: SUCCESS)/g, '<span class="log-ok">$1</span>')
                return html
            },
            callFather(parm) {
                this.formInline.page = parm.page
                this.formInline.limit = parm.limit
                this.getData()
            },
            search() {
                this.formInline.page = 1
                this.formInline.limit = 10
                this.getData()
            },
            //获取列表
            async getData() {
                this.loadingPage = true
                try {
                    const res = await packageBuildList(this.formInline)
                    this.loadingPage = false
                    if (res.code === 2000) {
                        this.tableData = res.data.data || []
                        this.pageparm.page = res.data.page
                        this.pageparm.limit = res.data.limit
                        this.pageparm.total = res.data.total
                    }
                } catch (e) {
                    this.loadingPage = false
                    console.error('获取打包列表失败:', e)
                }
            },
            // 计算搜索栏的高度
            listenResize() {
                this.$nextTick(() => {
                    this.getTheTableHeight()
                })
            },
            getTheTableHeight(){
                let tabSelectHeight = this.$refs.tableSelect?this.$refs.tableSelect.offsetHeight:0
                tabSelectHeight = this.isFull?tabSelectHeight - 110:tabSelectHeight
                this.tableHeight = getTableHeight(tabSelectHeight)
            }
        },
        mounted() {
            window.addEventListener('resize', this.listenResize);
            this.$nextTick(() => {
                this.getTheTableHeight()
            })
        },
        unmounted() {
            window.removeEventListener("resize", this.listenResize);
            if (this.statusTimer) {
                clearInterval(this.statusTimer)
            }
            this.stopLogPolling()
        },
    }
</script>

<style lang="scss" scoped>
    /* 发包确认弹窗提示区 */
    .deliver-tip {
        background: #f0f9eb;
        border: 1px solid #e1f3d8;
        border-radius: 4px;
        color: #67c23a;
        font-size: 13px;
        line-height: 1.6;
        padding: 10px 12px;
        margin-bottom: 15px;
    }

    .deliver-tip-sub {
        color: #909399;
        font-size: 12px;
        line-height: 1.6;
        min-height: 20px;
    }

    /* 构建日志终端面板 */
    .log-panel {
        margin-top: 16px;
        border: 1px solid #e4e7ed;
        border-radius: 4px;
        overflow: hidden;

        .log-panel-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 6px 12px;
            background: #f5f7fa;
            border-bottom: 1px solid #e4e7ed;

            .log-panel-title {
                display: flex;
                align-items: center;
                gap: 8px;
                font-weight: 600;
                font-size: 14px;
                color: #303133;
            }
        }

        .log-body {
            max-height: 420px;
            overflow: auto;
            background: #1e1e1e;
            color: #d4d4d4;
            font-family: Consolas, Monaco, 'Courier New', monospace;
            font-size: 12px;
            line-height: 1.7;

            .log-line {
                display: flex;
                padding: 0 12px 0 0;

                &:hover {
                    background: rgba(255, 255, 255, 0.06);
                }

                .log-line-num {
                    flex: none;
                    width: 48px;
                    padding-right: 12px;
                    text-align: right;
                    color: #6a737d;
                    user-select: none;
                    border-right: 1px solid rgba(255, 255, 255, 0.08);
                    margin-right: 12px;
                    background: #252526;
                }

                .log-line-content {
                    white-space: pre-wrap;
                    word-break: break-all;
                }
            }

            .log-empty {
                padding: 30px 0;
                text-align: center;
                color: #8a8a8a;
            }

            /* 级别着色（v-html 注入内容需用 :deep 命中） */
            :deep(.log-err) { color: #f47067; font-weight: 600; }
            :deep(.log-warn) { color: #e5c07b; }
            :deep(.log-ok) { color: #89d185; }
        }
    }
</style>
