<template>
    <div :class="{'ly-is-full':isFull}">
        <!-- 搜索区域 -->
        <div class="tableSelect" ref="tableSelect">
            <el-form :inline="true" :model="formInline" label-position="left">
                <el-form-item label="License类型：">
                    <el-select v-model="formInline.license_type" placeholder="请选择" clearable @change="search" size="default" style="width:150px">
                        <el-option label="Bitanswer" value="bitanswer"></el-option>
                        <el-option label="FlexNet" value="flexnet"></el-option>
                    </el-select>
                </el-form-item>
                <el-form-item label="用户类型：">
                    <el-select v-model="formInline.user_type" placeholder="请选择" clearable @change="search" size="default" style="width:120px">
                        <el-option label="内部" value="internal"></el-option>
                        <el-option label="外部" value="external"></el-option>
                    </el-select>
                </el-form-item>
                <el-form-item label="字段名：">
                    <el-input size="default" v-model.trim="formInline.field" maxlength="60" clearable placeholder="原始字段名" @change="search" style="width:150px"></el-input>
                </el-form-item>
                <el-form-item label="字段含义：">
                    <el-input size="default" v-model.trim="formInline.name" maxlength="60" clearable placeholder="字段含义" @change="search" style="width:150px"></el-input>
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
                <el-table-column min-width="120" prop="license_type_name" label="License类型" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="100" prop="user_type_name" label="用户类型" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="120" prop="product" label="产品名称" show-overflow-tooltip>
                    <template #default="scope">
                        <el-tag v-if="scope.row.product" type="primary" size="small">{{ scope.row.product }}</el-tag>
                        <span v-else style="color: #909399;">-</span>
                    </template>
                </el-table-column>
                <el-table-column min-width="120" prop="field_type_name" label="字段类型" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="150" prop="field" label="原始字段名" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="200" prop="name" label="字段含义" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="150" prop="real_key" label="映射后的真实key" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="150" prop="remark" label="备注" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="100" prop="creator_name" label="创建人" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="100" label="状态" align="center">
                    <template #default="scope">
                        <el-tag v-if="!scope.row.is_deleted" type="success">正常</el-tag>
                        <el-tag v-else type="danger">已废弃</el-tag>
                    </template>
                </el-table-column>
                <el-table-column min-width="150" prop="create_datetime" label="创建时间"></el-table-column>
                <el-table-column label="操作" fixed="right" width="200">
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
                        <span class="table-operate-btn" @click="handleEdit(scope.row,'edit')" v-show="hasPermission(this.$route.name,'Update')">编辑</span>
                        <span class="table-operate-btn" @click="handleDelete(scope.row)" v-show="hasPermission(this.$route.name,'Delete')">删除</span>
                    </template>
                </el-table-column>
            </el-table>
        </div>
        
        <!-- 分页 -->
        <Pagination v-bind:child-msg="pageparm" @callFather="callFather"></Pagination>

        <!-- 新增/编辑对话框 -->
        <el-dialog 
            v-model="dialogVisible" 
            :title="dialogType === 'add' ? '新增字段映射' : '编辑字段映射'" 
            width="600px"
            :close-on-click-modal="false"
        >
            <el-form :model="form" :rules="rules" ref="formRef" label-width="120px">
                <el-form-item label="License类型" prop="license_type">
                    <el-select v-model="form.license_type" placeholder="请选择License类型" style="width: 100%">
                        <el-option label="Bitanswer" value="bitanswer"></el-option>
                        <el-option label="FlexNet" value="flexnet"></el-option>
                    </el-select>
                </el-form-item>
                <el-form-item label="用户类型" prop="user_type">
                    <el-select v-model="form.user_type" placeholder="请选择用户类型" style="width: 100%">
                        <el-option label="内部" value="internal"></el-option>
                        <el-option label="外部" value="external"></el-option>
                    </el-select>
                </el-form-item>
                <el-form-item label="产品名称" prop="product">
                    <el-select v-model="form.product" placeholder="请选择产品" style="width: 100%" clearable>
                        <el-option label="GloryBolt" value="GloryBolt"></el-option>
                        <el-option label="GloryEX" value="GloryEX"></el-option>
                        <el-option label="GloryEX3D" value="GloryEX3D"></el-option>
                        <el-option label="GloryGrid" value="GloryGrid"></el-option>
                        <el-option label="GloryEye" value="GloryEye"></el-option>
                        <el-option label="GloryWatt" value="GloryWatt"></el-option>
                        <el-option label="GloryPolaris" value="GloryPolaris"></el-option>
                        <el-option label="PhyBolt" value="PhyBolt"></el-option>
                        <el-option label="GloryLink" value="GloryLink"></el-option>
                        <el-option label="verilog2def" value="verilog2def"></el-option>
                        <el-option label="verilog2spef" value="verilog2spef"></el-option>
                    </el-select>
                    <div style="font-size: 12px; color: #909399; margin-top: 4px;">
                        提示：选择产品后，该字段的feature将被归类到该产品下
                    </div>
                </el-form-item>
                <el-form-item label="字段类型" prop="field_type">
                    <el-select v-model="form.field_type" placeholder="请选择字段类型" style="width: 100%">
                        <el-option label="Feature" value="feature"></el-option>
                        <el-option label="CustomerInfo" value="customer_info"></el-option>
                        <el-option label="ApplicantInfo" value="applicant_info"></el-option>
                        <el-option label="Common" value="common"></el-option>
                    </el-select>
                </el-form-item>
                <el-form-item label="原始字段名" prop="field">
                    <el-input v-model="form.field" placeholder="请输入原始字段名" maxlength="100"></el-input>
                </el-form-item>
                <el-form-item label="字段含义" prop="name">
                    <el-input v-model="form.name" placeholder="请输入字段含义" maxlength="200"></el-input>
                </el-form-item>
                <el-form-item label="映射后的key" prop="real_key">
                    <el-input v-model="form.real_key" placeholder="请输入映射后的真实key" maxlength="100"></el-input>
                </el-form-item>
                <el-form-item label="备注" prop="remark">
                    <el-input v-model="form.remark" type="textarea" :rows="3" placeholder="请输入备注信息" maxlength="500"></el-input>
                </el-form-item>
                <el-form-item label="是否废弃" prop="is_deleted">
                    <el-switch v-model="form.is_deleted" :active-value="true" :inactive-value="false"></el-switch>
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
    import {licenseFieldMapping, licenseFieldMappingAdd, licenseFieldMappingEdit, licenseFieldMappingDelete} from '@/api/api';
    
    export default {
        name: "fieldMapping",
        components:{
            Pagination,
        },
        data() {
            return {
                isFull:false,
                tableHeight:500,
                loadingPage:false,
                dialogVisible: false,
                dialogType: 'add',
                submitLoading: false,
                formInline:{
                    page: 1,
                    limit: 10,
                    license_type:'',
                    user_type:'',
                    field:'',
                    name:''
                },
                pageparm: {
                    page: 1,
                    limit: 10,
                    total: 0
                },
                tableData:[],
                form: {
                    id: '',
                    license_type: '',
                    user_type: '',
                    product: '',  // 新增：产品名称
                    field_type: 'common',
                    field: '',
                    name: '',
                    real_key: '',
                    remark: '',  // 新增：备注
                    is_deleted: false
                },
                rules: {
                    license_type: [
                        { required: true, message: '请选择License类型', trigger: 'change' }
                    ],
                    user_type: [
                        { required: true, message: '请选择用户类型', trigger: 'change' }
                    ],
                    field_type: [
                        { required: true, message: '请选择字段类型', trigger: 'change' }
                    ],
                    field: [
                        { required: true, message: '请输入原始字段名', trigger: 'blur' }
                    ],
                    name: [
                        { required: true, message: '请输入字段含义', trigger: 'blur' }
                    ],
                    real_key: [
                        { required: true, message: '请输入映射后的真实key', trigger: 'blur' }
                    ]
                }
            }
        },
        created() {
            this.getData()
        },
        methods:{
            // 表格序列号
            getIndex($index) {
                return (this.formInline.page - 1) * this.formInline.limit + $index + 1
            },
            // 获取数据
            async getData(){
                this.loadingPage = true
                try {
                    const params = {...this.formInline}
                    const res = await licenseFieldMapping(params)
                    
                    this.loadingPage = false
                    if(res.code === 2000) {
                        this.tableData = res.data.data
                        this.pageparm.page = res.data.page
                        this.pageparm.limit = res.data.limit
                        this.pageparm.total = res.data.total
                    }
                } catch (error) {
                    this.loadingPage = false
                    this.$message.error('获取数据失败')
                }
            },
            // 搜索
            search(){
                this.formInline.page = 1
                this.getData()
            },
            // 重置
            handleEdit(row, type){
                if(type === 'reset'){
                    this.formInline = {
                        page: 1,
                        limit: 10,
                        license_type:'',
                        user_type:'',
                        field:'',
                        name:''
                    }
                    this.getData()
                } else if(type === 'add'){
                    this.dialogType = 'add'
                    this.form = {
                        id: '',
                        license_type: '',
                        user_type: '',
                        product: '',  // 新增：产品名称
                        field_type: 'common',
                        field: '',
                        name: '',
                        real_key: '',
                        remark: '',
                        is_deleted: false
                    }
                    this.dialogVisible = true
                    this.$nextTick(() => {
                        if (this.$refs.formRef) {
                            this.$refs.formRef.clearValidate()
                        }
                    })
                } else if(type === 'edit'){
                    this.dialogType = 'edit'
                    this.form = {
                        id: row.id,
                        license_type: row.license_type,
                        user_type: row.user_type,
                        product: row.product || '',  // 新增：产品名称
                        field_type: row.field_type,
                        field: row.field,
                        name: row.name,
                        real_key: row.real_key,
                        remark: row.remark || '',
                        is_deleted: row.is_deleted
                    }
                    this.dialogVisible = true
                    this.$nextTick(() => {
                        if (this.$refs.formRef) {
                            this.$refs.formRef.clearValidate()
                        }
                    })
                }
            },
            // 提交
            handleSubmit(){
                if (!this.$refs.formRef) return
                this.$refs.formRef.validate((valid) => {
                    if (valid) {
                        this.submitLoading = true
                        const api = this.dialogType === 'add' ? licenseFieldMappingAdd : licenseFieldMappingEdit
                        api(this.form).then(res => {
                            this.$message.success(this.dialogType === 'add' ? '新增成功' : '编辑成功')
                            this.dialogVisible = false
                            this.getData()
                            this.submitLoading = false
                        }).catch(() => {
                            this.submitLoading = false
                        })
                    }
                })
            },
            // 删除
            handleDelete(row){
                this.$confirm('确认删除该字段映射吗？', '提示', {
                    confirmButtonText: '确定',
                    cancelButtonText: '取消',
                    type: 'warning'
                }).then(() => {
                    licenseFieldMappingDelete({id: row.id}).then(res => {
                        this.$message.success('删除成功')
                        this.getData()
                    })
                }).catch(() => {})
            },
            // 全屏切换
            setFull(){
                this.isFull = !this.isFull
                this.$nextTick(() => {
                    this.tableHeight = getTableHeight(this.$refs.tableSelect, 60)
                })
            },
            // 分页回调
            callFather(parm){
                this.formInline.page = parm.page
                this.formInline.limit = parm.limit
                this.getData()
            }
        },
        mounted() {
            this.tableHeight = getTableHeight(this.$refs.tableSelect, 60)
            window.addEventListener('resize', () => {
                this.tableHeight = getTableHeight(this.$refs.tableSelect, 60)
            })
        },
        beforeUnmount() {
            window.removeEventListener('resize', () => {
                this.tableHeight = getTableHeight(this.$refs.tableSelect, 60)
            })
        }
    }
</script>

<style scoped>
</style>
