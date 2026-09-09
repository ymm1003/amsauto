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
    def __init__(self, config_path=None):
        if config_path is None:
            config_path = self.get_config_path()
        self.log_file = None
        self.log_level = 'INFO'
        self.config = {}
        self.logger = None
        self.users_path = self._get_users_path()
        self.users = []
        self.load_config(config_path)
        self.session = requests.Session()
        self.setup_logging()
        self.load_users()
        self.last_executed = {}

    def _get_users_path(self):
        for i, arg in enumerate(sys.argv):
            if arg in ['-u', '--users'] and i + 1 < len(sys.argv):
                return sys.argv[i + 1]
        users_file = self.export_config.get('usersFile') if hasattr(self, 'export_config') else None
        if users_file:
            base_dir = os.path.dirname(self.get_config_path())
            users_path = users_file if os.path.isabs(users_file) else os.path.join(base_dir, users_file)
            if os.path.exists(users_path):
                return users_path
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_dir, 'users.json')

    def get_config_path(self):
        for i, arg in enumerate(sys.argv):
            if arg in ['-c', '--config'] and i + 1 < len(sys.argv):
                return sys.argv[i + 1]
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_dir, 'config.json')

    def load_config(self, config_path):
        self.logger = logging.getLogger('ReportExportTool')
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers = []

        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        self.a_config = self.config['aSystem']
        self.b_config = self.config['bSystem']
        self.schedule = self.config.get('schedule', {})
        self.export_config = self.config.get('reportExport', {})
        self.log_level = self.config.get('logLevel', 'INFO').upper()

    def setup_logging(self):
        log_dir = self.config.get('logPath', './logs')
        if getattr(sys, 'frozen', False):
            log_dir = os.path.join(os.path.dirname(sys.executable), 'logs')
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
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        self.a_config = self.config['aSystem']
        self.b_config = self.config['bSystem']
        self.schedule = self.config.get('schedule', {})
        self.export_config = self.config.get('reportExport', {})
        self.log_level = self.config.get('logLevel', 'INFO').upper()
        self.logger.setLevel(self.log_level)

        log_dir = self.config.get('logPath', './logs')
        if getattr(sys, 'frozen', False):
            log_dir = os.path.join(os.path.dirname(sys.executable), 'logs')
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
            if getattr(sys, 'frozen', False):
                save_dir = os.path.join(os.path.dirname(sys.executable), os.path.basename(save_dir))
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
        for task_cfg in tasks:
            result = self.export_one(task_cfg, b_cookie, begin_date, end_date)
            if result:
                success_count += 1
            else:
                fail_count += 1
            time.sleep(2)

        self.logger.info(f"导出完成: 成功 {success_count}, 失败 {fail_count}")
        return success_count, fail_count

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

    if args.users:
        sys.argv.extend(['-u', args.users])

    tool = ReportExportTool(config_path=args.config)
    if args.now:
        tool.logger.info("立即执行一次导出测试")
        tool.run_export()
    else:
        tool.run_schedule()


if __name__ == "__main__":
    main()
