# License授权管理系统 - 更新说明

## 📋 重要变更

### 1. 数据库模型重构

**删除的表：**
- ❌ `lylicense_generation_log` - License生成记录表（已移除）
- ❌ `lylicense_approval_log` - License审批记录表（已移除）

**新增的表：**
- ✅ `lylicense_record` - License制作记录表（新表）

**修改的表：**
- ✅ `lylicense_application` - License申请表（简化字段，去除审批相关）

### 2. 状态变更

**申请状态（LicenseApplication）：**
```
旧状态:
0 - 待审批
1 - 审批通过
2 - 审批拒绝
3 - IT确认中
4 - 生成中
5 - 已完成
6 - 生成失败

新状态:
0 - 待制作
1 - 制作中
2 - 制作成功
3 - 制作失败
```

**License记录状态（LicenseRecord）：**
```
0 - 有效
1 - 已过期
2 - 已撤销
```

### 3. 业务流程变更

**旧流程（含审批）：**
```
申请人提交 → 领导审批 → IT确认 → 生成License
```

**新流程（无审批）：**
```
放置JSON文件 → 解析并制作License → 保存License记录
```

---

## 🚀 部署步骤

### 第1步：备份数据（如果有旧数据）

```bash
# 备份数据库
mysqldump -u root -p lyadmin_db > backup_before_license_update.sql
```

### 第2步：删除旧的迁移文件

```bash
cd d:\eladmin\django-vue-lyadmin\backend

# 删除lylicense应用的旧迁移文件
del apps\lylicense\migrations\0*.py
```

### 第3步：重新生成迁移文件

```bash
python manage.py makemigrations lylicense
```

应该看到类似输出：
```
Migrations for 'lylicense':
  apps\lylicense\migrations\0001_initial.py
    - Create model LicenseApplication
    - Create model LicenseRecord
```

### 第4步：执行数据库迁移

```bash
python manage.py migrate lylicense
```

这将创建新的表结构。

### 第5步：初始化目录和示例数据

```bash
python init_license_data.py
```

### 第6步：初始化菜单权限

```bash
python add_license_menu_permissions.py
```

**注意：** 需要更新权限配置，因为API路径可能发生变化。

### 第7步：重启Django服务

```bash
python manage.py runserver
```

---

## 📁 新的数据库表结构

### LicenseApplication（申请表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| applicant | CharField | 申请人 |
| applicant_id | CharField | 申请人ID |
| application_type | CharField | License类型（flexnet/bitanswer） |
| feature | CharField | Feature |
| customer_name | CharField | 客户名称 |
| mac_address | CharField | MAC Address/HostID |
| start_time | DateTimeField | 开始时间 |
| end_time | DateTimeField | 结束时间 |
| quantity | IntegerField | 授权数量 |
| json_data | JSONField | JSON原始数据 |
| status | IntegerField | 状态（0待制作/1制作中/2成功/3失败） |
| fail_reason | TextField | 失败原因 |
| retry_count | IntegerField | 重试次数 |
| create_datetime | DateTimeField | 创建时间 |
| update_datetime | DateTimeField | 更新时间 |

### LicenseRecord（License记录表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| application | ForeignKey | 关联申请 |
| license_id | CharField | License ID（唯一） |
| license_type | CharField | 类型（flexnet/bitanswer） |
| file_name | CharField | 文件名称 |
| file_relative_path | CharField | 文件相对路径 |
| directory | CharField | 目录 |
| full_path | CharField | 完整路径 |
| feature | CharField | Feature |
| vendor | CharField | Vendor |
| version | CharField | Version |
| host_id | CharField | HostID |
| start_time | DateTimeField | 开始时间 |
| end_time | DateTimeField | 过期时间 |
| remaining_days | IntegerField | 剩余天数（自动计算） |
| quantity | IntegerField | 授权数量 |
| status | IntegerField | 状态（0有效/1已过期/2已撤销） |
| extra_info | JSONField | 额外信息 |
| create_datetime | DateTimeField | 创建时间 |
| update_datetime | DateTimeField | 更新时间 |

