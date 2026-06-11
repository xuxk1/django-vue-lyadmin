<template>
    <div ref="lyechartmain" style="width: 100%;height: 450px"></div>
</template>

<script setup>
    import {onMounted, nextTick, watch, onBeforeUnmount, ref, defineProps, defineExpose } from "vue";
    import echarts from "@/components/analysis/echartsInstall";
    
    const props = defineProps({
        data: {
            type: Array,
            default: () => []
        }
    });
    
    let myChart = null
    let lyechartmain = ref(null)
    
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
        
        // 取前10个客户
        const topCustomers = props.data && props.data.length > 0 ? props.data.slice(0, 10) : [];
        
        // 先调用 resize 确保容器尺寸正确
        myChart.resize();
        
        if (topCustomers.length === 0) {
            // 显示空数据提示
            const option = {
                title: {
                    text: '客户申请分布 TOP 10',
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
                text: '客户申请分布 TOP 10',
                left: 'center',
                textStyle: {
                    fontSize: 16,
                    fontWeight: 'bold'
                }
            },
            tooltip: {
                trigger: 'axis',
                axisPointer: {
                    type: 'shadow'
                },
                formatter: '{b}: {c}次'
            },
            grid: {
                left: '3%',
                right: '4%',
                bottom: '3%',
                top: '60px',
                containLabel: true
            },
            xAxis: {
                type: 'value',
                name: '申请次数'
            },
            yAxis: {
                type: 'category',
                data: topCustomers.map(item => item.customer_name || '未知客户'),
                axisLabel: {
                    fontSize: 11,
                    interval: 0
                }
            },
            series: [
                {
                    name: '申请次数',
                    type: 'bar',
                    data: topCustomers.map(item => item.count),
                    itemStyle: {
                        color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
                            { offset: 0, color: '#83bff6' },
                            { offset: 0.5, color: '#188df0' },
                            { offset: 1, color: '#188df0' }
                        ])
                    },
                    emphasis: {
                        itemStyle: {
                            color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
                                { offset: 0, color: '#2378f7' },
                                { offset: 0.7, color: '#2378f7' },
                                { offset: 1, color: '#83bff6' }
                            ])
                        }
                    },
                    barWidth: '60%'
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
