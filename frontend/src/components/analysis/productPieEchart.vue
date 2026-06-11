<template>
    <div ref="lyechartmain" style="width: 100%;height: 450px"></div>
</template>

<script setup>
    import {onMounted, nextTick, watch, onUnmounted, onBeforeUnmount, ref, defineProps, defineExpose } from "vue";
    import echarts from "@/components/analysis/echartsInstall";
    
    const props = defineProps({
        data: {
            type: Array,
            default: () => []
        }
    });
    
    let myChart = null
    let lyechartmain = ref(null)
    
    // 颜色方案
    const colorPalette = [
        '#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de',
        '#3ba272', '#fc8452', '#9a60b4', '#ea7ccc', '#5470c6'
    ];
    
    const initChart = () => {
        if (!lyechartmain.value) return;
        
        // 如果已经初始化过，只更新数据
        if (myChart) {
            updateChart();
            return;
        }
        
        myChart = echarts.init(lyechartmain.value);
        updateChart();
        
        window.addEventListener('resize', handleResize);
    };
    
    const updateChart = () => {
        if (!myChart) return;
        
        // 检查容器是否有尺寸
        if (!lyechartmain.value || lyechartmain.value.clientWidth === 0 || lyechartmain.value.clientHeight === 0) {
            // 容器不可见，延迟更新
            setTimeout(() => {
                updateChart();
            }, 100);
            return;
        }
        
        // 取前10个产品
        const topProducts = props.data && props.data.length > 0 ? props.data.slice(0, 10) : [];
        
        // 先调用 resize 确保容器尺寸正确
        myChart.resize();
        
        if (topProducts.length === 0) {
            // 显示空数据提示
            const option = {
                title: {
                    text: '产品申请分布 TOP 10',
                    left: 'center',
                    textStyle: {
                        fontSize: 16,
                        fontWeight: 'bold'
                    }
                },
                graphic: {
                    type: 'text',
                    left: 'center',
                    top: 'middle',
                    style: {
                        text: '暂无数据',
                        fontSize: 16,
                        fill: '#999'
                    }
                }
            };
            myChart.setOption(option, true);
            return;
        }
        
        const option = {
            title: {
                text: '产品申请分布 TOP 10',
                left: 'center',
                textStyle: {
                    fontSize: 16,
                    fontWeight: 'bold'
                }
            },
            tooltip: {
                trigger: 'item',
                formatter: '{b}: {c}次 ({d}%)'
            },
            legend: {
                orient: 'vertical',
                right: '5%',
                top: 'center',
                textStyle: {
                    fontSize: 12
                }
            },
            color: colorPalette,
            series: [
                {
                    name: '申请次数',
                    type: 'pie',
                    radius: ['40%', '70%'],
                    center: ['35%', '55%'],
                    avoidLabelOverlap: false,
                    itemStyle: {
                        borderRadius: 10,
                        borderColor: '#fff',
                        borderWidth: 2
                    },
                    label: {
                        show: false,
                        position: 'center'
                    },
                    emphasis: {
                        label: {
                            show: true,
                            fontSize: 18,
                            fontWeight: 'bold'
                        }
                    },
                    labelLine: {
                        show: false
                    },
                    data: topProducts.map((item, index) => ({
                        value: item.count,
                        name: item.product || '未知产品',
                        itemStyle: {
                            color: colorPalette[index % colorPalette.length]
                        }
                    }))
                }
            ]
        };
        
        myChart.setOption(option);
    };
    
    const handleResize = () => {
        if (myChart) {
            myChart.resize();
        }
    };
    
    // 监听数据变化
    watch(() => props.data, (newData) => {
        updateChart();
    }, { deep: true });
    
    onMounted(() => {
        setTimeout(() => {
            nextTick(() => {
                initChart();
            });
        }, 300);
    });
    
    onBeforeUnmount(() => {
        window.removeEventListener('resize', handleResize);
        if (myChart) {
            myChart.dispose();
        }
    });
    
    defineExpose({
        resize: handleResize
    });
</script>

<style scoped>

</style>
