<template>
    <div class="workflow-dashboard">
        <el-row :gutter="20" style="margin-bottom: 20px;">
            <!-- 统计卡片 -->
            <el-col :span="4">
                <el-card shadow="hover">
                    <div class="stat-card">
                        <div class="stat-icon" style="background: #409EFF;">
                            <i class="el-icon-document"></i>
                        </div>
                        <div class="stat-content">
                            <div class="stat-value">{{ statistics.total || 0 }}</div>
                            <div class="stat-label">总流程数</div>
                        </div>
                    </div>
                </el-card>
            </el-col>
            
            <el-col :span="4">
                <el-card shadow="hover">
                    <div class="stat-card">
                        <div class="stat-icon" style="background: #E6A23C;">
                            <i class="el-icon-time"></i>
                        </div>
                        <div class="stat-content">
                            <div class="stat-value">{{ statistics.pending || 0 }}</div>
                            <div class="stat-label">审批中</div>
                        </div>
                    </div>
                </el-card>
            </el-col>
            
            <el-col :span="4">
                <el-card shadow="hover">
                    <div class="stat-card">
                        <div class="stat-icon" style="background: #67C23A;">
                            <i class="el-icon-check"></i>
                        </div>
                        <div class="stat-content">
                            <div class="stat-value">{{ statistics.approved || 0 }}</div>
                            <div class="stat-label">已通过</div>
                        </div>
                    </div>
                </el-card>
            </el-col>
            
            <el-col :span="4">
                <el-card shadow="hover">
                    <div class="stat-card">
                        <div class="stat-icon" style="background: #F56C6C;">
                            <i class="el-icon-close"></i>
                        </div>
                        <div class="stat-content">
                            <div class="stat-value">{{ statistics.rejected || 0 }}</div>
                            <div class="stat-label">已驳回</div>
                        </div>
                    </div>
                </el-card>
            </el-col>
            
            <el-col :span="4">
                <el-card shadow="hover">
                    <div class="stat-card">
                        <div class="stat-icon" style="background: #909399;">
                            <i class="el-icon-refresh-left"></i>
                        </div>
                        <div class="stat-content">
                            <div class="stat-value">{{ statistics.withdrawn || 0 }}</div>
                            <div class="stat-label">已撤回</div>
                        </div>
                    </div>
                </el-card>
            </el-col>
            
            <el-col :span="4">
                <el-card shadow="hover">
                    <div class="stat-card">
                        <div class="stat-icon" style="background: #8B5CF6;">
                            <i class="el-icon-tickets"></i>
                        </div>
                        <div class="stat-content">
                            <div class="stat-value">{{ statistics.my_pending_tasks || 0 }}</div>
                            <div class="stat-label">待我审批</div>
                        </div>
                    </div>
                </el-card>
            </el-col>
        </el-row>

        <el-row :gutter="20">
            <!-- 流程趋势图 -->
            <el-col :span="12">
                <el-card shadow="hover">
                    <template #header>
                        <span>最近7天流程趋势</span>
                    </template>
                    <div ref="trendChart" style="height: 300px;"></div>
                </el-card>
            </el-col>
            
            <!-- 流程类型分布 -->
            <el-col :span="12">
                <el-card shadow="hover">
                    <template #header>
                        <span>流程类型分布（Top 10）</span>
                    </template>
                    <div ref="typeChart" style="height: 300px;"></div>
                </el-card>
            </el-col>
        </el-row>
    </div>
</template>

<script>
import { workflowDashboardStatistics } from '@/api/api'
import * as echarts from 'echarts'

