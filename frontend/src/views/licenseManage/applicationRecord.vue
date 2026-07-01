<template>
    <div :class="{'ly-is-full':isFull}">
        <!-- 搜索区域 -->
        <div class="tableSelect" ref="tableSelect">
            <el-form :inline="true" :model="formInline" label-position="left">
                <el-form-item label="申请人：">
                    <el-input size="default" v-model.trim="formInline.applicant" maxlength="60" clearable placeholder="申请人" @change="search" style="width:150px"></el-input>
                </el-form-item>
                <el-form-item label="License类型：">
                    <el-select v-model="formInline.application_type" placeholder="请选择" clearable @change="search" size="default" style="width:120px">
                        <el-option label="FlexNet" value="flexnet"></el-option>
                        <el-option label="Bitanswer" value="bitanswer"></el-option>
                    </el-select>
                </el-form-item>
                <el-form-item label="客户名称：">
                    <el-input size="default" v-model.trim="formInline.customer_name" maxlength="60" clearable placeholder="客户名称" @change="search" style="width:150px"></el-input>
                </el-form-item>
                <el-form-item label="序列号：">
                    <el-input size="default" v-model.trim="formInline.serial_number" maxlength="100" clearable placeholder="序列号" @change="search" style="width:180px"></el-input>
                </el-form-item>
                <el-form-item label="产品名称：">
                    <el-input size="default" v-model.trim="formInline.product_name" maxlength="100" clearable placeholder="产品名称" @change="search" style="width:150px"></el-input>
                </el-form-item>
                <el-form-item label="状态：">
                    <el-select v-model="formInline.status" placeholder="请选择" clearable @change="search" size="default" style="width:120px">
                        <el-option label="待制作" :value="3"></el-option>
                        <el-option label="制作中" :value="2"></el-option>
                        <el-option label="制作成功" :value="1"></el-option>
                        <el-option label="制作失败" :value="0"></el-option>
                    </el-select>
                </el-form-item>
                <el-form-item label="">
                    <el-button @click="search" type="primary" icon="Search" v-show="hasPermission(this.$route.name,'Search')">查询</el-button>
                </el-form-item>
                <el-form-item label="">
                    <el-button @click="handleEdit('','reset')" icon="Refresh">重置</el-button>
                </el-form-item>
                <el-form-item label="">
                    <el-button @click="handleEdit('','add')" type="primary" icon="Plus" v-show="hasPermission(this.$route.name,'Create')">新增</el-button>
                </el-form-item>
            </el-form>
        </div>

        <!-- 表格区域 -->
        <div class="table">
            <el-table :height="'calc('+(tableHeight)+'px)'" border :data="tableData" ref="tableref" v-loading="loadingPage" style="width: 100%">
                <el-table-column type="index" width="60" align="center" label="序号">
                    <template #default="scope">
                        <span v-text="getIndex(scope.$index)"></span>
                    </template>
                </el-table-column>
                <el-table-column min-width="100" prop="applicant" label="申请人" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="100" prop="application_type_display" label="License类型" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="150" prop="keyword" label="关键字" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="120" prop="customer_name" label="客户名称" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="150" prop="mac_address" label="MAC Address/HostID" show-overflow-tooltip></el-table-column>
                <!-- 产品组特殊处理：显示产品名称、开始时间、结束时间三列 -->
                <el-table-column v-if="hasProductGroup()" min-width="150" label="产品名称">
                    <template #default="scope">
                        <div v-if="scope.row.user_info_list && scope.row.user_info_list.length > 0">
                            <div v-for="(item, index) in scope.row.user_info_list" :key="index" 
                                 class="product-cell-item">
                                {{ item.product }}
                            </div>
                        </div>
                        <span v-else>{{ scope.row.quantity }}</span>
                    </template>
                </el-table-column>
                <!-- ✅ Feature 列：放在产品名称后面，只显示 features 内容 -->
                <el-table-column min-width="350" prop="feature" label="Feature" align="left">
                    <template #default="scope">
                        <!-- 产品组：从 user_info_list 中获取每个产品的 features -->
                        <div v-if="scope.row.user_info_list && scope.row.user_info_list.length > 0" class="product-feature-list">
                            <div v-for="(item, index) in scope.row.user_info_list" :key="index" 
                                 class="product-feature-row">
                                <div class="feature-content">
                                    <pre :class="{'expanded': expandedFeatures[item.product + '_' + scope.row.id]}" 
                                         class="feature-text">{{ getProductFeaturesText(item, scope.row.quantity, scope.row.id) }}</pre>
                                    <div v-if="shouldShowExpandProductFeatures(item, scope.row.quantity, scope.row.id)" 
                                         class="expand-btn-inline" 
                                         @click="toggleExpand('product_feature', item.product + '_' + scope.row.id)">
                                        <el-icon><ArrowDown v-if="!expandedFeatures[item.product + '_' + scope.row.id]" /><ArrowUp v-else /></el-icon>
                                        {{ expandedFeatures[item.product + '_' + scope.row.id] ? '收起' : '展开' }}
                                    </div>
                                </div>
                            </div>
                        </div>
                        <!-- 非产品组：直接从 quantity 中解析 features -->
                        <div v-else-if="scope.row.quantity && typeof scope.row.quantity === 'object'" class="non-product-feature">
                            <pre :class="{'expanded': expandedFeatures[scope.row.id]}" 
                                 class="feature-text">{{ getQuantityFeaturesText(scope.row.quantity, scope.row.id) }}</pre>
                            <div v-if="shouldShowExpandQuantityFeatures(scope.row.quantity, scope.row.id)" 
                                 class="expand-btn-inline" 
                                 @click="toggleExpand('quantity', scope.row.id)">
                                <el-icon><ArrowDown v-if="!expandedFeatures[scope.row.id]" /><ArrowUp v-else /></el-icon>
                                {{ expandedFeatures[scope.row.id] ? '收起' : '展开' }}
                            </div>
                        </div>
                        <!-- 普通字符串格式 -->
                        <span v-else>{{ scope.row.feature }}</span>
                    </template>
                </el-table-column>
                <el-table-column v-if="hasProductGroup()" min-width="150" label="开始时间">
                    <template #default="scope">
                        <div v-if="scope.row.user_info_list && scope.row.user_info_list.length > 0">
                            <div v-for="(item, index) in scope.row.user_info_list" :key="index" 
                                 class="product-cell-item">
                                {{ item.start_date || '--' }}
                            </div>
                        </div>
                        <span v-else>{{ scope.row.start_time }}</span>
                    </template>
                </el-table-column>
                <el-table-column v-if="hasProductGroup()" min-width="150" label="结束时间">
                    <template #default="scope">
                        <div v-if="scope.row.user_info_list && scope.row.user_info_list.length > 0">
                            <div v-for="(item, index) in scope.row.user_info_list" :key="index" 
                                 class="product-cell-item">
                                {{ item.end_date || '--' }}
                            </div>
                        </div>
                        <span v-else>{{ scope.row.end_time }}</span>
                    </template>
                </el-table-column>
                
                <!-- 非产品组：显示开始时间、结束时间（授权数量已合并到 Feature 列） -->
                <el-table-column v-if="!hasProductGroup()" min-width="150" prop="start_time" label="开始时间"></el-table-column>
                <el-table-column v-if="!hasProductGroup()" min-width="150" prop="end_time" label="结束时间"></el-table-column>
                <el-table-column min-width="100" label="状态">
                    <template #default="scope">
                        <el-tag v-if="scope.row.status==3" type="info">待制作</el-tag>
                        <el-tag v-else-if="scope.row.status==2" type="warning">制作中</el-tag>
                        <el-tag v-else-if="scope.row.status==1" type="success">制作成功</el-tag>
                        <el-tag v-else-if="scope.row.status==0" type="danger">制作失败</el-tag>
                    </template>
                </el-table-column>
                <el-table-column min-width="100" prop="retry_count" label="重试次数" align="center">
                    <template #default="scope">
                        <span>{{ scope.row.retry_count }}/{{ scope.row.max_retry_count || 3 }}</span>
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
                        <span class="table-operate-btn" @click="handleEdit(scope.row, 'edit')" v-show="hasPermission(this.$route.name,'Update')">编辑</span>
                        <span 
                            class="table-operate-btn" 
                            :class="{ 'disabled-btn': isEndTimeExpired(scope.row.end_time) || !scope.row.start_time || !scope.row.end_time || scope.row.status === 1 || scope.row.status === 2 }"
                            @click="!isEndTimeExpired(scope.row.end_time) && scope.row.start_time && scope.row.end_time && scope.row.status !== 1 && scope.row.status !== 2 && handleGenerate(scope.row)" 
                            v-show="hasPermission(this.$route.name,'Generate') && (scope.row.status==3)"
                            :title="!scope.row.start_time || !scope.row.end_time ? '开始时间或结束时间未设置，无法制作' : (isEndTimeExpired(scope.row.end_time) ? '结束时间已过期，无法制作' : (scope.row.status === 1 ? 'License已制作成功，无需再次制作' : (scope.row.status === 2 ? 'License正在制作中...' : '制作License')))"
                        >制作License</span>
                        <span class="table-operate-btn" @click="handleRetry(scope.row)" v-show="hasPermission(this.$route.name,'Retry') && scope.row.status==0 && scope.row.retry_count < (scope.row.max_retry_count || 3)">重试</span>
                        <span class="table-operate-btn" @click="handleViewDetail(scope.row)" v-show="hasPermission(this.$route.name,'Retrieve')">详情</span>
                        <span class="table-operate-btn" @click="handleDelete(scope.row)" v-show="hasPermission(this.$route.name,'Delete')">删除</span>
                    </template>
                </el-table-column>
            </el-table>
        </div>
        
        <!-- 分页 -->
        <Pagination v-bind:child-msg="pageparm" @callFather="callFather"></Pagination>

        <!-- 详情对话框 -->
        <el-dialog v-model="detailDialogVisible" title="申请详情" width="800px">
            <el-descriptions :column="2" border v-if="currentRow">
                <el-descriptions-item label="申请人">{{ currentRow.applicant }}</el-descriptions-item>
                <el-descriptions-item label="License类型">{{ currentRow.application_type_display }}</el-descriptions-item>
                <!-- <el-descriptions-item label="Feature" :span="2">
                    <pre v-if="currentRow.feature && Array.isArray(currentRow.feature)" style="margin: 0; font-size: 13px; line-height: 1.6; background: #f5f7fa; padding: 10px; border-radius: 4px;">{{ currentRow.feature.join('\n') }}</pre>
                    <pre v-else-if="currentRow.feature && typeof currentRow.feature === 'object'" style="margin: 0; font-size: 13px; line-height: 1.6; background: #f5f7fa; padding: 10px; border-radius: 4px;">{{ JSON.stringify(currentRow.feature, null, 2) }}</pre>
                    <span v-else>{{ currentRow.feature }}</span>
                </el-descriptions-item> -->
                <el-descriptions-item label="关键字">{{ currentRow.keyword }}</el-descriptions-item>
                <el-descriptions-item label="客户名称">{{ currentRow.customer_name }}</el-descriptions-item>
                <el-descriptions-item label="MAC Address">{{ currentRow.mac_address }}</el-descriptions-item>
                <el-descriptions-item label="授权数量" :span="2">
                    <pre v-if="currentRow.quantity && typeof currentRow.quantity === 'object'" style="margin: 0; font-size: 13px; line-height: 1.6; background: #f5f7fa; padding: 10px; border-radius: 4px;">{{ JSON.stringify(currentRow.quantity, null, 2) }}</pre>
                    <span v-else>{{ currentRow.quantity }}</span>
                </el-descriptions-item>
                <el-descriptions-item label="状态">{{ currentRow.status_display }}</el-descriptions-item>
                <el-descriptions-item label="开始时间">{{ currentRow.start_time }}</el-descriptions-item>
                <el-descriptions-item label="结束时间">{{ currentRow.end_time }}</el-descriptions-item>
                <el-descriptions-item label="创建时间" :span="2">{{ currentRow.create_datetime }}</el-descriptions-item>
                <el-descriptions-item label="失败原因" :span="2" v-if="currentRow.fail_reason">{{ currentRow.fail_reason }}</el-descriptions-item>
                <el-descriptions-item label="重试次数">{{ currentRow.retry_count }}</el-descriptions-item>
            </el-descriptions>
            <template #footer>
                <el-button @click="detailDialogVisible = false">关闭</el-button>
            </template>
        </el-dialog>

        <!-- 新增/编辑对话框 -->
        <el-dialog v-model="dialogVisible" :title="dialogType === 'add' ? '新增申请' : '编辑申请'" width="700px" @close="handleDialogClose">
            <el-form :model="form" :rules="rules" ref="formRef" label-width="120px">
                <el-row :gutter="20">
                    <el-col :span="12">
                        <el-form-item label="申请人" prop="applicant">
                            <el-input v-model="form.applicant" placeholder="请输入申请人" clearable></el-input>
                        </el-form-item>
                    </el-col>
                    <el-col :span="12">
                        <el-form-item label="申请人账号" prop="applicant_id">
                            <el-input v-model="form.applicant_id" placeholder="请输入申请人账号（如ltjiadong）" clearable></el-input>
                        </el-form-item>
                    </el-col>
                </el-row>
                <el-row :gutter="20">
                    <el-col :span="12">
                        <el-form-item label="License类型" prop="application_type">
                            <el-select v-model="form.application_type" placeholder="请选择" style="width: 100%">
                                <el-option label="FlexNet" value="flexnet"></el-option>
                                <el-option label="Bitanswer" value="bitanswer"></el-option>
                            </el-select>
                        </el-form-item>
                    </el-col>
                    <el-col :span="12">
                        <el-form-item label="客户名称" prop="customer_name">
                            <el-input v-model="form.customer_name" placeholder="请输入客户名称" clearable></el-input>
                        </el-form-item>
                    </el-col>
                    <el-col :span="12">
                        <el-form-item label="MAC Address" prop="mac_address">
                            <el-input v-model="form.mac_address" placeholder="请输入MAC地址/HostID" clearable></el-input>
                        </el-form-item>
                    </el-col>
                </el-row>
                <el-form-item label="Feature" prop="feature">
                    <el-input v-model="form.feature" type="textarea" :rows="3" placeholder="请输入Feature，多个用逗号分隔"></el-input>
                </el-form-item>
                <el-row :gutter="20">
                    <el-col :span="12">
                        <el-form-item label="关键字" prop="keyword">
                            <el-input v-model="form.keyword" placeholder="用于匹配映射表中的selectField字段" clearable></el-input>
                        </el-form-item>
                    </el-col>
                    <el-col :span="12">
                        <el-form-item label="申请序列号" prop="serial_number">
                            <el-input 
                                v-model="form.serial_number" 
                                placeholder="请输入唯一序列号，防止重复申请" 
                                clearable
                                :disabled="dialogType === 'edit'"
                            ></el-input>
                            <div style="font-size: 12px; color: #909399; margin-top: 4px;">
                                {{ dialogType === 'edit' ? '编辑时不可修改序列号' : '每个申请的唯序列号，不能重复' }}
                            </div>
                        </el-form-item>
                    </el-col>
                </el-row>
                <el-row :gutter="20">
                    <el-col :span="12">
                        <el-form-item label="开始时间" prop="start_time">
                            <el-date-picker 
                                v-model="form.start_time" 
                                type="date" 
                                placeholder="选择开始时间" 
                                style="width: 100%" 
                                value-format="YYYY-MM-DD"
                                :disabled-date="disabledStartDate">
                            </el-date-picker>
                        </el-form-item>
                    </el-col>
                </el-row>
                <el-row :gutter="20">
                    <el-col :span="12">
                        <el-form-item label="结束时间" prop="end_time">
                            <el-date-picker 
                                v-model="form.end_time" 
                                type="date" 
                                placeholder="选择结束时间" 
                                style="width: 100%" 
                                value-format="YYYY-MM-DD"
                                :disabled-date="disabledEndDate">
                            </el-date-picker>
                        </el-form-item>
                    </el-col>
                </el-row>
                <el-form-item label="授权数量" prop="quantity">
                    <el-input 
                        v-model="form.quantity" 
                        type="textarea" 
                        :rows="8" 
                        placeholder='请输入 JSON 格式，例如：{"GloryEX": 10, "GloryEX_Basic": 5}'
                        style="font-family: monospace; font-size: 13px;"
                    ></el-input>
                    <div style="color: #909399; font-size: 12px; margin-top: 5px;">
                        <i class="el-icon-info"></i> 提示：使用 JSON 格式，每个 Feature 对应一个数量
                    </div>
                </el-form-item>
            </el-form>
            <template #footer>
                <el-button @click="dialogVisible = false">取消</el-button>
                <el-button type="primary" @click="handleSubmit" :loading="submitLoading">确定</el-button>
            </template>
        </el-dialog>
    </div>
