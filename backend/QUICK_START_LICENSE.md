# License授权管理系统 - 快速部署指南

## 📦 一键部署步骤

### 第1步：初始化目录和示例数据
```bash
cd d:\eladmin\django-vue-lyadmin\backend
python init_license_data.py
```

### 第2步：执行数据库迁移
```bash
python manage.py makemigrations lylicense
python manage.py migrate lylicense
```

### 第3步：初始化菜单权限
```bash
python add_license_menu_permissions.py
```

### 第4步：测试系统（可选）
```bash
python test_license_generation.py
```

### 第5步：启动服务
```bash
python manage.py runserver
```

---

## 🔧 重要配置

### 1. FlexNet命令配置

**位置**: `apps/lylicense/views.py` 第197行左右

确保系统中已安装flexnet命令，或在代码中指定完整路径：

```python
# 当前配置（假设flexnet在PATH中）
cmd = f'flexnet {license_file}'

# 如果需要指定完整路径，修改为：
# cmd = f'C:\\Program Files\\FlexNet\\flexnet.exe {license_file}'
```

### 2. Bitanswer API配置

**位置**: `apps/lylicense/views.py` 第240行左右

需要修改以下两个配置项：

```python
# 替换为实际的Bitanswer API地址
bitanswer_api_url = 'http://your-bitanswer-server/api/generate-license'

# 替换为实际的API密钥
bitanswer_api_key = 'your-actual-api-key'
```

**根据实际API调整参数**（第226-233行）：
```python
params = {
    'customer_name': json_data.get('customer_name', instance.customer_name),
    'mac_address': json_data.get('mac_address', instance.mac_address),
    'feature': json_data.get('feature', instance.feature),
    'start_time': json_data.get('start_time'),
    'end_time': json_data.get('end_time'),
    'quantity': json_data.get('quantity', instance.quantity),
}
```

如果API需要其他参数，请在此处添加。

---

## 📁 文件存放说明

### JSON数据文件
- **目录**: `backend/license_data/`
- **命名规则**: `{申请ID}.json`
- **示例**: `1.json`, `2.json`, `123.json`

### License生成文件
- **FlexNet**: `backend/media/license/flexnet/{id}_flex.lic`
- **Bitanswer**: `backend/media/license/bitanswer/{id}_bit.lic`

---

## 🎯 使用流程

### 场景1: 创建新License申请

1. **前端操作**: 
   - 登录系统 → License授权管理 → 新增申请
   - 填写申请人、类别、Feature、客户名称、MAC地址等信息
   - 选择License类型（FlexNet或Bitanswer）
   - 提交申请

2. **领导审批**:
   - 查看待审批列表
   - 点击"审批"按钮
   - 选择通过或拒绝，填写审批意见

3. **IT确认**:
   - 准备JSON数据文件，保存到 `license_data/{申请ID}.json`
   - 在前端点击"IT确认"按钮
   - 系统自动读取JSON文件并解析

4. **生成License**:
   - 点击"生成License"按钮
   - 系统根据类型自动处理：
     - FlexNet: 执行 `flexnet {license_file}` 命令
     - Bitanswer: 调用API生成License
   - 查看生成结果

### 场景2: 手动放置JSON文件

如果您已经有JSON数据，可以直接放到目录中：

```bash
# 例如申请ID为5的申请
# 创建文件: backend/license_data/5.json
# 内容格式参考示例文件
```

然后在前端进行IT确认和生成操作。

---

## 🧪 测试验证

### 验证目录结构
```bash
python init_license_data.py
```
应该看到所有目录都已创建成功。

### 验证JSON解析
```bash
python test_license_generation.py
```
应该看到JSON文件被正确解析。

### 验证FlexNet命令
```bash
# 在命令行执行
flexnet --version
# 或
where flexnet
```

### 验证Bitanswer API
```bash
# 使用curl测试API连通性
curl -X POST http://your-bitanswer-server/api/generate-license \
  -H "Authorization: Bearer your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"test": true}'
```

---

## ❓ 常见问题快速解决

### Q1: 提示"JSON文件不存在"
**解决**: 
- 检查文件是否在 `license_data/` 目录下
- 文件名必须是 `{申请ID}.json`
- 确保文件编码为UTF-8

### Q2: FlexNet命令执行失败
**解决**:
- 确认flexnet命令已安装
- 检查命令是否在系统PATH中
- 或在代码中使用绝对路径

### Q3: Bitanswer API调用失败
**解决**:
- 检查API地址是否正确
- 检查API密钥是否有效
- 查看日志文件 `logs/server.log` 获取详细错误

### Q4: 看不到License管理菜单
**解决**:
- 确认已执行 `add_license_menu_permissions.py`
- 清除浏览器缓存并重新登录
- 检查用户角色是否有相应权限

### Q5: 数据库迁移失败
**解决**:
```bash
# 删除旧的迁移文件（如果有）
rm apps/lylicense/migrations/0*.py

# 重新生成
python manage.py makemigrations lylicense
python manage.py migrate lylicense
```

---

## 📊 监控和日志

### 查看实时日志
```bash
# Windows PowerShell
Get-Content logs/server.log -Wait -Tail 50

# 或使用工具如 Notepad++ 的监控功能
```

### 关键日志位置
- **主日志**: `logs/server.log` - 所有操作记录
- **错误日志**: `logs/error.log` - 错误信息

### 关键日志关键词
- `执行FlexNet命令` - FlexNet生成开始
- `调用Bitanswer API` - Bitanswer生成开始
- `License生成成功` - 生成成功
- `License生成失败` - 生成失败，查看后续错误信息

---

## 🚀 生产环境建议

1. **备份策略**
   - 定期备份 `license_data/` 目录
   - 定期备份 `media/license/` 目录
   - 定期备份数据库

2. **安全措施**
   - 限制JSON文件上传权限
   - 定期轮换API密钥
   - 启用HTTPS

3. **性能优化**
   - 定期清理旧的License文件
   - 设置日志轮转
   - 监控磁盘空间

4. **高可用**
   - 考虑使用任务队列（Celery）异步生成License
   - 实现重试机制
   - 设置超时时间

---

## 📞 技术支持

如遇问题，请按以下步骤排查：

1. ✅ 检查目录结构是否正确
2. ✅ 检查JSON文件格式是否正确
3. ✅ 检查FlexNet命令或Bitanswer API是否可用
4. ✅ 查看日志文件获取详细错误信息
5. ✅ 运行测试脚本验证系统状态

---

**祝您使用愉快！** 🎉
