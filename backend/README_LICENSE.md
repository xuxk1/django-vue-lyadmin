# License授权管理系统 - 部署说明

## 📋 目录结构

```
backend/
├── apps/lylicense/          # License管理应用
│   ├── models.py            # 数据模型
│   ├── serializers.py       # 序列化器
│   ├── views.py             # 视图层（核心业务逻辑）
│   ├── urls.py              # 路由配置
│   └── migrations/          # 数据库迁移文件
├── license_data/            # JSON数据存放目录（自动生成）
│   ├── {id}.json           # 每个申请的JSON文件
│   └── ...
├── media/license/           # License文件存储目录（自动生成）
│   ├── flexnet/            # FlexNet生成的License文件
│   │   └── {id}_flex.lic
│   └── bitanswer/          # Bitanswer生成的License文件
│       └── {id}_bit.lic
├── init_license_data.py     # 初始化脚本
├── add_license_menu_permissions.py  # 菜单权限初始化脚本
└── README_LICENSE.md        # 本文件
```

## 🚀 快速开始

### 1. 初始化数据目录

```bash
cd d:\eladmin\django-vue-lyadmin\backend
python init_license_data.py
```

这将自动创建：
- `license_data/` - JSON数据存放目录
- `media/license/flexnet/` - FlexNet License存储目录
- `media/license/bitanswer/` - Bitanswer License存储目录
- 示例JSON文件用于测试

### 2. 执行数据库迁移

```bash
python manage.py makemigrations lylicense
python manage.py migrate lylicense
```

### 3. 初始化菜单权限

```bash
python add_license_menu_permissions.py
```

### 4. 启动Django服务

```bash
python manage.py runserver
```

## 📝 JSON数据格式

### FlexNet类型示例 (`license_data/1.json`)

```json
{
  "id": 1,
  "customer_name": "客户A公司",
  "mac_address": "00:11:22:33:44:55",
  "feature": "FlexNet基础功能包",
  "start_time": "2026-01-01 00:00:00",
  "end_time": "2027-12-31 23:59:59",
  "quantity": 5,
  "license_type": "flexnet",
  "product_id": "FN-2026-001",
  "version": "1.0",
  "notes": "备注信息"
}
```

### Bitanswer类型示例 (`license_data/2.json`)

```json
{
  "id": 2,
  "customer_name": "客户B公司",
  "mac_address": "AA:BB:CC:DD:EE:FF",
  "feature": "Bitanswer高级功能包",
  "start_time": "2026-01-01 00:00:00",
  "end_time": "2026-12-31 23:59:59",
  "quantity": 10,
  "license_type": "bitanswer",
  "api_key": "ba-api-key-12345",
  "module_ids": ["MOD001", "MOD002", "MOD003"],
  "notes": "备注信息"
}
```

## 🔄 License生成流程

### 完整流程图

```
1. 申请人提交申请
   ↓
2. 领导审批（通过/拒绝）
   ↓
3. IT确认，上传JSON数据到 license_data/{id}.json
   ↓
4. 调用生成License接口
   ↓
5. 系统读取JSON文件并解析
   ↓
6. 根据application_type选择生成方式：
   ├─ FlexNet: 执行 os.system('flexnet {license_file}')
   └─ Bitanswer: 调用API生成License
   ↓
7. 保存License文件到对应目录
   ↓
8. 更新状态为"已完成"或"生成失败"
   ↓
9. 记录生成日志
   ↓
10. （TODO）发送邮件通知申请人
```

## 🔧 配置说明

### FlexNet配置

在 `views.py` 的 `_generate_flexnet_license` 方法中：

```python
# 确保flexnet命令在系统PATH中，或使用绝对路径
cmd = f'flexnet {license_file}'

# 如果需要指定flexnet的完整路径：
# cmd = f'C:\\path\\to\\flexnet.exe {license_file}'
```

**要求：**
- `flexnet` 命令必须在系统PATH中可访问
- 或者使用绝对路径指向flexnet可执行文件
- 命令执行成功返回0表示License生成成功

### Bitanswer配置

在 `views.py` 的 `_generate_bitanswer_license` 方法中修改以下配置：

```python
# Bitanswer API配置
bitanswer_api_url = 'http://your-bitanswer-server/api/generate-license'
bitanswer_api_key = 'your-actual-api-key'
```

