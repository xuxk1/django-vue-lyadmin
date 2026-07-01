<template>
    <div :class="{'ly-is-full':isFull}">
        <!-- 统计卡片 -->
        <el-row :gutter="20" style="margin-bottom: 20px;">
            <el-col :span="6">
                <el-card shadow="hover">
                    <div class="stat-card">
                        <div class="stat-icon" style="background-color: #409EFF;">
                            <el-icon size="30"><document /></el-icon>
                        </div>
                        <div class="stat-info">
                            <div class="stat-value">{{ statistics.total || 0 }}</div>
                            <div class="stat-label">总数</div>
                        </div>
                    </div>
                </el-card>
            </el-col>
            <el-col :span="6">
                <el-card shadow="hover">
                    <div class="stat-card">
                        <div class="stat-icon" style="background-color: #67C23A;">
                            <el-icon size="30"><circle-check /></el-icon>
                        </div>
                        <div class="stat-info">
                            <div class="stat-value">{{ statistics.activeCount || 0 }}</div>
                            <div class="stat-label">有效</div>
                        </div>
                    </div>
                </el-card>
            </el-col>
            <el-col :span="6">
                <el-card shadow="hover">
                    <div class="stat-card">
                        <div class="stat-icon" style="background-color: #E6A23C;">
                            <el-icon size="30"><warning /></el-icon>
                        </div>
                        <div class="stat-info">
                            <div class="stat-value">{{ statistics.expiring_soon || 0 }}</div>
                            <div class="stat-label">即将过期</div>
                        </div>
                    </div>
                </el-card>
            </el-col>
            <el-col :span="6">
                <el-card shadow="hover">
                    <div class="stat-card">
                        <div class="stat-icon" style="background-color: #F56C6C;">
                            <el-icon size="30"><circle-close /></el-icon>
                        </div>
                        <div class="stat-info">
                            <div class="stat-value">{{ statistics.expired || 0 }}</div>
                            <div class="stat-label">已过期</div>
                        </div>
                    </div>
                </el-card>
            </el-col>
        </el-row>

        <!-- 搜索区域 -->
        <div class="tableSelect" ref="tableSelect">
            <el-form :inline="true" :model="formInline" label-position="left">
                <el-form-item label="License ID：">
                    <el-input size="default" v-model.trim="formInline.license_id" maxlength="100" clearable placeholder="License ID" @change="search" style="width:180px"></el-input>
                </el-form-item>
                <el-form-item label="类型：">
                    <el-select v-model="formInline.license_type" placeholder="请选择" clearable @change="search" size="default" style="width:120px">
                        <el-option label="FlexNet" value="flexnet"></el-option>
                        <el-option label="Bitanswer" value="bitanswer"></el-option>
                    </el-select>
                </el-form-item>
                <el-form-item label="客户名称：">
                    <el-input size="default" v-model.trim="formInline.customer_name" maxlength="60" clearable placeholder="客户名称" @change="search" style="width:150px"></el-input>
                </el-form-item>
                <el-form-item label="HostID：">
                    <el-input size="default" v-model.trim="formInline.host_id" maxlength="100" clearable placeholder="HostID" @change="search" style="width:180px"></el-input>
                </el-form-item>
                <el-form-item label="状态：">
                    <el-select v-model="formInline.status" placeholder="请选择" clearable @change="search" size="default" style="width:120px">
                        <el-option label="有效" :value="1"></el-option>
                        <el-option label="已过期" :value="2"></el-option>
                        <el-option label="已撤销" :value="0"></el-option>
                    </el-select>
                </el-form-item>
                <el-form-item label="">
                    <el-button @click="search" type="primary" icon="Search" v-show="hasPermission(this.$route.name,'Search')">查询</el-button>
                </el-form-item>
                <el-form-item label="">
                    <el-button @click="handleEdit('','reset')" icon="Refresh">重置</el-button>
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
                <el-table-column min-width="150" prop="license_id" label="License ID" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="100" prop="license_type_display" label="类型" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="120" prop="file_name" label="文件名称" show-overflow-tooltip></el-table-column>
                <!-- ✅ HostID 放在文件名称后面 -->
                <el-table-column min-width="150" prop="host_id" label="HostID" show-overflow-tooltip></el-table-column>
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
                <el-table-column min-width="350" prop="feature" label="Feature">
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
                        <span v-else>{{ scope.row.start_date_str }}</span>
                    </template>
                </el-table-column>
                <el-table-column v-if="hasProductGroup()" min-width="150" label="过期时间">
                    <template #default="scope">
                        <div v-if="scope.row.user_info_list && scope.row.user_info_list.length > 0">
                            <div v-for="(item, index) in scope.row.user_info_list" :key="index" 
                                 class="product-cell-item">
                                {{ item.end_date || '--' }}
                            </div>
                        </div>
                        <span v-else>{{ scope.row.end_date_str }}</span>
                    </template>
                </el-table-column>
                
                <!-- ✅ 剩余天数列：放在过期时间后面 -->
                <el-table-column min-width="120" label="剩余天数" align="center">
                    <template #default="scope">
                        <!-- 产品组：每个产品显示自己的剩余天数 -->
                        <div v-if="scope.row.user_info_list && scope.row.user_info_list.length > 0">
                            <div v-for="(item, index) in scope.row.user_info_list" :key="index" 
                                 class="product-cell-item">
                                <!-- 已过期显示0天，其他情况用不同颜色区分 -->
                                <el-tag v-if="scope.row.status === 2" type="danger">0天</el-tag>
                                <el-tag v-else-if="item.remaining_days > 30" type="success">{{ item.remaining_days }}天</el-tag>
                                <el-tag v-else-if="item.remaining_days == 30" type="warning" effect="dark">{{ item.remaining_days }}天 ⚠️</el-tag>
                                <el-tag v-else-if="item.remaining_days == 15" type="warning" effect="dark">{{ item.remaining_days }}天 ️⚠️</el-tag>
                                <el-tag v-else-if="item.remaining_days == 7" type="danger" effect="dark">{{ item.remaining_days }}天 ⚠️⚠️⚠️</el-tag>
                                <el-tag v-else-if="item.remaining_days > 0" type="warning">{{ item.remaining_days }}天</el-tag>
                                <el-tag v-else type="info">0天</el-tag>
                            </div>
                        </div>
                        <!-- 非产品组：使用原有的 remaining_days -->
                        <span v-else>
                            <el-tag v-if="scope.row.status === 2" type="danger">0天</el-tag>
                            <el-tag v-else-if="scope.row.remaining_days > 30" type="success">{{ scope.row.remaining_days }}天</el-tag>
                            <el-tag v-else-if="scope.row.remaining_days == 30" type="warning" effect="dark">{{ scope.row.remaining_days }}天 ⚠️</el-tag>
                            <el-tag v-else-if="scope.row.remaining_days == 15" type="warning" effect="dark">{{ scope.row.remaining_days }}天 ⚠️⚠️</el-tag>
                            <el-tag v-else-if="scope.row.remaining_days == 7" type="danger" effect="dark">{{ scope.row.remaining_days }}天 ️⚠️⚠️</el-tag>
                            <el-tag v-else-if="scope.row.remaining_days > 0" type="warning">{{ scope.row.remaining_days }}天</el-tag>
                            <el-tag v-else type="info">0天</el-tag>
                        </span>
                    </template>
                </el-table-column>
                <!-- 非产品组：不显示单独的授权数量列，已合并到 Feature 列 -->
                <el-table-column v-if="!hasProductGroup()" min-width="150" prop="start_date_str" label="开始时间"></el-table-column>
                <el-table-column v-if="!hasProductGroup()" min-width="150" prop="end_date_str" label="过期时间"></el-table-column>
                <el-table-column min-width="100" label="状态">
                    <template #default="scope">
                        <el-tag v-if="scope.row.status==1" type="success">有效</el-tag>
                        <el-tag v-else-if="scope.row.status==2" type="danger">已过期</el-tag>
                        <el-tag v-else-if="scope.row.status==0" type="info">已撤销</el-tag>
                    </template>
                </el-table-column>
                <el-table-column min-width="100" prop="applicant" label="申请人" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="120" prop="customer_name" label="客户名称" show-overflow-tooltip></el-table-column>
                <el-table-column label="操作" fixed="right" width="150">
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
                        <span class="table-operate-btn" @click="handleViewDetail(scope.row)" v-show="hasPermission(this.$route.name,'Retrieve')">详情</span>
                        <span class="table-operate-btn" @click="handleDownload(scope.row)" v-show="hasPermission(this.$route.name,'Download')">下载</span>
                    </template>
                </el-table-column>
            </el-table>
        </div>
        
        <!-- 分页 -->
        <Pagination v-bind:child-msg="pageparm" @callFather="callFather"></Pagination>

        <!-- 详情对话框 -->
        <el-dialog v-model="detailDialogVisible" title="License详情" width="900px">
            <el-descriptions :column="2" border v-if="currentRow">
                <el-descriptions-item label="License ID">{{ currentRow.license_id }}</el-descriptions-item>
                <el-descriptions-item label="类型">{{ currentRow.license_type_display }}</el-descriptions-item>
                <el-descriptions-item label="文件名称" :span="2">{{ currentRow.file_name }}</el-descriptions-item>
                <el-descriptions-item label="完整路径" :span="2">{{ currentRow.full_path }}</el-descriptions-item>
                <el-descriptions-item label="Vendor">{{ currentRow.vendor }}</el-descriptions-item>
                <el-descriptions-item label="Version">{{ currentRow.version }}</el-descriptions-item>
                <el-descriptions-item label="HostID">{{ currentRow.host_id }}</el-descriptions-item>
                <el-descriptions-item label="授权数量">{{ currentRow.quantity }}</el-descriptions-item>
                <el-descriptions-item label="开始时间">{{ currentRow.start_date_str }}</el-descriptions-item>
                <el-descriptions-item label="过期时间">{{ currentRow.end_date_str }}</el-descriptions-item>
                <el-descriptions-item label="剩余天数">
                    <!-- 已过期显示0天，其他情况用不同颜色区分 -->
                    <el-tag v-if="currentRow.status === 2" type="danger">0天</el-tag>
                    <el-tag v-else-if="currentRow.remaining_days > 30" type="success">{{ currentRow.remaining_days }}天</el-tag>
                    <el-tag v-else-if="currentRow.remaining_days == 30" type="warning" effect="dark">{{ currentRow.remaining_days }}天 ️</el-tag>
                    <el-tag v-else-if="currentRow.remaining_days == 15" type="warning" effect="dark">{{ currentRow.remaining_days }}天 ⚠️️</el-tag>
                    <el-tag v-else-if="currentRow.remaining_days == 7" type="danger" effect="dark">{{ currentRow.remaining_days }}天 ⚠️️⚠️</el-tag>
                    <el-tag v-else-if="currentRow.remaining_days > 0" type="warning">{{ currentRow.remaining_days }}天</el-tag>
                    <el-tag v-else type="info">0天</el-tag>
                </el-descriptions-item>
                <el-descriptions-item label="状态">{{ currentRow.status_display }}</el-descriptions-item>
                <el-descriptions-item label="申请人">{{ currentRow.applicant }}</el-descriptions-item>
                <el-descriptions-item label="客户名称">{{ currentRow.customer_name }}</el-descriptions-item>
                <el-descriptions-item label="创建时间" :span="2">{{ currentRow.create_datetime }}</el-descriptions-item>
            </el-descriptions>
            <template #footer>
                <el-button @click="detailDialogVisible = false">关闭</el-button>
            </template>
        </el-dialog>
    </div>