---

## 🔌 API接口变更

### 申请管理接口

#### 1. 获取申请列表
```
GET /api/license/application/
Query Params: page, limit, applicant, application_type, customer_name, status
```

#### 2. 创建申请
```
POST /api/license/application/
Body: {
    "applicant": "张三",
    "application_type": "flexnet",
    "feature": "基础功能",
    "customer_name": "ABC公司",
    "mac_address": "00:11:22:33:44:55",
    "start_time": "2026-01-01 00:00:00",
    "end_time": "2026-12-31 23:59:59",
    "quantity": 10
}
```

#### 3. 解析JSON并制作License
```
POST /api/license/application/{id}/parse_and_generate/
// 无需参数，系统自动从 license_data/{id}.json 读取
```

**返回示例：**
```json
{
    "code": 2000,
    "msg": "License制作成功",
    "data": {
        "application_id": 1,
        "license_id": "FN-1",
        "result": {
            "success": true,
            "file_name": "1_flex.lic",
            "file_relative_path": "license/flexnet/1_flex.lic",
            "directory": "D:\\...\\media\\license\\flexnet",
            "full_path": "D:\\...\\media\\license\\flexnet\\1_flex.lic",
            "vendor": "FlexNet",
            "version": "1.0",
            "license_id": "FN-1",
            "message": "FlexNet License制作成功"
        }
    }
}
```

#### 4. 重试制作
```
POST /api/license/application/{id}/retry/
```

### License记录接口

#### 1. 获取License记录列表
```
GET /api/license/record/
Query Params: page, limit, license_id, license_type, vendor, host_id, status
```

**返回示例：**
```json
{
    "code": 2000,
    "data": {
        "page": 1,
        "limit": 10,
        "total": 5,
        "data": [
            {
                "id": "uuid...",
                "license_id": "FN-1",
                "license_type": "flexnet",
                "license_type_display": "FlexNet",
                "file_name": "1_flex.lic",
                "file_relative_path": "license/flexnet/1_flex.lic",
                "directory": "D:\\...\\media\\license\\flexnet",
                "full_path": "D:\\...\\media\\license\\flexnet\\1_flex.lic",
                "feature": "基础功能",
                "vendor": "FlexNet",
                "version": "1.0",
                "host_id": "00:11:22:33:44:55",
                "start_time": "2026-01-01 00:00:00",
                "end_time": "2026-12-31 23:59:59",
                "remaining_days": 230,
                "quantity": 10,
                "status": 0,
                "status_display": "有效",
                "applicant": "张三",
                "customer_name": "ABC公司",
                "create_datetime": "2026-05-15 10:00:00"
            }
        ]
    }
}
```

#### 2. 获取统计信息
```
GET /api/license/record/statistics/
```

**返回示例：**
```json
{
    "code": 2000,
    "data": {
        "type_stats": [
            {"license_type": "flexnet", "count": 3},
            {"license_type": "bitanswer", "count": 2}
        ],
        "status_stats": [
            {"status": 0, "count": 4},
            {"status": 1, "count": 1}
        ],
        "expiring_soon": 2,
        "expired": 1,
        "total": 5
    }
}
```

---

## 🎨 前端页面

### 1. License申请管理页面
**路径：** `/src/views/licenseManage/licenseManage.vue`

**功能：**
- ✅ 显示申请列表
- ✅ 筛选查询（申请人、类型、客户、状态）
- ✅ 制作License按钮（调用parse_and_generate接口）
- ✅ 重试按钮（制作失败后可用）
- ✅ 查看详情
- ✅ 删除申请

**主要操作：**
- 点击"制作License"：系统读取JSON文件，解析数据，生成License
- 点击"重试"：重置状态为"待制作"，可以重新制作

### 2. License记录列表页面（新增）
**路径：** `/src/views/licenseManage/licenseRecord.vue`

