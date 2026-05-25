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

    # 用户类型映射（前端显示 -> 数据库值）
    USER_TYPE_MAPPING = {
        '内部': 'internal',
        '外部': 'external',
        'internal': 'internal',
        'external': 'external',
    }

    # License类型映射（前端显示 -> 数据库值）
    LICENSE_TYPE_MAPPING = {
        'FlexNet': 'flexnet',
        'Bitanswer': 'bitanswer',
        'flexnet': 'flexnet',
        'bitanswer': 'bitanswer',
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

    def classify_field(self, key: str, license_type: str = 'FlexNet', user_type: str = '外部') -> Tuple[str, str, str, bool]:
        """
        根据key分类字段类型

        Args:
            key: JSON中的键名
            license_type: License类型 (FlexNet/Bitanswer)
            user_type: 用户类型 (内部/外部)

        Returns:
            (license_type, user_type, field_type, is_feature) 元组
            is_feature: 是否为feature类型，用于判断real_key的处理方式
        """
        # 转换为用户类型数据库值
        user_type_db = self.USER_TYPE_MAPPING.get(user_type, 'external')

        # 转换为License类型数据库值
        license_type_db = self.LICENSE_TYPE_MAPPING.get(license_type, 'flexnet')

        field_type = 'common'  # 默认为Common
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

        return license_type_db, user_type_db, field_type, is_feature

    def parse_json_data(self, json_data: Dict, license_type: str = 'FlexNet', user_type: str = '外部', creator_id: int = None) -> List[Dict]:
        """
        解析JSON数据，提取需要插入的字段映射

        Args:
            json_data: JSON数据字典
            license_type: License类型 (FlexNet/Bitanswer)
            user_type: 用户类型 (内部/外部)，如果JSON中有Usage字段则优先使用
            creator_id: 创建人ID

        Returns:
            字段映射列表
        """
        mappings = []
        field_type_value = ''

        # 检查JSON中是否有Usage字段，如果有则覆盖传入的user_type参数
        if 'Usage' in json_data:
            usage_value = json_data['Usage']
            # 转换Usage值为数据库值
            user_type_from_json = self.USER_TYPE_MAPPING.get(usage_value, usage_value)
            print(f"✅ 检测到Usage字段: {usage_value} -> {user_type_from_json}")
            user_type = user_type_from_json

        for key, value in json_data.items():
            # 特殊处理LicenseType字段 - 映射到license_type
            if key == 'LicenseType':
                continue  # LicenseType是元数据，不需要作为字段映射存储

            # 分类字段
            license_type_db, user_type_db, field_type, is_feature = self.classify_field(key, license_type, user_type)

            # 只处理已知类型的字段
            if field_type in ['Feature', 'CustomerInfo', 'ApplicantInfo']:
                # 处理real_key：feature类型使用对应的值，其他类型查询数据库获取准确的real_key
                if is_feature:
                    real_key = value  # feature类型使用对应的值
                else:
                    # 其他类型从数据库查询real_key，需要匹配license_type和user_type
                    real_key = self.extract_real_key(key, license_type_db, user_type_db)
                
                # 设置field_type_value
                if field_type == 'Feature':
                    field_type_value = 'feature'
                elif field_type == 'CustomerInfo':
                    field_type_value = 'customer_info'
                elif field_type == 'ApplicantInfo':
                    field_type_value = 'applicant_info'
                
                mapping = {
                    'license_type': license_type_db,
                    'user_type': user_type_db,
                    'field_type': field_type_value,
                    'field': key,
                    'name': value,
                    'real_key': real_key,
                    'is_deleted': False,
                    'description': f"{field_type}字段映射",
                    'modifier': None,
                    'creator_id': str(creator_id) if creator_id else None  # 转换为字符串（UUID格式）
                }
                mappings.append(mapping)

                # 打印解析信息
                if is_feature:
                    print(f"解析字段: {key} -> {field_type} -> {value} (real_key: {real_key})")
                else:
                    print(f"解析字段: {key} -> {field_type} -> {value} (real_key: {real_key})")

        return mappings

    def extract_real_key(self, key: str, license_type: str = None, user_type: str = None) -> str:
        """
        提取真实的键名（去除前缀）

        Args:
            key: 原始键名
            license_type: License类型 (flexnet/bitanswer)
            user_type: 用户类型 (internal/external)

        Returns:
            简化后的键名或从数据库查询到的real_key
        """
        # 首先尝试从数据库查询准确的real_key
        if license_type and user_type:
            db_real_key = self.query_real_key_from_db(key, license_type, user_type)
            if db_real_key:
                print(f"✅ 从数据库查询到 {key} 的 real_key: {db_real_key}")
                return db_real_key
            else:
                print(f"⚠️ 数据库中未找到 {key} 的映射，使用默认规则")

        # 如果数据库中没有，使用默认规则处理
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

    def query_real_key_from_db(self, field: str, license_type: str, user_type: str) -> Optional[str]:
        """
        从数据库查询field对应的real_key

        Args:
            field: 原始字段名
            license_type: License类型 (flexnet/bitanswer)
            user_type: 用户类型 (internal/external)

        Returns:
            real_key值，如果不存在则返回None
        """
        try:
            with self.connection.cursor() as cursor:
                sql = """
                    SELECT real_key 
                    FROM lylicense_field_mapping 
                    WHERE field = %s 
                      AND license_type = %s 
                      AND user_type = %s 
                      AND is_deleted = 0
                    LIMIT 1
                """
                cursor.execute(sql, (field, license_type, user_type))
                result = cursor.fetchone()
                if result:
                    return result['real_key']
                return None
        except Exception as e:
            print(f"⚠️ 查询real_key失败: {e}")
            return None

    def get_admin_user_id(self) -> Optional[int]:
        """
        获取 admin 用户的 ID

        Returns:
            admin 用户 ID，如果不存在则返回 None
        """
        try:
            with self.connection.cursor() as cursor:
                # 正确的表名是 lyadmin_users
                cursor.execute("SELECT id FROM lyadmin_users WHERE username = 'admin' LIMIT 1")
                result = cursor.fetchone()
                if result:
                    print(f"✅ 找到 admin 用户，ID: {result['id']}")
                    return result['id']
                else:
                    print("⚠️ 未找到 admin 用户")
                    return None
        except Exception as e:
            print(f" 获取 admin 用户 ID 失败: {e}")
            return None


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
                              description, modifier, creator_id, create_datetime, update_datetime)
                             VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON DUPLICATE KEY \
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
                     description, modifier, creator_id, create_datetime, update_datetime)
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
            # 转换为显示名称
            field_type_display = {
                'feature': 'Feature',
                'customer_info': 'CustomerInfo',
                'applicant_info': 'ApplicantInfo',
                'common': 'Common'
            }.get(field_type, field_type)
            stats[field_type_display] = stats.get(field_type_display, 0) + 1

        print("\n字段统计:")
        for field_type, count in stats.items():
            print(f"  {field_type}: {count} 个字段")

        print("\n详细列表:")
        for mapping in mappings:
            field_type_display = {
                'feature': 'Feature',
                'customer_info': 'CustomerInfo',
                'applicant_info': 'ApplicantInfo',
                'common': 'Common'
            }.get(mapping['field_type'], mapping['field_type'])
            real_key_info = f" (real_key: {mapping['real_key']})" if mapping['field_type'] == 'feature' else ""
            print(f"  [{field_type_display:15s}] {mapping['field']:40s} -> {mapping['name']}{real_key_info}")

    def get_existing_mappings(self, license_type: str = None, field_type: str = None, user_type: str = None) -> List[
        Dict]:
        """
        查询已存在的映射

        Args:
            license_type: 许可证类型（可选）- flexnet/bitanswer
            field_type: 字段类型（可选）- feature/customer_info/applicant_info/common
            user_type: 用户类型（可选）- internal/external

        Returns:
            映射列表
        """
        try:
            with self.connection.cursor() as cursor:
                sql = "SELECT * FROM lylicense_field_mapping WHERE is_deleted = 0"
                params = []

                if license_type:
                    # 转换为数据库值
                    license_type_db = self.LICENSE_TYPE_MAPPING.get(license_type, license_type)
                    sql += " AND license_type = %s"
                    params.append(license_type_db)

                if field_type:
                    sql += " AND field_type = %s"
                    params.append(field_type)

                if user_type:
                    # 转换为数据库值
                    user_type_db = self.USER_TYPE_MAPPING.get(user_type, user_type)
                    sql += " AND user_type = %s"
                    params.append(user_type_db)

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
                         license_type: str = 'FlexNet',
                         user_type: str = '外部',
                         auto_insert: bool = True,
                         encoding: str = 'utf-8') -> Tuple[List[Dict], bool]:
    """
    处理许可证数据：读取TXT -> 解析JSON -> 分类 -> 写入数据库

    Args:
        txt_file_path: TXT文件路径
        db_config: 数据库配置
        license_type: License类型 (FlexNet/Bitanswer)
        user_type: 用户类型 (内部/external)，如果JSON中有Usage字段则优先使用
        auto_insert: 是否自动插入数据库
        encoding: 文件编码

    Returns:
        (字段映射列表, 是否成功)
    """
    # 转换传入的 license_type 为数据库值
    license_type_mapping = {
        'FlexNet': 'flexnet',
        'Bitanswer': 'bitanswer',
        'flexnet': 'flexnet',
        'bitanswer': 'bitanswer',
    }
    license_type_db = license_type_mapping.get(license_type, license_type)

    # 转换传入的 user_type 为数据库值（仅作为默认值）
    user_type_mapping = {
        '内部': 'internal',
        '外部': 'external',
        'internal': 'internal',
        'external': 'external',
    }
    user_type_db_default = user_type_mapping.get(user_type, user_type)

    print("\n" + "=" * 80)
    print("开始处理许可证数据")
    print(f"传入参数 - License类型: {license_type} -> {license_type_db}")
    print(f"传入参数 - 用户类型: {user_type} -> {user_type_db_default} (默认值)")
    print(f"⚠️  注意: 如果JSON中有Usage字段，将优先使用Usage的值")
    print(f"⚠️  支持四种场景: flexnet+internal, flexnet+external, bitanswer+internal, bitanswer+external")
    print("=" * 80)

    # 步骤1：读取TXT文件并解析JSON
    print("\n步骤1: 读取TXT文件并解析JSON")
    print("-" * 40)

    json_data = TxtJsonParser.process_txt_file(txt_file_path, encoding)
    if not json_data:
        print(" ️ 解析JSON失败")
        return [], False

    print(f"✅ 成功解析JSON，包含 {len(json_data)} 个字段")

    # 步骤2：分类解析JSON数据
    print("\n步骤2: 分类解析JSON数据")
    print("-" * 40)

    processor = LicenseFieldMapping(db_config)

    try:
        processor.connect()

        # 获取 admin 用户 ID
        admin_user_id = processor.get_admin_user_id()
        if not admin_user_id:
            print("⚠️  未找到 admin 用户，创建人字段将为空")
            print("⚠️  提示: 请确保数据库中存在 username='admin' 的用户")
            admin_user_id = None
        else:
            print(f"✅ 将使用 admin 用户 (ID: {admin_user_id}) 作为创建人")

        # 解析数据（使用转换后的数据库值，但parse_json_data会检测JSON中的Usage字段）
        mappings = processor.parse_json_data(json_data, license_type_db, user_type_db_default, admin_user_id)

        if not mappings:
            print("❌ 没有需要处理的字段")
            return [], False

        # 打印摘要
        processor.print_summary(mappings)

        # 步骤3：写入数据库
        if auto_insert:
            print("\n步骤4: 写入数据库")
            print("-" * 40)

            count = processor.insert_mappings(mappings)
            print(f"✅ 成功处理 {count} 条记录")
            return mappings, True
        else:
            print("\n步骤4: 跳过数据库写入（auto_insert=False）")
            return mappings, True

    except Exception as e:
        print(f"❌ 处理失败: {e}")
        return [], False
    finally:
        processor.close()


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
    txt_file_path = "C:\\Users\\xuxiaokui\\Downloads\\internalB.txt"

    # 3. 处理数据 - 示例1: FlexNet 外部用户
    print("\n" + "#" * 80)
    print("示例1: 处理 FlexNet - 外部用户 数据")
    print("#" * 80)

    mappings, success = process_license_data(
        txt_file_path=txt_file_path,
        db_config=db_config,
        license_type='Bitanswer',      # License类型: FlexNet 或 Bitanswer
        user_type='内部',             # 用户类型: 内部 或 外部
        auto_insert=True,            # 自动插入数据库
        encoding='utf-8'
    )

    if success:
        print(f"\n✅ 处理完成，共解析 {len(mappings)} 个字段")
    else:
        print("\n❌ 处理失败")

    # 示例2: 处理 Bitanswer 内部用户
    # print("\n" + "#" * 80)
    # print("示例2: 处理 Bitanswer - 内部用户 数据")
    # print("#" * 80)
    #
    # mappings, success = process_license_data(
    #     txt_file_path="C:\\Users\\xuxiaokui\\Downloads\\bitanswer.txt",
    #     db_config=db_config,
    #     license_type='Bitanswer',
    #     user_type='内部',
    #     auto_insert=True,
    #     encoding='utf-8'
    # )