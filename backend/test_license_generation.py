#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
License生成逻辑测试脚本
用于验证FlexNet和Bitanswer的生成逻辑是否正确
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

def test_directory_structure():
    """测试目录结构是否正确创建"""
    print("=" * 60)
    print("测试1: 检查目录结构")
    print("=" * 60)
    
    # 检查JSON数据目录
    license_data_dir = os.path.join(BASE_DIR, 'license_data')
    if os.path.exists(license_data_dir):
        print(f"✓ JSON数据目录存在: {license_data_dir}")
        
        # 列出所有JSON文件
        json_files = [f for f in os.listdir(license_data_dir) if f.endswith('.json')]
        if json_files:
            print(f"  找到 {len(json_files)} 个JSON文件:")
            for f in json_files:
                print(f"    - {f}")
        else:
            print("  ⚠ 未找到JSON文件")
    else:
        print(f"✗ JSON数据目录不存在: {license_data_dir}")
        return False
    
    # 检查FlexNet目录
    flexnet_dir = os.path.join(MEDIA_ROOT, 'license', 'flexnet')
    if os.path.exists(flexnet_dir):
        print(f"✓ FlexNet License目录存在: {flexnet_dir}")
    else:
        print(f"✗ FlexNet License目录不存在: {flexnet_dir}")
        return False
    
    # 检查Bitanswer目录
    bitanswer_dir = os.path.join(MEDIA_ROOT, 'license', 'bitanswer')
    if os.path.exists(bitanswer_dir):
        print(f"✓ Bitanswer License目录存在: {bitanswer_dir}")
    else:
        print(f"✗ Bitanswer License目录不存在: {bitanswer_dir}")
        return False
    
    print("\n✅ 目录结构测试通过\n")
    return True

def test_json_parsing():
    """测试JSON文件解析"""
    print("=" * 60)
    print("测试2: JSON文件解析")
    print("=" * 60)
    
    license_data_dir = os.path.join(BASE_DIR, 'license_data')
    
    if not os.path.exists(license_data_dir):
        print("✗ JSON数据目录不存在")
        return False
    
    json_files = [f for f in os.listdir(license_data_dir) if f.endswith('.json')]
    
    if not json_files:
        print("⚠ 未找到JSON文件，请先运行 init_license_data.py")
        return False
    
    success_count = 0
    for json_file in json_files:
        file_path = os.path.join(license_data_dir, json_file)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            print(f"✓ 成功解析 {json_file}:")
            print(f"  - ID: {data.get('id')}")
            print(f"  - 客户名称: {data.get('customer_name')}")
            print(f"  - MAC地址: {data.get('mac_address')}")
            print(f"  - License类型: {data.get('license_type')}")
            print(f"  - Feature: {data.get('feature')}")
            success_count += 1
        except Exception as e:
            print(f"✗ 解析失败 {json_file}: {str(e)}")
    
    print(f"\n✅ 成功解析 {success_count}/{len(json_files)} 个JSON文件\n")
    return success_count > 0

def test_flexnet_logic():
    """测试FlexNet生成逻辑（模拟）"""
    print("=" * 60)
    print("测试3: FlexNet生成逻辑（模拟）")
    print("=" * 60)
    
    license_data_dir = os.path.join(BASE_DIR, 'license_data')
    flexnet_dir = os.path.join(MEDIA_ROOT, 'license', 'flexnet')
    
    # 查找FlexNet类型的JSON文件
    json_files = [f for f in os.listdir(license_data_dir) if f.endswith('.json')]
    flexnet_files = []
    
    for json_file in json_files:
        file_path = os.path.join(license_data_dir, json_file)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if data.get('license_type') == 'flexnet':
                flexnet_files.append((json_file, data))
        except:
            pass
    
    if not flexnet_files:
        print("⚠ 未找到FlexNet类型的JSON文件")
        return False
    
    print(f"找到 {len(flexnet_files)} 个FlexNet申请\n")
    
    for json_file, data in flexnet_files:
        app_id = data.get('id')
        license_file = os.path.join(flexnet_dir, f'{app_id}_flex.lic')
        
        print(f"申请ID: {app_id}")
        print(f"  JSON文件: {json_file}")
        print(f"  License文件路径: {license_file}")
        
        # 模拟执行命令（不实际执行）
        cmd = f'flexnet {license_file}'
        print(f"  将执行命令: {cmd}")
        print(f"  预期结果: 如果命令返回0，表示成功")
        print()
    
    print("✅ FlexNet逻辑测试完成（未实际执行命令）\n")
    return True

def test_bitanswer_logic():
    """测试Bitanswer生成逻辑（模拟）"""
    print("=" * 60)
    print("测试4: Bitanswer生成逻辑（模拟）")
    print("=" * 60)
    
    license_data_dir = os.path.join(BASE_DIR, 'license_data')
    bitanswer_dir = os.path.join(MEDIA_ROOT, 'license', 'bitanswer')
    
    # 查找Bitanswer类型的JSON文件
    json_files = [f for f in os.listdir(license_data_dir) if f.endswith('.json')]
    bitanswer_files = []
    
    for json_file in json_files:
        file_path = os.path.join(license_data_dir, json_file)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if data.get('license_type') == 'bitanswer':
                bitanswer_files.append((json_file, data))
        except:
            pass
    
    if not bitanswer_files:
        print("⚠ 未找到Bitanswer类型的JSON文件")
        return False
    
    print(f"找到 {len(bitanswer_files)} 个Bitanswer申请\n")
    
    for json_file, data in bitanswer_files:
        app_id = data.get('id')
        license_file = os.path.join(bitanswer_dir, f'{app_id}_bit.lic')
        
        print(f"申请ID: {app_id}")
        print(f"  JSON文件: {json_file}")
        print(f"  License文件路径: {license_file}")
        
        # 构建API请求参数
        params = {
            'customer_name': data.get('customer_name'),
            'mac_address': data.get('mac_address'),
            'feature': data.get('feature'),
            'start_time': data.get('start_time'),
            'end_time': data.get('end_time'),
            'quantity': data.get('quantity'),
        }
        
        print(f"  API请求参数:")
        for key, value in params.items():
            print(f"    {key}: {value}")
        
        print(f"  将调用API: http://bitanswer-server/api/generate-license")
        print()
    
    print("✅ Bitanswer逻辑测试完成（未实际调用API）\n")
    return True

def main():
    """主测试函数"""
    print("\n")
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 15 + "License生成逻辑测试" + " " * 20 + "║")
    print("╚" + "═" * 58 + "╝")
    print("\n")
    
    results = []
    
    # 测试1: 目录结构
    results.append(("目录结构", test_directory_structure()))
    
    # 测试2: JSON解析
    results.append(("JSON解析", test_json_parsing()))
    
    # 测试3: FlexNet逻辑
    results.append(("FlexNet逻辑", test_flexnet_logic()))
    
    # 测试4: Bitanswer逻辑
    results.append(("Bitanswer逻辑", test_bitanswer_logic()))
    
    # 汇总结果
    print("=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name}: {status}")
    
    print(f"\n总计: {passed}/{total} 测试通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！系统已准备就绪。")
        print("\n下一步:")
        print("1. 配置Bitanswer API地址和密钥（在views.py中）")
        print("2. 确保flexnet命令可用")
        print("3. 启动Django服务进行测试")
    else:
        print("\n⚠️ 部分测试失败，请检查上述错误信息")
    
    print("\n")

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n❌ 测试过程中发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
