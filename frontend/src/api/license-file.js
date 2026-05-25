/**
 * License 文件处理 API
 */
import { ajaxPost } from './request'

/**
 * 扫描目录中的 TXT/JSON 文件（手动触发）
 */
export function scanTxtFiles() {
  return ajaxPost('/lylicense/application/scan_txt_files/')
}

/**
 * 启动文件监听器（自动监听）
 */
export function startFileWatcher() {
  return ajaxPost('/lylicense/application/start_file_watcher/')
}

/**
 * 解析并生成 License
 * @param {number} id - 申请记录 ID
 */
export function parseAndGenerate(id) {
  return ajaxPost(`/lylicense/application/${id}/parse_and_generate/`)
}
