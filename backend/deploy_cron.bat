@echo off
REM License 过期检查定时任务 - Windows 部署脚本
REM 使用方法：双击运行此脚本即可自动安装和配置定时任务

echo ========================================
echo License 过期检查定时任务 - Windows 部署
echo ========================================
echo.

cd /d %~dp0

echo [1/4] 检查 Python 环境...
python --version
if errorlevel 1 (
    echo 错误: 未找到 Python，请先安装 Python 3.9+
    pause
    exit /b 1
)
echo ✓ Python 环境正常
echo.

echo [2/4] 安装 django-crontab...
pip install django-crontab -i https://mirrors.aliyun.com/pypi/simple/
if errorlevel 1 (
    echo 警告: django-crontab 安装失败，但将继续执行
)
echo ✓ django-crontab 安装完成
echo.

echo [3/4] 清理旧的定时任务...
python manage.py crontab remove
echo ✓ 旧任务已清理
echo.

echo [4/4] 注册新的定时任务...
python manage.py crontab add
if errorlevel 1 (
    echo 错误: 定时任务注册失败
    echo.
    echo 可能的原因：
    echo 1. Windows 不支持 crontab，需要使用任务计划程序
    echo 2. 请手动执行: python manage.py check_license_expiration
    pause
    exit /b 1
)
echo ✓ 定时任务注册成功
echo.

echo ========================================
echo 部署完成！
echo ========================================
echo.
echo 定时任务信息：
echo - 执行时间：每天凌晨 2:00
echo - 任务内容：检查 License 过期状态并发送邮件提醒
echo.
echo 查看已注册的任务：
echo   python manage.py crontab show
echo.
echo 手动测试执行：
echo   python manage.py check_license_expiration
echo.
echo 强制重新发送所有提醒（测试用）：
echo   python manage.py check_license_expiration --force
echo.
echo 删除所有定时任务：
echo   python manage.py crontab remove
echo.
echo 日志文件位置：
echo   D:\eladmin\django-vue-lyadmin\backend\logs\server.log
echo.

pause