</template>

<script>
    import Pagination from "@/components/Pagination";
    import {getTableHeight} from "@/utils/util";
    import {licenseApplication, licenseApplicationAdd, licenseApplicationEdit, licenseApplicationDelete, licenseApplicationGenerate, licenseApplicationRetry} from '@/api/api';
    
    export default {
        name: "applicationRecord",
        components:{
            Pagination,
        },
        data() {
            return {
                isFull:false,
                tableHeight:500,
                loadingPage:false,
                detailDialogVisible: false,
                currentRow: null,
                // 展开/收起状态 - 使用对象确保响应式
                expandedFeatures: {},  // 记录每个行的Feature是否展开 {id: true/false}
                expandedQuantities: {},  // 记录每个行的Quantity是否展开 {id: true/false}
                // 新增/编辑对话框
                dialogVisible: false,
                dialogType: 'add', // 'add' or 'edit'
                submitLoading: false,
                form: {
                    id: '',
                    applicant: '',
                    applicant_id: '',
                    application_type: '',
                    feature: '',
                    keyword: '',
                    serial_number: '',
                    customer_name: '',
                    mac_address: '',
                    start_time: '',
                    end_time: '',
                    quantity: 1,
                    status: 3, // 默认待制作
                    max_retry_count: 3
                },
                rules: {
                    applicant: [
                        { required: true, message: '请输入申请人', trigger: 'blur' }
                    ],
                    application_type: [
                        { required: true, message: '请选择License类型', trigger: 'change' }
                    ],
                    feature: [
                        { required: true, message: '请输入Feature', trigger: 'blur' }
                    ],
                    customer_name: [
                        { required: true, message: '请输入客户名称', trigger: 'blur' }
                    ],
                    mac_address: [
                        { required: true, message: '请输入MAC地址', trigger: 'blur' }
                    ],
                    serial_number: [
                        { 
                            validator: (rule, value, callback) => {
                                if (!value) {
                                    callback(new Error('请输入申请序列号'))
                                } else if (value.length < 3) {
                                    callback(new Error('序列号长度不能少于3个字符'))
                                } else {
                                    callback()
                                }
                            }, 
                            trigger: 'blur' 
                        }
                    ]
                },
                formInline:{
                    page: 1,
                    limit: 10,
                    applicant:'',
                    application_type:'',
                    customer_name:'',
                    serial_number:'',
                    product_name:'',  // 新增产品名称筛选
                    status:''
                },
                pageparm: {
                    page: 1,
                    limit: 10,
                    total: 0
                },
                tableData:[]
            }
        },
        created() {
            this.getData()
        },
        methods:{
            // 表格序列号
            getIndex($index) {
                return (this.pageparm.page-1)*this.pageparm.limit + $index +1
            },
            // 判断结束时间是否已过期
            isEndTimeExpired(endTime) {
                if (!endTime) {
                    return false // 如果没有结束时间，默认不过期
                }
                const now = new Date()
                const end = new Date(endTime)
                return end < now
            },
            // 检查是否有产品组（GloryEX组或GloryBolt组）
            hasProductGroup() {
                // 检查当前表格数据中是否有产品组
                for (let row of this.tableData) {
                    if (row.user_info_list && row.user_info_list.length > 0) {
                        return true
                    }
                }
                return false
            },
            // 检查是否可以制作License（开始时间和结束时间都必须存在）
            canGenerateLicense(row) {
                return row.start_time && row.end_time && !this.isEndTimeExpired(row.end_time)
            },
            
            // ========== 展开/收起相关方法 ==========
            
            // 切换展开/收起状态
            toggleExpand(type, rowId) {
                console.log('toggleExpand called:', type, rowId)
                if (type === 'feature') {
                    // Vue 3 不需要使用 $set，直接赋值即可
                    this.expandedFeatures[rowId] = !this.expandedFeatures[rowId]
                    console.log('expandedFeatures:', this.expandedFeatures)
                } else if (type === 'quantity') {
                    this.expandedQuantities[rowId] = !this.expandedQuantities[rowId]
                    console.log('expandedQuantities:', this.expandedQuantities)
                } else if (type === 'product_feature') {
                    // 产品组的 feature 展开
                    this.expandedFeatures[rowId] = !this.expandedFeatures[rowId]
                    console.log('expandedFeatures (product):', this.expandedFeatures)
                }
            },
            
            // 获取限制显示的Feature内容（默认显示3行）
            getLimitedFeatures(features, rowId) {
                if (!features || !Array.isArray(features)) return ''
                
                const isExpanded = this.expandedFeatures[rowId] || false
                console.log('getLimitedFeatures - rowId:', rowId, 'isExpanded:', isExpanded, 'features.length:', features.length)
                
                if (isExpanded) {
                    return features.join('\n')
                }
                
                // 默认只显示前3个
                const limited = features.slice(0, 3)
                return limited.join('\n')
            },
            
            // 【新增】判断产品是否有 features
            hasProductFeatures(productInfo, quantity) {
                if (!productInfo || !productInfo.product) return false
                
                const product = productInfo.product
                
                // ✅ 【关键修复】优先从 item.features 中获取，如果不存在则从 quantity 中获取
                let productFeatures = null
                if (productInfo.features && typeof productInfo.features === 'object') {
                    productFeatures = productInfo.features
                } else if (quantity && typeof quantity === 'object' && quantity[product]) {
                    productFeatures = quantity[product]
                }
                
                return productFeatures && typeof productFeatures === 'object' && Object.keys(productFeatures).length > 0
            },
            
            // 【新增】获取产品的 features 文本（用于显示）
            getProductFeaturesText(productInfo, quantity, rowId) {
                if (!productInfo || !productInfo.product) return ''
                
                const product = productInfo.product
                const uniqueKey = product + '_' + rowId
                const isExpanded = this.expandedFeatures[uniqueKey] || false
                
                // ✅ 【关键修复】优先从 item.features 中获取，如果不存在则从 quantity 中获取
                let productFeatures = null
                if (productInfo.features && typeof productInfo.features === 'object') {
                    productFeatures = productInfo.features
                } else if (quantity && typeof quantity === 'object' && quantity[product]) {
                    productFeatures = quantity[product]
                }
                
                if (!productFeatures || typeof productFeatures !== 'object') {
                    return ''
                }
                
                // 提取该产品的所有 features，格式化为 "feature: count"
                let featuresWithCount = []
                for (const [featName, count] of Object.entries(productFeatures)) {
                    featuresWithCount.push(`${featName}: ${count}`)
                }
                
                if (isExpanded) {
                    return featuresWithCount.join('\n')
                }
                
                // 默认只显示前3个
                const limited = featuresWithCount.slice(0, 3)
                return limited.join('\n')
            },
            
            // 【新增】直接从 quantity 中解析 features 和数量
            getQuantityFeaturesText(quantity, rowId) {
                if (!quantity || typeof quantity !== 'object') return JSON.stringify(quantity, null, 2)
                
                const isExpanded = this.expandedFeatures[rowId] || false
                
                // 展平所有 products 的 features
                const flattenedEntries = []
                for (const [product, features] of Object.entries(quantity)) {
                    if (typeof features === 'object' && features !== null) {
                        // 嵌套结构，将每个 feature 格式化为 "feature: count"
                        for (const [featureName, count] of Object.entries(features)) {
                            flattenedEntries.push(`${featureName}: ${count}`)
                        }
                    } else {
                        // 非嵌套结构，直接格式化
                        flattenedEntries.push(`${product}: ${features}`)
                    }
                }
                
                if (isExpanded) {
                    return flattenedEntries.join('\n')
                }
                
                // 默认只显示前3个
                const limited = flattenedEntries.slice(0, 3)
                const hasMore = flattenedEntries.length > 3
                
                let result = limited.join('\n')
                if (hasMore) {
                    result += `\n... 还有 ${flattenedEntries.length - 3} 个`
                }
                
                return result
            },
            
            // 【新增】判断非产品组的 quantity 是否需要展开按钮
            shouldShowExpandQuantityFeatures(quantity, rowId) {
                if (!quantity || typeof quantity !== 'object') return false
                
                // 统计所有 features 的总数
                let totalCount = 0
                for (const [product, features] of Object.entries(quantity)) {
                    if (typeof features === 'object' && features !== null) {
                        totalCount += Object.keys(features).length
                    } else {
                        totalCount++
                    }
                }
                
                return totalCount > 3
            },
            
            // 判断Feature是否需要显示展开按钮
            shouldShowExpand(features) {
                if (!features || !Array.isArray(features)) return false
                const shouldShow = features.length > 3
                console.log('shouldShowExpand - features.length:', features.length, 'shouldShow:', shouldShow)
                return shouldShow
            },
            
            // 【新增】判断产品的 features 是否需要显示展开按钮
            shouldShowExpandProductFeatures(productInfo, quantity, rowId) {
                if (!productInfo || !productInfo.product) return false
                
                const product = productInfo.product
                
                // ✅ 【关键修复】优先从 item.features 中获取，如果不存在则从 quantity 中获取
                let productFeatures = null
                if (productInfo.features && typeof productInfo.features === 'object') {
                    productFeatures = productInfo.features
                } else if (quantity && typeof quantity === 'object' && quantity[product]) {
                    productFeatures = quantity[product]
                }
                
                if (!productFeatures || typeof productFeatures !== 'object') {
                    return false
                }
                
                // 统计该产品的 features 数量
                const featureCount = Object.keys(productFeatures).length
                
                return featureCount > 3
            },
            
            // 判断Quantity是否需要显示展开按钮
            shouldShowExpandQuantity(quantity) {
                if (!quantity || typeof quantity !== 'object') return false
                
                // 统计所有feature的总数（包括嵌套结构）
                let totalFeatures = 0
                for (const [product, features] of Object.entries(quantity)) {
                    if (typeof features === 'object' && features !== null) {
                        // 嵌套结构，统计第二层的键数量
                        totalFeatures += Object.keys(features).length
                    } else {
                        // 非嵌套结构，直接计数
                        totalFeatures += 1
                    }
                }
                
                const shouldShow = totalFeatures > 3
                console.log('shouldShowExpandQuantity - totalFeatures:', totalFeatures, 'shouldShow:', shouldShow)
                return shouldShow
            },
            
            // 复制内容到剪贴板
            async copyContent(content, fieldName) {
                try {
                    // 将内容转换为字符串
                    let textToCopy
                    if (typeof content === 'object' && content !== null) {
                        textToCopy = JSON.stringify(content, null, 2)
                    } else {
                        textToCopy = String(content)
                    }
                    
                    // 使用 Clipboard API
                    if (navigator.clipboard && navigator.clipboard.writeText) {
                        await navigator.clipboard.writeText(textToCopy)
                        this.$message.success(`${fieldName}内容已复制到剪贴板`)
                    } else {
                        // 降级方案：使用 textarea
                        const textarea = document.createElement('textarea')
                        textarea.value = textToCopy
                        textarea.style.position = 'fixed'
                        textarea.style.opacity = '0'
                        document.body.appendChild(textarea)
                        textarea.select()
                        document.execCommand('copy')
                        document.body.removeChild(textarea)
                        this.$message.success(`${fieldName}内容已复制到剪贴板`)
                    }
                } catch (error) {
                    console.error('复制失败:', error)
                    this.$message.error('复制失败，请手动选择内容复制')
                }
            },
            
            setFull(){
                this.isFull=!this.isFull
                window.dispatchEvent(new Event('resize'))
            },
            // 对话框关闭时清除表单缓存
            handleDialogClose() {
                // 重置表单数据和验证状态
                this.form = {
                    id: '',
                    applicant: '',
                    applicant_id: '',
                    application_type: '',
                    feature: '',
                    keyword: '',
                    customer_name: '',
                    mac_address: '',
                    start_time: '',
                    end_time: '',
                    quantity: '',
                    status: 3,
                    max_retry_count: 3
                }
                // 清除表单验证
                this.$nextTick(() => {
                    if (this.$refs.formRef) {
                        this.$refs.formRef.resetFields()
                        this.$refs.formRef.clearValidate()
                    }
                })
            },
            // 禁用开始日期：不能选择结束日期之后的日期
            disabledStartDate(time) {
                if (this.form.end_time) {
                    const endDate = new Date(this.form.end_time)
                    // 结束日期的 00:00:00
                    endDate.setHours(0, 0, 0, 0)
                    return time.getTime() > endDate.getTime()
                }
                return false
            },
            // 禁用结束日期：不能选择开始日期之前的日期
            disabledEndDate(time) {
                if (this.form.start_time) {
                    const startDate = new Date(this.form.start_time)
                    // 开始日期的 00:00:00
                    startDate.setHours(0, 0, 0, 0)
                    return time.getTime() < startDate.getTime()
                }
                return false
            },
            handleGenerate(row) {
                let vm = this
                
                // 检查开始时间和结束时间是否存在
                if (!row.start_time || !row.end_time) {
                    vm.$message.warning('开始时间或结束时间未设置，无法制作License')
                    return
                }
                
                // 检查结束时间是否已过期
                if (this.isEndTimeExpired(row.end_time)) {
                    vm.$message.warning('结束时间已过期，无法制作License')
                    return
                }
                
                vm.$confirm('确认要制作该License吗？系统将读取JSON文件并生成License。', {
                    confirmButtonText: '确定',
                    cancelButtonText: '取消',
                    type: 'warning'
                }).then(() => {
                    vm.loadingPage = true
                    licenseApplicationGenerate(row.id).then(res => {
                        vm.loadingPage = false
                        if(res.code === 2000) {
                            vm.$message.success('License制作成功')
                            vm.getData()
                        } else {
                            vm.$message.error(res.msg || 'License制作失败')
                        }
                    }).catch(err => {
                        vm.loadingPage = false
                        vm.$message.error('License制作失败：' + (err.message || '未知错误'))
                    })
                }).catch(() => {
                    // 取消操作
                })
            },
            handleRetry(row) {
                let vm = this
                const remainingRetries = (row.max_retry_count || 3) - row.retry_count
                vm.$confirm(`确认要重试制作该License吗？\n当前重试次数：${row.retry_count}/${row.max_retry_count || 3}\n剩余重试次数：${remainingRetries}`, {
                    confirmButtonText: '确定',
                    cancelButtonText: '取消',
                    type: 'warning'
                }).then(() => {
                    vm.loadingPage = true
                    licenseApplicationRetry(row.id).then(res => {
                        vm.loadingPage = false
                        if(res.code === 2000) {
                            vm.$message.success('License制作成功')
                            vm.getData()
                        } else {
                            // 如果返回了can_retry字段，显示更详细的错误信息
                            if(res.data && res.data.can_retry !== undefined) {
                                const retryInfo = `重试次数：${res.data.retry_count}/${res.data.max_retry_count}`
                                vm.$message.error({
                                    message: `${res.msg || 'License制作失败'}\n${retryInfo}`,
                                    duration: 5000
                                })
                            } else {
                                vm.$message.error(res.msg || '重试失败')
                            }
                            vm.getData()
                        }
                    }).catch(err => {
                        vm.loadingPage = false
                        vm.$message.error('重试失败：' + (err.message || '未知错误'))
                    })
                }).catch(() => {
                    // 取消操作
                })
            },
            handleViewDetail(row) {
                this.currentRow = row
                this.detailDialogVisible = true
            },
            handleDelete(row) {
                let vm = this
                vm.$confirm('您确定要删除选中的数据吗？', {
                    closeOnClickModal:false
                }).then(() => {
                    licenseApplicationDelete({id: row.id}).then(res => {
                        if(res.code === 2000) {
                            vm.$message.success('删除成功')
                            vm.getData()
                        } else {
                            vm.$message.error(res.msg || '删除失败')
                        }
                    }).catch(err => {
                        vm.$message.error('删除失败：' + (err.message || '未知错误'))
                    })
                }).catch(() => {
                    // 取消操作
                })
            },
            handleEdit(row,flag) {
                if(flag=="reset"){
                    this.formInline = {
                        page:1,
                        limit: 10,
                        applicant:'',
                        application_type:'',
                        customer_name:'',
                        serial_number:'',
                        status:''
                    }
                    this.pageparm={
                        page: 1,
                        limit: 10,
                        total: 0
                    }
                    this.getData()
                } else if(flag === 'add') {
                    // 新增 - 先关闭对话框清除缓存
                    this.dialogVisible = false
                    // 重置表单数据
                    this.form = {
                        id: '',
                        applicant: '',
                        applicant_id: '',
                        application_type: '',
                        feature: '',
                        keyword: '',
                        customer_name: '',
                        mac_address: '',
                        start_time: '',
                        end_time: '',
                        quantity: '',
                        status: 3,
                        max_retry_count: 3
                    }
                    // 打开对话框
                    this.dialogType = 'add'
                    this.dialogVisible = true
                    // 清除表单验证和缓存
                    this.$nextTick(() => {
                        if (this.$refs.formRef) {
                            this.$refs.formRef.resetFields()
                            this.$refs.formRef.clearValidate()
                        }
                    })
                } else if(flag === 'edit') {
                    // 编辑
                    this.dialogType = 'edit'
                    // 将 quantity 对象转换为 JSON 字符串
                    let quantityValue = row.quantity
                    if (quantityValue && typeof quantityValue === 'object') {
                        quantityValue = JSON.stringify(quantityValue, null, 2)
                    }
                    // 将 feature 数组转换为逗号分隔的字符串
                    let featureValue = row.feature
                    if (featureValue && Array.isArray(featureValue)) {
                        featureValue = featureValue.join(', ')
                    }
                    
                    this.form = {
                        id: row.id,
                        applicant: row.applicant,
                        applicant_id: row.applicant_id || '',
                        application_type: row.application_type,
                        feature: featureValue,
                        keyword: row.keyword || '',
                        customer_name: row.customer_name,
                        mac_address: row.mac_address,
                        start_time: row.start_time || '',
                        end_time: row.end_time || '',
                        quantity: quantityValue,
                        status: row.status,
                        max_retry_count: row.max_retry_count || 3
                    }
                    this.dialogVisible = true
                    this.$nextTick(() => {
                        if (this.$refs.formRef) {
                            this.$refs.formRef.clearValidate()
                        }
                    })
                }
            },
            // 提交表单
            handleSubmit() {
                if (!this.$refs.formRef) return
                this.$refs.formRef.validate((valid) => {
                    if (valid) {
                        this.submitLoading = true
                        
                        // 准备提交的数据
                        const submitData = {...this.form}
                        
                        // 将 quantity 的 JSON 字符串转换为对象
                        if (submitData.quantity && typeof submitData.quantity === 'string') {
                            try {
                                submitData.quantity = JSON.parse(submitData.quantity)
                            } catch (e) {
                                this.submitLoading = false
                                this.$message.error('授权数量格式错误，请输入有效的 JSON 格式')
                                return
                            }
                        }
                        
                        // 将 feature 字符串转换为数组
                        if (submitData.feature && typeof submitData.feature === 'string') {
                            // 按逗号分隔，去除空白字符
                            submitData.feature = submitData.feature.split(',').map(f => f.trim()).filter(f => f)
                        }
                        
                        const api = this.dialogType === 'add' ? licenseApplicationAdd : licenseApplicationEdit
                        api(submitData).then(res => {
                            this.submitLoading = false
                            if(res.code === 2000) {
                                this.$message.success(this.dialogType === 'add' ? '新增成功' : '编辑成功')
                                this.dialogVisible = false
                                this.getData()
                            } else {
                                this.$message.error(res.msg || '操作失败')
                            }
                        }).catch(err => {
                            this.submitLoading = false
                            this.$message.error('操作失败：' + (err.message || '未知错误'))
                        })
                    }
                })
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
                    const params = {...this.formInline}
                    const res = await licenseApplication(params)
                    
                    this.loadingPage = false
                    if(res.code === 2000) {
                        this.tableData = res.data.data
                        this.pageparm.page = res.data.page;
                        this.pageparm.limit = res.data.limit;
                        this.pageparm.total = res.data.total;
                    }
                } catch (error) {
                    this.loadingPage = false
                    this.$message.error('获取数据失败')
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
        },
    }
</script>

<style lang="scss" scoped>
// 禁用的按钮样式
.disabled-btn {
    color: #c0c4cc !important;
    cursor: not-allowed !important;
    opacity: 0.6;
    
    &:hover {
        color: #c0c4cc !important;
    }
}

// 可展开内容的样式
.expandable-content {
    position: relative;
    
    pre {
        overflow: hidden;
        transition: max-height 0.3s ease;
        white-space: pre-wrap;  // 保留换行和空格，但允许自动换行
        word-break: break-all;  // 长单词或URL可以换行
        
        // 收起状态下的提示文字样式
        &.collapsed {
            ::v-deep .more-items-hint {
                color: #909399;  // 灰色，表示还有更多内容
                font-style: italic;
                font-weight: 500;
            }
        }
        
        &.expanded {
            max-height: 2000px;  // 展开后的高度，足够显示大量内容
            overflow-y: auto;  // 内容过多时显示滚动条
        }
    }
    
    .expand-btn-group {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-top: 4px;
    }
    
    .expand-btn,
    .copy-btn {
        display: flex;
        align-items: center;
        gap: 4px;
        color: #409eff;
        cursor: pointer;
        font-size: 12px;
        padding: 2px 6px;
        border-radius: 3px;
        transition: all 0.2s;
        
        &:hover {
            color: #66b1ff;
            background-color: #ecf5ff;
        }
        
        .el-icon {
            font-size: 14px;
        }
    }
    
    .copy-btn {
        color: #67c23a;
        
        &:hover {
            color: #85ce61;
            background-color: #f0f9eb;
        }
    }
}

// 产品单元格样式（用于多产品合并显示）
.product-cell-item {
    padding: 8px 0;
    border-bottom: 1px solid #eee;
    
    &:last-child {
        border-bottom: none;
    }
}

// 产品 feature 列表容器
.product-feature-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
}

