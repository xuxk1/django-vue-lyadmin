"""
License 文件监听器
使用 watchdog 监听目录变化，自动处理新创建的 JSON/TXT 文件
"""
import os
import time
import logging
import sys
from pathlib import Path

# Windows系统下使用PollingObserver更稳定
if sys.platform == 'win32':
    from watchdog.observers.polling import PollingObserver as Observer
else:
    from watchdog.observers import Observer

from watchdog.events import FileSystemEventHandler

logger = logging.getLogger(__name__)


class LicenseFileHandler(FileSystemEventHandler):
    """License 文件事件处理器"""
    
    def __init__(self, process_callback=None):
        """
        初始化文件处理器
        
        Args:
            process_callback: 文件处理回调函数，接收文件路径作为参数
        """
        super().__init__()
        self.process_callback = process_callback
        self.processed_files = set()  # 记录已处理的文件，避免重复处理
    
    def on_created(self, event):
        """
        文件创建事件
        
        Args:
            event: 文件系统事件
        """
        if event.is_directory:
            logger.debug(f"忽略目录创建事件: {event.src_path}")
            return
        
        file_path = event.src_path
        logger.info(f"检测到文件创建事件: {file_path}")
        
        # 只处理 .txt 和 .json 文件
        if not (file_path.endswith('.txt') or file_path.endswith('.json')):
            logger.debug(f"忽略非目标文件: {file_path}")
            return
        
        logger.info(f"检测到新文件: {file_path}")
        
        # 延迟一下，确保文件写入完成
        time.sleep(2)
        
        # 检查文件是否已经处理过
        if file_path in self.processed_files:
            logger.warning(f"文件已处理过，跳过: {file_path}")
            return
        
        try:
            # 调用回调函数处理文件
            logger.info(f"准备调用回调函数处理文件: {file_path}")
            if self.process_callback:
                logger.info(f"回调函数存在，开始调用...")
                result = self.process_callback(file_path)
                logger.info(f"回调函数返回结果: {result}")
                if result:
                    self.processed_files.add(file_path)
                    logger.info(f"文件处理成功: {file_path}")
                else:
                    logger.error(f"文件处理失败: {file_path}")
            else:
                logger.warning("未设置文件处理回调函数")
        except Exception as e:
            logger.error(f"处理文件时出错 {file_path}: {str(e)}", exc_info=True)
    
    def on_modified(self, event):
        """
        文件修改事件（可选）
        
        Args:
            event: 文件系统事件
        """
        if event.is_directory:
            return
        
        file_path = event.src_path
        
        # 只处理 .txt 和 .json 文件
        if not (file_path.endswith('.txt') or file_path.endswith('.json')):
            return
        
        logger.info(f"检测到文件修改: {file_path}")


def start_file_watcher(watch_dir, process_callback, interval=1):
    """
    启动文件监听器
    
    Args:
        watch_dir: 监听的目录路径
        process_callback: 文件处理回调函数
        interval: 检查间隔（秒）
    
    Returns:
        Observer: 监听器对象
    """
    # 确保目录存在
    if not os.path.exists(watch_dir):
        os.makedirs(watch_dir)
        logger.info(f"创建监听目录: {watch_dir}")
    
    # 创建事件处理器
    event_handler = LicenseFileHandler(process_callback=process_callback)
    
    # 创建观察者
    observer = Observer()
    observer.schedule(event_handler, watch_dir, recursive=False)
    
    # 启动观察者
    observer.start()
    logger.info(f"文件监听器已启动，监听目录: {watch_dir}")
    
    try:
        while True:
            time.sleep(interval)
    except KeyboardInterrupt:
        observer.stop()
        logger.info("文件监听器已停止")
    
    observer.join()
    return observer


if __name__ == '__main__':
    # 测试代码
    def test_process_file(file_path):
        """测试文件处理函数"""
        print(f"处理文件: {file_path}")
        return True
    
    watch_dir = r"D:\eladmin\license_data"
    start_file_watcher(watch_dir, test_process_file)