export default {
    name: 'workflowDashboard',
    data() {
        return {
            statistics: {
                total: 0,
                draft: 0,
                pending: 0,
                approved: 0,
                rejected: 0,
                withdrawn: 0,
                my_pending_tasks: 0,
                trends: [],
                by_type: []
            },
            trendChart: null,
            typeChart: null
        }
    },
    mounted() {
        this.loadStatistics()
    },
    methods: {
        // 加载统计数据
        loadStatistics() {
            workflowDashboardStatistics().then(res => {
                console.log('监控大屏统计数据:', res)
                console.log('res.data 类型:', typeof res.data)
                console.log('res.data 内容:', JSON.stringify(res.data))
                
                if (res.code === 2000) {
                    // 后端返回的数据可能被分页器包装了，需要提取真正的数据
                    let actualData = res.data
                    
                    // 如果 res.data 包含 data 属性，说明被分页器包装了
                    if (res.data && res.data.data && typeof res.data.data === 'object') {
                        console.log('检测到分页器包装，提取真实数据')
                        actualData = res.data.data
                    }
                    
                    console.log('实际使用的数据:', actualData)
                    
                    // 直接赋值，因为 statistics 已经在 data() 中预定义了所有字段
                    this.statistics = { ...this.statistics, ...actualData }
                    console.log('解析后的statistics:', this.statistics)
                    console.log('rejected 值:', this.statistics.rejected)
                    console.log('trends 长度:', this.statistics.trends ? this.statistics.trends.length : 'undefined')
                    console.log('by_type 长度:', this.statistics.by_type ? this.statistics.by_type.length : 'undefined')
                    
                    // 等待 DOM 更新后再初始化图表
                    this.$nextTick(() => {
                        this.initCharts()
                    })
                } else {
                    console.error('API返回错误:', res.msg)
                    this.$message.error('加载统计数据失败: ' + (res.msg || ''))
                }
            }).catch(err => {
                console.error('API调用失败:', err)
                this.$message.error('加载统计数据失败')
            })
        },
        
        // 初始化图表
        initCharts() {
            this.initTrendChart()
            this.initTypeChart()
        },
        
        // 初始化趋势图
        initTrendChart() {
            if (!this.$refs.trendChart) {
                console.warn('trendChart ref 不存在')
                return
            }
            
            if (this.trendChart) {
                this.trendChart.dispose()
            }
            
            this.trendChart = echarts.init(this.$refs.trendChart)
            
            const trends = this.statistics.trends || []
            console.log('趋势数据:', trends)
            
            if (trends.length === 0) {
                console.warn('没有趋势数据')
                return
            }
            
            const option = {
                tooltip: {
                    trigger: 'axis'
                },
                xAxis: {
                    type: 'category',
                    data: trends.map(item => item.date)
                },
                yAxis: {
                    type: 'value'
                },
                series: [{
                    data: trends.map(item => item.count),
                    type: 'line',
                    smooth: true,
                    itemStyle: {
                        color: '#409EFF'
                    },
                    areaStyle: {
                        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                            { offset: 0, color: 'rgba(64, 158, 255, 0.5)' },
                            { offset: 1, color: 'rgba(64, 158, 255, 0.1)' }
                        ])
                    }
                }]
            }
            
            this.trendChart.setOption(option)
            console.log('趋势图初始化完成')
        },
        
        // 初始化类型分布图
        initTypeChart() {
            if (!this.$refs.typeChart) {
                console.warn('typeChart ref 不存在')
                return
            }
            
            if (this.typeChart) {
                this.typeChart.dispose()
            }
            
            this.typeChart = echarts.init(this.$refs.typeChart)
            
            const byType = this.statistics.by_type || []
            console.log('流程类型数据:', byType)
            
            if (byType.length === 0) {
                console.warn('没有流程类型数据')
                return
            }
            
            const option = {
                tooltip: {
                    trigger: 'item'
                },
                legend: {
                    orient: 'vertical',
                    left: 'left'
                },
                series: [{
                    type: 'pie',
                    radius: '60%',
                    data: byType.map(item => ({
                        name: item.workflow_type__name,
                        value: item.count
                    })),
                    emphasis: {
                        itemStyle: {
                            shadowBlur: 10,
                            shadowOffsetX: 0,
                            shadowColor: 'rgba(0, 0, 0, 0.5)'
                        }
                    }
                }]
            }
            
            this.typeChart.setOption(option)
            console.log('类型分布图初始化完成')
        }
    },
    beforeDestroy() {
        if (this.trendChart) {
            this.trendChart.dispose()
        }
        if (this.typeChart) {
            this.typeChart.dispose()
        }
    }
}
</script>

<style scoped>
.workflow-dashboard {
    padding: 20px;
}

.stat-card {
    display: flex;
    align-items: center;
}

.stat-icon {
    width: 60px;
    height: 60px;
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-right: 15px;
}

.stat-icon i {
    font-size: 30px;
    color: white;
}

.stat-content {
    flex: 1;
}

.stat-value {
    font-size: 28px;
    font-weight: bold;
    color: #303133;
    margin-bottom: 5px;
}

.stat-label {
    font-size: 14px;
    color: #909399;
}
</style>