// 产品 feature 行（每个产品一行）
.product-feature-row {
    display: flex;
    align-items: flex-start;
    padding: 6px 0;
    border-bottom: 1px solid #f0f0f0;
    
    &:last-child {
        border-bottom: none;
    }
    
    // Feature 内容列
    .feature-content {
        flex: 1;
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 8px;
        
        .feature-text {
            margin: 0;
            font-size: 12px;
            line-height: 1.8;  // 增加行高，更易读
            color: #606266;
            white-space: pre-wrap;
            word-break: break-all;
            flex: 1;
            font-family: 'Courier New', monospace;  // 使用等宽字体，对齐更美观
            background-color: #f9fafb;  // 添加浅色背景
            padding: 4px 8px;  // 添加内边距
            border-radius: 3px;  // 圆角
            min-width: 200px;  // ✅ 确保最小宽度，防止内容被压缩
            
            &.expanded {
                white-space: pre-wrap;
            }
        }
        
        .expand-btn-inline {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            color: #409eff;
            cursor: pointer;
            font-size: 12px;
            padding: 2px 6px;
            border-radius: 4px;
            transition: all 0.3s;
            flex-shrink: 0;
            
            &:hover {
                color: #66b1ff;
                background-color: #ecf5ff;
            }
            
            .el-icon {
                font-size: 14px;
            }
        }
    }
}

