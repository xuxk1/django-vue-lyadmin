import json
import re
import os
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from pathlib import Path
import pymysql
from pymysql.cursors import DictCursor


class LicenseFieldMapping:
    """许可证字段映射处理类"""

    # 字段分类定义 - 映射到field_type
    FIELD_TYPE_MAPPING = {
        'feature': 'Feature',  # numberField_ 开头
        'customer': 'CustomerInfo',  # 客户信息
        'applicant': 'ApplicantInfo',  # 申请人信息
    }

    def __init__(self, db_config: Dict):
        """
        初始化数据库连接

        Args:
            db_config: 数据库配置字典，包含 host, port, user, password, database
        """
        self.db_config = db_config
        self.connection = None

    def connect(self):
        """建立数据库连接"""
        try:
            self.connection = pymysql.connect(
                host=self.db_config.get('host', 'localhost'),
                port=self.db_config.get('port', 3306),
                user=self.db_config['user'],
                password=self.db_config['password'],
                database=self.db_config['database'],
                charset='utf8mb4',
                cursorclass=DictCursor,
                autocommit=False
            )
            print("数据库连接成功")
        except Exception as e:
            print(f"数据库连接失败: {e}")
            raise

    def close(self):
        """关闭数据库连接"""
        if self.connection:
            self.connection.close()
            print("数据库连接已关闭")

    def classify_field(self, key: str) -> Tuple[str, str, str, bool]:
        """
        根据key分类字段类型

        Args:
            key: JSON中的键名

        Returns:
            (license_type, user_type, field_type, is_feature) 元组
            is_feature: 是否为feature类型，用于判断real_key的处理方式
        """
        license_type = 'FlexNet'
        user_type = '外部'  # 固定为外部
        field_type = 'Common'  # 默认为Common
        is_feature = False

        # 检查是否是feature (numberField_ 开头)
        if re.match(r'^numberField_', key):
            field_type = 'Feature'
            is_feature = True
        # 检查是否是客户信息 (以 selectField_/dateField_/textField_ 开头且包含 mdy73q6)
        elif re.match(r'^(selectField_|dateField_|textField_)mdy73q6', key):
            field_type = 'CustomerInfo'
        # 检查是否是申请人信息 (以特定前缀开头且包含 me87gr)
        elif re.match(
                r'^(textField_|dateField_|departmentSelectField_|employeeField_|radioField_|serialNumberField_)me87gr',
                key):
            field_type = 'ApplicantInfo'

        return license_type, user_type, field_type, is_feature

    def parse_json_data(self, json_data: Dict) -> List[Dict]:
        """
        解析JSON数据，提取需要插入的字段映射

        Args:
            json_data: JSON数据字典

        Returns:
            字段映射列表
        """
        mappings = []

        # 需要跳过的字段（不写入数据库）
        skip_keys = ['LicenseType', 'Usage']

        for key, value in json_data.items():
            # 跳过特殊字段
            if key in skip_keys:
                continue

            # 分类字段
            license_type, user_type, field_type, is_feature = self.classify_field(key)

            # 只处理已知类型的字段
            if field_type in ['Feature', 'CustomerInfo', 'ApplicantInfo']:
                # 处理real_key：feature类型使用对应的值，其他类型先不处理
                if is_feature:
                    real_key = value  # feature类型使用对应的值
                else:
                    real_key = self.extract_real_key(key)  # 其他类型先用简化后的key

                mapping = {
                    'license_type': license_type,
                    'user_type': user_type,  # 固定为'外部'
                    'field_type': field_type,
                    'field': key,
                    'name': value,
                    'real_key': real_key,
                    'is_deleted': False,
                    'description': f"{field_type}字段映射",
                    'modifier': None,
                    'dept_belong_id': None,
                    'creator_id': None
                }
                mappings.append(mapping)

                # 打印解析信息
                if is_feature:
                    print(f"解析字段: {key} -> {field_type} -> {value} (real_key: {real_key})")
                else:
                    print(f"解析字段: {key} -> {field_type} -> {value}")

        return mappings

    def extract_real_key(self, key: str) -> str:
        """
        提取真实的键名（去除前缀）

        Args:
            key: 原始键名

        Returns:
            简化后的键名
        """
        # 移除常见前缀
        prefixes = [
            'numberField_', 'selectField_', 'dateField_', 'textField_',
            'departmentSelectField_', 'employeeField_', 'radioField_',
            'serialNumberField_'
        ]

        for prefix in prefixes:
            if key.startswith(prefix):
                return key.replace(prefix, '', 1)

        return key

    def insert_mappings(self, mappings: List[Dict]) -> int:
        """
        插入字段映射到数据库

        Args:
            mappings: 字段映射列表

        Returns:
            插入的记录数
        """
        if not mappings:
            print("没有需要插入的数据")
            return 0

        insert_count = 0
        update_count = 0

        try:
            with self.connection.cursor() as cursor:
                # 使用 ON DUPLICATE KEY UPDATE
                insert_sql = """
                             INSERT INTO lylicense_field_mapping
                             (license_type, user_type, field_type, field, name, real_key, is_deleted,
                              description, modifier, dept_belong_id, creator_id, create_datetime, update_datetime)
                             VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON DUPLICATE KEY \
                             UPDATE \
                                 name = \
                             VALUES (name), real_key = \
                             VALUES (real_key), field_type = \
                             VALUES (field_type), description = \
                             VALUES (description), update_datetime = \
                             VALUES (update_datetime) \
                             """

                current_time = datetime.now()

                for mapping in mappings:
                    try:
                        cursor.execute(insert_sql, (
                            mapping['license_type'],
                            mapping['user_type'],
                            mapping['field_type'],
                            mapping['field'],
                            mapping['name'],
                            mapping['real_key'],
                            mapping['is_deleted'],
                            mapping['description'],
                            mapping['modifier'],
                            mapping['dept_belong_id'],
                            mapping['creator_id'],
                            current_time,
                            current_time
                        ))

                        if cursor.rowcount == 1:
                            insert_count += 1
                        elif cursor.rowcount == 2:
                            update_count += 1

                    except Exception as e:
                        print(f"插入失败 {mapping['field']}: {e}")
                        continue

                self.connection.commit()

        except Exception as e:
            print(f"批量插入失败: {e}")
            self.connection.rollback()
            raise

        print(f"\n插入完成: 新增 {insert_count} 条, 更新 {update_count} 条")
        return insert_count + update_count

    def insert_mappings_simple(self, mappings: List[Dict]) -> int:
        """
        简化版插入（使用 REPLACE INTO）

        Args:
            mappings: 字段映射列表

        Returns:
            插入的记录数
        """
        if not mappings:
            print("没有需要插入的数据")
            return 0

        insert_count = 0

        try:
            with self.connection.cursor() as cursor:
                insert_sql = """
                             REPLACE \
                             INTO lylicense_field_mapping 
                    (license_type, user_type, field_type, field, name, real_key, is_deleted, 
                     description, modifier, dept_belong_id, creator_id, create_datetime, update_datetime)
                    VALUES ( \
                             %s, \
                             %s, \
                             %s, \
                             %s, \
                             %s, \
                             %s, \
                             %s, \
                             %s, \
                             %s, \
                             %s, \
                             %s, \
                             %s, \
                             %s \
                             ) \
                             """

                current_time = datetime.now()

                for mapping in mappings:
                    try:
                        cursor.execute(insert_sql, (
                            mapping['license_type'],
                            mapping['user_type'],
                            mapping['field_type'],
                            mapping['field'],
                            mapping['name'],
                            mapping['real_key'],
                            mapping['is_deleted'],
                            mapping['description'],
                            mapping['modifier'],
                            mapping['dept_belong_id'],
                            mapping['creator_id'],
                            current_time,
                            current_time
                        ))
                        insert_count += 1
                    except Exception as e:
                        print(f"插入失败 {mapping['field']}: {e}")
                        continue

                self.connection.commit()

        except Exception as e:
            print(f"批量插入失败: {e}")
            self.connection.rollback()
            raise

        print(f"\n插入完成: 成功 {insert_count} 条")
        return insert_count

    def print_summary(self, mappings: List[Dict]):
        """
        打印解析结果摘要

        Args:
            mappings: 字段映射列表
        """
        print("\n" + "=" * 80)
        print("解析结果摘要")
        print("=" * 80)

        # 按类型分组统计
        stats = {}
        for mapping in mappings:
            field_type = mapping['field_type']
            stats[field_type] = stats.get(field_type, 0) + 1

        print("\n字段统计:")
        for field_type, count in stats.items():
            print(f"  {field_type}: {count} 个字段")

        print("\n详细列表:")
        for mapping in mappings:
            real_key_info = f" (real_key: {mapping['real_key']})" if mapping['field_type'] == 'Feature' else ""
            print(f"  [{mapping['field_type']:15s}] {mapping['field']:40s} -> {mapping['name']}{real_key_info}")

    def get_existing_mappings(self, license_type: str = None, field_type: str = None, user_type: str = None) -> List[
        Dict]:
        """
        查询已存在的映射

        Args:
            license_type: 许可证类型（可选）
            field_type: 字段类型（可选） Feature/CustomerInfo/ApplicantInfo/Common
            user_type: 用户类型（可选） 内部/外部

        Returns:
            映射列表
        """
        try:
            with self.connection.cursor() as cursor:
                sql = "SELECT * FROM lylicense_field_mapping WHERE is_deleted = 0"
                params = []

                if license_type:
                    sql += " AND license_type = %s"
                    params.append(license_type)

                if field_type:
                    sql += " AND field_type = %s"
                    params.append(field_type)

                if user_type:
                    sql += " AND user_type = %s"
                    params.append(user_type)

                sql += " ORDER BY id"

                cursor.execute(sql, params)
                results = cursor.fetchall()
                return results
        except Exception as e:
            print(f"查询失败: {e}")
            return []


