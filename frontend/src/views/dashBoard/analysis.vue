<template>
    <div class="lycontainer">
        <el-scrollbar>
            <div>
                <ly-growcard :loading="showloading" :rows="2" v-model="growData"></ly-growcard>
            </div>
            <div class="echarts-inner">
                <!-- License 统计分析 -->
                <el-tabs type="border-card" class="lycard" v-model="licenseActiveName">
                    <el-tab-pane label="产品申请分布" name="product">
                        <el-skeleton :rows="3" :animated="true" :loading="licenseLoading">
                            <ly-product-pie ref="lyProductPie" :data="productStats"></ly-product-pie>
                        </el-skeleton>
                    </el-tab-pane>
                    <el-tab-pane label="Feature申请分布" name="feature">
                        <el-skeleton :rows="3" :animated="true" :loading="licenseLoading">
                            <ly-feature-bar ref="lyFeatureBar" :data="featureStats"></ly-feature-bar>
                        </el-skeleton>
                    </el-tab-pane>
                    <el-tab-pane label="客户申请分布" name="customer">
                        <el-skeleton :rows="3" :animated="true" :loading="licenseLoading">
                            <ly-customer-bar ref="lyCustomerBar" :data="customerStats"></ly-customer-bar>
                        </el-skeleton>
                    </el-tab-pane>
                </el-tabs>
            </div>
        </el-scrollbar>
    </div>
</template>

<script>
    import LyGrowcard from "../../components/analysis/growCard";
    import LyProductPie from "../../components/analysis/productPieEchart";
    import LyFeatureBar from "../../components/analysis/featureBarEchart";
    import LyCustomerBar from "../../components/analysis/customerBarEchart";
    import { licenseDashboardStatistics } from '@/api/api';
    
    export default {
        name: "analysis",
        components: {LyGrowcard, LyProductPie, LyFeatureBar, LyCustomerBar},
        data(){
            return{
                showloading:true,
                growData:[
                    {id:1,title:"产品数",nums:0,totalnums:0,icon:{
                            type:"GoodsFilled",
                            background:"#67c23a",
                        },
                        time:{
                            name:"总计",
                            type:"success"
                        }},
                    {id:2,title:"申请Feature数",nums:0,totalnums:0,icon:{
                            type:"Menu",
                            background:"#e6a23c",
                        },
                        time:{
                            name:"总计",
                            type:"warning"
                        }},
                    {id:3,title:"客户数",nums:0,totalnums:0,icon:{
                            type:"User",
                            background:"#409eff",
                        },
                        time:{
                            name:"总计",
                            type:"info"
                        }},
                    {id:4,title:"申请人数",nums:0,totalnums:0,icon:{
                            type:"Avatar",
                            background:"#f56c6c",
                        },
                        time:{
                            name:"总计",
                            type:"danger"
                        }},
                ],
                echartsData:[

                ],
                licenseActiveName: 'product',
                licenseLoading: true,
                productStats: [],
                featureStats: [],
                customerStats: []
            }
        },
        created() {
            setTimeout(() => {
                this.showloading = false
            }, 600)
            // 加载 License 统计数据
            this.loadLicenseStatistics()
        },
        watch: {
            // 监听 Tab 切换，触发图表 resize
            licenseActiveName(newVal) {
                // 使用更长的延迟确保 DOM 完全渲染
                setTimeout(() => {
                    // 触发当前图表组件的 resize
                    const componentMap = {
                        'product': 'lyProductPie',
                        'feature': 'lyFeatureBar',
                        'customer': 'lyCustomerBar'
                    }
                    const refName = componentMap[newVal]
                    if (this.$refs[refName]) {
                        this.$refs[refName].resize()
                    }
                }, 150)
            }
        },
        methods: {
            async loadLicenseStatistics() {
                try {
                    this.licenseLoading = true
                    const res = await licenseDashboardStatistics({})
                    
                    if (res.code === 2000) {
                        const data = res.data.data
                        this.productStats = data.product_stats || []
                        this.featureStats = data.feature_stats || []
                        this.customerStats = data.customer_stats || []
                        
                        // 更新顶部统计卡片
                        this.growData[0].nums = this.productStats.length
                        this.growData[0].totalnums = this.productStats.reduce((sum, item) => sum + item.count, 0)
                        
                        this.growData[1].nums = this.featureStats.length
                        this.growData[1].totalnums = this.featureStats.reduce((sum, item) => sum + item.count, 0)
                        
                        this.growData[2].nums = this.customerStats.length
                        this.growData[2].totalnums = this.customerStats.reduce((sum, item) => sum + item.count, 0)
                        
                        this.growData[3].nums = data.total_applications || 0
                        this.growData[3].totalnums = data.total_applications || 0
                    }
                } catch (error) {
                    console.error('获取License统计数据失败', error)
                    this.$message.error('获取License统计数据失败')
                } finally {
                    this.licenseLoading = false
                    this.showloading = false
                }
            }
        },
    }
</script>
<style lang="scss" scoped>
    .lycontainer{
        width: 100%;
        height: calc(100vh - 130px); //动态计算长度值
        /*overflow-x: hidden;*/
        /*overflow-y:auto;*/
    }
    .echarts-inner{
        margin-top: 20px;
    }
    ::v-deep(.el-scrollbar__bar.is-horizontal) {
        display: none;
    }
    ::v-deep(.el-tabs__content) {
        padding: 20px;
    }
</style>