// 非产品组 feature 显示
.non-product-feature,
.array-feature {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 8px;
    
    .feature-text {
        margin: 0;
        font-size: 12px;
        line-height: 1.8;  // 增加行高，更易读
        color: #606266;
        white-space: pre-wrap;
        word-break: break-all;
        flex: 1;
        font-family: 'Courier New', monospace;  // 使用等宽字体，对齐更美观
        background-color: #f9fafb;  // 添加浅色背景
        padding: 4px 8px;  // 添加内边距
        border-radius: 3px;  // 圆角
        min-width: 200px;  // ✅ 确保最小宽度，防止内容被压缩
        
        &.expanded {
            white-space: pre-wrap;
        }
    }
    
    .expand-btn-inline {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        color: #409eff;
        cursor: pointer;
        font-size: 12px;
        padding: 2px 6px;
        border-radius: 4px;
        transition: all 0.3s;
        flex-shrink: 0;
        
        &:hover {
            color: #66b1ff;
            background-color: #ecf5ff;
        }
        
        .el-icon {
            font-size: 14px;
        }
    }
    
    .copy-btn-inline {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        color: #67c23a;
        cursor: pointer;
        font-size: 12px;
        padding: 2px 6px;
        border-radius: 4px;
        transition: all 0.3s;
        flex-shrink: 0;
        
        &:hover {
            color: #85ce61;
            background-color: #f0f9eb;
        }
        
        .el-icon {
            font-size: 14px;
        }
    }
}
</style>