class TxtJsonParser:
    """TXT文件JSON解析器"""

    @staticmethod
    def read_txt_file(file_path: str, encoding: str = 'utf-8') -> Optional[str]:
        """读取TXT文件内容"""
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
            print(f"成功读取文件: {file_path}")
            return content
        except UnicodeDecodeError:
            try:
                with open(file_path, 'r', encoding='gbk') as f:
                    content = f.read()
                print(f"使用GBK编码成功读取文件: {file_path}")
                return content
            except Exception as e:
                print(f"读取文件失败: {e}")
                return None
        except Exception as e:
            print(f"读取文件失败: {e}")
            return None

    @staticmethod
    def extract_json_from_txt(content: str) -> Optional[Dict]:
        """从TXT文件中提取JSON数据"""
        # 尝试直接解析
        try:
            json_data = json.loads(content)
            print("成功解析JSON数据")
            return json_data
        except json.JSONDecodeError:
            pass

        # 查找JSON对象
        json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        matches = re.findall(json_pattern, content, re.DOTALL)

        for match in matches:
            try:
                json_data = json.loads(match)
                print("成功从文本中提取JSON数据")
                return json_data
            except json.JSONDecodeError:
                continue

        print("未能从文本中提取有效的JSON数据")
        return None

    @staticmethod
    def process_txt_file(file_path: str, encoding: str = 'utf-8') -> Optional[Dict]:
        """处理单个TXT文件，提取JSON数据"""
        content = TxtJsonParser.read_txt_file(file_path, encoding)
        if not content:
            return None

        json_data = TxtJsonParser.extract_json_from_txt(content)
        return json_data


