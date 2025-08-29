from flask import Flask, request, make_response
import hashlib
import xml.etree.ElementTree as ET
import json
import time
import requests
from typing import Dict, Any, Optional

app = Flask(__name__)

# 配置
WECHAT_TOKEN = 'zwp123'  # 微信公众号后台设置的 Token
DIFY_API_KEY = "app-xxxxx" # 这里替换成你自己的 API Key
DIFY_BASE_URL = "xxx" # 这里替换成你自己的 Dify 实例地址


def verify_signature(signature: str, timestamp: str, nonce: str) -> bool:
    """
    验证微信服务器签名
    """
    token = WECHAT_TOKEN
    # 将 token, timestamp, nonce 三个参数进行字典序排序
    arr = sorted([token, timestamp, nonce])
    # 拼接成字符串并进行 sha1 加密
    sha1_str = hashlib.sha1(''.join(arr).encode('utf-8')).hexdigest()
    # 对比加密后的字符串与 signature
    return sha1_str == signature


def parse_xml_to_dict(xml_data: str) -> Dict[str, Any]:
    """
    将微信服务器 POST 的 XML 数据解析为字典
    """
    root = ET.fromstring(xml_data)
    result = {}
    for child in root:
        result[child.tag] = child.text
    return result


def make_text_response(to_user: str, from_user: str, content: str) -> str:
    """
    构造微信文本消息的 XML 响应
    """
    return f"""
<xml>
<ToUserName><![CDATA[{to_user}]]></ToUserName>
<FromUserName><![CDATA[{from_user}]]></FromUserName>
<CreateTime>{int(time.time())}</CreateTime>
<MsgType><![CDATA[text]]></MsgType>
<Content><![CDATA[{content}]]></Content>
</xml>
"""


def get_conversations(user_id: str, last_id: str = "", limit: int = 20) -> Dict[Any, Any]:
    """
    获取对话列表
    """
    url = f"{DIFY_BASE_URL}/conversations"
    headers = {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json"
    }
    params = {
        "user": user_id,
        "last_id": last_id,
        "limit": limit
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        if response:
            raise Exception(f"HTTP {response.status_code}: {response.text}")
        else:
            raise Exception(f"Request failed: {str(e)}")


def send_chat_message(query: str, user_id: str, conversation_id: str = "",
                      inputs: Dict = None, files: list = None,
                      response_mode: str = "blocking") -> Dict[Any, Any]:
    """
    发送聊天消息
    """
    if inputs is None:
        inputs = {}
    if files is None:
        files = []

    url = f"{DIFY_BASE_URL}/chat-messages"
    headers = {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "inputs": inputs,
        "query": query,
        "response_mode": response_mode,
        "conversation_id": conversation_id,
        "user": user_id,
        "files": files
    }

    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        if response:
            raise Exception(f"HTTP {response.status_code}: {response.text}")
        else:
            raise Exception(f"Request failed: {str(e)}")


@app.route('/wx', methods=['GET', 'POST'])
def index():
    """
    处理微信服务器验证 (GET 请求) 和消息接收 (POST 请求)
    """
    if request.method == 'GET':
        # GET 请求：服务器验证
        signature = request.args.get('signature')
        echostr = request.args.get('echostr')
        timestamp = request.args.get('timestamp')
        nonce = request.args.get('nonce')

        if not all([signature, echostr, timestamp, nonce]):
            return 'Invalid request', 400

        if verify_signature(signature, timestamp, nonce):
            return echostr
        else:
            return 'Invalid signature', 403

    elif request.method == 'POST':
        # POST 请求：接收并处理消息
        try:
            # 记录开始时间
            start_time = int(time.time() * 1000)
            print(f"Start time: {start_time}")

            # 解析 XML 请求体
            xml_data = request.data.decode('utf-8')
            print(f"Received XML: {xml_data}")

            xml_dict = parse_xml_to_dict(xml_data)
            to_user_name = xml_dict.get('ToUserName', '')
            from_user_name = xml_dict.get('FromUserName', '')
            content = xml_dict.get('Content', '').strip()

            print(f"Parsed: ToUser={to_user_name}, FromUser={from_user_name}, Content={content}")

            if not content:
                response_content = "收到消息，但内容为空。"
            else:
                # 获取用户对话列表
                conv_obj = get_conversations(user_id=from_user_name)
                conversation_id = conv_obj['data'][0]['id'] if conv_obj.get('data') else ''

                # 发送消息给 AI 并获取回复
                ai_response = send_chat_message(
                    query=content,
                    user_id=from_user_name,
                    conversation_id=conversation_id
                )
                response_content = ai_response.get('answer', 'AI 未返回有效回复。')

            # 构造响应 XML
            response_xml = make_text_response(from_user_name, to_user_name, response_content)

            # 创建响应对象，设置正确的 Content-Type
            response = make_response(response_xml)
            response.headers['Content-Type'] = 'text/xml'
            return response

        except Exception as e:
            print(f"Error processing message: {str(e)}")
            # 返回一个错误消息给微信服务器
            error_response = make_text_response(
                from_user_name, to_user_name, f"处理消息时出错: {str(e)}"
            )
            error_resp = make_response(error_response)
            error_resp.headers['Content-Type'] = 'text/xml'
            return error_resp

    return 'Method Not Allowed', 405


if __name__ == '__main__':
    # 在生产环境中，请使用更健壮的服务器 (如 gunicorn)
    app.run(host='0.0.0.0', port=7001, debug=True)