**功能：**
- ✅ 统计卡片（总数、有效、即将过期、已过期）
- ✅ 显示License记录列表
- ✅ 筛选查询（License ID、类型、Vendor、HostID、状态）
- ✅ 剩余天数显示（颜色区分）
- ✅ 查看详情
- ✅ 下载License文件（待实现）

**统计信息：**
- 总数：所有License数量
- 有效：状态为"有效"的数量
- 即将过期：剩余天数<=30天的数量
- 已过期：已过期的数量

---

## 📝 JSON文件格式

### FlexNet示例 (`license_data/1.json`)
```json
{
  "id": 1,
  "customer_name": "ABC公司",
  "mac_address": "00:11:22:33:44:55",
  "feature": "基础功能模块",
  "start_time": "2026-01-01 00:00:00",
  "end_time": "2026-12-31 23:59:59",
  "quantity": 10,
  "license_type": "flexnet",
  "product_id": "FN-2026-001",
  "version": "1.0",
  "notes": "备注信息"
}
```

### Bitanswer示例 (`license_data/2.json`)
```json
{
  "id": 2,
  "customer_name": "XYZ公司",
  "mac_address": "AA:BB:CC:DD:EE:FF",
  "feature": "高级功能包",
  "start_time": "2026-01-01 00:00:00",
  "end_time": "2026-12-31 23:59:59",
  "quantity": 5,
  "license_type": "bitanswer",
  "api_key": "ba-api-key-12345",
  "module_ids": ["MOD001", "MOD002"],
  "notes": "备注信息"
}
```

---

## ⚙️ 配置说明

### FlexNet配置

在 `views.py` 的 `_generate_flexnet_license` 方法中：

```python
# 确保flexnet命令可用
cmd = f'flexnet {license_file}'

# 如需指定完整路径：
# cmd = f'C:\\path\\to\\flexnet.exe {license_file}'
```

### Bitanswer API配置

在 `views.py` 的 `_generate_bitanswer_license` 方法中：

```python
# 替换为实际的API地址
bitanswer_api_url = 'http://your-bitanswer-server/api/generate-license'

# 替换为实际的API密钥
bitanswer_api_key = 'your-actual-api-key'
```

---

## 🔄 迁移注意事项

### 如果有旧数据

1. **备份数据库**
2. **导出旧数据**（如果需要保留）
3. **执行迁移**（会删除旧表，创建新表）
4. **手动迁移数据**（如果必要）

### 如果没有旧数据

直接执行迁移即可，不会有任何问题。

---

## ✅ 验证清单

部署完成后，请验证以下内容：

- [ ] 数据库表已正确创建（`lylicense_application`, `lylicense_record`）
- [ ] 旧表已删除（`lylicense_generation_log`, `lylicense_approval_log`）
- [ ] 目录结构已创建（`license_data/`, `media/license/flexnet/`, `media/license/bitanswer/`）
- [ ] 示例JSON文件已生成
- [ ] Django服务正常启动
- [ ] 前端页面可以访问
- [ ] 可以申请列表查询
- [ ] 可以制作License（FlexNet或Bitanswer）
- [ ] License记录列表正常显示
- [ ] 统计信息正确显示
- [ ] 详情查看功能正常

---

## 🆘 常见问题

### Q1: 迁移时提示表已存在
**解决：** 删除旧的迁移文件后重新生成

### Q2: 前端页面报错404
**解决：** 检查路由配置，确保后端URL正确

### Q3: 制作License时提示JSON文件不存在
**解决：** 确保JSON文件放在 `backend/license_data/{id}.json`

### Q4: FlexNet命令找不到
**解决：** 确认flexnet命令在PATH中，或使用绝对路径

### Q5: Bitanswer API调用失败
**解决：** 检查API地址和密钥配置，查看日志获取详细错误

---

## 📞 技术支持

如遇问题，请检查：
1. 日志文件：`logs/server.log` 和 `logs/error.log`
2. 浏览器控制台错误信息
3. 数据库表结构是否正确
4. JSON文件格式是否正确

---

**更新日期**: 2026-05-15  
**版本**: v2.0（去除审批流程，简化License制作）
