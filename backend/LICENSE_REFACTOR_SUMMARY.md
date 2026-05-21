# License系统重构总结

## 📊 变更概览

本次重构移除了领导审批流程，专注于JSON文件解析和License自动化制作。

---

## 🗂️ 后端变更

### 1. 数据模型 (`models.py`)

#### LicenseApplication（申请表）- 简化

**删除的字段：**
- ❌ `category` - 申请类别
- ❌ `it_json_data` - IT审核通过的JSON数据
- ❌ `it_confirm_time` - IT确认时间
- ❌ `it_confirmer` - IT确认人
- ❌ `license_file_path` - License文件路径
- ❌ `generate_result` - 生成结果

**新增/修改的字段：**
- ✅ `json_data` - JSON原始数据（替代it_json_data）
- ✅ 状态简化为4种：待制作(0)、制作中(1)、制作成功(2)、制作失败(3)

#### LicenseRecord（License记录表）- 新建

**包含字段：**
- `license_id` - License ID（唯一标识）
- `license_type` - 类型（FlexNet/Bitanswer）
- `file_name` - 文件名称
- `file_relative_path` - 文件相对路径
- `directory` - 目录
- `full_path` - 完整路径
- `feature` - Feature
- `vendor` - Vendor
- `version` - Version
- `host_id` - HostID
- `start_time` - 开始时间
- `end_time` - 过期时间
- `remaining_days` - 剩余天数（自动计算）
- `quantity` - 授权数量
- `status` - 状态（有效/已过期/已撤销）
- `extra_info` - 额外信息

**特性：**
- 保存时自动计算剩余天数
- 与申请表通过外键关联

#### 删除的模型：
- ❌ `LicenseGenerationLog` - 生成记录表
- ❌ `LicenseApprovalLog` - 审批记录表

---

### 2. 序列化器 (`serializers.py`)

**简化的序列化器：**
- ✅ `LicenseApplicationSerializer` - 申请序列化器
- ✅ `LicenseApplicationCreateSerializer` - 创建序列化器
- ✅ `LicenseRecordSerializer` - License记录序列化器（新增）

**删除的序列化器：**
- ❌ `LicenseApprovalSerializer`
- ❌ `LicenseITConfirmSerializer`
- ❌ `LicenseGenerationLogSerializer`
- ❌ `LicenseApprovalLogSerializer`

---

### 3. 视图层 (`views.py`)

#### LicenseApplicationViewSet

**主要方法：**

1. **parse_and_generate** (核心方法)
   ```python
   POST /api/license/application/{id}/parse_and_generate/
   ```
   - 从 `license_data/{id}.json` 读取JSON文件
   - 解析JSON数据并更新到数据库
   - 根据类型调用不同的生成方法
   - 成功后创建LicenseRecord记录

2. **retry**
   ```python
   POST /api/license/application/{id}/retry/
   ```
   - 重置状态为"待制作"
   - 清空失败原因
   - 增加重试次数

3. **_generate_flexnet_license**
   - 执行 `os.system('flexnet {license_file}')`
   - 返回0表示成功
   - 记录文件路径和信息

4. **_generate_bitanswer_license**
   - 从JSON提取参数
   - 调用Bitanswer API
   - 保存API返回的license内容

#### LicenseRecordViewSet (新增)

**主要方法：**

1. **列表查询**
   ```python
   GET /api/license/record/
   ```
   - 支持筛选：license_type, status, host_id, vendor
   - 支持搜索：license_id, feature, vendor, host_id, file_name

2. **statistics** (统计接口)
   ```python
   GET /api/license/record/statistics/
   ```
   - 按类型统计
   - 按状态统计
   - 即将过期数量（<=30天）
   - 已过期数量
   - 总数

---

### 4. 路由配置 (`urls.py`)

```python
router.register('application', LicenseApplicationViewSet)
router.register('record', LicenseRecordViewSet)  # 新增
```

**删除的路由：**
- ❌ `generation-log`
- ❌ `approval-log`

---

## 🎨 前端变更

### 1. licenseManage.vue（申请管理页面）

**主要变更：**

#### 搜索条件
- 移除：类别（category）
- 保留：申请人、License类型、客户名称、状态

#### 表格列
- 移除：类别列
- 修改：MAC Address → MAC Address/HostID
- 修改：申请数量 → 授权数量
- 修改：状态显示（4种新状态）

#### 操作按钮
- 移除：审批按钮
- 新增：制作License按钮（状态为待制作或失败时显示）
- 新增：重试按钮（状态为失败时显示）
- 保留：详情、删除

#### 功能实现
- ✅ 对接真实API获取数据
- ✅ 制作License功能（调用parse_and_generate）
- ✅ 重试功能（调用retry）
- ✅ 详情查看（对话框展示）
- ✅ 删除功能

---

### 2. licenseRecord.vue（License记录页面）- 新建

**功能模块：**

#### 统计卡片
- 总数
- 有效数量
- 即将过期（<=30天）
- 已过期

#### 搜索条件
- License ID
- 类型（FlexNet/Bitanswer）
- Vendor
- HostID
- 状态（有效/已过期/已撤销）

#### 表格列
- License ID
- 类型
- 文件名称
- Feature
- Vendor
- Version
- HostID
- 授权数量
- 开始时间
- 过期时间
- 剩余天数（颜色标签区分）
- 状态
- 申请人
- 客户名称

