<template>
    <div :class="{'ly-is-full':isFull}">
        <!-- 搜索栏 -->
        <div class="tableSelect" ref="tableSelect">
            <el-form :inline="true" :model="formInline" label-position="left">
                <el-form-item label="">
                    <el-button @click="refreshData" icon="Refresh">刷新</el-button>
                </el-form-item>
                <el-form-item label="">
                    <el-select v-model="formInline.status" placeholder="处理结果" clearable @change="refreshData" style="width: 140px;">
                        <el-option label="通过" :value="1"></el-option>
                        <el-option label="驳回" :value="2"></el-option>
                        <el-option label="退回" :value="3"></el-option>
                    </el-select>
                </el-form-item>
                <el-form-item label="">
                    <el-input v-model="formInline.search" placeholder="请输入流程编号/标题" clearable @keyup.enter="refreshData" style="width: 220px;"></el-input>
                </el-form-item>
                <el-form-item label="">
                    <el-button type="primary" @click="refreshData" icon="Search">查询</el-button>
                </el-form-item>
            </el-form>
        </div>

        <!-- 已办任务列表 -->
        <el-table 
            :height="'calc('+(tableHeight)+'px)'" 
            border 
            :data="tableData" 
            ref="tableref" 
            v-loading="loadingPage" 
            row-key="id"
            style="width: 100%">
            
            <el-table-column type="index" width="60" align="center" label="序号">
                <template #default="scope">
                    <span v-text="getIndex(scope.$index)"></span>
                </template>
            </el-table-column>

            <el-table-column min-width="180" prop="instance_no" label="流程编号"></el-table-column>

            <el-table-column min-width="200" prop="instance_title" label="流程标题" show-overflow-tooltip></el-table-column>

            <el-table-column min-width="100" prop="applicant_name" label="申请人"></el-table-column>

            <el-table-column min-width="150" prop="step_name" label="审批节点">
                <template #default="scope">
                    <el-tag>{{ scope.row.step_name }}</el-tag>
                </template>
            </el-table-column>

            <el-table-column min-width="100" label="处理结果">
                <template #default="scope">
                    <el-tag :type="resultTagType(scope.row.status)">{{ scope.row.status_display }}</el-tag>
                </template>
            </el-table-column>

            <el-table-column min-width="180" prop="approve_comment" label="审批意见" show-overflow-tooltip></el-table-column>

            <el-table-column min-width="150" prop="approve_time" label="审批时间"></el-table-column>

            <el-table-column min-width="100" label="流程状态">
                <template #default="scope">
                    <el-tag :type="instanceStatusTagType(scope.row.instance_status)" size="small">
                        {{ scope.row.instance_status_display }}
                    </el-tag>
                </template>
            </el-table-column>

            <!-- 操作列 -->
            <el-table-column label="操作" fixed="right" width="100">
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
                    <span class="table-operate-btn" @click="viewWorkflowDetail(scope.row)">详情</span>
                </template>
            </el-table-column>
        </el-table>

        <!-- 分页 -->
        <Pagination v-bind:child-msg="pageparm" @callFather="callFather"></Pagination>

        <!-- 流程详情弹窗（公共组件：流程列表/我的待办/我的已办共用） -->
        <WorkflowDetailDialog v-model="detailDialogVisible" :instance-id="detailInstanceId" />
    </div>
</template>

<script>
import Pagination from "@/components/Pagination";
import { getTableHeight } from "@/utils/util";
import { getMyHandledTasks } from '@/api/api';
import WorkflowDetailDialog from "@/components/workflowDetailDialog";

export default {
    components: {
        Pagination,
        WorkflowDetailDialog
    },
    name: 'myHandled',
    data() {
        return {
            isFull: false,
            tableHeight: 500,
            loadingPage: false,
            formInline: {
                page: 1,
                limit: 10,
                status: null, // 处理结果：null=全部，1=通过，2=驳回，3=退回
                search: '' // 流程编号/标题关键字
            },
            pageparm: {
                page: 1,
                limit: 10,
                total: 0
            },
            tableData: [],
            detailDialogVisible: false,
            detailInstanceId: null  // 查看详情的流程实例ID（传递给公共详情组件）
        }
    },
    methods: {
        // 表格序列号
        getIndex($index) {
            return (this.pageparm.page - 1) * this.pageparm.limit + $index + 1
        },

        setFull() {
            this.isFull = !this.isFull
            window.dispatchEvent(new Event('resize'))
        },

        // 处理结果标签颜色：1=通过，2=驳回，3=退回
        resultTagType(status) {
            const map = { 1: 'success', 2: 'danger', 3: 'warning' }
            return map[status] || 'info'
        },

        // 流程实例状态标签颜色：0草稿 1审批中 2已通过 3已驳回 4已撤回 5已取消 6已退回
        instanceStatusTagType(status) {
            const map = { 1: 'primary', 2: 'success', 3: 'danger', 4: 'info', 5: 'info', 6: 'warning' }
            return map[status] || 'info'
        },

        // 刷新/查询
        refreshData() {
            this.formInline.page = 1
            this.getData()
        },

        callFather(parm) {
            this.formInline.page = parm.page
            this.formInline.limit = parm.limit
            this.getData()
        },

        // 获取我的已办列表
        getData() {
            this.loadingPage = true
            const params = { ...this.formInline }
            if (!params.search) {
                delete params.search
            }
            if (params.status === null || params.status === '') {
                delete params.status
            }
            getMyHandledTasks(params).then(res => {
                this.loadingPage = false
                if (res.code === 2000) {
                    this.tableData = res.data.data || []
                    this.pageparm.page = res.data.page
                    this.pageparm.limit = res.data.limit
                    this.pageparm.total = res.data.total
                }
            }).catch(err => {
                this.loadingPage = false
                this.$message.error('获取已办任务列表失败')
            })
        },

        // 查看流程详情：打开公共详情弹窗（与流程列表/我的待办展示一致）
        viewWorkflowDetail(row) {
            let vm = this
            const instanceId = row.instance
            if (!instanceId) {
                vm.$message.warning('未获取到对应的流程实例信息')
                return
            }
            vm.detailInstanceId = instanceId
            vm.detailDialogVisible = true
        },

        // 计算搜索栏的高度
        listenResize() {
            this.$nextTick(() => {
                this.getTheTableHeight()
            })
        },

        getTheTableHeight() {
            let tabSelectHeight = this.$refs.tableSelect ? this.$refs.tableSelect.offsetHeight : 0
            tabSelectHeight = this.isFull ? tabSelectHeight - 110 : tabSelectHeight
            this.tableHeight = getTableHeight(tabSelectHeight)
        }
    },
    created() {
        this.getData()
    },
    mounted() {
        // 监听页面宽度变化搜索框的高度
        window.addEventListener('resize', this.listenResize);
        this.$nextTick(() => {
            this.getTheTableHeight()
        })
    },
    unmounted() {
        // 页面销毁，去掉监听事件
        window.removeEventListener("resize", this.listenResize);
    },
}
</script>
