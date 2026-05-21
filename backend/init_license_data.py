#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
初始化License数据目录结构
创建必要的目录和JSON数据示例
"""

import os
import sys
import json
import django

# 设置Django环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
django.setup()

from django.conf import settings

BASE_DIR = settings.BASE_DIR
MEDIA_ROOT = settings.MEDIA_ROOT

def create_directories():
    """创建必要的目录结构"""
    print("=" * 50)
    print("创建License数据目录结构")
    print("=" * 50)
    
    # 1. 创建JSON数据目录
    license_data_dir = os.path.join(BASE_DIR, 'license_data')
    if not os.path.exists(license_data_dir):
        os.makedirs(license_data_dir)
        print(f"✓ 已创建JSON数据目录: {license_data_dir}")
    else:
        print(f"- JSON数据目录已存在: {license_data_dir}")
    
    # 2. 创建License文件存储目录 - FlexNet
    flexnet_dir = os.path.join(MEDIA_ROOT, 'license', 'flexnet')
    if not os.path.exists(flexnet_dir):
        os.makedirs(flexnet_dir)
        print(f"✓ 已创建FlexNet License目录: {flexnet_dir}")
    else:
        print(f"- FlexNet License目录已存在: {flexnet_dir}")
    
    # 3. 创建License文件存储目录 - Bitanswer
    bitanswer_dir = os.path.join(MEDIA_ROOT, 'license', 'bitanswer')
    if not os.path.exists(bitanswer_dir):
        os.makedirs(bitanswer_dir)
        print(f"✓ 已创建Bitanswer License目录: {bitanswer_dir}")
    else:
        print(f"- Bitanswer License目录已存在: {bitanswer_dir}")
    
    print("\n" + "=" * 50)
    print("目录结构创建完成")
    print("=" * 50)

def create_sample_json():
    """创建示例JSON数据"""
    print("\n" + "=" * 50)
    print("创建示例JSON数据")
    print("=" * 50)
    
    license_data_dir = os.path.join(BASE_DIR, 'license_data')
    
    # FlexNet示例
    flexnet_sample = {
        "id": 1,
        "customer_name": "示例客户A公司",
        "mac_address": "00:11:22:33:44:55",
        "feature": "FlexNet基础功能包",
        "start_time": "2026-01-01 00:00:00",
        "end_time": "2027-12-31 23:59:59",
        "quantity": 5,
        "license_type": "flexnet",
        "product_id": "FN-2026-001",
        "version": "1.0",
        "notes": "这是一个FlexNet License示例"
    }
    
    flexnet_file = os.path.join(license_data_dir, '1.json')
    if not os.path.exists(flexnet_file):
        with open(flexnet_file, 'w', encoding='utf-8') as f:
            json.dump(flexnet_sample, f, ensure_ascii=False, indent=2)
        print(f"✓ 已创建FlexNet示例JSON: {flexnet_file}")
    else:
        print(f"- FlexNet示例JSON已存在: {flexnet_file}")
    
    # Bitanswer示例
    bitanswer_sample = {
        "id": 2,
        "customer_name": "示例客户B公司",
        "mac_address": "AA:BB:CC:DD:EE:FF",
        "feature": "Bitanswer高级功能包",
        "start_time": "2026-01-01 00:00:00",
        "end_time": "2026-12-31 23:59:59",
        "quantity": 10,
        "license_type": "bitanswer",
        "api_key": "ba-api-key-12345",
        "module_ids": ["MOD001", "MOD002", "MOD003"],
        "notes": "这是一个Bitanswer License示例"
    }
    
    bitanswer_file = os.path.join(license_data_dir, '2.json')
    if not os.path.exists(bitanswer_file):
        with open(bitanswer_file, 'w', encoding='utf-8') as f:
            json.dump(bitanswer_sample, f, ensure_ascii=False, indent=2)
        print(f"✓ 已创建Bitanswer示例JSON: {bitanswer_file}")
    else:
        print(f"- Bitanswer示例JSON已存在: {bitanswer_file}")
    
    print("\n" + "=" * 50)
    print("示例JSON数据创建完成")
    print("=" * 50)

def main():
    """主函数"""
    print("\n")
    print("╔" + "═" * 48 + "╗")
    print("║" + " " * 10 + "License数据目录初始化脚本" + " " * 10 + "║")
    print("╚" + "═" * 48 + "╝")
    print("\n")
    
    try:
        # 1. 创建目录
        create_directories()
        
        # 2. 创建示例数据
        create_sample_json()
        
        print("\n" + "=" * 50)
        print("✅ 所有初始化操作完成！")
        print("=" * 50)
        print("\n下一步:")
        print("1. 执行数据库迁移: python manage.py migrate lylicense")
        print("2. 启动Django服务: python manage.py runserver")
        print("3. 访问前端页面进行测试")
        print("\n")
        
    except Exception as e:
        print(f"\n❌ 初始化失败: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
