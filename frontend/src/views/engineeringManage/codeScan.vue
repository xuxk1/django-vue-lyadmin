<template>
    <div :class="{'ly-is-full':isFull}">
        <div class="tableSelect" ref="tableSelect">
            <el-form :inline="true" :model="formInline" label-position="left">
                <el-form-item label="项目名称：">
                    <el-input size="default" v-model.trim="formInline.project_name" maxlength="60" clearable placeholder="项目名称" @change="search" style="width:200px"></el-input>
                </el-form-item>
                <el-form-item label="扫描状态：">
                    <el-select v-model="formInline.scan_status" placeholder="请选择" clearable @change="search" size="default" style="width:120px">
                        <el-option
                            v-for="item in statusList"
                            :key="item.id"
                            :label="item.name"
                            :value="item.id">
                        </el-option>
                    </el-select>
                </el-form-item>
                <el-form-item label="严重级别：">
                    <el-select v-model="formInline.severity" placeholder="请选择" clearable @change="search" size="default" style="width:120px">
                        <el-option
                            v-for="item in severityList"
                            :key="item.id"
                            :label="item.name"
                            :value="item.id">
                        </el-option>
                    </el-select>
                </el-form-item>
                <el-form-item label=""><el-button @click="search" type="primary" icon="Search" v-show="hasPermission(this.$route.name,'Search')">查询</el-button></el-form-item>
                <el-form-item label=""><el-button @click="handleEdit('','reset')" icon="Refresh">重置</el-button></el-form-item>
                <el-form-item label="" v-show="hasPermission(this.$route.name,'Create')">
                    <el-button icon="Plus" type="primary" @click="addScan">新增扫描</el-button>
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
                <el-table-column min-width="120" prop="scan_type" label="扫描类型" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="100" label="扫描状态">
                    <template #default="scope">
                        <el-tag v-if="scope.row.scan_status==1" type="success">完成</el-tag>
                        <el-tag v-else-if="scope.row.scan_status==2" type="danger">失败</el-tag>
                        <el-tag v-else type="info">扫描中</el-tag>
                    </template>
                </el-table-column>
                <el-table-column min-width="80" prop="critical_count" label="严重" align="center">
                    <template #default="scope">
                        <span style="color: #F56C6C; font-weight: bold;">{{ scope.row.critical_count || 0 }}</span>
                    </template>
                </el-table-column>
                <el-table-column min-width="80" prop="major_count" label="重要" align="center">
                    <template #default="scope">
                        <span style="color: #E6A23C; font-weight: bold;">{{ scope.row.major_count || 0 }}</span>
                    </template>
                </el-table-column>
                <el-table-column min-width="80" prop="minor_count" label="一般" align="center">
                    <template #default="scope">
                        <span style="color: #909399;">{{ scope.row.minor_count || 0 }}</span>
                    </template>
                </el-table-column>
                <el-table-column min-width="80" prop="info_count" label="提示" align="center">
                    <template #default="scope">
                        <span style="color: #409EFF;">{{ scope.row.info_count || 0 }}</span>
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
                        <span class="table-operate-btn" @click="handleEdit(scope.row,'scan')" v-show="hasPermission(this.$route.name,'Create')">扫描</span>
                        <span class="table-operate-btn" @click="handleEdit(scope.row,'detail')" v-show="hasPermission(this.$route.name,'Retrieve')">详情</span>
                        <span class="table-operate-btn" @click="handleEdit(scope.row,'report')" v-show="hasPermission(this.$route.name,'Retrieve')">报告</span>
                        <span class="table-operate-btn" @click="handleEdit(scope.row,'delete')" v-show="hasPermission(this.$route.name,'Delete')">删除</span>
                    </template>
                </el-table-column>
            </el-table>
        </div>
        <Pagination v-bind:child-msg="pageparm" @callFather="callFather"></Pagination>
    </div>
</template>

<script>
    import Pagination from "@/components/Pagination";
    import {getTableHeight} from "@/utils/util";
    export default {
        name: "codeScan",
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
                    scan_status:'',
                    severity:''
                },
                pageparm: {
                    page: 1,
                    limit: 10,
                    total: 0
                },
                tableData:[],
                statusList:[
                    {id:0,name:'扫描中'},
                    {id:1,name:'完成'},
                    {id:2,name:'失败'},
                ],
                severityList:[
                    {id:'critical',name:'严重'},
                    {id:'major',name:'重要'},
                    {id:'minor',name:'一般'},
                    {id:'info',name:'提示'},
                ]
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
            addScan() {
                this.$message.info('新增扫描功能待开发')
            },
            handleEdit(row,flag) {
                if(flag=='scan') {
                    this.$message.info('开始扫描功能待开发')
                }
                else if(flag=='detail') {
                    this.$message.info('详情功能待开发')
                }
                else if(flag=='report') {
                    this.$message.info('查看报告功能待开发')
                }
                else if(flag=='delete') {
                    let vm = this
                    vm.$confirm('您确定要删除选中的数据吗？',{
                        closeOnClickModal:false
                    }).then(res=>{
                        vm.$message.success('删除成功')
                        vm.getData()
                    }).catch(()=>{

                    })
                }
                else if(flag=="reset"){
                    this.formInline = {
                        page:1,
                        limit: 10,
                        project_name:'',
                        scan_status:'',
                        severity:''
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
            //获取列表
            async getData() {
                this.loadingPage = true
                // TODO: 调用后端API获取数据
                // codeScanApi(this.formInline).then(res => {
                //      this.loadingPage = false
                //      if(res.code ==2000) {
                //          this.tableData = res.data.data
                //          this.pageparm.page = res.data.page;
                //          this.pageparm.limit = res.data.limit;
                //          this.pageparm.total = res.data.total;
                //      }
                //  })
                
                // 模拟数据
                setTimeout(() => {
                    this.loadingPage = false
                    this.tableData = [
                        {
                            id: 1,
                            project_name: '测试项目A',
                            scan_type: 'SonarQube',
                            scan_status: 1,
                            critical_count: 2,
                            major_count: 5,
                            minor_count: 12,
                            info_count: 28,
                            create_datetime: '2026-05-15 10:00:00'
                        }
                    ]
                    this.pageparm.total = 1
                }, 500)
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
