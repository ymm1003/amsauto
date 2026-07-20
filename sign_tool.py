import requests
import json
import time
from datetime import datetime
import os
import sys

def get_resource_path(relative_path):
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

class AutoSignTool:
    def __init__(self, config_path=None):
        if config_path is None:
            config_path = get_resource_path('config.json')
        self.load_config(config_path)
        self.session = requests.Session()
        self.setup_logging()

    def load_config(self, config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        self.a_config = self.config['aSystem']
        self.b_config = self.config['bSystem']
        self.users = self.config['users']

    def setup_logging(self):
        log_dir = self.config.get('logPath', './logs')
        if getattr(sys, 'frozen', False):
            log_dir = os.path.join(os.path.dirname(sys.executable), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        self.log_file = os.path.join(log_dir, f"sign_{datetime.now().strftime('%Y%m%d')}.log")

    def log(self, user_no, message, status="INFO"):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_msg = f"[{timestamp}] [{status}] [{user_no}] {message}"
        print(log_msg)
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_msg + '\n')

    def jump_to_b_system(self, sub_acct_id, sub_acct_no):
        try:
            url = f"{self.a_config['baseUrl']}{self.a_config['jumpPath']}"
            headers = {
                "Content-Type": "application/json",
                "Cookie": f"z4a-web-token={self.a_config['token']}",
                "User-Agent": "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 Chrome/94.0.4606.71 Safari/537.36"
            }
            payload = {
                "loginUrl": f"{self.b_config['baseUrl']}/dcits/auto4Alogin",
                "subAcctId": sub_acct_id,
                "subAcctNo": sub_acct_no,
                "appCode": "SXGAMS",
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

            response = requests.post(url, headers=headers, json=payload, timeout=30)
            cookies = response.cookies

            b_cookie = cookies.get("JSESSIONID", "")
            if not b_cookie:
                return None
            return b_cookie

        except Exception as e:
            self.log(sub_acct_no, f"跳转B系统失败: {str(e)}", "ERROR")
            return None

    def sign_out(self, sub_acct_id, sub_acct_no, b_cookie):
        try:
            url = f"{self.b_config['baseUrl']}{self.b_config['signOutPath']}"
            headers = {
                "Content-Type": "application/json",
                "Cookie": f"JSESSIONID={b_cookie}",
                "User-Agent": "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 Chrome/94.0.4606.71 Safari/537.36"
            }

            response = requests.post(url, headers=headers, json={}, timeout=30)
            result = response.text

            self.log(sub_acct_no, f"签退结果: {result}", "SUCCESS")
            return True

        except Exception as e:
            self.log(sub_acct_no, f"签退失败: {str(e)}", "ERROR")
            return False

    def process_user(self, user):
        sub_acct_id = user['subAcctId']
        sub_acct_no = user['subAcctNo']

        self.log(sub_acct_no, "开始处理签退")

        b_cookie = self.jump_to_b_system(sub_acct_id, sub_acct_no)
        if not b_cookie:
            return False

        return self.sign_out(sub_acct_id, sub_acct_no, b_cookie)

    def run(self):
        print(f"{'='*50}")
        print(f"自动签退工具启动 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"待处理人数: {len(self.users)}")
        print(f"{'='*50}")

        success_count = 0
        fail_count = 0

        for user in self.users:
            if self.process_user(user):
                success_count += 1
            else:
                fail_count += 1
            time.sleep(1)

        print(f"{'='*50}")
        print(f"处理完成 - 成功: {success_count}, 失败: {fail_count}")
        print(f"{'='*50}")

if __name__ == "__main__":
    tool = AutoSignTool()
    tool.run()