**需要调整的内容：**
1. `bitanswer_api_url` - 替换为实际的Bitanswer API地址
2. `bitanswer_api_key` - 替换为实际的API密钥
3. `params` 字典中的字段 - 根据实际API要求的参数进行调整
4. `result_data.get('license_content')` - 根据API返回的实际字段名调整

## 📊 状态流转

| 状态值 | 状态名称 | 说明 |
|--------|---------|------|
| 0 | 待审批 | 申请刚提交，等待领导审批 |
| 1 | 审批通过 | 领导已批准 |
| 2 | 审批拒绝 | 领导已拒绝 |
| 3 | IT确认中 | IT已确认JSON数据，准备生成 |
| 4 | 生成中 | License正在生成 |
| 5 | 已完成 | License生成成功 |
| 6 | 生成失败 | License生成失败，可查看失败原因 |

## 🔌 API接口说明

### 1. 领导审批
```
POST /api/license/application/{id}/approval/
Body: {
    "status": 1,  // 1-通过, 2-拒绝
    "approval_comment": "审批意见"
}
```

### 2. IT确认
```
POST /api/license/application/{id}/it_confirm/
Body: {
    "it_json_data": {...}  // JSON数据
}
```

### 3. 生成License
```
POST /api/license/application/{id}/generate_license/
// 无需参数，系统会自动从 license_data/{id}.json 读取
```

### 4. 重试生成
```
POST /api/license/application/{id}/retry/
// 重新尝试生成失败的License
```

## 🛠️ 常见问题

### Q1: JSON文件应该放在哪里？
A: 放在 `backend/license_data/` 目录下，文件名格式为 `{申请ID}.json`

### Q2: 如何知道申请ID是多少？
A: 
- 在前端页面查看申请列表，每条记录都有ID
- 或者在数据库中查询 `lylicense_application` 表

### Q3: FlexNet命令找不到怎么办？
A: 
- 确保flexnet命令已安装并在系统PATH中
- 或者在代码中使用绝对路径：`cmd = f'C:\\path\\to\\flexnet.exe {license_file}'`

### Q4: Bitanswer API调用失败怎么办？
A: 
- 检查 `bitanswer_api_url` 是否正确
- 检查 `bitanswer_api_key` 是否有效
- 查看日志文件 `logs/server.log` 获取详细错误信息
- 确认API返回的数据格式与代码中的解析逻辑匹配

### Q5: License文件保存在哪里？
A: 
- FlexNet: `media/license/flexnet/{id}_flex.lic`
- Bitanswer: `media/license/bitanswer/{id}_bit.lic`

## 📧 邮件通知（待实现）

当前代码中预留了邮件通知功能的位置：

```python
# TODO: 发送邮件通知申请人
self._send_email_notification(instance, 'success')
```

如需实现，可以在 `views.py` 中完善 `_send_email_notification` 方法。

## 📝 日志查看

所有操作都会记录在日志文件中：
- 主日志：`logs/server.log`
- 错误日志：`logs/error.log`

可以通过日志查看License生成的详细信息和错误信息。

## 🔐 权限说明

系统包含以下权限按钮：
- **查询** (Search) - 查看申请列表
- **新增** (Create) - 创建新申请
- **编辑** (Update) - 修改申请信息
- **删除** (Delete) - 删除申请
- **审批** (Approval) - 领导审批
- **IT确认** (Itconfirm) - IT确认JSON数据
- **生成License** (Generate) - 触发License生成
- **重试** (Retry) - 重试失败的生成
- **详情** (Detail) - 查看详情
- **导出** (Export) - 导出数据

需要在后台为用户角色分配相应权限。

## 💡 最佳实践

1. **JSON数据规范**：确保JSON文件格式正确，编码为UTF-8
2. **定期备份**：定期备份 `license_data/` 和 `media/license/` 目录
3. **监控日志**：定期检查日志文件，及时发现和处理问题
4. **测试环境验证**：在生产环境使用前，先在测试环境充分验证
5. **权限控制**：严格控制审批和生成权限，避免误操作

## 🆘 技术支持

如遇到问题，请检查：
1. 数据库迁移是否成功执行
2. 目录权限是否正确设置
3. 日志文件中的错误信息
4. JSON文件格式是否正确
5. FlexNet命令或Bitanswer API是否可正常访问

---

**最后更新**: 2026-05-15
