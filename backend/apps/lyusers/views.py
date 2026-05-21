from django.shortcuts import render
from rest_framework.views import APIView
from utils.jsonResponse import SuccessResponse,ErrorResponse
from utils.common import get_parameter_dic,getRandomSet
import re
from django.db.models import Q,F,Sum
from rest_framework.serializers import ModelSerializer
from rest_framework import serializers
from rest_framework_simplejwt.authentication import JWTAuthentication
from utils.serializers import CustomModelSerializer
from utils.viewset import CustomModelViewSet
from rest_framework.permissions import IsAuthenticated
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from utils.imageupload import ImageUpload
from mysystem.models import Users
from utils.filters import UsersManageTimeFilter
from django.contrib.auth.hashers import make_password
from utils.export_excel import export_excel
from django.db import transaction
from apps.oauth.models import OAuthWXUser
# Create your views here.

# ================================================= #
# ************** 后端用户管理 view  ************** #
# ================================================= #

class UserManageSerializer(CustomModelSerializer):
    """
    用户管理-序列化器
    """
    dept_name = serializers.SerializerMethodField(read_only=True)  # 部门名称
    role_names = serializers.SerializerMethodField(read_only=True)  # 角色名称列表
    
    def to_representation(self, instance):
        """调试：查看序列化过程"""
        print(f"\n{'='*60}")
        print(f"[UserManageSerializer.to_representation]")
        print(f"{'='*60}")
        print(f"instance.id: {instance.id}")
        try:
            print(f"instance.dept: {instance.dept}")
        except Exception as e:
            print(f"instance.dept: Error accessing - {str(e)}")
        print(f"instance.dept_id: {instance.dept_id if hasattr(instance, 'dept_id') else 'N/A'}")
        try:
            print(f"instance.role (ManyToMany): {list(instance.role.all())}")
        except Exception as e:
            print(f"instance.role: Error accessing - {str(e)}")
        ret = super().to_representation(instance)
        print(f"ret.keys(): {list(ret.keys())}")
        print(f"'dept' in ret: {'dept' in ret}")
        print(f"'role' in ret: {'role' in ret}")
        print(f"ret.get('dept'): {ret.get('dept')}")
        print(f"ret.get('role'): {ret.get('role')}")
        print(f"{'='*60}\n")
        return ret
    
    def get_dept_name(self, obj):
        try:
            return obj.dept.name if obj.dept else ''
        except Exception:
            return ''
    
    def get_role_names(self, obj):
        try:
            return list(obj.role.values_list('name', flat=True))
        except Exception:
            return []

    class Meta:
        model = Users
        read_only_fields = ["id"]
        fields = [
            'id', 'username', 'email', 'mobile', 'avatar', 'name', 'nickname', 'gender',
            'post', 'role', 'dept',  # 重要：包含 role 和 dept
            'identity', 'balance', 'is_delete', 'is_active', 'is_staff', 'is_superuser',
            'last_login', 'date_joined', 'first_name', 'last_name',
            'dept_name', 'role_names',  # 自定义字段
            'create_datetime', 'update_datetime',
            'creator', 'modifier', 'creator_name', 'modifier_name',
            'dept_belong_id', 'description'
        ]
        extra_kwargs = {
            'post': {'required': False, 'allow_empty': True},
            'dept': {'required': False},
            'role': {'required': False, 'allow_empty': True},
        }

