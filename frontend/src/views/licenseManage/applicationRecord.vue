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
                <el-table-column min-width="150" prop="feature" label="Feature" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="120" prop="customer_name" label="客户名称" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="150" prop="mac_address" label="MAC Address/HostID" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="100" prop="quantity" label="授权数量" align="center"></el-table-column>
                <el-table-column min-width="150" prop="start_time" label="开始时间"></el-table-column>
                <el-table-column min-width="150" prop="end_time" label="结束时间"></el-table-column>
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
                        <span class="table-operate-btn" @click="handleGenerate(scope.row)" v-show="hasPermission(this.$route.name,'Generate') && (scope.row.status==0 || scope.row.status==3)">制作License</span>
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
                <el-descriptions-item label="Feature" :span="2">{{ currentRow.feature }}</el-descriptions-item>
                <el-descriptions-item label="客户名称">{{ currentRow.customer_name }}</el-descriptions-item>
                <el-descriptions-item label="MAC Address">{{ currentRow.mac_address }}</el-descriptions-item>
                <el-descriptions-item label="授权数量">{{ currentRow.quantity }}</el-descriptions-item>
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
        <el-dialog v-model="dialogVisible" :title="dialogType === 'add' ? '新增申请' : '编辑申请'" width="700px">
            <el-form :model="form" :rules="rules" ref="formRef" label-width="120px">
                <el-row :gutter="20">
                    <el-col :span="12">
                        <el-form-item label="申请人" prop="applicant">
                            <el-input v-model="form.applicant" placeholder="请输入申请人" clearable></el-input>
                        </el-form-item>
                    </el-col>
                    <el-col :span="12">
                        <el-form-item label="License类型" prop="application_type">
                            <el-select v-model="form.application_type" placeholder="请选择" style="width: 100%">
                                <el-option label="FlexNet" value="flexnet"></el-option>
                                <el-option label="Bitanswer" value="bitanswer"></el-option>
                            </el-select>
                        </el-form-item>
                    </el-col>
                </el-row>
                <el-row :gutter="20">
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
                        <el-form-item label="开始时间" prop="start_time">
                            <el-date-picker v-model="form.start_time" type="datetime" placeholder="选择开始时间" style="width: 100%" value-format="YYYY-MM-DD HH:mm:ss"></el-date-picker>
                        </el-form-item>
                    </el-col>
                    <el-col :span="12">
                        <el-form-item label="结束时间" prop="end_time">
                            <el-date-picker v-model="form.end_time" type="datetime" placeholder="选择结束时间" style="width: 100%" value-format="YYYY-MM-DD HH:mm:ss"></el-date-picker>
                        </el-form-item>
                    </el-col>
                </el-row>
                <el-row :gutter="20">
                    <el-col :span="12">
                        <el-form-item label="授权数量" prop="quantity">
                            <el-input-number v-model="form.quantity" :min="1" :max="9999" style="width: 100%"></el-input-number>
                        </el-form-item>
                    </el-col>
                </el-row>
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
                    ]
                },
                formInline:{
                    page: 1,
                    limit: 10,
                    applicant:'',
                    application_type:'',
                    customer_name:'',
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
            setFull(){
                this.isFull=!this.isFull
                window.dispatchEvent(new Event('resize'))
            },
            handleGenerate(row) {
                let vm = this
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
                        status:''
                    }
                    this.pageparm={
                        page: 1,
                        limit: 10,
                        total: 0
                    }
                    this.getData()
                } else if(flag === 'add') {
                    // 新增
                    this.dialogType = 'add'
                    this.form = {
                        id: '',
                        applicant: '',
                        applicant_id: '',
                        application_type: '',
                        feature: '',
                        customer_name: '',
                        mac_address: '',
                        start_time: '',
                        end_time: '',
                        quantity: 1,
                        status: 3,
                        max_retry_count: 3
                    }
                    this.dialogVisible = true
                    this.$nextTick(() => {
                        if (this.$refs.formRef) {
                            this.$refs.formRef.clearValidate()
                        }
                    })
                } else if(flag === 'edit') {
                    // 编辑
                    this.dialogType = 'edit'
                    this.form = {
                        id: row.id,
                        applicant: row.applicant,
                        applicant_id: row.applicant_id || '',
                        application_type: row.application_type,
                        feature: row.feature,
                        customer_name: row.customer_name,
                        mac_address: row.mac_address,
                        start_time: row.start_time,
                        end_time: row.end_time,
                        quantity: row.quantity,
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
                        const api = this.dialogType === 'add' ? licenseApplicationAdd : licenseApplicationEdit
                        api(this.form).then(res => {
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
</style>
