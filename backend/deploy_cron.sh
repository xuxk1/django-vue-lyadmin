#!/bin/bash
# License 过期检查定时任务 - Linux/Mac 部署脚本
# 使用方法: chmod +x deploy_cron.sh && ./deploy_cron.sh

set -e  # 遇到错误立即退出

echo "========================================"
echo "License 过期检查定时任务 - Linux/Mac 部署"
echo "========================================"
echo ""

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "[1/3] 检查 Python 环境..."
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到 Python3，请先安装 Python 3.9+"
    exit 1
fi
python3 --version
echo "✓ Python 环境正常"

echo "[2/3] 清理旧的定时任务..."
python3 manage.py crontab remove || true
echo "✓ 旧任务已清理"
echo ""

echo "[3/3] 注册新的定时任务..."
python3 manage.py crontab add
if [ $? -ne 0 ]; then
    echo "错误: 定时任务注册失败"
    echo ""
    echo "可能的原因："
    echo "1. crontab 命令不存在，请安装 cron"
    echo "2. 权限不足，请使用 sudo"
    echo "3. 请手动执行: python3 manage.py check_license_expiration"
    exit 1
fi
echo "✓ 定时任务注册成功"
echo ""

echo "========================================"
echo "部署完成！"
echo "========================================"
echo ""
echo "定时任务信息："
echo "- 执行时间：每天凌晨 2:00"
echo "- 任务内容：检查 License 过期状态并发送邮件提醒"
echo ""
echo "查看已注册的任务："
echo "  python3 manage.py crontab show"
echo ""
echo "手动测试执行："
echo "  python3 manage.py check_license_expiration"
echo ""
echo "强制重新发送所有提醒（测试用）："
echo "  python3 manage.py check_license_expiration --force"
echo ""
echo "删除所有定时任务："
echo "  python3 manage.py crontab remove"
echo ""
echo "日志文件位置："
echo "  /efficiency/django-vue-lyadmin/log/license_check.log"
echo "  $SCRIPT_DIR/logs/server.log"
echo ""
echo "查看实时日志："
echo "  tail -f /efficiency/log/license_check.log"
echo ""
