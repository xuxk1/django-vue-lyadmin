# -*- coding: utf-8 -*-

"""
@Remark: 用户管理
"""
from django.contrib.auth.hashers import make_password
from rest_framework import serializers

from mysystem.models import Users,Role
from utils.jsonResponse import SuccessResponse, ErrorResponse
from utils.permission import CustomPermission
from utils.serializers import CustomModelSerializer
from utils.validator import CustomUniqueValidator
from utils.viewset import CustomModelViewSet
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from utils.filters import UsersManageTimeFilter

class UserSerializer(CustomModelSerializer):
    """
    用户管理-序列化器
    """
    rolekey = serializers.SerializerMethodField(read_only=True)  # 角色key列表
    dept_name = serializers.SerializerMethodField(read_only=True)  # 部门名称
    role_names = serializers.SerializerMethodField(read_only=True)  # 角色名称列表
    
    def to_representation(self, instance):
        """调试：查看序列化过程"""
        print(f"\n{'='*60}")
        print(f"[UserSerializer.to_representation]")
        print(f"{'='*60}")
        print(f"instance.id: {instance.id}")
        print(f"instance.dept: {instance.dept}")
        print(f"instance.dept_id: {instance.dept_id if hasattr(instance, 'dept_id') else 'N/A'}")
        print(f"instance.role (ManyToMany): {list(instance.role.all())}")
        ret = super().to_representation(instance)
        print(f"ret.keys(): {list(ret.keys())}")
        print(f"'dept' in ret: {'dept' in ret}")
        print(f"'role' in ret: {'role' in ret}")
        print(f"ret.get('dept'): {ret.get('dept')}")
        print(f"ret.get('role'): {ret.get('role')}")
        print(f"{'='*60}\n")
        return ret

    def get_rolekey(self,obj):
        return list(obj.role.values_list('key', flat=True))
    
    def get_dept_name(self, obj):
        return obj.dept.name if obj.dept else ''
    
    def get_role_names(self, obj):
        return list(obj.role.values_list('name', flat=True))

    class Meta:
        model = Users
        read_only_fields = ["id"]
        # 使用 exclude 黑名单方式，只排除不需要的字段
        exclude = ['password', 'user_permissions', 'groups']
        extra_kwargs = {
            'post': {'required': False},
            'dept': {'required': False},
            'role': {'required': False},
        }


class UserCreateSerializer(CustomModelSerializer):
    """
    管理员用户新增-序列化器
    """
    username = serializers.CharField(max_length=50,validators=[CustomUniqueValidator(queryset=Users.objects.all(), message="账号必须唯一")])
    password = serializers.CharField(required=False, default=make_password("123456"))

    is_staff = serializers.BooleanField(required=False,default=False)#是否允许登录后台

    def create(self, validated_data):
        if "password" in validated_data.keys():
            if validated_data['password']:
                validated_data['password'] = make_password(validated_data['password'])
        validated_data['identity'] = 1
        return super().create(validated_data)

    def save(self, **kwargs):
        print(f"\n{'='*60}")
        print(f"[UserCreateSerializer.save]")
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
                print(f"✓ Dept set successfully: {dept_id} -> {dept.name}")
            except Dept.DoesNotExist:
                print(f"✗ Dept not found: {dept_id}")
            except Exception as e:
                print(f"✗ Error setting dept: {str(e)}")
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
                print(f"✓ Roles set successfully: {role_ids}")
            except Exception as e:
                print(f"✗ Error setting roles: {str(e)}")
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

    class Meta:
        model = Users
        fields = "__all__"
        read_only_fields = ["id"]
        extra_kwargs = {
            'post': {'required': False},
            'dept': {'required': False},
            'role': {'required': False},
        }


class UserUpdateSerializer(CustomModelSerializer):
    """
    用户修改-序列化器
    """
    username = serializers.CharField(max_length=50,validators=[CustomUniqueValidator(queryset=Users.objects.all(), message="账号必须唯一")])
    password = serializers.CharField(required=False, allow_blank=True)

    def update(self, instance, validated_data):
        if "password" in validated_data.keys():
            if validated_data['password']:
                validated_data['password'] = make_password(validated_data['password'])
        return super().update(instance,validated_data)

    def save(self, **kwargs):
        print(f"[UserUpdateSerializer] initial_data: {self.initial_data}")
        print(f"[UserUpdateSerializer] dept: {self.initial_data.get('dept')}")
        print(f"[UserUpdateSerializer] role: {self.initial_data.get('role')}")
        
        data = super().save(**kwargs)
        print(f"[UserUpdateSerializer] After super().save(), data.dept: {data.dept}")
        
        # 设置岗位
        data.post.set(self.initial_data.get('post', []))
        # 设置部门
        dept_id = self.initial_data.get('dept', None)
        if dept_id:
            from mysystem.models import Dept
            try:
                dept = Dept.objects.get(id=dept_id)
                data.dept = dept
                data.save()
                print(f"[UserUpdateSerializer] Dept set successfully: {dept_id}")
            except Dept.DoesNotExist:
                print(f"[UserUpdateSerializer] Dept not found: {dept_id}")
                pass
        # 设置角色
        role_ids = self.initial_data.get('role', [])
        if role_ids:
            from mysystem.models import Role
            roles = Role.objects.filter(id__in=role_ids)
            data.role.set(roles)
            print(f"[UserUpdateSerializer] Roles set successfully: {role_ids}")
        else:
            print(f"[UserUpdateSerializer] No roles to set")
        
        print(f"[UserUpdateSerializer] Final data.dept: {data.dept}")
        print(f"[UserUpdateSerializer] Final data.role: {list(data.role.all())}")
        return data

    class Meta:
        model = Users
        read_only_fields = ["id"]
        fields = "__all__"
        extra_kwargs = {
            'post': {'required': False},
            'dept': {'required': False},
            'role': {'required': False},
        }


class UserViewSet(CustomModelViewSet):
    """
    后台管理员用户接口:
    """
    queryset = Users.objects.filter(identity=1,is_delete=False).order_by('-create_datetime')
    serializer_class = UserSerializer
    create_serializer_class = UserCreateSerializer
    update_serializer_class = UserUpdateSerializer
    # filterset_fields = ('name','is_active','username')
    filterset_class = UsersManageTimeFilter

    def user_info(self,request):
        """获取当前用户信息"""
        user = request.user
        result = {
            "name":user.name,
            "mobile":user.mobile,
            "gender":user.gender,
            "email":user.email
        }
        return SuccessResponse(data=result,msg="获取成功")

    def update_user_info(self,request):
        """修改当前用户信息"""
        user = request.user
        Users.objects.filter(id=user.id).update(**request.data)
        return SuccessResponse(data=None, msg="修改成功")


    def change_password(self,request,*args, **kwargs):
        """密码修改"""
        user = request.user
        instance = Users.objects.filter(id=user.id,identity__in=[0,1]).first()
        data = request.data
        old_pwd = data.get('oldPassword')
        new_pwd = data.get('newPassword')
        new_pwd2 = data.get('newPassword2')
        if instance:
            if new_pwd != new_pwd2:
                return ErrorResponse(msg="2次密码不匹配")
            elif instance.check_password(old_pwd):
                instance.password = make_password(new_pwd)
                instance.save()
                return SuccessResponse(data=None, msg="修改成功")
            else:
                return ErrorResponse(msg="旧密码不正确")
        else:
            return ErrorResponse(msg="未获取到用户")
