import os
import re
import sys
import time
import hmac
import hashlib
import base64
import urllib.parse

import requests


# ============================================================
# 钉钉消息推送
# ============================================================

def send_dingtalk(title, message):
    """
    使用钉钉自定义机器人发送 Markdown 消息
    GitHub Secrets:
        DINGTALK_WEBHOOK
        DINGTALK_SECRET
    """

    webhook = os.getenv("DINGTALK_WEBHOOK", "").strip()
    secret = os.getenv("DINGTALK_SECRET", "").strip()

    if not webhook:
        print("❌ 未配置 DINGTALK_WEBHOOK")
        return False

    try:
        # ----------------------------------------------------
        # 钉钉“加签”安全模式
        # ----------------------------------------------------
        if secret:
            timestamp = str(round(time.time() * 1000))

            string_to_sign = f"{timestamp}\n{secret}"

            hmac_code = hmac.new(
                secret.encode("utf-8"),
                string_to_sign.encode("utf-8"),
                digestmod=hashlib.sha256
            ).digest()

            sign = urllib.parse.quote_plus(
                base64.b64encode(hmac_code).decode("utf-8")
            )

            webhook_url = (
                f"{webhook}"
                f"&timestamp={timestamp}"
                f"&sign={sign}"
            )
        else:
            webhook_url = webhook

        # 把普通换行转换为 Markdown 换行
        markdown_message = message.replace("\n", "\n\n")

        data = {
            "msgtype": "markdown",
            "markdown": {
                "title": title,
                "text": (
                    f"### {title}\n\n"
                    f"{markdown_message}"
                )
            }
        }

        response = requests.post(
            webhook_url,
            json=data,
            timeout=20
        )

        response.raise_for_status()

        result = response.json()

        if result.get("errcode") == 0:
            print("✅ 钉钉消息推送成功")
            return True

        print(
            "❌ 钉钉消息推送失败："
            f"{result.get('errmsg', result)}"
        )
        return False

    except Exception as err:
        print(f"❌ 钉钉消息推送异常：{err}")
        return False


# ============================================================
# 获取夸克 Cookie
# ============================================================

def get_env():
    """
    获取 COOKIE_QUARK。

    多账号支持：
    1. 每个账号换行
    2. 使用 && 分隔
    """

    cookie_value = os.getenv("COOKIE_QUARK", "").strip()

    if not cookie_value:
        print("❌ 未添加 COOKIE_QUARK 变量")

        send_dingtalk(
            "❌ 夸克签到失败",
            "没有检测到 COOKIE_QUARK。\n"
            "请检查 GitHub Secrets。"
        )

        return []

    cookie_list = re.split(r"\n|&&", cookie_value)

    # 删除空白项目
    cookie_list = [
        cookie.strip()
        for cookie in cookie_list
        if cookie.strip()
    ]

    return cookie_list


# ============================================================
# 夸克签到
# ============================================================

