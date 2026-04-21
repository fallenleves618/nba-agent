from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from nba_agent.http import post_json
from nba_agent.models import DeliveryChannelSettings, DeliverySettings


def deliver_to_webhooks(report: str, settings: DeliverySettings) -> None:
    _deliver_channel("feishu", report, settings.feishu)
    _deliver_channel("wecom", report, settings.wecom)


def _deliver_channel(
    channel_name: str, report: str, channel: DeliveryChannelSettings
) -> None:
    if not channel.enabled:
        return
    if not channel.webhook_url:
        print(f"delivery skipped: {channel_name}: missing webhook_url")
        return

    if channel_name == "feishu":
        payload = _build_feishu_payload(report, channel.msg_type, channel.secret)
    elif channel_name == "wecom":
        payload = _build_wecom_payload(report, channel.msg_type)
    else:
        print(f"delivery skipped: unsupported channel {channel_name}")
        return

    ok, response_text = post_json(channel.webhook_url, payload)
    if ok and _is_delivery_response_ok(channel_name, response_text):
        return

    print(f"delivery failed: {channel_name}: {response_text}")


def _build_feishu_payload(
    report: str, msg_type: str, secret: str
) -> dict[str, object]:
    normalized_type = "text" if msg_type not in {"text", "post"} else msg_type
    if normalized_type == "post":
        payload: dict[str, object] = {
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {
                        "title": "NBA 日报",
                        "content": [[{"tag": "text", "text": report}]],
                    }
                }
            },
        }
    else:
        payload = {
            "msg_type": "text",
            "content": {
                "text": report,
            },
        }

    if secret:
        timestamp = str(int(time.time()))
        string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
        sign = base64.b64encode(
            hmac.new(string_to_sign, digestmod=hashlib.sha256).digest()
        ).decode("utf-8")
        payload["timestamp"] = timestamp
        payload["sign"] = sign

    return payload


def _build_wecom_payload(report: str, msg_type: str) -> dict[str, object]:
    normalized_type = "markdown" if msg_type not in {"text", "markdown"} else msg_type
    if normalized_type == "text":
        return {
            "msgtype": "text",
            "text": {
                "content": report,
            },
        }

    return {
        "msgtype": "markdown",
        "markdown": {
            "content": report,
        },
    }


def _is_delivery_response_ok(channel_name: str, response_text: str) -> bool:
    try:
        data = json.loads(response_text) if response_text else {}
    except json.JSONDecodeError:
        return False

    if channel_name == "feishu":
        return int(data.get("code", -1)) == 0
    if channel_name == "wecom":
        return int(data.get("errcode", -1)) == 0
    return False
