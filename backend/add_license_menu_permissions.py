# License管理菜单权限配置脚本
# 运行方式: python add_license_menu_permissions.py

import os
import sys
import django

# 设置Django环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
django.setup()

from mysystem.models import MenuButton

# License授权管理菜单ID（需要根据实际情况修改）
LICENSE_APPLICATION_MENU_ID = '8d7c2a1b5f3e4a9c8e1d2f3a4b5c6d7e'  # 申请记录菜单
LICENSE_RECORD_MENU_ID = '8d7c2a1b5f3e4a9c8e1d2f3a4b5c6d7f'  # License记录菜单

# 定义菜单权限 - 申请记录
application_menu_buttons = [
    {
        'id': '9a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d',
        'menu_id': LICENSE_APPLICATION_MENU_ID,
        'name': '查询',
        'value': 'Search',
        'api': '/api/license/application/',
        'method': 0
    },
    {
        'id': '9a1b2c3d4e5f6a7b8c9d0e1f2a3b4c60',
        'menu_id': LICENSE_APPLICATION_MENU_ID,
        'name': '详情',
        'value': 'Retrieve',
        'api': '/api/license/application/{id}/',
        'method': 0
    },
    {
        'id': '9a1b2c3d4e5f6a7b8c9d0e1f2a3b4c61',
        'menu_id': LICENSE_APPLICATION_MENU_ID,
        'name': '删除',
        'value': 'Delete',
        'api': '/api/license/application/{id}/',
        'method': 3
    },
    {
        'id': '9a1b2c3d4e5f6a7b8c9d0e1f2a3b4c64',
        'menu_id': LICENSE_APPLICATION_MENU_ID,
        'name': '制作License',
        'value': 'Generate',
        'api': '/api/license/application/{id}/parse_and_generate/',
        'method': 2
    },
    {
        'id': '9a1b2c3d4e5f6a7b8c9d0e1f2a3b4c65',
        'menu_id': LICENSE_APPLICATION_MENU_ID,
        'name': '重试',
        'value': 'Retry',
        'api': '/api/license/application/{id}/retry/',
        'method': 2
    }
]

# 定义菜单权限 - License记录
license_record_menu_buttons = [
    {
        'id': '9a1b2c3d4e5f6a7b8c9d0e1f2a3b4c70',
        'menu_id': LICENSE_RECORD_MENU_ID,
        'name': '查询',
        'value': 'Search',
        'api': '/api/license/record/',
        'method': 0
    },
    {
        'id': '9a1b2c3d4e5f6a7b8c9d0e1f2a3b4c71',
        'menu_id': LICENSE_RECORD_MENU_ID,
        'name': '详情',
        'value': 'Retrieve',
        'api': '/api/license/record/{id}/',
        'method': 0
    },
    {
        'id': '9a1b2c3d4e5f6a7b8c9d0e1f2a3b4c72',
        'menu_id': LICENSE_RECORD_MENU_ID,
        'name': '下载',
        'value': 'Download',
        'api': '/api/license/record/{id}/download/',
        'method': 0
    }
]

def main():
    print("="*60)
    print("开始添加License管理菜单权限...")
    print("="*60)
    
    print("\n【申请记录菜单权限】")
    for item in application_menu_buttons:
        obj, created = MenuButton.objects.get_or_create(
            id=item['id'],
            defaults=item
        )
        if created:
            print(f"✓ 已添加权限: {item['name']} ({item['value']})")
        else:
            print(f"- 权限已存在: {item['name']} ({item['value']})")
    
    print("\n【License记录菜单权限】")
    for item in license_record_menu_buttons:
        obj, created = MenuButton.objects.get_or_create(
            id=item['id'],
            defaults=item
        )
        if created:
            print(f"✓ 已添加权限: {item['name']} ({item['value']})")
        else:
            print(f"- 权限已存在: {item['name']} ({item['value']})")
    
    print("\n" + "="*60)
    print("✅ License管理菜单权限配置完成!")
    print("="*60)
    print("\n注意:")
    print("1. 请确保菜单ID与实际数据库中的菜单ID一致")
    print("2. 如需要修改菜单ID，请更新脚本顶部的常量")
    print("3. 清除浏览器缓存并重新登录以应用新权限")
    print()

if __name__ == '__main__':
    main()
