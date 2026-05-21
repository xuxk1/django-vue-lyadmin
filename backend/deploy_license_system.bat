@echo off
chcp 65001 >nul
echo.
echo ╔═══════════════════════════════════════════════════════════╗
echo ║           License系统重构 - 一键部署脚本                  ║
echo ╚═══════════════════════════════════════════════════════════╝
echo.

REM 检查是否在正确的目录
if not exist "manage.py" (
    echo [错误] 请在backend目录下运行此脚本
    pause
    exit /b 1
)

echo [步骤 1/6] 备份数据库（可选）...
echo.
set /p backup="是否需要备份数据库？(y/n): "
if /i "%backup%"=="y" (
    echo 请手动执行以下命令备份数据库：
    echo mysqldump -u root -p lyadmin_db ^> backup_before_license_update.sql
    echo.
    pause
)

echo.
echo [步骤 2/6] 删除旧的迁移文件...
del apps\lylicense\migrations\0*.py 2>nul
if %errorlevel%==0 (
    echo ✓ 旧迁移文件已删除
) else (
    echo - 没有找到旧迁移文件
)

echo.
echo [步骤 3/6] 生成新的迁移文件...
python manage.py makemigrations lylicense
if %errorlevel% neq 0 (
    echo [错误] 迁移文件生成失败
    pause
    exit /b 1
)
echo ✓ 迁移文件生成成功

echo.
echo [步骤 4/6] 执行数据库迁移...
python manage.py migrate lylicense
if %errorlevel% neq 0 (
    echo [错误] 数据库迁移失败
    pause
    exit /b 1
)
echo ✓ 数据库迁移成功

echo.
echo [步骤 5/6] 初始化目录和示例数据...
python init_license_data.py
if %errorlevel% neq 0 (
    echo [警告] 初始化脚本执行失败，但不影响使用
)

echo.
echo [步骤 6/6] 初始化菜单权限...
python add_license_menu_permissions.py
if %errorlevel% neq 0 (
    echo [警告] 权限初始化失败，请手动配置
)

echo.
echo ╔═══════════════════════════════════════════════════════════╗
echo ║                    部署完成！                              ║
echo ╚═══════════════════════════════════════════════════════════╝
echo.
echo 下一步操作：
echo 1. 启动Django服务: python manage.py runserver
echo 2. 访问前端页面进行测试
echo 3. 查看文档: LICENSE_UPDATE_GUIDE.md
echo.
echo 注意事项：
echo - 确保FlexNet命令或Bitanswer API已配置
echo - JSON文件放在 license_data/ 目录下
echo - 查看日志文件 logs/server.log 获取详细信息
echo.
pause