class UserManageCreateSerializer(CustomModelSerializer):
    """
    用户管理-新增序列化器
    """

    def save(self, **kwargs):
        """重写save方法，处理dept和role字段"""
        print(f"\n{'='*60}")
        print(f"[UserManageCreateSerializer.save]")
        print(f"{'='*60}")
        print(f"initial_data keys: {list(self.initial_data.keys())}")
        print(f"dept: {self.initial_data.get('dept')}")
        print(f"role: {self.initial_data.get('role')}")
        print(f"type(dept): {type(self.initial_data.get('dept'))}")
        print(f"type(role): {type(self.initial_data.get('role'))}")
        
        data = super().save(**kwargs)
        print(f"\nAfter super().save():")
        print(f"data.id: {data.id}")
        print(f"data.dept: {data.dept}")
        print(f"data.dept_id: {data.dept_id}")
        print(f"data.role (ManyToMany): {list(data.role.all())}")
        
        # 设置岗位
        post_ids = self.initial_data.get('post', [])
        print(f"\nSetting post: {post_ids}")
        data.post.set(post_ids)
        
        # 设置部门
        dept_id = self.initial_data.get('dept', None)
        print(f"\nSetting dept: {dept_id}")
        if dept_id and dept_id != '':
            from mysystem.models import Dept
            try:
                dept = Dept.objects.get(id=dept_id)
                data.dept = dept
                data.save(update_fields=['dept'])  # 只更新 dept 字段
                print(f"OK Dept set successfully: {dept_id} -> {dept.name}")
            except Dept.DoesNotExist:
                print(f"FAIL Dept not found: {dept_id}")
            except Exception as e:
                print(f"FAIL Error setting dept: {str(e)}")
        else:
            print(f"No dept to set (dept_id is: {dept_id})")
        
        # 设置角色
        role_ids = self.initial_data.get('role', [])
        print(f"\nSetting role: {role_ids}")
        if role_ids and len(role_ids) > 0:
            from mysystem.models import Role
            try:
                roles = Role.objects.filter(id__in=role_ids)
                data.role.set(roles)
                print(f"OK Roles set successfully: {role_ids}")
            except Exception as e:
                print(f"FAIL Error setting roles: {str(e)}")
        else:
            print(f"No roles to set (role_ids is: {role_ids})")
        
        # 验证最终结果
        data.refresh_from_db()
        print(f"\nFinal result:")
        print(f"data.dept: {data.dept}")
        print(f"data.dept_id: {data.dept_id}")
        print(f"data.role: {list(data.role.all())}")
        print(f"{'='*60}\n")
        
        return data

    # 新增重写
    def create(self, validated_data):
        if "password" in validated_data.keys():
            if validated_data['password']:
                validated_data['password'] = make_password(validated_data['password'])
        validated_data['identity'] = 2
        return super().create(validated_data)

    class Meta:
        model = Users
        read_only_fields = ["id"]
        fields = [
            'id', 'username', 'email', 'mobile', 'avatar', 'name', 'nickname', 'gender',
            'post', 'role', 'dept',  # 重要：包含 role 和 dept
            'identity', 'balance', 'is_delete', 'is_active', 'is_staff', 'is_superuser',
            'last_login', 'date_joined', 'first_name', 'last_name',
            'create_datetime', 'update_datetime',
            'creator', 'modifier', 'creator_name', 'modifier_name',
            'dept_belong_id', 'description', 'password'
        ]
        extra_kwargs = {
            'post': {'required': False, 'allow_empty': True},
            'dept': {'required': False},
            'role': {'required': False, 'allow_empty': True},
            'name': {'required': False},
            'password': {'required': False},
        }

class UserManageUpdateSerializer(CustomModelSerializer):
    """
    用户管理-更新序列化器
    """
    
    def save(self, **kwargs):
        """重写save方法，处理dept和role字段"""
        print(f"\n{'='*60}")
        print(f"[UserManageUpdateSerializer.save]")
        print(f"{'='*60}")
        print(f"initial_data keys: {list(self.initial_data.keys())}")
        print(f"dept: {self.initial_data.get('dept')}")
        print(f"role: {self.initial_data.get('role')}")
        print(f"type(dept): {type(self.initial_data.get('dept'))}")
        print(f"type(role): {type(self.initial_data.get('role'))}")
        
        data = super().save(**kwargs)
        print(f"\nAfter super().save():")
        print(f"data.id: {data.id}")
        print(f"data.dept: {data.dept}")
        print(f"data.dept_id: {data.dept_id}")
        print(f"data.role (ManyToMany): {list(data.role.all())}")
        
        # 设置岗位
        post_ids = self.initial_data.get('post', [])
        print(f"\nSetting post: {post_ids}")
        data.post.set(post_ids)
        
        # 设置部门
        dept_id = self.initial_data.get('dept', None)
        print(f"\nSetting dept: {dept_id}")
        if dept_id and dept_id != '':
            from mysystem.models import Dept
            try:
                dept = Dept.objects.get(id=dept_id)
                data.dept = dept
                data.save(update_fields=['dept'])  # 只更新 dept 字段
                print(f"OK Dept set successfully: {dept_id} -> {dept.name}")
            except Dept.DoesNotExist:
                print(f"FAIL Dept not found: {dept_id}")
            except Exception as e:
                print(f"FAIL Error setting dept: {str(e)}")
        else:
            print(f"No dept to set (dept_id is: {dept_id})")
        
        # 设置角色
        role_ids = self.initial_data.get('role', [])
        print(f"\nSetting role: {role_ids}")
        if role_ids and len(role_ids) > 0:
            from mysystem.models import Role
            try:
                roles = Role.objects.filter(id__in=role_ids)
                data.role.set(roles)
                print(f"OK Roles set successfully: {role_ids}")
            except Exception as e:
                print(f"FAIL Error setting roles: {str(e)}")
        else:
            print(f"No roles to set (role_ids is: {role_ids})")
        
        # 验证最终结果
        data.refresh_from_db()
        print(f"\nFinal result:")
        print(f"data.dept: {data.dept}")
        print(f"data.dept_id: {data.dept_id}")
        print(f"data.role: {list(data.role.all())}")
        print(f"{'='*60}\n")
        
        return data
    
    # 更新重写
    def update(self, instance, validated_data):
        if "password" in validated_data.keys():
            if validated_data['password']:
                validated_data['password'] = make_password(validated_data['password'])
            else:
                validated_data.pop('password', None)
        return super().update(instance,validated_data)

    class Meta:
        model = Users
        read_only_fields = ["id"]
        fields = [
            'id', 'username', 'email', 'mobile', 'avatar', 'name', 'nickname', 'gender',
            'post', 'role', 'dept',  # 重要：包含 role 和 dept
            'identity', 'balance', 'is_delete', 'is_active', 'is_staff', 'is_superuser',
            'last_login', 'date_joined', 'first_name', 'last_name',
            'create_datetime', 'update_datetime',
            'creator', 'modifier', 'creator_name', 'modifier_name',
            'dept_belong_id', 'description', 'password'
        ]
        extra_kwargs = {
            'post': {'required': False, 'allow_empty': True},
            'dept': {'required': False},
            'role': {'required': False, 'allow_empty': True},
            'name': {'required': False},
            'password': {'required': False},
        }
