# Django-Vue-LyAdmin 开发规范

欢迎加入 Django-Vue-LyAdmin 项目的开发！本文档旨在帮助新成员快速了解项目架构、开发流程及注意事项，确保代码质量和系统稳定性。

## 1. 项目概述

本项目是一个基于 **Django 4.1** (后端) 和 **Vue 3 + Element Plus** (前端) 的后台管理系统。
- **后端**: Python, Django, Django REST Framework (DRF), MySQL, Redis, Celery
- **前端**: Vue 3, Pinia, Vue Router, Axios, Element Plus

## 2. 环境准备

### 2.1 后端环境
1. **Python 版本**: 建议使用 Python 3.9+
2. **依赖安装**:
   ```bash
   cd backend
   pip install -r requirements.txt
   ```
3. **数据库**: 配置 `backend/config.py` (需自行创建，参考 `config.py.example` 如果存在) 中的 MySQL 和 Redis 连接信息。
4. **初始化**:
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   python manage.py createsuperuser # 创建管理员账号
   ```

### 2.2 前端环境
1. **Node.js 版本**: 建议使用 Node.js 16+
2. **依赖安装**:
   ```bash
   cd frontend
   npm install
   ```
3. **启动开发服务器**:
   ```bash
   npm run dev
   ```

## 3. 后端开发规范 (Django)

### 3.1 应用结构
每个业务模块（App）通常包含以下文件：
- `models.py`: 定义数据模型
- `serializers.py`: 定义 DRF 序列化器
- `views.py`: 定义视图逻辑 (ViewSet)
- `urls.py`: 定义路由
- `filters.py`: 定义过滤器 (可选)

### 3.2 模型 (Models)
1. **继承 `CoreModel`**: 除非有特殊需求，否则所有模型都应继承自 `utils.models.CoreModel`。它提供了标准的审计字段：`id` (UUID), `creator`, `modifier`, `dept_belong_id`, `create_datetime`, `update_datetime`。
2. **表名前缀**: 使用 `utils.models.table_prefix` (默认为 `lyadmin_`)。
3. **字段注释**: 务必为每个字段添加 `verbose_name` 和 `help_text`。
4. **软删除**: 如果需要逻辑删除，请添加 `is_delete = models.BooleanField(default=False)`。

```python
from utils.models import CoreModel, table_prefix

class MyModel(CoreModel):
    name = models.CharField(max_length=100, verbose_name="名称", help_text="名称")
    
    class Meta:
        db_table = table_prefix + "my_model"
        verbose_name = '我的模型'
        verbose_name_plural = verbose_name
```

### 3.3 序列化器 (Serializers)
1. **继承 `CustomModelSerializer`**: 位于 `utils.serializers`。
2. **多序列化器策略**: 
   - `MyModelSerializer`: 用于列表展示和详情获取。
   - `MyModelCreateSerializer`: 用于新增操作。
   - `MyModelUpdateSerializer`: 用于更新操作。
3. **在 ViewSet 中指定**:
   ```python
   class MyViewSet(CustomModelViewSet):
       serializer_class = MyModelSerializer
       create_serializer_class = MyModelCreateSerializer
       update_serializer_class = MyModelUpdateSerializer
   ```

### 3.4 视图集 (ViewSets)
1. **继承 `CustomModelViewSet`**: 位于 `utils.viewset`。它提供了统一的响应格式、分页、权限控制和过滤功能。
2. **统一响应格式**:
   - 成功: `SuccessResponse(data=..., msg="...")` 或 `DetailResponse(data=..., msg="...")`
   - 失败: `ErrorResponse(msg="...", code=400)`
3. **权限控制**: 默认使用 `CustomPermission` 和 `IsAuthenticated`。
4. **过滤与搜索**:
   - `filterset_fields`: 精确匹配字段。
   - `search_fields`: 模糊搜索字段。
   - `ordering_fields`: 排序字段。

```python
from utils.viewset import CustomModelViewSet
from utils.jsonResponse import SuccessResponse

class MyViewSet(CustomModelViewSet):
    queryset = MyModel.objects.all()
    serializer_class = MyModelSerializer
    filterset_fields = ['name', 'status']
    search_fields = ['name']

    @action(methods=['get'], detail=False)
    def my_custom_action(self, request):
        # 自定义逻辑
        return SuccessResponse(data={"info": "ok"}, msg="自定义接口成功")