</template>

<script>
    import Pagination from "@/components/Pagination";
    import {getTableHeight} from "@/utils/util";
    import {licenseRecord, licenseRecordStatistics} from '@/api/api';
    
    export default {
        name: "licenseRecord",
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
                expandedFeatures: {},  // 记录每个行的Feature是否展开 {id: true/false}
                expandedQuantities: {},  // 记录每个行的Quantity是否展开 {id: true/false}
                statistics: {
                    total: 0,
                    activeCount: 0,
                    expiring_soon: 0,
                    expired: 0
                },
                formInline:{
                    page: 1,
                    limit: 10,
                    license_id:'',
                    license_type:'',
                    customer_name:'',
                    host_id:'',
                    status:''
                },
                pageparm: {
                    page: 1,
                    limit: 10,
                    total: 0
                },
                tableData:[],
                remainingDaysTimer: null  // 剩余天数更新定时器
            }
        },
        created() {
            this.getData()
            this.getStatistics()
            // 启动定时器，每分钟更新一次剩余天数
            this.startRemainingDaysTimer()
        },
        methods:{
            // 表格序列号
            getIndex($index) {
                return (this.pageparm.page-1)*this.pageparm.limit + $index +1
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
            setFull(){
                this.isFull=!this.isFull
                window.dispatchEvent(new Event('resize'))
            },
            handleViewDetail(row) {
                this.currentRow = row
                this.detailDialogVisible = true
            },
            handleDownload(row) {
                // TODO: 实现下载功能
                this.$message.info('下载功能待实现')
            },
            handleEdit(row,flag) {
                if(flag=="reset"){
                    this.formInline = {
                        page:1,
                        limit: 10,
                        license_id:'',
                        license_type:'',
                        customer_name:'',
                        host_id:'',
                        status:''
                    }
                    this.pageparm={
                        page: 1,
                        limit: 10,
                        total: 0
                    }
                    this.getData()
                }
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
            // 获取统计数据
            async getStatistics() {
                try {
                    const res = await licenseRecordStatistics({})
                    
                    if(res.code === 2000) {
                        this.statistics = res.data.data
                        // 计算有效数量
                        // const activeStats = this.statistics.status_stats?.find(s => s.status === 0)
                        this.statistics.activeCount = this.statistics.efficient
                    }
                } catch (error) {
                    console.error('获取统计数据失败', error)
                }
            },
            //获取列表
            async getData() {
                this.loadingPage = true
                try {
                    const params = {...this.formInline}
                    const res = await licenseRecord(params)
                    
                    this.loadingPage = false
                    console.log('License Record API Response:', res) // 调试日志
                    if(res.code === 2000) {
                        this.tableData = res.data.data
                        // 动态计算剩余天数
                        this.updateRemainingDays()
                        this.pageparm.page = res.data.page;
                        this.pageparm.limit = res.data.limit;
                        this.pageparm.total = res.data.total;
                        console.log('pageparm after update:', this.pageparm) // 调试日志
                    }
                } catch (error) {
                    this.loadingPage = false
                    this.$message.error('获取数据失败')
                    console.error('Error:', error)
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
                // 加上统计卡片的高度（约100px + margin-bottom 20px）
                tabSelectHeight += 120
                tabSelectHeight = this.isFull?tabSelectHeight - 110:tabSelectHeight
                this.tableHeight = getTableHeight(tabSelectHeight)
            },
            // ========== 展开/收起相关方法 ==========
            
            // 切换展开/收起状态
            toggleExpand(type, rowId) {
                if (type === 'feature') {
                    this.expandedFeatures[rowId] = !this.expandedFeatures[rowId]
                } else if (type === 'quantity') {
                    this.expandedQuantities[rowId] = !this.expandedQuantities[rowId]
                } else if (type === 'product_feature') {
                    // 产品组的 feature 展开
                    this.expandedFeatures[rowId] = !this.expandedFeatures[rowId]
                }
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
            
            // 获取限制显示的Feature内容（默认显示3行）
            getLimitedFeatures(features, rowId) {
                if (!features || !Array.isArray(features)) return ''
                
                const isExpanded = this.expandedFeatures[rowId] || false
                
                if (isExpanded) {
                    return features.join('\n')
                }
                
                // 默认只显示前3个
                const limited = features.slice(0, 3)
                return limited.join('\n')
            },
            
            // 判断是否需要显示展开按钮
            shouldShowExpand(features) {
                if (!features || !Array.isArray(features)) return false
                return features.length > 3
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
            
            // 获取限制显示的Quantity内容（默认显示3个）
            getLimitedQuantity(quantity, rowId) {
                if (!quantity || typeof quantity !== 'object') return JSON.stringify(quantity, null, 2)
                
                const isExpanded = this.expandedQuantities[rowId] || false
                
                if (isExpanded) {
                    // 展开状态，显示完整结构
                    return JSON.stringify(quantity, null, 2)
                }
                
                // 收起状态，展平显示前3个feature
                const flattenedEntries = []
                for (const [product, features] of Object.entries(quantity)) {
                    if (typeof features === 'object' && features !== null) {
                        // 将每个产品的features展平
                        for (const [featureName, count] of Object.entries(features)) {
                            flattenedEntries.push([`${product}/${featureName}`, count])
                        }
                    } else {
                        // 如果不是嵌套对象，直接添加
                        flattenedEntries.push([product, features])
                    }
                }
                
                // 只显示前3个，用简洁的文本格式
                const limited = flattenedEntries.slice(0, 3)
                const hasMore = flattenedEntries.length > 3
                
                // 格式化为易读的文本：每行一个 feature: count
                const lines = limited.map(([key, value]) => `  "${key}": ${value}`)
                let result = '{\n' + lines.join(',\n')
                
                if (hasMore) {
                    // 使用特殊标记，前端会用颜色区分显示
                    result += `,\n  <span class="more-items-hint">... 还有 ${flattenedEntries.length - 3} 个</span>`
                }
                
                result += '\n}'
                return result
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
                
                return totalFeatures > 3
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
            // 动态计算剩余天数（基于当前日期）
            updateRemainingDays() {
                const now = new Date()
                now.setHours(0, 0, 0, 0) // 设置为当天零点
                
                this.tableData.forEach(row => {
                    if (row.end_time) {
                        const endDate = new Date(row.end_time)
                        endDate.setHours(0, 0, 0, 0) // 设置为过期日零点
                        
                        const diffTime = endDate - now
                        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24))
                        
                        // 更新行的 remaining_days 字段
                        row.remaining_days = Math.max(0, diffDays)
                    }
                })
            },
            // 启动剩余天数更新定时器
            startRemainingDaysTimer() {
                // 清除旧的定时器
                if (this.remainingDaysTimer) {
                    clearInterval(this.remainingDaysTimer)
                }
                
                // 每分钟更新一次剩余天数
                this.remainingDaysTimer = setInterval(() => {
                    this.updateRemainingDays()
                }, 60000) // 60秒
            },
        },
        mounted() {
            window.addEventListener('resize', this.listenResize);
            this.$nextTick(() => {
                this.getTheTableHeight()
            })
        },
        unmounted() {
            window.removeEventListener("resize", this.listenResize);
            // 清除定时器
            if (this.remainingDaysTimer) {
                clearInterval(this.remainingDaysTimer)
                this.remainingDaysTimer = null
            }
        },
    }
</script>

<style lang="scss" scoped>
.stat-card {
    display: flex;
    align-items: center;
    
    .stat-icon {
        width: 60px;
        height: 60px;
        border-radius: 8px;
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        margin-right: 15px;
    }
    
    .stat-info {
        flex: 1;
        
        .stat-value {
            font-size: 28px;
            font-weight: bold;
            color: #303133;
            line-height: 1;
            margin-bottom: 5px;
        }
        
        .stat-label {
            font-size: 14px;
            color: #909399;
        }
    }
}

// 展开/收起样式
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
}
</style>
