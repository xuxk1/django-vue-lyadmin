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
                <el-form-item label="Vendor：">
                    <el-input size="default" v-model.trim="formInline.vendor" maxlength="60" clearable placeholder="Vendor" @change="search" style="width:150px"></el-input>
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
                <el-table-column min-width="150" prop="feature" label="Feature" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="100" prop="vendor" label="Vendor" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="80" prop="version" label="Version" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="150" prop="host_id" label="HostID" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="100" prop="quantity" label="授权数量" align="center"></el-table-column>
                <el-table-column min-width="150" prop="start_time" label="开始时间"></el-table-column>
                <el-table-column min-width="150" prop="end_time" label="过期时间"></el-table-column>
                <el-table-column min-width="100" prop="remaining_days" label="剩余天数" align="center">
                    <template #default="scope">
                        <el-tag v-if="scope.row.remaining_days > 30" type="success">{{ scope.row.remaining_days }}天</el-tag>
                        <el-tag v-else-if="scope.row.remaining_days > 0" type="warning">{{ scope.row.remaining_days }}天</el-tag>
                        <el-tag v-else type="danger">已过期</el-tag>
                    </template>
                </el-table-column>
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
                <el-descriptions-item label="Feature" :span="2">{{ currentRow.feature }}</el-descriptions-item>
                <el-descriptions-item label="Vendor">{{ currentRow.vendor }}</el-descriptions-item>
                <el-descriptions-item label="Version">{{ currentRow.version }}</el-descriptions-item>
                <el-descriptions-item label="HostID">{{ currentRow.host_id }}</el-descriptions-item>
                <el-descriptions-item label="授权数量">{{ currentRow.quantity }}</el-descriptions-item>
                <el-descriptions-item label="开始时间">{{ currentRow.start_time }}</el-descriptions-item>
                <el-descriptions-item label="过期时间">{{ currentRow.end_time }}</el-descriptions-item>
                <el-descriptions-item label="剩余天数">
                    <el-tag v-if="currentRow.remaining_days > 30" type="success">{{ currentRow.remaining_days }}天</el-tag>
                    <el-tag v-else-if="currentRow.remaining_days > 0" type="warning">{{ currentRow.remaining_days }}天</el-tag>
                    <el-tag v-else type="danger">已过期</el-tag>
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
                    vendor:'',
                    host_id:'',
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
            this.getStatistics()
        },
        methods:{
            // 表格序列号
            getIndex($index) {
                return (this.pageparm.page-1)*this.pageparm.limit + $index +1
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
                        vendor:'',
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
</style>