```

### 3.5 路由 (URLs)
在每个 App 的 `urls.py` 中使用 DRF 的 `DefaultRouter` 注册 ViewSet。

```python
from rest_framework.routers import DefaultRouter
from .views import MyViewSet

router = DefaultRouter()
router.register(r'my-model', MyViewSet, basename='my-model')

urlpatterns = router.urls
```

并在主路由 `application/urls.py` 中包含该 App 的路由。

### 3.6 工具函数
- **常用工具**: `utils/common.py` 包含手机号验证、随机码生成、日期格式化等。
- **响应封装**: `utils/jsonResponse.py` 提供 `SuccessResponse`, `DetailResponse`, `ErrorResponse`。
- **权限与过滤**: `utils/permission.py`, `utils/filters.py`。

## 4. 前端开发规范 (Vue 3)

### 4.1 目录结构
- `src/api/`: API 请求封装。
- `src/views/`: 页面组件。
- `src/components/`: 公共组件。
- `src/store/`: Pinia 状态管理。
- `src/router/`: 路由配置。
- `src/utils/`: 工具函数。

### 4.2 API 请求
1. **统一封装**: 使用 `src/api/request.js` 中的 `ajaxGet`, `ajaxPost`, `ajaxPut`, `ajaxDelete`。
2. **定义接口**: 在 `src/api/` 下按模块创建文件，例如 `user.js`。

```javascript
import { ajaxGet, ajaxPost } from './request';

export function getUserList(params) {
    return ajaxGet({ url: '/api/system/user/', params });
}

export function createUser(data) {
    return ajaxPost({ url: '/api/system/user/', params: data });
}
```

### 4.3 组件开发
1. **Composition API**: 推荐使用 `<script setup>` 语法。
2. **Element Plus**: 优先使用 Element Plus 组件库。
3. **样式**: 使用 SCSS，避免全局样式污染，推荐使用 scoped。

### 4.4 状态管理
使用 Pinia 进行全局状态管理。

## 5. 数据库迁移

1. **修改模型后**:
   ```bash
   python manage.py makemigrations <app_name>
   python manage.py migrate <app_name>
   ```
2. **注意**: 在生产环境中执行迁移前，请务必备份数据库。

## 6. 注意事项与禁止事项

### ✅ 推荐做法
1. **代码复用**: 充分利用 `utils` 目录下的通用类和函数。
2. **日志记录**: 使用 Python 标准 `logging` 模块记录关键操作和错误。
3. **异常处理**: 在后端捕获并处理异常，返回友好的错误信息。
4. **安全性**: 
   - 不要硬编码敏感信息（如密钥、密码），使用环境变量或配置文件。
   - 对用户输入进行验证和清洗。
5. **注释**: 为复杂的逻辑添加清晰的注释。

### ❌ 禁止事项
1. **直接修改 `CoreModel`**: 除非你清楚后果，否则不要修改基础模型。
2. **绕过权限系统**: 不要随意移除 `permission_classes`。
3. **在视图中编写复杂 SQL**: 尽量使用 ORM，复杂查询可使用 `annotate` 和 `aggregate`。
4. **提交敏感配置**: 不要将 `config.py` 或包含密钥的文件提交到版本控制系统。
5. **忽略迁移冲突**: 解决合并时产生的迁移文件冲突。
6. **前端硬编码 URL**: 所有 API 地址应通过 `request.js` 统一管理。

## 7. 调试与测试

1. **后端调试**: 
   - 使用 `print()` 或断点调试 (pdb/IDE debugger)。
   - 查看 `logs/server.log` 和 `logs/error.log`。
2. **前端调试**: 
   - 使用浏览器开发者工具。
   - 检查 Network 面板的 API 请求和响应。
3. **API 文档**: 访问 `/swagger/` 查看自动生成的接口文档。

## 8. 部署

1. **静态文件收集**:
   ```bash
   python manage.py collectstatic
   ```
2. **服务启动**:
   - 后端: 使用 Gunicorn + Nginx (生产环境) 或 `daphne` (如果需要 WebSocket)。
   - 前端: 构建 `npm run build`，并将 `dist` 目录部署到 Nginx。
   - Celery: 启动 Worker 和 Beat 服务处理异步任务。

---

如有疑问，请参考现有模块的代码实现或联系项目负责人。祝开发愉快！
