<template>
    <div :class="{'ly-is-full':isFull}">
        <!-- 标签页 -->
        <el-tabs v-model="activeTab" @tab-click="handleTabClick" style="margin-bottom: 20px;">
            <el-tab-pane label="全部消息" name="all"></el-tab-pane>
            <el-tab-pane label="系统通知" name="1"></el-tab-pane>
            <el-tab-pane label="平台公告" name="2"></el-tab-pane>
        </el-tabs>

        <!-- 搜索栏 -->
        <div class="tableSelect" ref="tableSelect">
            <el-form :inline="true" :model="formInline" label-position="left">
                <el-form-item label="">
                    <el-button @click="refreshData" icon="Refresh">刷新</el-button>
                </el-form-item>
                <el-form-item label="">
                    <el-button @click="markAllAsRead" type="primary" icon="Check">全部已读</el-button>
                </el-form-item>
            </el-form>
        </div>

        <!-- 消息列表 -->
        <el-table 
            :height="'calc('+(tableHeight)+'px)'" 
            border 
            :data="tableData" 
            ref="tableref" 
            v-loading="loadingPage" 
            style="width: 100%">
            
            <el-table-column type="index" width="60" align="center" label="序号">
                <template #default="scope">
                    <span v-text="getIndex(scope.$index)"></span>
                </template>
            </el-table-column>

            <el-table-column min-width="80" label="状态">
                <template #default="scope">
                    <el-tag v-if="!scope.row.is_read" type="warning">未读</el-tag>
                    <el-tag v-else type="success">已读</el-tag>
                </template>
            </el-table-column>

            <el-table-column min-width="200" prop="msg_title" label="标题">
                <template #default="scope">
                    <span :style="{fontWeight: scope.row.is_read ? 'normal' : 'bold', color: scope.row.is_read ? '#606266' : '#303133'}">
                        {{ scope.row.msg_title }}
                    </span>
                </template>
            </el-table-column>

            <el-table-column min-width="300" prop="msg_content" show-overflow-tooltip label="内容">
                <template #default="scope">
                    <div v-html="customEllipsis(scope.row.msg_content)" class="ellipsis"></div>
                </template>
            </el-table-column>

            <el-table-column min-width="150" prop="create_datetime" label="接收时间"></el-table-column>

            <el-table-column label="操作" fixed="right" width="240">
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
                    <!-- 如果是审批任务且未审批，显示审批按钮 -->
                    <span class="table-operate-btn" 
                          @click="approveTask(scope.row)" 
                          v-if="scope.row.is_approval_task && !scope.row.is_read"
                          style="color: #409EFF;">
                        审批
                    </span>
                    <span class="table-operate-btn" @click="viewMessage(scope.row)">查看</span>
                    <span class="table-operate-btn" @click="markAsRead(scope.row)" v-if="!scope.row.is_read">标记已读</span>
                    <span class="table-operate-btn" @click="deleteMessage(scope.row)">删除</span>
                </template>
            </el-table-column>
        </el-table>

        <!-- 分页 -->
        <Pagination v-bind:child-msg="pageparm" @callFather="callFather"></Pagination>

        <!-- 查看消息对话框 -->
        <el-dialog 
            v-model="viewDialogVisible" 
            title="消息详情" 
            width="600px"
            :close-on-click-modal="false">
            <div v-if="currentMessage">
                <h3>{{ currentMessage.msg_title }}</h3>
                <div style="color: #909399; margin-bottom: 15px;">
                    接收时间：{{ currentMessage.create_datetime }}
                </div>
                <div style="line-height: 1.8;" v-html="currentMessage.msg_content"></div>
            </div>
            <template #footer>
                <span class="dialog-footer">
                    <el-button @click="viewDialogVisible = false">关闭</el-button>
                    <el-button type="primary" @click="markAsReadAndClose" v-if="currentMessage && !currentMessage.is_read">
                        标记为已读
                    </el-button>
                </span>
            </template>
        </el-dialog>
    </div>
</template>

<script>
import Pagination from "@/components/Pagination";
import { getTableHeight } from "@/utils/util";
import { getUserMessages, updateUserMessageStatus, workflowTaskApprove, workflowTaskReject } from '@/api/api';

