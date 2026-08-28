import hashlib
import requests
import logging
from abc import ABC, abstractmethod
from alipay import AliPay, AliPayConfig

logger = logging.getLogger(__name__)

class PaymentGateway(ABC):
    """支付接口抽象类"""

    @abstractmethod
    def generate_payment_url(self, order):
        """生成支付链接"""
        pass

    @abstractmethod
    def process_callback(self, data):
        """处理支付回调"""
        pass

class WeChatPay(PaymentGateway):
    """微信支付实现"""

    def __init__(self, app_id, merchant_id, api_key, callback_url):
        self.app_id = app_id
        self.merchant_id = merchant_id
        self.api_key = api_key
        self.callback_url = callback_url

    def generate_payment_url(self, order):
        """调用微信支付统一下单接口生成支付链接"""
        try:
            if not order or not order.id:
                raise ValueError("Invalid order: Order object or ID is missing")

            url = "https://api.mch.weixin.qq.com/pay/unifiedorder"
            payload = {
                "appid": self.app_id,
                "mch_id": self.merchant_id,
                "nonce_str": self._generate_nonce_str(),
                "body": f"Order {order.id}",
                "out_trade_no": str(order.id),
                "total_fee": int(order.amount * 100),  # 单位为分
                "spbill_create_ip": "127.0.0.1",
                "notify_url": self.callback_url,
                "trade_type": "NATIVE",  # NATIVE 表示生成二维码支付
            }
            payload["sign"] = self._generate_sign(payload)

            # 发送请求
            response = requests.post(url, data=self._dict_to_xml(payload))
            response_data = self._xml_to_dict(response.text)

            if response_data.get("return_code") == "SUCCESS" and response_data.get("result_code") == "SUCCESS":
                return response_data.get("code_url")  # 返回支付二维码链接
            else:
                raise ValueError(f"WeChat Pay API Error: {response_data.get('return_msg')}")
        except Exception as e:
            logger.error(f"Error generating WeChat Pay URL: {e}")
            raise

    def process_callback(self, data):
        """处理微信支付回调"""
        try:
            if not data.get("out_trade_no") or not data.get("transaction_id"):
                raise ValueError("Invalid callback data: Missing out_trade_no or transaction_id")
            logger.info(f"Processing WeChat Pay callback: {data}")
            return {
                "order_id": data.get("out_trade_no"),
                "transaction_id": data.get("transaction_id"),
                "status": data.get("result_code"),
            }
        except Exception as e:
            logger.error(f"Error processing WeChat Pay callback: {e}")
            raise

    def _generate_nonce_str(self):
        """生成随机字符串"""
        import random
        import string
        return ''.join(random.choices(string.ascii_letters + string.digits, k=32))

    def _generate_sign(self, data):
        """生成签名"""
        sorted_data = sorted(data.items())
        string_to_sign = "&".join(f"{k}={v}" for k, v in sorted_data if v) + f"&key={self.api_key}"
        return hashlib.md5(string_to_sign.encode("utf-8")).hexdigest().upper()

    def _dict_to_xml(self, data):
        """将字典转换为 XML"""
        xml = ["<xml>"]
        for k, v in data.items():
            xml.append(f"<{k}>{v}</{k}>")
        xml.append("</xml>")
        return "".join(xml)

    def _xml_to_dict(self, xml):
        """将 XML 转换为字典"""
        import xml.etree.ElementTree as ET
        tree = ET.fromstring(xml)
        return {child.tag: child.text for child in tree}

class Alipay(PaymentGateway):
    """支付宝支付实现"""

    def __init__(self, app_id, private_key_path, alipay_public_key_path, callback_url):
        self.app_id = app_id
        self.private_key_path = private_key_path
        self.alipay_public_key_path = alipay_public_key_path
        self.callback_url = callback_url
        # self.gateway_url = "https://openapi.alipaydev.com/gateway.do"  # 沙箱网关
        self.gateway_url = "https://openapi-sandbox.dl.alipaydev.com/gateway.do"  # 沙箱网关
    def generate_payment_url(self, order):
        """调用支付宝支付接口生成支付链接"""
        try:
            alipay = self._get_alipay_client()

            # 构造支付请求
            order_string = alipay.api_alipay_trade_page_pay(
                out_trade_no=str(order.id),
                total_amount=str(order.amount),
                subject=f"Order {order.id}",
                return_url="http://127.0.0.1:8000/order/payment_success",  # 同步回调地址
                notify_url=self.callback_url,  # 异步回调地址
            )

            # 拼接支付链接
            payment_url = f"{self.gateway_url}?{order_string}"
            logger.info(f"Generated Alipay payment URL: {payment_url}")
            return payment_url
        except Exception as e:
            logger.error(f"Error generating Alipay payment URL: {e}")
            raise

    def process_callback(self, data):
        """处理支付宝支付回调"""
        try:
            # 获取支付宝客户端
            alipay = self._get_alipay_client()

            # 验证签名
            signature = data.pop("sign", None)  # 移除签名字段
            if not signature:
                logger.error("Missing signature in callback data")
                raise ValueError("Missing signature in callback data")

            success = alipay.verify(data, signature)  # 验证签名
            if not success:
                logger.error("Invalid callback signature")
                raise ValueError("Invalid callback signature")

            # 记录成功的回调数据
            logger.info(f"Processing Alipay callback: {data}")

            # 返回处理结果
            return {
                "order_id": data.get("out_trade_no"),
                "transaction_id": data.get("trade_no"),
                "status": data.get("trade_status"),
            }

        except Exception as e:
            # 捕获异常并记录日志
            logger.error(f"Error processing Alipay callback: {e}")
            raise

    def _get_alipay_client(self):
        """获取支付宝客户端"""
        return AliPay(
            appid=self.app_id,
            app_notify_url=self.callback_url,
            app_private_key_string=open(self.private_key_path).read(),
            alipay_public_key_string=open(self.alipay_public_key_path).read(),
            sign_type="RSA2",
            debug=True,  # 沙箱模式
            config=AliPayConfig(timeout=15),
            # charset = "utf-8",
        )

