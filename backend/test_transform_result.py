import os
import sys
import json
from datetime import datetime
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'application.settings')
import django
django.setup()

from apps.lylicense.views import transform_json_with_mapping
from apps.lylicense.models import LicenseApplication, LicenseRecord
from django.conf import settings

def process_json_file(file_path):
    """
    处理单个 JSON 文件，解析并创建申请记录
    """
    print(f"\n{'='*80}")
    print(f"处理文件: {os.path.basename(file_path)}")
    print(f"{'='*80}")
    
    # 读取 JSON 文件
    with open(file_path, 'r', encoding='utf-8') as f:
        raw_json = json.load(f)
    
    # 获取 LicenseType
    license_type = raw_json.get('LicenseType', '').lower()
    usage = raw_json.get('Usage', '').lower()
    user_type = ''
    if usage:
        if usage == '内部':
            user_type = 'internal'
        elif usage == '外部':
            user_type = 'external'
    print(f"License 类型: {license_type}")
    
    # 调用转换函数
    result = transform_json_with_mapping(raw_json, license_type, user_type)
    transformed_data = result['transformed_data']
    features = result['features']
    feature_values = result['feature_values']
    
    # 从转换后的数据中提取关键字段
    applicant = ''
    customer_name = ''
    serial_number = ''
    mac_address = ''
    hostname = ''
    start_time = None
    end_time = None
    product = ''  # 产品名（使用第一个 feature）
    
    # 提取申请人
    if 'Applicant' in transformed_data:
        applicant_value = transformed_data['Applicant']
        if isinstance(applicant_value, list) and len(applicant_value) > 0:
            applicant = applicant_value[0]
        elif isinstance(applicant_value, str):
            applicant = applicant_value
    
    # 提取客户名称
    if 'CustomerName' in transformed_data:
        customer_name = str(transformed_data['CustomerName'])
    
    # 提取序列号
    if 'SerialNumber' in transformed_data:
        serial_number = str(transformed_data['SerialNumber'])
    
    # 提取 MAC 地址和主机名（从表格数据中）
    if 'UserInfo' in transformed_data or 'tableField_mdy73q6i' in transformed_data:
        table_key = 'UserInfo' if 'UserInfo' in transformed_data else 'tableField_mdy73q6i'
        table_data = transformed_data[table_key]
        
        if isinstance(table_data, list) and len(table_data) > 0:
            # 取第一行数据
            first_row = table_data[0]
            
            # 提取 MAC 地址（使用映射后的 real_key 或原始 key）
            if 'MacAddress' in first_row:
                mac_address = str(first_row['MacAddress'])
            elif 'textField_mdy73q6m' in first_row:
                mac_address = str(first_row['textField_mdy73q6m'])
            elif 'HostID' in first_row:
                mac_address = str(first_row['HostID'])
            
            # 提取主机名
            if 'HostName' in first_row:
                hostname = str(first_row['HostName'])
            elif 'Hostname' in first_row:
                hostname = str(first_row['Hostname'])
            elif 'textField_mdy73q6l' in first_row:
                hostname = str(first_row['textField_mdy73q6l'])
            
            # 提取开始时间
            if 'StartDate' in first_row:
                date_value = first_row['StartDate']
                if isinstance(date_value, (int, float)):
                    start_time = datetime.fromtimestamp(date_value / 1000)
            elif 'Startdate' in first_row:
                date_value = first_row['Startdate']
                if isinstance(date_value, (int, float)):
                    start_time = datetime.fromtimestamp(date_value / 1000)
            elif 'dateField_mdy73q6o' in first_row:
                date_value = first_row['dateField_mdy73q6o']
                if isinstance(date_value, (int, float)):
                    start_time = datetime.fromtimestamp(date_value / 1000)
            
            # 提取结束时间
            if 'ExpiryDate' in first_row:
                date_value = first_row['ExpiryDate']
                if isinstance(date_value, (int, float)):
                    end_time = datetime.fromtimestamp(date_value / 1000)
            elif 'Expirydate' in first_row:
                date_value = first_row['Expirydate']
                if isinstance(date_value, (int, float)):
                    end_time = datetime.fromtimestamp(date_value / 1000)
            elif 'dateField_mdy73q6p' in first_row:
                date_value = first_row['dateField_mdy73q6p']
                if isinstance(date_value, (int, float)):
                    end_time = datetime.fromtimestamp(date_value / 1000)
            
            # 提取产品名称（从表格中的 Feature 字段）
            if 'Product' in first_row:
                product = str(first_row['Product'])
            elif 'selectField_mdy73q6j' in first_row:
                product = str(first_row['selectField_mdy73q6j'])
    
    # 如果没有从表格中提取到时间，尝试从顶层字段提取
    if not start_time and 'ApplicationDate' in transformed_data:
        date_value = transformed_data['ApplicationDate']
        if isinstance(date_value, (int, float)):
            start_time = datetime.fromtimestamp(date_value / 1000)
    
    if not end_time and 'ExpiryDate' in transformed_data:
        date_value = transformed_data['ExpiryDate']
        if isinstance(date_value, (int, float)):
            end_time = datetime.fromtimestamp(date_value / 1000)
    
    # 提取 Feature 信息（如果表格中没有 Product）
    if not product and features:
        # 使用第一个 feature 作为产品名
        product = features[0]
    
    print(f"\n提取的关键字段:")
    print(f"  申请人: {applicant}")
    print(f"  客户名称: {customer_name}")
    print(f"  序列号: {serial_number}")
    print(f"  MAC地址: {mac_address}")
    print(f"  主机名: {hostname}")
    print(f"  产品: {product}")
    print(f"  开始时间: {start_time}")
    print(f"  结束时间: {end_time}")
    print(f"  Features: {features}")
    print(f"  Feature Values (Quantity): {feature_values}")
    
    # 创建申请记录
    try:
        application = LicenseApplication.objects.create(
            applicant=applicant or '未知申请人',
            application_type=license_type,
            feature=features if features else [],  # Feature 列表
            product=product or '',  # 产品名称
            serial_number=serial_number or '',  # 序列号
            customer_name=customer_name or '未指定客户',
            mac_address=mac_address or '未指定',
            hostname=hostname or '',  # 主机名
            start_time=start_time,
            end_time=end_time,
            quantity=feature_values if feature_values else {},  # Feature 数量字典，如 {"GloryEX": 10, "GloryEX_Basic": 5}
            json_data=raw_json,  # 保存原始 JSON
            status=3,  # 待制作
            max_retry_count=3
        )
        
        print(f"\n✅ 成功创建申请记录，ID: {application.id}")
        
        # 验证 quantity 字段是否正确写入
        print(f"\n{'='*80}")
        print(f"验证 quantity 字段:")
        print(f"{'='*80}")
        print(f"  写入的 quantity: {feature_values}")
        print(f"  类型: {type(feature_values)}")
        
        # 从数据库重新读取验证
        app_from_db = LicenseApplication.objects.get(id=application.id)
        print(f"\n  从数据库读取的 quantity: {app_from_db.quantity}")
        print(f"  类型: {type(app_from_db.quantity)}")
        
        # 验证每个 Feature 的数量
        if app_from_db.quantity and isinstance(app_from_db.quantity, dict):
            print(f"\n  ✅ Quantity 字段正确存储为字典格式")
            for feature_name, qty in app_from_db.quantity.items():
                print(f"     - {feature_name}: {qty}")
            
            # 验证是否与 feature_values 一致
            if app_from_db.quantity == feature_values:
                print(f"\n  ✅ 数据库中的 quantity 与 feature_values 完全一致")
            else:
                print(f"\n  ️  警告：数据库中的 quantity 与 feature_values 不一致")
                print(f"     预期: {feature_values}")
                print(f"     实际: {app_from_db.quantity}")
        else:
            print(f"\n  ❌ 错误：quantity 字段不是字典格式")
        
        print(f"{'='*80}")
        
        # 保存转换后的 JSON 到文件
        json_dir = os.path.join(settings.BASE_DIR, 'license_data')
        if not os.path.exists(json_dir):
            os.makedirs(json_dir)

        json_file_path = os.path.join(json_dir, f'{application.id}.json')
        with open(json_file_path, 'w', encoding='utf-8') as f:
            json.dump(transformed_data, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 转换后的 JSON 已保存到: {json_file_path}")
        
        return application
        
    except Exception as e:
        print(f"\n✗ 创建申请记录失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def test_license_record_date_format():
    """
    测试 LicenseRecord 的日期格式化功能
    验证写入数据库后，start_date_str 和 end_date_str 字段是否为"年月日"格式
    """
    print(f"\n{'='*80}")
    print(f"测试 LicenseRecord 日期格式化功能")
    print(f"{'='*80}")
    
    # 1. 检查是否有申请记录
    print("\n1. 检查申请记录...")
    applications = LicenseApplication.objects.all()[:1]
    
    if not applications.exists():
        print("   ⚠️  没有找到申请记录，无法创建测试数据")
        print("   提示: 需要先运行主函数创建申请记录")
        return False
    
    app = applications.first()
    print(f"   ✅ 使用申请记录 ID={app.id}, applicant='{app.applicant}'")
    
    # 2. 创建测试 LicenseRecord
    print("\n2. 创建测试 LicenseRecord...")
    try:
        import uuid
        test_license_id = f"TEST-DATE-{uuid.uuid4().hex[:8].upper()}"
        
        # 设置时间
        from datetime import datetime, timedelta
        start_time = datetime.now()
        end_time = start_time + timedelta(days=365)
        
        print(f"   开始时间 (原始): {start_time}")
        print(f"   过期时间 (原始): {end_time}")
        
        # 创建 LicenseRecord
        record = LicenseRecord.objects.create(
            application=app,
            license_id=test_license_id,
            license_type='flexnet',
            file_name='test_date_format.lic',
            file_relative_path='license/flexnet/test_date_format.lic',
            directory='/path/to/license',
            full_path='/path/to/license/test_date_format.lic',
            feature='TestFeature',
            vendor='TestVendor',
            version='1.0',
            host_id='AA:BB:CC:DD:EE:FF',
            start_time=start_time,
            end_time=end_time,
            quantity=1,
            status=1
        )
        
        print(f"   ✅ LicenseRecord 创建成功, ID={record.id}")
        print(f"   License ID: {record.license_id}")
        
    except Exception as e:
        print(f"   ❌ 创建失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 3. 验证日期格式化
    print("\n3. 验证日期格式化...")
    try:
        # 重新从数据库读取
        record.refresh_from_db()
        
        print(f"   start_time (原始): {record.start_time}")
        print(f"   start_date_str (格式化): {record.start_date_str}")
        print(f"   end_time (原始): {record.end_time}")
        print(f"   end_date_str (格式化): {record.end_date_str}")
        
        # 验证格式是否正确
        expected_start = start_time.strftime('%Y年%m月%d日')
        expected_end = end_time.strftime('%Y年%m月%d日')
        
        start_ok = record.start_date_str == expected_start
        end_ok = record.end_date_str == expected_end
        
        if start_ok:
            print(f"   ✅ start_date_str 格式正确: {record.start_date_str}")
        else:
            print(f"   ❌ start_date_str 格式错误")
            print(f"      期望: {expected_start}")
            print(f"      实际: {record.start_date_str}")
        
        if end_ok:
            print(f"   ✅ end_date_str 格式正确: {record.end_date_str}")
        else:
            print(f"   ❌ end_date_str 格式错误")
            print(f"      期望: {expected_end}")
            print(f"      实际: {record.end_date_str}")
        
        print(f"   剩余天数: {record.remaining_days}天")
        
        # 4. 模拟前端显示
        print("\n4. 模拟前端显示效果...")
        print(f"   表格列 - 开始时间: {record.start_date_str}")
        print(f"   表格列 - 过期时间: {record.end_date_str}")
        print(f"   详情对话框 - 开始时间: {record.start_date_str}")
        print(f"   详情对话框 - 过期时间: {record.end_date_str}")
        print(f"   ✅ 前端直接使用 start_date_str 和 end_date_str，无需额外格式化")
        
        # 清理测试数据
        print("\n5. 清理测试数据...")
        record.delete()
        print(f"   ✅ 测试记录已删除")
        
        return start_ok and end_ok
        
    except Exception as e:
        print(f"   ❌ 验证失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """
    主函数：扫描目录中的所有 JSON 文件并处理
    """
    # 固定目录
    json_dir = os.path.join(settings.JSON_FILE_PATH, 'json_file')
    
    print(f"\n扫描目录: {json_dir}")
    
    # 检查目录是否存在
    if not os.path.exists(json_dir):
        print(f" 目录不存在: {json_dir}")
        return
    
    # 扫描所有 JSON 文件
    json_files = [f for f in os.listdir(json_dir) if f.endswith('.json')]
    
    if not json_files:
        print("✗ 目录中没有找到 JSON 文件")
        return
    
    print(f"找到 {len(json_files)} 个 JSON 文件\n")
    
    # 处理每个文件
    success_count = 0
    error_count = 0
    
    for idx, json_file in enumerate(json_files, 1):
        print(f"\n[{idx}/{len(json_files)}] 处理文件: {json_file}")
        file_path = os.path.join(json_dir, json_file)
        
        try:
            result = process_json_file(file_path)
            if result:
                success_count += 1
            else:
                error_count += 1
        except Exception as e:
            print(f"✗ 处理文件失败: {str(e)}")
            import traceback
            traceback.print_exc()
            error_count += 1
    
    # 统计结果
    print(f"\n{'='*80}")
    print(f"处理完成！")
    print(f"  总文件数: {len(json_files)}")
    print(f"  成功: {success_count}")
    print(f"  失败: {error_count}")
    print(f"{'='*80}")


if __name__ == '__main__':
    # 首先运行日期格式化测试
    print("\n" + "="*80)
    print("开始测试 LicenseRecord 日期格式化功能")
    print("="*80)
    test_result = test_license_record_date_format()
    
    if test_result:
        print("\n✅ 日期格式化测试通过！")
    else:
        print("\n❌ 日期格式化测试失败！")
    
    # 然后运行主函数处理 JSON 文件
    print("\n" + "="*80)
    print("开始处理 JSON 文件")
    print("="*80)
    main()
