import requests
import json
import time
from datetime import datetime
import os
import sys

def get_config_path():
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
        config_path = os.path.join(base_dir, 'config.json')
    else:
        config_path = 'config.json'

    if not os.path.exists(config_path):
        print(f"[ERROR] 配置文件不存在: {config_path}")
        sys.exit(1)

    return config_path

class AutoSignTool:
    def __init__(self, config_path=None):
        if config_path is None:
            config_path = get_config_path()
        self.load_config(config_path)
        self.session = requests.Session()
        self.setup_logging()

    def load_config(self, config_path):
        print(f"[VERBOSE] 加载配置文件: {config_path}")
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        self.a_config = self.config['aSystem']
        self.b_config = self.config['bSystem']
        self.users = self.config['users']
        print(f"[VERBOSE] 配置文件加载完成，A系统地址: {self.a_config['baseUrl']}")
        print(f"[VERBOSE] B系统地址: {self.b_config['baseUrl']}")
        print(f"[VERBOSE] 签退接口: {self.b_config['signOutPath']}")
        print(f"[VERBOSE] 用户数量: {len(self.users)}")

    def setup_logging(self):
        log_dir = self.config.get('logPath', './logs')
        if getattr(sys, 'frozen', False):
            log_dir = os.path.join(os.path.dirname(sys.executable), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        self.log_file = os.path.join(log_dir, f"sign_{datetime.now().strftime('%Y%m%d')}.log")
        print(f"[VERBOSE] 日志文件: {self.log_file}")

    def log(self, user_no, message, status="INFO"):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_msg = f"[{timestamp}] [{status}] [{user_no}] {message}"
        print(log_msg)
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_msg + '\n')

    def jump_to_b_system(self, sub_acct_id, sub_acct_no):
        print(f"[VERBOSE] ====== 开始处理用户: {sub_acct_no} ======")
        print(f"[VERBOSE] 准备跳转B系统...")
        print(f"[VERBOSE] SubAcctId: {sub_acct_id}")
        try:
            url = f"{self.a_config['baseUrl']}{self.a_config['jumpPath']}"
            print(f"[VERBOSE] 跳转URL: {url}")
            headers = {
                "Content-Type": "application/json",
                "Cookie": f"z4a-web-token={self.a_config['token']}",
                "User-Agent": "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 Chrome/94.0.4606.71 Safari/537.36"
            }
            print(f"[VERBOSE] 请求头: {json.dumps(headers, ensure_ascii=False, indent=2)}")

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
            print(f"[VERBOSE] 请求Payload: {json.dumps(payload, ensure_ascii=False, indent=2)}")

            print(f"[VERBOSE] 发送跳转请求...")
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            print(f"[VERBOSE] 响应状态码: {response.status_code}")
            headers_dict = dict(response.headers)
            print(f"[VERBOSE] 响应头: {headers_dict}")

            cookies = response.cookies
            cookies_dict = dict(cookies)
            print(f"[VERBOSE] 响应Cookie: {cookies_dict}")

            b_cookie = cookies.get("JSESSIONID", "")
            if not b_cookie:
                print(f"[VERBOSE] 未获取到JSESSIONID Cookie，跳转失败")
                self.log(sub_acct_no, "未获取到B系统Cookie，跳转失败", "ERROR")
                return None

            print(f"[VERBOSE] 成功获取B系统Cookie: {b_cookie[:20]}...")
            return b_cookie

        except Exception as e:
            print(f"[VERBOSE] 跳转B系统异常: {str(e)}")
            self.log(sub_acct_no, f"跳转B系统失败: {str(e)}", "ERROR")
            return None

    def sign_out(self, sub_acct_id, sub_acct_no, b_cookie):
        print(f"[VERBOSE] 开始签退操作...")
        try:
            url = f"{self.b_config['baseUrl']}{self.b_config['signOutPath']}"
            print(f"[VERBOSE] 签退URL: {url}")
            headers = {
                "Content-Type": "application/json",
                "Cookie": f"JSESSIONID={b_cookie}",
                "User-Agent": "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 Chrome/94.0.4606.71 Safari/537.36"
            }
            print(f"[VERBOSE] Cookie: JSESSIONID={b_cookie[:20]}...")

            print(f"[VERBOSE] 发送签退请求...")
            response = requests.post(url, headers=headers, json={}, timeout=30)
            print(f"[VERBOSE] 响应状态码: {response.status_code}")
            print(f"[VERBOSE] 响应内容: {response.text}")

            result = response.text
            self.log(sub_acct_no, f"签退结果: {result}", "SUCCESS")
            print(f"[VERBOSE] 用户 {sub_acct_no} 签退成功")
            return True

        except Exception as e:
            print(f"[VERBOSE] 签退异常: {str(e)}")
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
        print(f"{'='*60}")
        print(f"自动签退工具启动 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"待处理人数: {len(self.users)}")
        print(f"{'='*60}")

        success_count = 0
        fail_count = 0

        for idx, user in enumerate(self.users, 1):
            print(f"\n[进度] 当前: {idx}/{len(self.users)}")
            if self.process_user(user):
                success_count += 1
            else:
                fail_count += 1
            time.sleep(1)

        print(f"\n{'='*60}")
        print(f"处理完成 - 成功: {success_count}, 失败: {fail_count}")
        print(f"{'='*60}")

if __name__ == "__main__":
    tool = AutoSignTool()
    tool.run()