class UnionPay(PaymentGateway):
    """银联支付实现"""

    def __init__(self, api_key, merchant_id, callback_url):
        self.api_key = api_key
        self.merchant_id = merchant_id
        self.callback_url = callback_url
        self.gateway_url = "https://gateway.95516.com/gateway/api/frontTransReq.do"

    def generate_payment_url(self, order):
        """调用银联支付接口生成支付链接"""
        try:
            if not order or not order.id:
                raise ValueError("Invalid order: Order object or ID is missing")

            # 构造请求参数
            payload = {
                "version": "5.1.0",
                "encoding": "UTF-8",
                "signMethod": "01",  # 签名方法：01表示RSA
                "txnType": "01",  # 交易类型：01表示消费
                "txnSubType": "01",  # 交易子类：01表示普通消费
                "bizType": "000201",  # 产品类型：000201表示B2C网关支付
                "channelType": "07",  # 渠道类型：07表示互联网
                "accessType": "0",  # 接入类型：0表示商户直连接入
                "merId": self.merchant_id,  # 商户号
                "orderId": str(order.id),  # 商户订单号
                "txnTime": self._get_current_time(),  # 订单发送时间
                "txnAmt": str(int(order.amount * 100)),  # 交易金额，单位为分
                "currencyCode": "156",  # 交易币种：156表示人民币
                "backUrl": self.callback_url,  # 后台通知地址
                "frontUrl": self.callback_url,  # 前台通知地址（可选）
            }

            # 签名
            payload["signature"] = self._generate_sign(payload)

            # 拼接支付链接
            response = requests.post(self.gateway_url, data=payload)
            if response.status_code == 200:
                logger.info(f"Generated UnionPay payment URL for order {order.id}")
                return self.gateway_url  # 银联支付通常直接跳转到支付网关
            else:
                raise ValueError(f"UnionPay API Error: {response.text}")
        except Exception as e:
            logger.error(f"Error generating UnionPay payment URL: {e}")
            raise

    def process_callback(self, data):
        """处理银联支付回调"""
        try:
            # 验证签名
            if not self._verify_sign(data):
                raise ValueError("Invalid callback signature")

            logger.info(f"Processing UnionPay callback: {data}")
            return {
                "order_id": data.get("orderId"),
                "transaction_id": data.get("queryId"),
                "status": data.get("respCode"),
            }
        except Exception as e:
            logger.error(f"Error processing UnionPay callback: {e}")
            raise

    def _generate_sign(self, data):
        """生成签名"""
        from Crypto.Signature import PKCS1_v1_5
        from Crypto.Hash import SHA256
        from Crypto.PublicKey import RSA

        # 排序参数并拼接为字符串
        sorted_data = sorted(data.items())
        string_to_sign = "&".join(f"{k}={v}" for k, v in sorted_data if v and k != "signature")

        # 使用私钥生成签名
        private_key = RSA.importKey(self.api_key)
        signer = PKCS1_v1_5.new(private_key)
        digest = SHA256.new(string_to_sign.encode("utf-8"))
        sign = signer.sign(digest)
        return sign.hex()

    def _verify_sign(self, data):
        """验证签名"""
        from Crypto.Signature import PKCS1_v1_5
        from Crypto.Hash import SHA256
        from Crypto.PublicKey import RSA

        # 提取签名和待验证数据
        sign = data.pop("signature", None)
        sorted_data = sorted(data.items())
        string_to_verify = "&".join(f"{k}={v}" for k, v in sorted_data if v)

        # 使用银联公钥验证签名
        public_key = RSA.importKey(self.api_key)  # 银联公钥
        verifier = PKCS1_v1_5.new(public_key)
        digest = SHA256.new(string_to_verify.encode("utf-8"))
        return verifier.verify(digest, bytes.fromhex(sign))

    def _get_current_time(self):
        """获取当前时间，格式为yyyyMMddHHmmss"""
        from datetime import datetime
        return datetime.now().strftime("%Y%m%d%H%M%S")

class PaymentFactory:
    @staticmethod
    def get_payment_gateway(payment_method):
        try:
            if payment_method == "wechat":
                return WeChatPay(
                    app_id="your_wechat_app_id",
                    merchant_id="your_wechat_merchant_id",
                    api_key="your_wechat_api_key",
                    callback_url="https://yourdomain.com/payment/callback/wechat"
                )
            elif payment_method == "alipay":
                return Alipay(
                    app_id="9021000136679148",  # 替换为你的沙箱应用 ID
                    private_key_path="a_order/key/alipay_key/app_private_key.pem",
                    alipay_public_key_path="a_order/key/alipay_key/alipay_public_key.pem",
                    # callback_url="http://127.0.0.1:8000/order/callback/alipay",  # 异步回调地址
                    callback_url="http://t8b59df3.natappfree.cc/order/callback/alipay"  # 替换为你的异步回调地址
                )
            elif payment_method == "unionpay":
                return UnionPay(
                    api_key="your_unionpay_api_key",
                    merchant_id="your_unionpay_merchant_id",
                    callback_url="https://yourdomain.com/payment/callback/unionpay"
                )
            else:
                raise ValueError(f"Unsupported payment method: {payment_method}")
        except Exception as e:
            logger.error(f"Error getting payment gateway for method {payment_method}: {e}")
            raise