class ExportUserManageSerializer(CustomModelSerializer):
    """
    导出 用户信息 简单序列化器
    """
    is_active_name = serializers.SerializerMethodField()
    def get_is_active_name(self, obj):
        if obj.is_active:
            return "正常"
        else:
            return "禁用"

    class Meta:
        model = Users
        fields = ('id', 'nickname','mobile', 'is_active_name','create_datetime')

class UserManageViewSet(CustomModelViewSet):
    """
    后台用户管理 接口:
    """
    queryset = Users.objects.filter(identity=2).order_by("-create_datetime")#排除管理员
    serializer_class = UserManageSerializer
    create_serializer_class = UserManageCreateSerializer
    update_serializer_class = UserManageUpdateSerializer
    filterset_class = UsersManageTimeFilter

    def disableuser(self,request,*args, **kwargs):
        """禁用用户"""
        instance = Users.objects.filter(id=kwargs.get('pk')).first()
        if instance:
            if instance.is_active:
                instance.is_active = False
            else:
                instance.is_active = True
            instance.save()
            return SuccessResponse(data=None, msg="修改成功")
        else:
            return ErrorResponse(msg="未获取到用户")

    def exportexecl(self, request):
        field_data = ['主键', '昵称', '手机号', '状态', '创建时间']
        queryset = self.filter_queryset(self.get_queryset())
        data = ExportUserManageSerializer(queryset, many=True).data
        return SuccessResponse(data=export_excel(request, field_data, data, '用户数据.xls'), msg='success')

# ================================================= #
# ************** 前端用户中心 view  ************** #
# ================================================= #

#前端图片上传
class uploadImagesView(APIView):
    '''
    前端图片上传
    post:
    【功能描述】前端图片上传</br>
    【参数说明】无，需要登录携带token后才能调用</br>
    '''
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        result = ImageUpload(request,"frontendimages")
        if result['code'] == 200 :
            return SuccessResponse(data=result['img'],msg=result['msg'])
        else:
            return ErrorResponse(msg=result['msg'])

class SetUserNicknameView(APIView):
    """
    修改昵称
    post:
    修改昵称
    【参数】nickname:需要修改的用户新昵称
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    #api文档参数

    @swagger_auto_schema(operation_summary='app回收员修改昵称',
    # manual_parameters=[#GET请求需要
    #     # openapi.Parameter("nickname", openapi.IN_QUERY, description="要修改昵称", type=openapi.TYPE_STRING)
    # ],
    request_body=openapi.Schema(#POST请求需要
        type=openapi.TYPE_OBJECT,
        required=['nickname'],
        properties={
                'nickname':openapi.Schema(type=openapi.TYPE_STRING,description="要修改昵称"),
             },
        ),
    responses={200:'success'},
    )

    def post(self, request):
        nickname = get_parameter_dic(request)['nickname']
        if nickname is None:
            return ErrorResponse(msg="昵称不能为空")
        if not isinstance(nickname,str):
            return ErrorResponse(msg='类型错误')
        user = request.user
        user.nickname  = nickname
        user.save()
        return SuccessResponse(msg="success")

#前端app头像修改
class ChangeAvatarView(APIView):
    '''
    前端app头像修改
    post:
    【功能描述】前端app头像修改</br>
    【参数说明】无，需要登录携带token后才能调用</br>
    '''
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        result = ImageUpload(request,"avatar")
        if result['code'] == 200 :
            user = request.user
            user.avatar = result['img'][0]
            user.save()
            return SuccessResponse(data=result['img'],msg=result['msg'])
        else:
            return ErrorResponse(msg=result['msg'])

#注销账号(标记已注销)
class DestroyUserView(APIView):
    '''
    注销账号(标记已注销)
    post:
    【功能描述】注销账号(标记已注销)</br>
    '''
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        user = request.user
        if user.identity in [0,1]:
            return ErrorResponse(msg="该用户不支持注销")
        if '(已注销)' in user.username:
            return ErrorResponse(msg="该用户已注销或不支持注销")
        with transaction.atomic():
            randstr = getRandomSet(6)
            user.username = user.username + "(已注销)" + randstr
            user.mobile = user.mobile + "(已注销)" + randstr
            user.is_delete = True
            user.is_active = False
            user.save()
            OAuthWXUser.objects.filter(user=user).delete()
            return SuccessResponse(data={},msg="success")

#前端APP下载页面
def downloadapp(request):
    return render(request,"download-app/index.html")