export default {
    components: {
        Pagination
    },
    name: 'myMessages',
    data() {
        return {
            isFull: false,
            tableHeight: 500,
            loadingPage: false,
            activeTab: 'all', // 当前激活的标签页：all=全部，1=系统通知，2=平台公告
            formInline: {
                page: 1,
                limit: 10,
                type: null // null=全部，1=系统通知，2=平台公告
            },
            pageparm: {
                page: 1,
                limit: 10,
                total: 0
            },
            tableData: [],
            viewDialogVisible: false,
            currentMessage: null
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
        
        // 当渲染的文字超出10字后显示省略号
        customEllipsis(value) {
            value = value.replace(/<.*?>/ig, "") // 把v-html的格式标签替换掉
            if (!value) return ""
            if (value.length > 10) {
                return value.slice(0, 10) + "..."
            }
            return value
        },
        
        // 标签页切换
        handleTabClick(tab) {
            this.activeTab = tab.paneName
            this.formInline.type = tab.paneName === 'all' ? null : tab.paneName
            this.formInline.page = 1
            this.getData()
        },
        
        // 刷新数据
        refreshData() {
            this.formInline.page = 1
            this.getData()
        },
        
        // 标记全部为已读
        markAllAsRead() {
            let vm = this
            vm.$confirm('确定要将所有消息标记为已读吗？', {
                closeOnClickModal: false
            }).then(res => {
                // 获取所有未读消息的ID
                const unreadIds = vm.tableData.filter(item => !item.is_read).map(item => item.id)
                
                if (unreadIds.length === 0) {
                    vm.$message.info('没有未读消息')
                    return
                }
                
                // 逐个标记为已读
                let successCount = 0
                let promises = unreadIds.map(id => {
                    return updateUserMessageStatus({ id: id, type: 'isread' })
                        .then(res => {
                            if (res.code === 2000) {
                                successCount++
                            }
                        })
                })
                
                Promise.all(promises).then(() => {
                    vm.$message.success(`已将 ${successCount} 条消息标记为已读`)
                    vm.getData()
                })
            }).catch(() => {})
        },
        
        // 查看消息
        viewMessage(row) {
            this.currentMessage = row
            this.viewDialogVisible = true
            
            // 如果未读，自动标记为已读
            if (!row.is_read) {
                this.markAsRead(row, false)
            }
        },
        
        // 标记为已读
        markAsRead(row, showMessage = true) {
            let vm = this
            updateUserMessageStatus({ id: row.id, type: 'isread' }).then(res => {
                if (res.code === 2000) {
                    row.is_read = true
                    if (showMessage) {
                        vm.$message.success('已标记为已读')
                    }
                } else {
                    vm.$message.warning(res.msg || '操作失败')
                }
            }).catch(err => {
                vm.$message.error('操作失败')
            })
        },
        
        // 标记为已读并关闭对话框
        markAsReadAndClose() {
            if (this.currentMessage) {
                this.markAsRead(this.currentMessage, true)
                this.currentMessage.is_read = true
            }
            this.viewDialogVisible = false
        },
        
        // 删除消息
        deleteMessage(row) {
            let vm = this
            vm.$confirm('确定要删除这条消息吗？', {
                closeOnClickModal: false
            }).then(res => {
                updateUserMessageStatus({ id: row.id, type: 'del' }).then(res => {
                    if (res.code === 2000) {
                        vm.$message.success('删除成功')
                        vm.getData()
                    } else {
                        vm.$message.warning(res.msg || '删除失败')
                    }
                }).catch(err => {
                    vm.$message.error('删除失败')
                })
            }).catch(() => {})
        },
        
        // 审批任务（通过）
        approveTask(row) {
            let vm = this
            if (!row.task_id) {
                vm.$message.warning('无法找到对应的审批任务')
                return
            }
            
            vm.$prompt('请输入审批意见（可选）', '审批通过', {
                confirmButtonText: '确定',
                cancelButtonText: '取消',
                inputPlaceholder: '请输入审批意见',
                closeOnClickModal: false
            }).then(({ value }) => {
                const data = {
                    remark: value || ''
                }
                
                workflowTaskApprove(row.task_id, data).then(res => {
                    if (res.code === 2000) {
                        vm.$message.success('审批通过')
                        // 标记消息为已读
                        vm.markAsRead(row, false)
                        // 刷新列表
                        vm.getData()
                    } else {
                        vm.$message.error(res.msg || '审批失败')
                    }
                }).catch(err => {
                    vm.$message.error('审批失败')
                })
            }).catch(() => {})
        },
        
        callFather(parm) {
            this.formInline.page = parm.page
            this.formInline.limit = parm.limit
            this.getData()
        },
        
        // 获取列表
        async getData() {
            this.loadingPage = true
            getUserMessages(this.formInline).then(res => {
                this.loadingPage = false
                if (res.code === 2000) {
                    this.tableData = res.data.data
                    this.pageparm.page = res.data.page
                    this.pageparm.limit = res.data.limit
                    this.pageparm.total = res.data.total
                }
            }).catch(err => {
                this.loadingPage = false
                this.$message.error('获取消息列表失败')
            })
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

<style scoped>
.ellipsis {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
</style>
