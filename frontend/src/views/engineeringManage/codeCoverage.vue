<template>
    <div :class="{'ly-is-full':isFull}">
        <div class="tableSelect" ref="tableSelect">
            <el-form :inline="true" :model="formInline" label-position="left">
                <el-form-item label="项目名称：">
                    <el-input size="default" v-model.trim="formInline.project_name" maxlength="60" clearable placeholder="项目名称" @change="search" style="width:200px"></el-input>
                </el-form-item>
                <el-form-item label="模块名称：">
                    <el-input size="default" v-model.trim="formInline.module_name" maxlength="60" clearable placeholder="模块名称" @change="search" style="width:200px"></el-input>
                </el-form-item>
                <el-form-item label="覆盖率范围：">
                    <el-select v-model="formInline.coverage_type" placeholder="请选择" clearable @change="search" size="default" style="width:120px">
                        <el-option
                            v-for="item in coverageTypeList"
                            :key="item.id"
                            :label="item.name"
                            :value="item.id">
                        </el-option>
                    </el-select>
                </el-form-item>
                <el-form-item label=""><el-button @click="search" type="primary" icon="Search" v-show="hasPermission(this.$route.name,'Search')">查询</el-button></el-form-item>
                <el-form-item label=""><el-button @click="handleEdit('','reset')" icon="Refresh">重置</el-button></el-form-item>
                <el-form-item label="" v-show="hasPermission(this.$route.name,'Create')">
                    <el-button icon="Plus" type="primary" @click="addCoverage">新增</el-button>
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
                <el-table-column min-width="150" prop="module_name" label="模块名称" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="100" prop="coverage_type" label="覆盖率类型" show-overflow-tooltip></el-table-column>
                <el-table-column min-width="120" label="行覆盖率" align="center">
                    <template #default="scope">
                        <el-progress :percentage="scope.row.line_coverage || 0" :color="getCoverageColor(scope.row.line_coverage)" style="width: 100px;"></el-progress>
                        <span style="margin-left: 5px;">{{ scope.row.line_coverage || 0 }}%</span>
                    </template>
                </el-table-column>
                <el-table-column min-width="120" label="分支覆盖率" align="center">
                    <template #default="scope">
                        <el-progress :percentage="scope.row.branch_coverage || 0" :color="getCoverageColor(scope.row.branch_coverage)" style="width: 100px;"></el-progress>
                        <span style="margin-left: 5px;">{{ scope.row.branch_coverage || 0 }}%</span>
                    </template>
                </el-table-column>
                <el-table-column min-width="120" label="方法覆盖率" align="center">
                    <template #default="scope">
                        <el-progress :percentage="scope.row.method_coverage || 0" :color="getCoverageColor(scope.row.method_coverage)" style="width: 100px;"></el-progress>
                        <span style="margin-left: 5px;">{{ scope.row.method_coverage || 0 }}%</span>
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
                        <span class="table-operate-btn" @click="handleEdit(scope.row,'analyze')" v-show="hasPermission(this.$route.name,'Create')">分析</span>
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
        name: "codeCoverage",
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
                    module_name:'',
                    coverage_type:''
                },
                pageparm: {
                    page: 1,
                    limit: 10,
                    total: 0
                },
                tableData:[],
                coverageTypeList:[
                    {id:'line',name:'行覆盖率'},
                    {id:'branch',name:'分支覆盖率'},
                    {id:'method',name:'方法覆盖率'},
                    {id:'class',name:'类覆盖率'},
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
            // 根据覆盖率获取颜色
            getCoverageColor(coverage) {
                if (coverage >= 80) {
                    return '#67C23A' // 绿色
                } else if (coverage >= 60) {
                    return '#E6A23C' // 黄色
                } else {
                    return '#F56C6C' // 红色
                }
            },
            addCoverage() {
                this.$message.info('新增代码覆盖率功能待开发')
            },
            handleEdit(row,flag) {
                if(flag=='analyze') {
                    this.$message.info('代码分析功能待开发')
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
                        module_name:'',
                        coverage_type:''
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
                // codeCoverageApi(this.formInline).then(res => {
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
                            module_name: '用户模块',
                            coverage_type: '综合',
                            line_coverage: 85,
                            branch_coverage: 72,
                            method_coverage: 90,
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