#### 操作按钮
- 详情
- 下载（待实现）

#### 详情对话框
- 展示完整的License信息
- 包括文件路径、时间信息等

---

## 📁 文件清单

### 后端文件

| 文件 | 状态 | 说明 |
|------|------|------|
| `apps/lylicense/models.py` | ✅ 修改 | 简化申请模型，新增LicenseRecord模型 |
| `apps/lylicense/serializers.py` | ✅ 重写 | 简化序列化器 |
| `apps/lylicense/views.py` | ✅ 重写 | 新增parse_and_generate方法，新增LicenseRecordViewSet |
| `apps/lylicense/urls.py` | ✅ 修改 | 更新路由配置 |
| `init_license_data.py` | ✅ 保留 | 初始化脚本 |
| `add_license_menu_permissions.py` | ⚠️ 需更新 | 需要更新权限配置 |
| `test_license_generation.py` | ✅ 保留 | 测试脚本 |
| `LICENSE_UPDATE_GUIDE.md` | ✅ 新增 | 更新指南文档 |
| `README_LICENSE.md` | ✅ 保留 | 技术文档 |
| `QUICK_START_LICENSE.md` | ✅ 保留 | 快速部署指南 |

### 前端文件

| 文件 | 状态 | 说明 |
|------|------|------|
| `src/views/licenseManage/licenseManage.vue` | ✅ 重写 | 申请管理页面，对接真实API |
| `src/views/licenseManage/licenseRecord.vue` | ✅ 新增 | License记录列表页面 |

---

## 🔄 业务流程对比

### 旧流程（含审批）

```
1. 申请人提交申请
   ↓
2. 领导审批（通过/拒绝）
   ↓
3. IT确认，上传JSON数据
   ↓
4. 生成License
   ↓
5. 记录生成日志
   ↓
6. 邮件通知
```

### 新流程（无审批）

```
1. 放置JSON文件到 license_data/{id}.json
   ↓
2. 点击"制作License"按钮
   ↓
3. 系统读取并解析JSON
   ↓
4. 根据类型生成License：
   ├─ FlexNet: os.system('flexnet {file}')
   └─ Bitanswer: 调用API
   ↓
5. 创建LicenseRecord记录
   ↓
6. 更新申请状态为"制作成功"
```

---

## 📊 数据库迁移

### 迁移步骤

```bash
# 1. 删除旧迁移文件
del apps\lylicense\migrations\0*.py

# 2. 重新生成迁移
python manage.py makemigrations lylicense

# 3. 执行迁移
python manage.py migrate lylicense
```

### 迁移效果

**删除的表：**
- `lylicense_generation_log`
- `lylicense_approval_log`

**创建的表：**
- `lylicense_application`（新结构）
- `lylicense_record`（新表）

---

## 🔑 关键特性

### 1. 自动化程度提升
- 无需人工审批
- JSON文件自动解析
- License自动生成
- 记录自动创建

### 2. 数据结构优化
- 申请表更简洁
- License记录更详细
- 支持剩余天数自动计算
- 完整的路径信息存储

### 3. 用户体验改进
- 一键制作License
- 实时状态反馈
- 详细的统计信息
- 清晰的剩余天数展示

### 4. 可维护性增强
- 代码更简洁
- 逻辑更清晰
- 易于扩展
- 完善的日志记录

---

## ⚙️ 配置要点

### FlexNet配置
```python
# views.py 第157行左右
cmd = f'flexnet {license_file}'
# 如需绝对路径：
# cmd = f'C:\\path\\to\\flexnet.exe {license_file}'
```

### Bitanswer配置
```python
# views.py 第203-204行左右
bitanswer_api_url = 'http://your-bitanswer-server/api/generate-license'
bitanswer_api_key = 'your-actual-api-key'
```

---

## 📝 使用示例

### 制作FlexNet License

1. 创建JSON文件 `license_data/1.json`
2. 在前端找到对应的申请记录
3. 点击"制作License"按钮
4. 系统执行 `flexnet 1_flex.lic`
5. 成功后在License记录页面查看

### 制作Bitanswer License

1. 创建JSON文件 `license_data/2.json`
2. 配置好Bitanswer API地址和密钥
3. 在前端点击"制作License"按钮
4. 系统调用API并保存返回的license
5. 在License记录页面查看

---

## 🎯 后续优化建议

1. **邮件通知**：实现制作完成后的邮件通知
2. **下载功能**：实现License文件下载
3. **批量制作**：支持批量选择多个申请一起制作
4. **定时检查**：定期检查License过期情况
5. **续期功能**：支持License续期操作
6. **撤销功能**：支持撤销已制作的License
7. **导入导出**：支持JSON文件批量导入和License记录导出

---

## ✅ 验证清单

部署后请验证：

- [ ] 数据库迁移成功
- [ ] 旧表已删除
- [ ] 新表结构正确
- [ ] 目录结构已创建
- [ ] 示例JSON文件存在
- [ ] Django服务正常
- [ ] 前端页面可访问
- [ ] 申请列表正常显示
- [ ] 可以制作License
- [ ] License记录正常显示
- [ ] 统计信息正确
- [ ] 详情查看正常
- [ ] 重试功能正常

---

**重构完成日期**: 2026-05-15  
**版本**: v2.0  
**主要改进**: 去除审批流程，简化License制作，新增License记录管理
