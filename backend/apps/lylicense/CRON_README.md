# License 过期检查定时任务使用说明

## 概述

本功能使用 `django-crontab` 实现每天自动检查 License 过期状态并发送邮件提醒。

## 功能特性

- ✅ **自动更新过期状态**：将已过期的 License 从"有效"更新为"已过期"
- ✅ **邮件提醒机制**：
  - 30天提醒（剩余天数在15-30天范围内）
  - 15天提醒（剩余天数在7-15天范围内）
  - 7天提醒（剩余天数在0-7天范围内）
  - 过期提醒（License已过期时立即发送）
- ✅ **防重复发送**：每个提醒阶段只发送一次，避免骚扰用户
- ✅ **支持产品组**：自动识别单产品和多产品场景
- ✅ **详细日志记录**：所有操作都有日志记录，方便排查问题

## 安装步骤

### 1. 安装依赖

```bash
cd D:\eladmin\django-vue-lyadmin\backend
pip install django-crontab
```

### 2. 配置定时任务

已在 `application/settings.py` 中配置完成：

```python
CRONJOBS = [
    # 每天凌晨2点执行License过期检查和邮件提醒
    ('0 2 * * *', 'apps.lylicense.management.commands.check_license_expiration.Command', ''),
]
```

### 3. 注册定时任务到系统

#### Windows 环境

```bash
# 添加定时任务到系统计划任务
python manage.py crontab add

# 查看已注册的定时任务
python manage.py crontab show

# 删除所有定时任务
python manage.py crontab remove
```

#### Linux/Mac 环境

```bash
# 添加定时任务到 cron
python manage.py crontab add

# 查看已注册的定时任务
python manage.py crontab show

# 删除所有定时任务
python manage.py crontab remove
```

### 4. 验证定时任务

#### 方法1：手动执行命令测试

```bash
python manage.py check_license_expiration
```

#### 方法2：强制重新发送所有提醒（测试用）

```bash
python manage.py check_license_expiration --force
```

#### 方法3：查看定时任务日志

**Windows**: 查看 `D:\eladmin\django-vue-lyadmin\backend\logs\` 目录下的日志文件

**Linux/Mac**: 查看 `/var/log/license_check.log` 文件

## 修改执行时间

如果需要修改定时任务的执行时间，编辑 `application/settings.py` 中的 `CRONJOBS` 配置：

```python
CRONJOBS = [
    # 格式: '分 时 日 月 周'  命令路径  参数  日志重定向
    
    # 每天凌晨2点执行
    ('0 2 * * *', 'apps.lylicense.management.commands.check_license_expiration.Command', ''),
    
    # 每天早上8点执行
    # ('0 8 * * *', 'apps.lylicense.management.commands.check_license_expiration.Command', ''),
    
    # 每6小时执行一次
    # ('0 */6 * * *', 'apps.lylicense.management.commands.check_license_expiration.Command', ''),
    
    # 每小时执行一次（开发测试用）
    # ('0 * * * *', 'apps.lylicense.management.commands.check_license_expiration.Command', ''),
]
```

修改后需要重新注册：

```bash
python manage.py crontab remove
python manage.py crontab add
```

## Cron 表达式说明

```
* * * * *  command_to_execute
│ │ │ │ │
│ │ │ │ └─ 星期几 (0-7, 0和7都代表周日)
│ │ │ └─── 月份 (1-12)
│ │ ───── 日期 (1-31)
│ └─────── 小时 (0-23)
└───────── 分钟 (0-59)
```

常用示例：
- `0 2 * * *` - 每天凌晨2点
- `0 8,14,20 * * *` - 每天8点、14点、20点
- `0 */6 * * *` - 每6小时
- `0 0 * * 0` - 每周日凌晨
- `0 0 1 * *` - 每月1号凌晨

## 常见问题

### Q1: 定时任务没有执行？

**A**: 检查以下几点：
1. 确认已执行 `python manage.py crontab add`
2. 查看系统计划任务/cron 是否已注册
3. 查看日志文件是否有错误信息
4. 手动执行命令测试是否正常

### Q2: 邮件没有发送？

**A**: 检查以下几点：
1. 查看日志中是否有"发现 X 条需要在X天提醒的 License 记录"
2. 确认 `applicant_id` 字段不为空
3. 确认邮箱配置正确（`config.py` 中的邮件相关配置）
4. 检查是否已经发送过提醒（防重复机制）

### Q3: 如何测试定时任务？

**A**: 使用以下命令手动执行：

```bash
# 正常模式（遵循防重复规则）
python manage.py check_license_expiration

# 强制模式（忽略防重复规则，重新发送所有提醒）
python manage.py check_license_expiration --force
```

### Q4: Windows 下定时任务不生效？

**A**: Windows 需要使用任务计划程序。可以：
1. 使用 `schtasks` 命令创建 Windows 计划任务
2. 或者使用第三方工具如 WinCron
3. 推荐使用 Linux/Mac 服务器部署生产环境

## 监控和维护

### 查看执行历史

```bash
# Linux/Mac
tail -f /var/log/license_check.log

# Windows
type D:\eladmin\django-vue-lyadmin\backend\logs\server.log | findstr "License"
```

### 清理旧的定时任务

```bash
python manage.py crontab remove
```

### 更新定时任务配置

```bash
# 1. 修改 settings.py 中的 CRONJOBS
# 2. 重新注册
python manage.py crontab remove
python manage.py crontab add
```

## 注意事项

️ **重要提示**：

1. **生产环境建议使用 Linux 服务器**，Windows 的计划任务管理相对复杂
2. **确保 Redis 服务正常运行**，邮件队列依赖 Redis
3. **定期检查日志文件**，确保定时任务正常执行
4. **测试环境可以先设置为每小时执行**，验证功能正常后再改为每天执行
5. **邮件发送失败不会影响任务继续执行**，失败的记录会记录在日志中

## 技术支持

如有问题，请查看：
- Django-Crontab 官方文档：https://github.com/kraiz/django-crontab
- 项目日志文件：`logs/server.log` 和 `logs/error.log`
