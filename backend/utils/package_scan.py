"""
包安全扫描 - 软件包文件操作工具

共享目录直接挂载/映射到后端服务器，基于本地文件系统（os/shutil）实现软件包
存在性检查、剪切到备份路径（目录按当天年月日创建 + 文件按"时间戳_包名"重命名）
与扫描报告 html 内容读取，复用 config 中的 PACKAGE_SCAN_SHARED_PATH /
PACKAGE_SCAN_BACKUP_PATH 路径配置。
"""
import logging
import os
import shutil
from datetime import datetime

import config

logger = logging.getLogger(__name__)


def file_exists(path):
    """
    判断路径是否存在（文件或目录，支持共享目录挂载/映射的本地绝对路径）

    Args:
        path: 软件包绝对路径

    Returns:
        True 存在；False 不存在或无法访问
    """
    try:
        return os.path.exists(path)
    except Exception as e:
        logger.warning(f"检查路径失败: {path}, 错误: {str(e)}")
        return False


def get_shared_package_path(package_name):
    """
    拼接"共享路径 + 软件包名称"并校验文件是否已就位

    Args:
        package_name: 软件包文件名（审批表单中填写的软件包名称）

    Returns:
        存在时返回绝对路径；不存在或校验失败返回 None
    """
    if not package_name or not package_name.strip():
        return None
    candidate = os.path.join(config.PACKAGE_SCAN_SHARED_PATH, package_name.strip())
    try:
        if file_exists(candidate):
            return candidate
        logger.info(f"共享路径中未找到软件包: {candidate}")
    except Exception as e:
        logger.warning(f"检查共享路径软件包失败: {candidate}, 错误: {str(e)}")
    return None


def resolve_backup_product_dir(product_names):
    """
    根据表单中选中的产品名解析备份目录名：与 config.PACKAGE_SCAN_PRODUCT_DIR_MAP 比较，
    任一命中（GloryEX 系列统一归入 GloryEX）即返回映射目录名，其余产品一对一（目录名即产品名）

    Args:
        product_names: 产品名（字符串或字符串列表，对应审批表单多选字段）

    Returns:
        产品目录名；未选择任何产品时返回 None（不创建产品目录）
    """
    if isinstance(product_names, str):
        # 多选值可能以逗号分隔字符串存储（如 'GloryEX3D, GloryPolaris, GloryEX'），先拆分再比较
        product_names = [
            part.strip() for part in product_names.replace('，', ',').replace('、', ',').split(',')
            if part.strip()
        ]
    fallback = None
    for name in product_names or []:
        name = (name or '').strip()
        if not name:
            continue
        # 与 config 映射比较（大小写不敏感）：任一命中即返回映射目录名，与勾选顺序无关
        for key, mapped in getattr(config, 'PACKAGE_SCAN_PRODUCT_DIR_MAP', {}).items():
            if key.lower() == name.lower():
                return mapped
        # 未命中映射的产品记录为兜底目录名（取第一个），继续检查后续产品是否命中映射
        if fallback is None:
            fallback = name
    return fallback


def _backup_to_dir(source_path, operation, product_dir=None):
    """
    按备份规则生成目标路径并执行文件操作：先按产品名创建目录（可选）、再按当天年月日创建目录，
    文件按"时间戳_包名"重命名

    Args:
        source_path: 源文件绝对路径
        operation: 文件操作函数（shutil.move 剪切 / shutil.copy2 复制），入参 (源路径, 目标路径)
        product_dir: 产品目录名（如 GloryEX）；为空时不创建产品目录，保持"备份路径/日期目录"结构

    Returns:
        操作后（重命名）的绝对路径；失败返回 None
    """
    try:
        package_name = os.path.basename(source_path.rstrip('/\\'))
        if not package_name:
            logger.error(f"备份软件包失败：无法从路径解析文件名: {source_path}")
            return None

        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        day_dir = datetime.now().strftime('%Y-%m-%d')
        if product_dir:
            target_dir = os.path.join(config.PACKAGE_SCAN_BACKUP_PATH, product_dir, day_dir)
        else:
            target_dir = os.path.join(config.PACKAGE_SCAN_BACKUP_PATH, day_dir)
        target_path = os.path.join(target_dir, f'{timestamp}_{package_name}')

        # 创建日期目录（幂等）后执行操作（剪切同一文件系统内为原子重命名，跨盘符自动复制+删除）
        os.makedirs(target_dir, exist_ok=True)
        operation(source_path, target_path)

        logger.info(f"软件包已备份: {target_path}")
        return target_path
    except Exception as e:
        logger.error(f"备份软件包到备份路径失败: {source_path}, 错误: {str(e)}")
        return None


def move_package_to_backup(source_path, product_dir=None):
    """
    将软件包剪切到备份路径：先按产品名创建目录（可选）、再按当天年月日创建目录，文件按"时间戳_包名"重命名

    Args:
        source_path: 源文件绝对路径（共享路径中的软件包）
        product_dir: 产品目录名（如 GloryEX）；为空时不创建产品目录

    Returns:
        剪切后（重命名）的绝对路径；失败返回 None
    """
    return _backup_to_dir(source_path, shutil.move, product_dir)


def read_file(path):
    """
    读取文本文件内容（如扫描报告 html）

    Args:
        path: 文件绝对路径

    Returns:
        文件文本内容；读取失败返回 None
    """
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except Exception as e:
        logger.warning(f"读取文件失败: {path}, 错误: {str(e)}")
        return None