class Quark:

    def __init__(self, user_data):
        self.param = user_data

    def convert_bytes(self, size):
        """
        字节转换为 B / KB / MB / GB / TB
        """

        try:
            size = float(size)
        except (TypeError, ValueError):
            return "未知"

        units = (
            "B",
            "KB",
            "MB",
            "GB",
            "TB",
            "PB",
            "EB",
            "ZB",
            "YB"
        )

        i = 0

        while size >= 1024 and i < len(units) - 1:
            size /= 1024
            i += 1

        return f"{size:.2f} {units[i]}"

    def get_growth_info(self):
        """
        获取签到 / 容量信息
        """

        url = (
            "https://drive-m.quark.cn/"
            "1/clouddrive/capacity/growth/info"
        )

        querystring = {
            "pr": "ucpro",
            "fr": "android",
            "kps": self.param.get("kps"),
            "sign": self.param.get("sign"),
            "vcode": self.param.get("vcode")
        }

        try:
            response = requests.get(
                url=url,
                params=querystring,
                timeout=20
            )

            response.raise_for_status()

            result = response.json()

            if result.get("data"):
                return result["data"], None

            error = (
                result.get("message")
                or result.get("msg")
                or "获取成长信息失败"
            )

            return None, error

        except Exception as err:
            return None, str(err)

    def get_growth_sign(self):
        """
        执行每日签到
        """

        url = (
            "https://drive-m.quark.cn/"
            "1/clouddrive/capacity/growth/sign"
        )

        querystring = {
            "pr": "ucpro",
            "fr": "android",
            "kps": self.param.get("kps"),
            "sign": self.param.get("sign"),
            "vcode": self.param.get("vcode")
        }

        data = {
            "sign_cyclic": True
        }

        try:
            response = requests.post(
                url=url,
                json=data,
                params=querystring,
                timeout=20
            )

            response.raise_for_status()

            result = response.json()

            if result.get("data"):
                reward = result["data"].get(
                    "sign_daily_reward",
                    0
                )

                return True, reward

            error = (
                result.get("message")
                or result.get("msg")
                or "签到接口返回异常"
            )

            return False, error

        except Exception as err:
            return False, str(err)

    def query_balance(self):
        """
        查询抽奖余额
        """

        url = (
            "https://coral2.quark.cn/"
            "currency/v1/queryBalance"
        )

        querystring = {
            "moduleCode":
                "1f3563d38896438db994f118d4ff53cb",
            "kps": self.param.get("kps")
        }

        try:
            response = requests.get(
                url=url,
                params=querystring,
                timeout=20
            )

            response.raise_for_status()

            result = response.json()

            if result.get("data"):
                return result["data"].get("balance")

            return None

        except Exception:
            return None

    def do_sign(self):
        """
        执行签到

        返回：
            success: True / False
            log:     显示给钉钉的签到结果
        """

        growth_info, error = self.get_growth_info()

        if not growth_info:
            return (
                False,
                "❌ 签到异常："
                f"{error or '获取成长信息失败'}"
            )

        user_name = self.param.get("user", "未知账号")

        is_vip = growth_info.get("88VIP", False)

        log = (
            f"{'👑 88VIP' if is_vip else '👤 普通用户'}："
            f"{user_name}\n"
        )

        # ----------------------------------------------------
        # 网盘容量
        # ----------------------------------------------------

        total_capacity = growth_info.get(
            "total_capacity",
            0
        )

        log += (
            "💾 网盘总容量："
            f"{self.convert_bytes(total_capacity)}\n"
        )

        cap_composition = growth_info.get(
            "cap_composition",
            {}
        )

        sign_reward = cap_composition.get(
            "sign_reward",
            0
        )

        log += (
            "🎁 签到累计容量："
            f"{self.convert_bytes(sign_reward)}\n"
        )

        cap_sign = growth_info.get(
            "cap_sign",
            {}
        )

        # ----------------------------------------------------
        # 今天已经签过
        # ----------------------------------------------------

        if cap_sign.get("sign_daily"):

            reward = cap_sign.get(
                "sign_daily_reward",
                0
            )

            progress = cap_sign.get(
                "sign_progress",
                "?"
            )

            target = cap_sign.get(
                "sign_target",
                "?"
            )

            log += (
                "✅ 今日已经签到\n"
                "🎉 今日奖励："
                f"{self.convert_bytes(reward)}\n"
                f"📅 连签进度：{progress}/{target}"
            )

            return True, log

        # ----------------------------------------------------
        # 今天还没有签到，开始签到
        # ----------------------------------------------------

        sign_success, sign_result = (
            self.get_growth_sign()
        )

        if sign_success:

            progress = cap_sign.get(
                "sign_progress",
                0
            )

            target = cap_sign.get(
                "sign_target",
                "?"
            )

            try:
                progress = int(progress) + 1
            except (TypeError, ValueError):
                pass

            log += (
                "✅ 签到成功\n"
                "🎉 本次获得："
                f"{self.convert_bytes(sign_result)}\n"
                f"📅 连签进度：{progress}/{target}"
            )

            return True, log

        log += (
            "❌ 签到失败\n"
            f"⚠️ 原因：{sign_result}"
        )

        return False, log


# ============================================================
# Cookie 转为参数
# ============================================================

def parse_cookie(cookie):
    """
    将 Cookie:

    kps=xxx; sign=xxx; vcode=xxx

    转换为字典。
    """

    user_data = {}

    for item in cookie.split(";"):

        item = item.strip()

        if not item:
            continue

        if "=" not in item:
            continue

        key, value = item.split("=", 1)

        user_data[key.strip()] = value.strip()

    return user_data


# ============================================================
# 主程序
# ============================================================

def main():

    print(
        "========== 夸克网盘开始签到 =========="
    )

    cookie_list = get_env()

    if not cookie_list:
        print("❌ 没有可以执行的夸克账号")
        return False

    print(
        f"✅ 检测到 {len(cookie_list)} 个夸克账号"
    )

    all_success = True
    result_messages = []

    for index, cookie in enumerate(
        cookie_list,
        start=1
    ):

        print(
            f"\n---------- 账号 {index} ----------"
        )

        try:
            user_data = parse_cookie(cookie)

            # 这几个字段是夸克签到需要的主要参数
            required_keys = [
                "kps",
                "sign",
                "vcode"
            ]

            missing_keys = [
                key
                for key in required_keys
                if not user_data.get(key)
            ]

            if missing_keys:

                log = (
                    f"🙍🏻‍♂️ 第 {index} 个账号\n"
                    "❌ Cookie 信息不完整\n"
                    "缺少："
                    f"{', '.join(missing_keys)}\n"
                    "可能需要重新获取夸克 Cookie。"
                )

                all_success = False

            else:

                success, account_log = (
                    Quark(user_data).do_sign()
                )

                log = (
                    f"🙍🏻‍♂️ 第 {index} 个账号\n"
                    f"{account_log}"
                )

                if not success:
                    all_success = False

            print(log)

            result_messages.append(log)

        except Exception as err:

            all_success = False

            error_log = (
                f"🙍🏻‍♂️ 第 {index} 个账号\n"
                f"❌ 程序异常：{err}"
            )

            print(error_log)

            result_messages.append(error_log)

    # --------------------------------------------------------
    # 汇总消息
    # --------------------------------------------------------

    final_message = "\n\n---\n\n".join(
        result_messages
    )

    if all_success:
        title = "✅ 夸克自动签到成功"
    else:
        title = "❌ 夸克自动签到异常"

    # --------------------------------------------------------
    # 钉钉推送
    # --------------------------------------------------------

    push_success = send_dingtalk(
        title,
        final_message
    )

    print(
        "========== 夸克网盘签到完毕 =========="
    )

    # 签到和通知都正常才认为任务正常
    return all_success and push_success


if __name__ == "__main__":

    success = main()

    # 如果签到或钉钉通知失败，
    # GitHub Actions 会显示红色 Failure
    if not success:
        sys.exit(1)

    sys.exit(0)
