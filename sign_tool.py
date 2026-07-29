import requests
import json
import time
from datetime import datetime
import os
import sys
import logging
import warnings

warnings.filterwarnings('ignore')

def get_config_path():
    for i, arg in enumerate(sys.argv):
        if arg in ['-c', '--config'] and i + 1 < len(sys.argv):
            return sys.argv[i + 1]

    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
        config_path = os.path.join(base_dir, 'config.json')
    else:
        config_path = 'config.json'

    if not os.path.exists(config_path):
        print(f"[ERROR] 配置文件不存在: {config_path}")
        print(f"[INFO] 使用 -c 或 --config 参数指定配置文件路径")
        sys.exit(1)

    return config_path

class AutoSignTool:
    def __init__(self, config_path=None):
        if config_path is None:
            config_path = get_config_path()
        self.log_file = None
        self.log_level = 'INFO'
        self.config = {}
        self.logger = None
        self.load_config(config_path)
        self.session = requests.Session()
        self.setup_logging()
        self.last_executed = {}

    def reload_config(self):
        config_path = get_config_path()
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        self.a_config = self.config['aSystem']
        self.b_config = self.config['bSystem']
        self.users = self.config['users']
        self.schedule = self.config.get('schedule', {})
        self.log_level = self.config.get('logLevel', 'INFO').upper()
        self.logger.setLevel(self.log_level)
        self.logger.info(f"配置已重新加载，用户数量: {len(self.users)}, 配置文件: {config_path}")

    def is_workday(self):
        now = datetime.now()
        if now.weekday() >= 5:
            return False
        holidays = self.config.get('holidays', [])
        if now.strftime('%Y-%m-%d') in holidays:
            return False
        return True

    def load_config(self, config_path):
        self.logger = logging.getLogger('AutoSignTool')
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers = []

        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        self.a_config = self.config['aSystem']
        self.b_config = self.config['bSystem']
        self.users = self.config['users']
        self.schedule = self.config.get('schedule', {})
        self.log_level = self.config.get('logLevel', 'INFO').upper()

    def setup_logging(self):
        log_dir = self.config.get('logPath', './logs')
        if getattr(sys, 'frozen', False):
            log_dir = os.path.join(os.path.dirname(sys.executable), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        self.log_file = os.path.join(log_dir, f"sign_{datetime.now().strftime('%Y%m%d')}.log")

        file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)

        console_handler = logging.StreamHandler()
        console_handler.setLevel(self.log_level)
        console_formatter = logging.Formatter('[%(levelname)s] %(message)s')
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)

        self.logger.setLevel(self.log_level)
        self.logger.info(f"日志文件: {self.log_file}")
        self.logger.info(f"日志级别: {self.log_level}")
        self.logger.info(f"配置文件加载完成，A系统地址: {self.a_config['baseUrl']}")
        self.logger.info(f"B系统地址: {self.b_config['baseUrl']}")
        self.logger.info(f"签退接口: {self.b_config['signOutPath']}")
        self.logger.info(f"用户数量: {len(self.users)}")
        self.logger.info(f"Token长度: {len(self.a_config.get('token', ''))}")

    def get_headers(self, need_x_router=False):
        headers = {
            "Content-Type": "application/json",
            "Cookie": f"z4a-web-token={self.a_config['token']}",
            "User-Agent": "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 Chrome/94.0.4606.71 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Origin": self.a_config['baseUrl'],
            "Referer": self.a_config['baseUrl'],
            "brower-type": "chrome",
            "cip": "",
            "responseType": "post",
            "tenantId": "1",
            "webToken": self.a_config['token'],
            "X-Frame-Options": "SAMEORIGIN",
            "sec-ch-ua": '"Chromium";v="94", "Google Chrome";v="94", ";Not A Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "showLoading": "false"
        }
        if need_x_router:
            headers["x-router"] = "https://10.210.112.223/appResource/v1/#/appResource/appResLogin"
        return headers

    def debug_request(self, step_name, url, headers, payload):
        self.logger.debug(f"========== {step_name} ==========")
        self.logger.debug(f"URL: {url}")
        self.logger.debug(f"Headers: {json.dumps(headers, ensure_ascii=False)}")
        self.logger.debug(f"Payload: {json.dumps(payload, ensure_ascii=False)}")
        self.logger.debug(f"----------------------------------")

    def debug_response(self, step_name, status_code, response_text, cookies):
        self.logger.debug(f"Status: {status_code}")
        self.logger.debug(f"Response: {response_text[:500] if response_text else 'Empty'}")
        self.logger.debug(f"Cookies: {dict(cookies)}")
        self.logger.debug(f"========== {step_name} END ==========")

    def step1_match_path(self, sub_acct_no):
        self.logger.debug(f"====== Step 1: /authn/sso/matchPath ======")
        try:
            url = f"{self.a_config['baseUrl']}/authn/sso/matchPath"
            headers = self.get_headers()
            payload = {
                "appCode": "SXNGAMS",
                "slaveAccount": sub_acct_no
            }
            self.debug_request("Step1", url, headers, payload)

            response = requests.post(url, headers=headers, json=payload, timeout=30, verify=False)
            self.debug_response("Step1", response.status_code, response.text, response.cookies)

            return response.json() if response.status_code == 200 else None
        except Exception as e:
            self.logger.debug(f"Step1 异常: {str(e)}")
            return None

    def step2_trigger_login(self):
        self.logger.debug(f"====== Step 2: /ais/configure/web/controller/gold/trigger/login ======")
        try:
            url = f"{self.a_config['baseUrl']}/ais/configure/web/controller/gold/trigger/login"
            headers = self.get_headers()
            headers["notVaultAction"] = "true"
            payload = {
                "serviceId": "AISIAM",
                "resType": "1",
                "mainLoginName": "9243b1aea8a88cde6a8b27e01b0f15fa"
            }
            self.debug_request("Step2", url, headers, payload)

            response = requests.post(url, headers=headers, json=payload, timeout=30, verify=False)
            self.debug_response("Step2", response.status_code, response.text, response.cookies)

            return response.json() if response.status_code == 200 else None
        except Exception as e:
            self.logger.debug(f"Step2 异常: {str(e)}")
            return None

    def jump_to_b_system(self, sub_acct_id, sub_acct_no):
        self.logger.info("=============================================")
        self.logger.info(f"开始处理用户: {sub_acct_no}")
        self.logger.info(f"SubAcctId: {sub_acct_id}")
        self.logger.info("=============================================")

        try:
            self.logger.debug("---- 执行前置步骤 ----")

            result1 = self.step1_match_path(sub_acct_no)
            self.logger.debug(f"Step1 返回: {result1}")
            time.sleep(0.5)

            result2 = self.step2_trigger_login()
            self.logger.debug(f"Step2 返回: {result2}")
            time.sleep(0.5)

            self.logger.debug("---- 执行最终跳转 ----")

            url = f"{self.a_config['baseUrl']}{self.a_config['jumpPath']}"
            headers = self.get_headers(need_x_router=True)

            payload = {
                "loginUrl": f"{self.b_config['baseUrl']}/dcits/auto4Alogin",
                "subAcctId": sub_acct_id,
                "subAcctNo": sub_acct_no,
                "appCode": "SXNGAMS",
                "appId": "702480616213505",
                "browser": "1",
                "dataStamp": int(time.time() * 1000),
                "terminalInfo": {
                    "address": [{
                        "ipv4": "",
                        "ipv6": "",
                        "mac": ""
                    }]
                },
                "transferUrl": f"{self.a_config['baseUrl']}{self.a_config['transferPath']}"
            }

            self.debug_request("FinalJump", url, headers, payload)
            self.logger.debug("发送最终跳转请求...")

            response = requests.post(url, headers=headers, json=payload, timeout=30, verify=False)
            self.debug_response("FinalJump", response.status_code, response.text, response.cookies)

            cookies = response.cookies
            self.logger.debug(f"所有Cookie: {dict(cookies)}")

            b_cookie = cookies.get("JSESSIONID", "")
            if not b_cookie:
                self.logger.debug("未从直接响应获取到JSESSIONID，尝试从返回data中提取URL...")
                try:
                    resp_data = response.json()
                    if resp_data.get('code') == '000000' and resp_data.get('data'):
                        b_login_url = resp_data['data']
                        self.logger.debug(f"B系统登录URL: {b_login_url}")

                        self.logger.debug("使用Session访问B系统登录URL...")
                        b_session = requests.Session()

                        self.logger.debug("Step A: GET请求B系统登录URL...")
                        b_get_resp = b_session.get(b_login_url, timeout=30, verify=False, allow_redirects=True)
                        self.logger.debug(f"GET响应状态码: {b_get_resp.status_code}")
                        self.logger.debug(f"GET响应Cookie: {dict(b_session.cookies)}")
                        self.logger.debug(f"GET响应最终URL: {b_get_resp.url}")
                        self.logger.debug(f"GET响应内容前200字符: {b_get_resp.text[:200]}")

                        b_cookie = b_session.cookies.get("JSESSIONID", "")

                        if not b_cookie:
                            self.logger.debug("GET未获取到Cookie，尝试POST请求...")
                            b_post_resp = b_session.post(b_login_url, timeout=30, verify=False, allow_redirects=True, data={})
                            self.logger.debug(f"POST响应状态码: {b_post_resp.status_code}")
                            self.logger.debug(f"POST响应Cookie: {dict(b_session.cookies)}")
                            self.logger.debug(f"POST响应内容前200字符: {b_post_resp.text[:200]}")
                            b_cookie = b_session.cookies.get("JSESSIONID", "")

                        if b_cookie:
                            self.logger.info(f"成功获取B系统Cookie: {b_cookie[:30]}...")
                            return b_cookie

                except Exception as e:
                    self.logger.debug(f"提取或访问B系统URL失败: {str(e)}")
                    import traceback
                    self.logger.debug(f"详细异常: {traceback.format_exc()}")

                self.logger.error(f"用户 {sub_acct_no} 未获取到B系统Cookie，跳转失败")
                return None

            self.logger.info(f"成功获取B系统Cookie: {b_cookie[:30]}...")
            return b_cookie

        except Exception as e:
            self.logger.error(f"用户 {sub_acct_no} 跳转B系统异常: {str(e)}")
            import traceback
            self.logger.debug(f"详细异常: {traceback.format_exc()}")
            return None

    def sign_in(self, sub_acct_id, sub_acct_no, b_cookie):
        self.logger.info("====== 签到操作 ======")
        try:
            url = f"{self.b_config['baseUrl']}/dcits/userloginrec/userloginrec/checkin"
            headers = {
                "Cookie": f"JSESSIONID={b_cookie}",
                "X-Requested-With": "XMLHttpRequest",
                "User-Agent": "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 Chrome/83.0.4103.115 Safari/537.36 Qaxbrowser"
            }

            self.logger.debug(f"URL: {url}")
            self.logger.debug(f"Cookie: JSESSIONID={b_cookie[:30]}...")

            response = requests.post(url, headers=headers, timeout=30, verify=False)
            self.logger.debug(f"响应状态码: {response.status_code}")
            self.logger.debug(f"响应内容: {response.text}")

            if response.status_code == 200:
                self.logger.info(f"用户 {sub_acct_no} 签到成功: {response.text}")
                return True
            else:
                self.logger.error(f"用户 {sub_acct_no} 签到失败: HTTP {response.status_code}")
                return False

        except Exception as e:
            self.logger.error(f"用户 {sub_acct_no} 签到异常: {str(e)}")
            return False

    def sign_out(self, sub_acct_id, sub_acct_no, b_cookie):
        self.logger.info("====== 签退操作 ======")
        try:
            url = f"{self.b_config['baseUrl']}{self.b_config['signOutPath']}"
            headers = {
                "Cookie": f"JSESSIONID={b_cookie}",
                "X-Requested-With": "XMLHttpRequest",
                "User-Agent": "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 Chrome/83.0.4103.115 Safari/537.36 Qaxbrowser"
            }

            self.logger.debug(f"URL: {url}")
            self.logger.debug(f"Cookie: JSESSIONID={b_cookie[:30]}...")

            response = requests.post(url, headers=headers, timeout=30, verify=False)
            self.logger.debug(f"响应状态码: {response.status_code}")
            self.logger.debug(f"响应内容: {response.text}")

            result = response.text
            self.logger.info(f"用户 {sub_acct_no} 签退结果: {result}")
            return True

        except Exception as e:
            self.logger.error(f"用户 {sub_acct_no} 签退异常: {str(e)}")
            return False

    def process_user_sign_in(self, user):
        sub_acct_id = user['subAcctId']
        sub_acct_no = user['subAcctNo']
        self.logger.info(f"用户 {sub_acct_no} 开始签到（跳转B系统）")

        b_cookie = self.jump_to_b_system(sub_acct_id, sub_acct_no)
        if not b_cookie:
            return False

        return self.sign_in(sub_acct_id, sub_acct_no, b_cookie)

    def process_user_sign_out(self, user):
        sub_acct_id = user['subAcctId']
        sub_acct_no = user['subAcctNo']
        self.logger.info(f"用户 {sub_acct_no} 开始处理签退")

        b_cookie = self.jump_to_b_system(sub_acct_id, sub_acct_no)
        if not b_cookie:
            return False

        return self.sign_out(sub_acct_id, sub_acct_no, b_cookie)

    def run_single_round(self, round_name="", mode="signin"):
        action = "签到" if mode == "signin" else "签退"
        start_time = datetime.now()
        self.logger.info(f"{'='*60}")
        self.logger.info(f"{action}第 {round_name} 执行 - {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info(f"待处理人数: {len(self.users)}")
        self.logger.info(f"{'='*60}")

        success_count = 0
        fail_count = 0

        for idx, user in enumerate(self.users, 1):
            user_start = datetime.now()
            self.logger.info(f"[进度] 当前: {idx}/{len(self.users)}")

            if mode == "signin":
                if self.process_user_sign_in(user):
                    success_count += 1
                else:
                    fail_count += 1
            else:
                if self.process_user_sign_out(user):
                    success_count += 1
                else:
                    fail_count += 1

            user_end = datetime.now()
            self.logger.debug(f"[进度] 用户处理耗时: {(user_end - user_start).seconds}秒")
            time.sleep(1)

        end_time = datetime.now()
        self.logger.info(f"{'='*60}")
        self.logger.info(f"{action}第 {round_name} 执行完成")
        self.logger.info(f"成功: {success_count}, 失败: {fail_count}")
        self.logger.info(f"总耗时: {(end_time - start_time).seconds}秒")
        self.logger.info(f"{'='*60}")
        return success_count, fail_count

    def run_schedule(self):
        self.logger.info(f"{'='*60}")
        self.logger.info(f"自动签到签退工具启动（定时模式）")
        self.logger.info(f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info(f"{'='*60}")

        schedules = self.schedule.get('tasks', [])

        if not schedules:
            self.logger.warning("没有配置定时任务，程序退出")
            sys.exit(0)

        for task in schedules:
            mode = task.get('mode', 'signout')
            action = "签到" if mode == "signin" else "签退"
            rounds = task.get('rounds', 1)
            times = task.get('times', [])
            self.logger.info(f"[定时任务] {task.get('name', '未命名')} - {action}")
            self.logger.info(f"  - 触发时间: {times}")
            self.logger.info(f"  - 执行轮数: {rounds}")

        self.logger.info(f"[INFO] 定时监控已启动，按 Ctrl+C 停止")
        self.logger.info(f"[INFO] 每30秒检查一次时间...\n")

        while True:
            now = datetime.now()
            current_time = now.strftime('%H:%M')

            for task in schedules:
                times = task.get('times', [])
                rounds = task.get('rounds', 1)
                task_name = task.get('name', '未命名')
                mode = task.get('mode', 'signout')
                task_key = f"{task_name}_{current_time}"

                if task_key in self.last_executed:
                    continue

                for target_time in times:
                    if current_time == target_time:
                        if not self.is_workday():
                            self.logger.info(f"跳过非工作日执行: {current_time}")
                            break
                        action = "签到" if mode == "signin" else "签退"
                        self.reload_config()
                        self.logger.info(f"{'='*60}")
                        self.logger.info(f"[触发] 定时任务: {task_name}")
                        self.logger.info(f"[触发] 触发时间: {current_time}")
                        self.logger.info(f"[触发] 动作: {action}")
                        self.logger.info(f"{'='*60}")

                        self.last_executed[task_key] = True

                        for round_num in range(1, rounds + 1):
                            self.logger.info(f"\n>>> 第 {round_num}/{rounds} 轮开始 <<<")
                            self.run_single_round(f"第{round_num}轮", mode)
                            self.logger.info(f">>> 第 {round_num}/{rounds} 轮结束 <<<\n")

                        break

            time.sleep(30)

if __name__ == "__main__":
    tool = AutoSignTool()
    tool.run_schedule()
