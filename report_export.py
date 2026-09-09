import requests
import json
import random
import time
from datetime import datetime, timedelta
import os
import sys
import logging
import urllib.parse

try:
    from sign_tool import AutoSignTool, get_config_path
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from sign_tool import AutoSignTool, get_config_path

warnings_msg = None
import warnings
warnings.filterwarnings('ignore')


class ReportExportTool(AutoSignTool):
    def __init__(self, config_path=None, users_path=None):
        if config_path is None:
            config_path = self.get_config_path()
        self.log_file = None
        self.log_level = 'INFO'
        self.config = {}
        self.logger = None
        self._users_path_override = users_path
        self.users_path = self._get_users_path()
        self.users = []
        self.load_config(config_path)
        self.session = requests.Session()
        self.setup_logging()
        self.load_users()
        self.last_executed = {}

    def _get_base_dir(self):
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

    def _get_users_path(self):
        if getattr(self, '_users_path_override', None):
            return self._users_path_override

        for i, arg in enumerate(sys.argv):
            if arg in ['-u', '--users'] and i + 1 < len(sys.argv):
                return sys.argv[i + 1]

        users_path = os.path.join(self._get_base_dir(), 'users.json')

        if not os.path.exists(users_path):
            print(f"[ERROR] 用户文件不存在: {users_path}")
            print(f"[INFO] 使用 -u 或 --users 参数指定用户文件路径")
            sys.exit(1)

        return users_path

    def get_config_path(self):
        for i, arg in enumerate(sys.argv):
            if arg in ['-c', '--config'] and i + 1 < len(sys.argv):
                return sys.argv[i + 1]

        config_path = os.path.join(self._get_base_dir(), 'config.json')

        if not os.path.exists(config_path):
            print(f"[ERROR] 配置文件不存在: {config_path}")
            sys.exit(1)

        return config_path

    @staticmethod
    def _read_json_file(file_path):
        for enc in ('utf-8-sig', 'utf-8', 'gbk', 'gb18030'):
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    return json.load(f)
            except UnicodeDecodeError:
                continue
        raise ValueError(f"无法解析文件编码: {file_path}")

    def load_config(self, config_path):
        self.logger = logging.getLogger('ReportExportTool')
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers = []

        self.config = self._read_json_file(config_path)
        self.a_config = self.config['aSystem']
        self.b_config = self.config['bSystem']
        self.schedule = self.config.get('schedule', {})
        self.export_config = self.config.get('reportExport', {})
        self.log_level = self.config.get('logLevel', 'INFO').upper()

    def setup_logging(self):
        log_dir = self.config.get('logPath', './logs')
        if not os.path.isabs(log_dir):
            log_dir = os.path.join(self._get_base_dir(), log_dir)
        os.makedirs(log_dir, exist_ok=True)
        self.log_file = os.path.join(log_dir, f"report_{datetime.now().strftime('%Y%m%d')}.log")

        file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)

        console_handler = logging.StreamHandler()
        console_handler.setLevel(self.log_level)
        console_formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)

        self.logger.setLevel(self.log_level)
        self.logger.info(f"日志文件: {self.log_file}")
        self.logger.info(f"报表导出工具初始化，用户数量: {len(self.users)}")

    def reload_config(self):
        config_path = self.get_config_path()
        self.users_path = self._get_users_path()
        self.config = self._read_json_file(config_path)
        self.a_config = self.config['aSystem']
        self.b_config = self.config['bSystem']
        self.schedule = self.config.get('schedule', {})
        self.export_config = self.config.get('reportExport', {})
        self.log_level = self.config.get('logLevel', 'INFO').upper()
        self.logger.setLevel(self.log_level)

        log_dir = self.config.get('logPath', './logs')
        if not os.path.isabs(log_dir):
            log_dir = os.path.join(self._get_base_dir(), log_dir)
        os.makedirs(log_dir, exist_ok=True)
        new_log_file = os.path.join(log_dir, f"report_{datetime.now().strftime('%Y%m%d')}.log")

        if new_log_file != self.log_file:
            for handler in self.logger.handlers[:]:
                if isinstance(handler, logging.FileHandler):
                    self.logger.removeHandler(handler)
            self.log_file = new_log_file
            file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            file_formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)

        self.load_users()
        self.logger.info(f"配置已重新加载，用户数量: {len(self.users)}, 配置文件: {config_path}")

    def get_export_user(self):
        target = self.export_config.get('exportUser')
        if not target:
            target = 'yanmm'
        for u in self.users:
            if u.get('subAcctNo') == target:
                return u
        self.logger.warning(f"配置的导出账号 {target} 不在用户列表中，使用第一个用户")
        return self.users[0]

    def build_list_params(self, task_cfg, begin_date, end_date):
        params = {
            'wfinstcode': '',
            'A_applyer_id': '',
            'wfinstname': '',
            'a_firstreqperson': '',
            'wfinststate': '',
            'orgname': '',
            'A_resource': '',
            'A_begindate1': begin_date,
            'A_begindate2': end_date,
            'costdepartment': '',
            'costorgcode': '',
            'a_onlinedate1': '',
            'a_onlinedate2': '',
            'jcstime1': '',
            'jcstime2': '',
            'ordertype': '',
            'kforgname': '',
            'kforgcode': '',
            'satisfactionsCore': '',
            'A_firstreqperson_id': '',
            'a_contract': '',
            'c_system': '',
            'openable': '',
            'BigDataDev': '',
        }
        extra = task_cfg.get('listParams', {})
        if extra:
            params.update(extra)
        return params

    def build_develop_params(self, task_cfg):
        params = {
            'wfinststate': '',
            'wfinstcode': '',
            'wfinstname': '',
            'dResolver': '',
            'productLine': '',
        }
        extra = task_cfg.get('listParams', {})
        if extra:
            params.update(extra)
        return params

    def export_one(self, task_cfg, b_cookie, begin_date, end_date):
        task_name = task_cfg.get('name', '未命名')
        base_url = self.b_config['baseUrl']

        if task_cfg.get('type') == 'developsubtask':
            list_url = f"{base_url}/dcits/task/report/businessdevelopsubtask/developsubtask/list"
            export_url = f"{base_url}/dcits/task/report/businessdevelopsubtask/developsubtask/export"
            referer = f"{base_url}/dcits/task/report/businessdevelopsubtask/developsubtask"
            params = self.build_develop_params(task_cfg)
        else:
            list_url = f"{base_url}/dcits/task/report/DemandRepairOrder/DemandRepairOrder/list"
            export_url = f"{base_url}/dcits/task/report/DemandRepairOrder/DemandRepairOrder/export"
            referer = f"{base_url}/dcits/task/report/DemandRepairOrder/DemandRepairOrder"
            params = self.build_list_params(task_cfg, begin_date, end_date)

        headers = {
            "Cookie": f"JSESSIONID={b_cookie}",
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": "Mozilla/5.0 (Windows NT 6.1; ) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.115 Safari/537.36 Qaxbrowser",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Origin": base_url,
            "Referer": referer,
        }

        self.logger.info(f"[{task_name}] 步骤1: 调用导出接口获取文件名")
        try:
            resp = requests.post(export_url, headers=headers, data=params, timeout=60, verify=False)
            self.logger.debug(f"[{task_name}] export响应状态码: {resp.status_code}")
            self.logger.debug(f"[{task_name}] export响应内容: {resp.text[:500]}")

            if resp.status_code != 200:
                self.logger.error(f"[{task_name}] 导出接口请求失败: HTTP {resp.status_code}")
                return None

            result = resp.json()
            if result.get('code') != 0:
                self.logger.error(f"[{task_name}] 导出接口返回失败: {result}")
                return None

            file_name = result.get('msg')
            if not file_name:
                self.logger.error(f"[{task_name}] 导出接口未返回文件名: {result}")
                return None

            self.logger.info(f"[{task_name}] 获取到文件名: {file_name}")
        except Exception as e:
            self.logger.error(f"[{task_name}] 调用导出接口异常: {str(e)}")
            return None

        self.logger.info(f"[{task_name}] 步骤2: 下载文件")
        try:
            download_url = f"{base_url}/dcits/common/download"
            download_headers = dict(headers)
            download_headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9"
            download_headers["Upgrade-Insecure-Requests"] = "1"

            resp = requests.get(
                download_url,
                headers=download_headers,
                params={"fileName": file_name, "delete": "true"},
                timeout=120,
                verify=False,
                stream=True
            )
            self.logger.debug(f"[{task_name}] download响应状态码: {resp.status_code}")
            self.logger.debug(f"[{task_name}] download响应头: {dict(resp.headers)}")

            if resp.status_code != 200:
                self.logger.error(f"[{task_name}] 下载失败: HTTP {resp.status_code}")
                return None

            content_type = resp.headers.get('Content-Type', '')
            if 'json' in content_type:
                self.logger.error(f"[{task_name}] 下载返回JSON(可能是错误): {resp.text[:300]}")
                return None

            save_dir = self.export_config.get('savePath', './export')
            if not os.path.isabs(save_dir):
                save_dir = os.path.join(self._get_base_dir(), save_dir)
            os.makedirs(save_dir, exist_ok=True)

            original_name = file_name
            if '_' in original_name:
                original_name = original_name.split('_', 1)[1]
            stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            save_name = f"{task_name}_{stamp}_{urllib.parse.unquote(original_name)}"
            save_path = os.path.join(save_dir, save_name)

            with open(save_path, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            file_size = os.path.getsize(save_path)
            if file_size < 100:
                self.logger.error(f"[{task_name}] 下载的文件过小({file_size}字节)，可能失败: {save_path}")
                return None

            self.logger.info(f"[{task_name}] 下载成功: {save_path} ({file_size}字节)")
            return save_path

        except Exception as e:
            self.logger.error(f"[{task_name}] 下载文件异常: {str(e)}")
            return None

    def run_export(self):
        tasks = self.export_config.get('tasks', [])
        if not tasks:
            self.logger.warning("没有配置导出任务")
            return 0, 0

        user = self.get_export_user()
        sub_acct_no = user.get('subAcctNo')
        self.logger.info(f"使用账号: {sub_acct_no} 导出报表")

        end_date = datetime.now().strftime('%Y-%m-%d')
        days = int(self.export_config.get('dateRangeDays', 30))
        begin_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        self.logger.info(f"日期范围: {begin_date} ~ {end_date}")

        b_cookie = self.jump_to_b_system(user['subAcctId'], sub_acct_no)
        if not b_cookie:
            self.logger.error(f"账号 {sub_acct_no} 获取B系统Cookie失败，导出中止")
            return 0, len(tasks)

        success_count = 0
        fail_count = 0
        order_file = None
        subtask_file = None
        for task_cfg in tasks:
            result = self.export_one(task_cfg, b_cookie, begin_date, end_date)
            if result:
                success_count += 1
                if task_cfg.get('type') == 'developsubtask':
                    subtask_file = result
                else:
                    order_file = result
            else:
                fail_count += 1
            time.sleep(2)

        self.logger.info(f"导出完成: 成功 {success_count}, 失败 {fail_count}")

        if order_file and subtask_file:
            self.logger.info("开始合并工单与子任务文件...")
            try:
                merged = self.merge_reports(order_file, subtask_file)
                if merged:
                    self.logger.info(f"合并完成: {merged}")
            except Exception as e:
                self.logger.error(f"合并文件异常: {str(e)}", exc_info=True)

        return success_count, fail_count

    @staticmethod
    def _col_num(letter):
        n = 0
        for c in letter.upper():
            n = n * 26 + ord(c) - 64
        return n

    def merge_reports(self, order_file, subtask_file):
        try:
            from openpyxl import Workbook
        except ImportError:
            self.logger.error("未安装openpyxl，无法执行合并")
            return None

        ORDER_COLS = ['A', 'B', 'F', 'G', 'H', 'J', 'K', 'L', 'O', 'P', 'Q', 'S', 'T', 'U',
                      'AA', 'AB', 'AA-AB', 'AF', 'AG']
        ORDER_KEYWORD_COL = 'R'
        KEYWORD = '思特奇'

        self.logger.info(f"读取工单文件: {order_file}")
        order_data = self._read_xlsx_rows(order_file)
        if not order_data:
            self.logger.error("工单文件无数据")
            return None

        self.logger.info(f"读取子任务文件: {subtask_file}")
        subtask_data = self._read_xlsx_rows(subtask_file, all_sheets=True)
        if not subtask_data:
            self.logger.error("子任务文件无数据")
            return None

        wb = Workbook()
        ws = wb.active
        ws.title = "工单与子任务合并"

        all_rows = []

        order_header = order_data[0]
        subtask_header = subtask_data[0]

        merged_header = []
        for c in ORDER_COLS:
            if c == 'AA-AB':
                merged_header.append("剩余工作量（人天）")
            else:
                merged_header.append(order_header[self._col_num(c) - 1])
        for c in ['D', 'E', 'F', 'G']:
            merged_header.append(subtask_header[self._col_num(c) - 1])
        ws.append(merged_header)
        all_rows.append(merged_header)

        g_col = self._col_num('G') - 1
        r_col = self._col_num(ORDER_KEYWORD_COL) - 1

        subtask_map = {}
        for row in subtask_data[1:]:
            name = row[3]
            if not name:
                continue
            name = str(name).strip()
            if '-思特奇-' in name:
                key = name.split('-思特奇-', 1)[0].strip()
                subtask_map.setdefault(key, []).append(row)

        matched_rows = 0
        matched_orders = 0

        for row in order_data[1:]:
            def cell(idx):
                return row[idx] if idx < len(row) else None

            vendor = cell(r_col)
            if not vendor or KEYWORD not in str(vendor):
                continue

            aa = self._to_num(cell(self._col_num('AA') - 1))
            ab = self._to_num(cell(self._col_num('AB') - 1))
            diff = aa - ab if (aa is not None and ab is not None) else None

            out = []
            for c in ORDER_COLS:
                if c == 'AA-AB':
                    out.append(diff)
                else:
                    out.append(cell(self._col_num(c) - 1))

            g_name = str(cell(g_col) or '').strip()
            sub_rows = subtask_map.get(g_name, [])

            if sub_rows:
                matched_orders += 1
                for srow in sub_rows:
                    data_row = out + [srow[self._col_num(c) - 1] for c in ['D', 'E', 'F', 'G']]
                    ws.append(data_row)
                    all_rows.append(data_row)
                    matched_rows += 1
            else:
                data_row = out + [None, None, None, None]
                ws.append(data_row)
                all_rows.append(data_row)

        save_dir = self.export_config.get('savePath', './export')
        if not os.path.isabs(save_dir):
            save_dir = os.path.join(self._get_base_dir(), save_dir)
        os.makedirs(save_dir, exist_ok=True)
        date_str = datetime.now().strftime('%Y%m%d')
        merged_path = os.path.join(save_dir, f"需求报工完成分析@{date_str}.xlsx")
        wb.save(merged_path)

        self.logger.info(f"合并统计: 思特奇工单 {matched_orders} 条(不重复需求), 匹配子任务 {matched_rows} 行写入")

        html_all = self._generate_html(all_rows, f"需求报工完成分析@{date_str}", stats={
            "需求总数": len(all_rows) - 1,
            "匹配子任务行": matched_rows,
            "未找到子任务需求数量": (len(all_rows) - 1) - matched_rows,
        })
        html_all_path = os.path.join(save_dir, f"需求报工完成分析@{date_str}.html")
        with open(html_all_path, 'w', encoding='utf-8') as f:
            f.write(html_all)
        self.logger.info(f"HTML已生成: {html_all_path}")

        return merged_path

    def _generate_html(self, rows, title, stats=None):
        import html as html_mod

        def esc(v):
            if v is None:
                return ''
            return html_mod.escape(str(v))

        header = rows[0] if rows else []
        body_rows = rows[1:] if rows else []

        stat_html = ''
        if stats:
            items = ''.join(
                f'<div class="stat"><span class="num">{v}</span><span class="label">{esc(k)}</span></div>'
                for k, v in stats.items()
            )
            stat_html = f'<div class="stats">{items}</div>'

        summary_html = self._build_summary_html(body_rows)

        th = ''.join(f'<th>{esc(h)}</th>' for h in header)
        trs = []
        for row in body_rows:
            tds = []
            for i, v in enumerate(row):
                if v is None or v == '':
                    tds.append('<td class="empty">-</td>')
                else:
                    css = ' num-cell' if isinstance(v, (int, float)) else ''
                    tds.append(f'<td class="{css.strip()}">{esc(v)}</td>')
            trs.append('<tr>' + ''.join(tds) + '</tr>')
        table_body = '\n'.join(trs)

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{esc(title)}</title>
<style>
* {{ box-sizing: border-box; }}
body {{ font-family: "Microsoft YaHei", "PingFang SC", sans-serif; margin: 0; background: #f5f7fa; color: #333; }}
.container {{ padding: 20px; }}
h1 {{ font-size: 20px; margin: 0 0 12px; }}
.stats {{ display: flex; gap: 16px; margin-bottom: 16px; flex-wrap: wrap; }}
.stat {{ background: #fff; border-radius: 8px; padding: 10px 20px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
.stat .num {{ font-size: 22px; font-weight: bold; color: #1677ff; margin-right: 8px; }}
.stat .label {{ font-size: 13px; color: #666; }}
.table-wrap {{ background: #fff; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,.08); overflow: auto; max-height: calc(100vh - 140px); }}
table {{ border-collapse: collapse; font-size: 12px; white-space: nowrap; }}
th {{ position: sticky; top: 0; background: #1677ff; color: #fff; padding: 8px 10px; text-align: left; z-index: 2; }}
td {{ padding: 6px 10px; border-bottom: 1px solid #f0f0f0; }}
tr:hover td {{ background: #e6f4ff; }}
td.empty {{ color: #ccc; text-align: center; }}
td.num-cell {{ text-align: right; font-family: Consolas, monospace; }}
.search-bar {{ margin-bottom: 12px; }}
.search-bar input {{ width: 320px; padding: 8px 12px; border: 1px solid #d9d9d9; border-radius: 6px; font-size: 14px; }}
.search-bar input:focus {{ outline: none; border-color: #1677ff; }}
.summary {{ background: #fff; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,.08); margin-bottom: 16px; overflow: auto; }}
.summary h2 {{ font-size: 15px; margin: 0; padding: 12px 16px; border-bottom: 1px solid #f0f0f0; }}
.summary table {{ width: 100%; table-layout: fixed; }}
.summary th {{ position: static; background: #fafafa; color: #333; text-align: center; }}
.summary th:nth-child(1), .summary td:nth-child(1) {{ width: 11%; text-align: center; }}
.summary th:nth-child(2), .summary td:nth-child(2) {{ width: 12%; text-align: left; font-family: inherit; white-space: normal; word-break: break-all; }}
.summary th:nth-child(3), .summary td:nth-child(3) {{ width: 14%; text-align: right; }}
.summary th:nth-child(4), .summary td:nth-child(4) {{ width: 21%; text-align: right; }}
.summary th:nth-child(5), .summary td:nth-child(5) {{ width: 20%; text-align: right; }}
.summary th:nth-child(6), .summary td:nth-child(6) {{ width: 22%; text-align: right; }}
.summary tr:hover td {{ background: #e6f4ff; }}
.summary td {{ padding: 6px 10px; border-bottom: 1px solid #f0f0f0; font-family: Consolas, monospace; white-space: nowrap; }}
.summary td:nth-child(2) {{ white-space: normal; font-family: inherit; }}
.summary .subtotal td {{ background: #f0f7ff; font-weight: bold; border-top: 2px solid #1677ff; }}
.summary .no-subtask td:nth-child(2) {{ color: #e6a23c; }}
</style>
</head>
<body>
<div class="container">
<h1>{esc(title)}</h1>
{stat_html}
{summary_html}
<div class="search-bar"><input type="text" id="kw" placeholder="输入关键字过滤..." oninput="filterRows(this.value)"></div>
<div class="table-wrap">
<table id="tbl">
<thead><tr>{th}</tr></thead>
<tbody>
{table_body}
</tbody>
</table>
</div>
</div>
<script>
function filterRows(kw) {{
  kw = kw.trim().toLowerCase();
  const rows = document.querySelectorAll('#tbl tbody tr');
  let visible = 0;
  rows.forEach(r => {{
    const show = !kw || r.textContent.toLowerCase().includes(kw);
    r.style.display = show ? '' : 'none';
    if (show) visible++;
  }});
  document.getElementById('cnt').textContent = visible;
}}
</script>
</body>
</html>"""

    @staticmethod
    def _to_num(v):
        if v is None or v == '':
            return None
        try:
            return float(str(v).strip())
        except (ValueError, TypeError):
            return None

    def _build_summary_html(self, body_rows):
        """按B列(排期月份,空不统计)归并到年月分组，组内按V列(产品线)细分，汇总O/P/Q三列求和"""
        import html as html_mod
        import re as re_mod

        def esc(v):
            return html_mod.escape(str(v)) if v is not None else ''

        IDX_B, IDX_O, IDX_P, IDX_Q, IDX_V = 1, 14, 15, 16, 21

        def fmt(v):
            if v is None:
                return '-'
            if isinstance(v, float) and v == int(v):
                return str(int(v))
            return f"{v:.2f}".rstrip('0').rstrip('.')

        def to_ym(raw):
            """把排期月份归并到年月: 2026-08-17/2026/8/17/20260817 → 2026-08"""
            s = str(raw).strip()
            m = re_mod.match(r'^(\d{4})[-/年.](\d{1,2})', s)
            if m:
                return f"{m.group(1)}-{int(m.group(2)):02d}"
            m = re_mod.match(r'^(\d{4})(\d{2})(\d{2})$', s)
            if m:
                return f"{m.group(1)}-{m.group(2)}"
            m = re_mod.match(r'^(\d{6})$', s)
            if m:
                return f"{m.group(1)[:4]}-{m.group(1)[4:]}"
            return s

        groups = {}
        for row in body_rows:
            month = row[IDX_B] if IDX_B < len(row) else None
            if month is None or str(month).strip() == '':
                continue
            ym = to_ym(month)
            product = row[IDX_V] if IDX_V < len(row) else None
            if not product or not str(product).strip():
                product = '未找到子任务'

            def num(idx):
                v = row[idx] if idx < len(row) else None
                return self._to_num(v) or 0.0

            g = groups.setdefault(ym, {})
            s = g.setdefault(product, [0.0, 0.0, 0.0, 0])
            s[0] += num(IDX_O)
            s[1] += num(IDX_P)
            s[2] += num(IDX_Q)
            s[3] += 1

        if not groups:
            return ''

        parts = ['<div class="summary"><h2>按年月×产品线 汇总分析</h2><table>',
                 '<thead><tr><th>年月</th><th>产品线</th><th>需求数</th>'
                 '<th>开发工作量(人天)</th><th>报工时长(人天)</th><th>剩余工作量(人天)</th></tr></thead><tbody>']

        for month in sorted(groups.keys(), reverse=True):
            prods = groups[month]
            subtotal = [0.0, 0.0, 0.0, 0]
            for product in sorted(prods.keys()):
                o, p, q, n = prods[product]
                subtotal[0] += o; subtotal[1] += p; subtotal[2] += q; subtotal[3] += n
                cls = ' class="no-subtask"' if product == '未找到子任务' else ''
                parts.append(f'<tr{cls}><td>{esc(month)}</td><td>{esc(product)}</td><td>{n}</td>'
                             f'<td>{fmt(o)}</td><td>{fmt(p)}</td><td>{fmt(q)}</td></tr>')
            parts.append(f'<tr class="subtotal"><td>{esc(month)}</td><td>小计</td><td>{subtotal[3]}</td>'
                         f'<td>{fmt(subtotal[0])}</td><td>{fmt(subtotal[1])}</td><td>{fmt(subtotal[2])}</td></tr>')

        parts.append('</tbody></table></div>')
        return '\n'.join(parts)

    def _read_xlsx_rows(self, file_path, all_sheets=False):
        try:
            from openpyxl import load_workbook
        except ImportError:
            self.logger.error("未安装openpyxl")
            return None

        def read_sheet(ws):
            out = []
            for row in ws.iter_rows(values_only=True):
                out.append(list(row))
            return out

        def merge_sheets(wb):
            sheet_names = wb.sheetnames
            rows = []
            if all_sheets and len(sheet_names) > 1:
                self.logger.info(f"文件包含{len(sheet_names)}个sheet: {sheet_names}，全部读取")
                for sn in sheet_names:
                    data = read_sheet(wb[sn])
                    if not data:
                        self.logger.warning(f"sheet[{sn}]无数据，跳过")
                        continue
                    if rows and data and data[0] == rows[0]:
                        data = data[1:]
                    rows.extend(data)
            else:
                rows = read_sheet(wb.active)
            return rows

        rows = []
        try:
            wb = load_workbook(file_path, read_only=True, data_only=True)
            rows = merge_sheets(wb)
            wb.close()

            # 该导出文件dimension标记为A1:A1导致read_only只读到表头，需普通模式重读
            if len(rows) <= 2:
                self.logger.debug(f"read_only模式读到的行数过少({len(rows)})，改用普通模式重读")
                rows = []
                wb = load_workbook(file_path, data_only=True)
                rows = merge_sheets(wb)
                wb.close()
        except Exception as e:
            self.logger.error(f"读取xlsx失败 {file_path}: {str(e)}")
            return None

        if not rows:
            return None

        width = max(len(r) for r in rows)
        rows = [r + [None] * (width - len(r)) if len(r) < width else r for r in rows]
        return rows

    def _shift_time(self, base_time, offset_minutes):
        try:
            t = datetime.strptime(base_time, '%H:%M') + timedelta(minutes=offset_minutes)
            return t.strftime('%H:%M')
        except Exception as e:
            self.logger.error(f"时间偏移计算失败: {base_time}, 偏移: {offset_minutes}, 错误: {str(e)}")
            return base_time

    def is_export_day(self):
        now = datetime.now()
        if now.weekday() >= 5:
            return False
        holidays = self.config.get('holidays', [])
        if now.strftime('%Y-%m-%d') in holidays:
            return False
        return True

    def run_schedule(self):
        export_times = self.export_config.get('times', ["08:00"])
        base_time = export_times[0] if export_times else "08:00"

        self.logger.info(f"{'=' * 60}")
        self.logger.info(f"报表自动导出工具启动（定时模式）")
        self.logger.info(f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info(f"每日执行时间: {base_time}（随机偏移5-10分钟）")
        self.logger.info(f"导出任务数: {len(self.export_config.get('tasks', []))}")
        self.logger.info(f"{'=' * 60}")

        last_date = None
        today_time = None

        while True:
            try:
                now = datetime.now()
                current_time = now.strftime('%H:%M')
                current_date = now.strftime('%Y-%m-%d')

                if last_date != current_date:
                    last_date = current_date
                    offset = random.randint(5, 10)
                    today_time = self._shift_time(base_time, offset)
                    self.logger.info(f"[当日排程] {current_date} 基准 {base_time} 偏移 {offset:+d} 分钟 -> 实际 {today_time}")

                if current_time == today_time and self.last_executed.get(current_date) != current_time:
                    if not self.is_export_day():
                        self.logger.info("非工作日，跳过导出")
                        self.last_executed[current_date] = current_time
                    else:
                        self.reload_config()
                        self.logger.info(f"[触发] 报表导出开始: {current_time}")
                        self.last_executed[current_date] = current_time
                        try:
                            self.run_export()
                        except Exception as e:
                            self.logger.error(f"导出执行异常: {str(e)}", exc_info=True)
                        self.logger.info("[触发] 报表导出结束")

                self.logger.info(f"[心跳] 监控中 {now.strftime('%Y-%m-%d %H:%M:%S')}")
            except Exception as e:
                self.logger.error(f"定时循环异常: {str(e)}", exc_info=True)

            time.sleep(30)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='报表自动导出工具')
    parser.add_argument('-c', '--config', help='配置文件路径', default=None)
    parser.add_argument('-u', '--users', help='用户配置文件路径', default=None)
    parser.add_argument('--now', action='store_true', help='立即执行一次导出')
    args = parser.parse_args()

    tool = ReportExportTool(config_path=args.config, users_path=args.users)
    if args.now:
        tool.logger.info("立即执行一次导出测试")
        tool.run_export()
    else:
        tool.run_schedule()


if __name__ == "__main__":
    main()