def process_license_data(txt_file_path: str, db_config: Dict,
                         auto_insert: bool = True,
                         encoding: str = 'utf-8') -> Tuple[List[Dict], bool]:
    """
    处理许可证数据：读取TXT -> 解析JSON -> 分类 -> 写入数据库

    Args:
        txt_file_path: TXT文件路径
        db_config: 数据库配置
        auto_insert: 是否自动插入数据库
        encoding: 文件编码

    Returns:
        (字段映射列表, 是否成功)
    """
    print("\n" + "=" * 80)
    print("开始处理许可证数据")
    print("=" * 80)

    # 步骤1：读取TXT文件并解析JSON
    print("\n步骤1: 读取TXT文件并解析JSON")
    print("-" * 40)

    json_data = TxtJsonParser.process_txt_file(txt_file_path, encoding)
    if not json_data:
        print("❌ 解析JSON失败")
        return [], False

    print(f"✅ 成功解析JSON，包含 {len(json_data)} 个字段")

    # 步骤2：分类解析JSON数据
    print("\n步骤2: 分类解析JSON数据")
    print("-" * 40)

    processor = LicenseFieldMapping(db_config)
    mappings = processor.parse_json_data(json_data)

    if not mappings:
        print("❌ 没有需要处理的字段")
        return [], False

    # 打印摘要
    processor.print_summary(mappings)

    # 步骤3：写入数据库
    if auto_insert:
        print("\n步骤3: 写入数据库")
        print("-" * 40)

        try:
            processor.connect()
            count = processor.insert_mappings(mappings)
            print(f"✅ 成功处理 {count} 条记录")
            return mappings, True
        except Exception as e:
            print(f"❌ 数据库操作失败: {e}")
            return mappings, False
        finally:
            processor.close()
    else:
        print("\n步骤3: 跳过数据库写入（auto_insert=False）")
        return mappings, True


# 使用示例
if __name__ == "__main__":
    # 1. 数据库配置
    db_config = {
        'host': 'localhost',
        'port': 3306,
        'user': 'root',
        'password': 'root123456',
        'database': 'lyadmin_db'
    }

    # 2. TXT文件路径
    txt_file_path = "C:\\Users\\xuxiaokui\\Downloads\\new.txt"

    # 3. 处理数据
    mappings, success = process_license_data(
        txt_file_path=txt_file_path,
        db_config=db_config,
        auto_insert=True,
        encoding='utf-8'
    )

    if success:
        print(f"\n✅ 处理完成，共解析 {len(mappings)} 个字段")

        # 4. 查询验证
        processor = LicenseFieldMapping(db_config)
        processor.connect()

        print("\n查询已插入的数据（user_type=外部）:")

        # 查询Feature类型
        features = processor.get_existing_mappings(license_type='FlexNet', field_type='Feature', user_type='外部')
        print(f"\nFeature字段数量: {len(features)}")
        for f in features[:5]:
            print(f"  - {f['field']}: {f['name']} -> real_key: {f['real_key']}")

        # 查询CustomerInfo类型
        customers = processor.get_existing_mappings(license_type='FlexNet', field_type='CustomerInfo', user_type='外部')
        print(f"\nCustomerInfo字段数量: {len(customers)}")
        for c in customers[:5]:
            print(f"  - {c['field']}: {c['name']}")

        # 查询ApplicantInfo类型
        applicants = processor.get_existing_mappings(license_type='FlexNet', field_type='ApplicantInfo',
                                                     user_type='外部')
        print(f"\nApplicantInfo字段数量: {len(applicants)}")
        for a in applicants[:5]:
            print(f"  - {a['field']}: {a['name']}")

        processor.close()
    else:
        print("\n❌ 处理失败")