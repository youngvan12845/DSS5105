from django.shortcuts import render,redirect,get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from .models import RechargeOrder, SubscriptionOrder, SubscriptionConfig
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt
import json
import logging
from .payment import PaymentFactory
from django.db import transaction
from .models import RechargeOrder

# 设置日志记录
logger = logging.getLogger(__name__)

def get_order_by_id(order_id):
    """通用订单查询方法"""
    return RechargeOrder.objects.filter(id=order_id).first() or SubscriptionOrder.objects.filter(id=order_id).first()



@login_required
def create_subscription_order(request):
    """创建会员订阅订单"""
    if request.method == 'POST':
        try:
            subscription_period = request.POST.get('subscription_period')

            # 获取订阅积分配置
            config = SubscriptionConfig.get_config()
            if not config:
                return render(request, 'a_order/error.html', {'error': '未找到订阅配置'})

            # 根据订阅周期动态获取积分
            points_required = {
                'monthly': config.monthly_points,
                'quarterly': config.quarterly_points,
                'yearly': config.yearly_points,
            }.get(subscription_period)

            if points_required is None:
                return render(request, 'a_order/error.html', {'error': '无效的订阅周期'})

            # 检查用户积分是否足够
            profile = request.user.profile
            if not profile.deduct_points(points_required, description="会员订阅"):
                return render(request, 'a_order/insufficient_points.html', {
                    'error': '积分不足',
                    'buy_points_url': '/order/create_recharge_order/'
                })

            # 创建订阅订单并处理订阅逻辑
            with transaction.atomic():
                profile.handle_subscription(subscription_period)
                order = SubscriptionOrder.objects.create(
                    user=request.user,
                    points=points_required,
                    subscription_period=subscription_period,
                    status='paid',  # 直接标记为已支付，因为积分已扣除
                )

            # 返回订单信息（例如支付链接）
            # return JsonResponse({'order_id': order.id, 'message': 'Subscription order created successfully'})
            return render(request, 'a_order/subscription_success.html', {'order': order})
            # return redirect('subscription_success')

        except Exception as e:
            logger.error(f"Error creating subscription order: {e}")
            return render(request, 'a_order/error.html', {'error': '创建订阅订单失败'})

    return render(request, 'a_order/create_subscription_order.html')


@login_required
def create_recharge_order(request):
    """创建积分充值订单"""
    if request.method == 'POST':
        try:
            # 解析请求数据
            data = json.loads(request.body)
            amount = int(data.get('amount', 0))  # 支付金额
            payment_method = data.get('payment_method', 'wechat')

            # 校验支付方式
            if payment_method not in ['wechat', 'alipay', 'unionpay']:
                logger.error(f"Unsupported payment method: {payment_method}")
                return JsonResponse({'error': '不支持的支付方式'}, status=400)

            # 计算积分
            points = amount * 10  # 假设 1 元兑换 10 积分

            # 创建充值订单
            order = RechargeOrder.objects.create(
                user=request.user,
                amount=amount,
                points=points,
                payment_method=payment_method,
                status='pending',  # 初始状态为 pending，等待支付回调更新状态
            )

            # 获取支付网关
            payment_gateway = PaymentFactory.get_payment_gateway(payment_method)

            # 生成支付链接
            payment_url = payment_gateway.generate_payment_url(order)
            logger.info(f"Payment URL generated: {payment_url}")

            return JsonResponse({'order_id': order.id, 'payment_url': payment_url})

        except Exception as e:
            logger.error(f"Error creating recharge order: {e}")
            return JsonResponse({'error': '创建充值订单失败'}, status=500)

    return render(request, 'a_order/create_recharge_order.html')



# @csrf_exempt
# def payment_callback(request):
#     """支付回调"""
#     try:
#         # 解析请求数据
#         if request.content_type == 'application/json':
#             data = json.loads(request.body)
#         else:
#             data = request.POST

#         payment_method = data.get('payment_method')
#         if not payment_method:
#             logger.error("Missing payment_method in callback data")
#             return HttpResponse("payment_method is required", status=400)

#         # 校验支付方式
#         if payment_method not in ['wechat', 'alipay', 'unionpay']:
#             logger.error(f"Unsupported payment method: {payment_method}")
#             return HttpResponse("Unsupported payment method", status=400)

#         # 获取支付网关
#         payment_gateway = PaymentFactory.get_payment_gateway(payment_method)

#         # 处理支付回调
#         callback_data = payment_gateway.process_callback(data)

#         order_id = callback_data.get("order_id")
#         transaction_id = callback_data.get("transaction_id")
#         status = callback_data.get("status")

#         # 查询订单
#         order = get_order_by_id(order_id)
#         if not order:
#             logger.error(f"Order not found: order_id={order_id}")
#             return render(request, 'a_order/error.html', {'error': '订单未找到'})

#         # 更新订单状态
#         with transaction.atomic():
#             if status == 'paid' and order.status != 'paid':
#                 order.transaction_id = transaction_id
#                 order.status = 'paid'
#                 order.save()

#                 # 调用订单的处理方法
#                 if isinstance(order, RechargeOrder):
#                     order.process_recharge()
#                 elif isinstance(order, SubscriptionOrder):
#                     order.process_subscription()

#                 logger.info(f"Payment processed successfully for order_id={order_id}")
#                 return redirect('payment_success')

#         # 如果支付未成功，根据订单类型返回不同的失败页面
#         logger.error(f"Payment failed for order_id={order_id}")
#         if isinstance(order, RechargeOrder):
#             return redirect('payment_failed_recharge')
#         elif isinstance(order, SubscriptionOrder):
#             return redirect('payment_failed_subscription')

#     except Exception as e:
#         logger.error(f"Unexpected error in payment callback: {e}")
#         return render(request, 'a_order/error.html', {'error': '发生意外错误'})
    
@csrf_exempt
def alipay_callback(request):
    """处理支付宝支付回调"""
    try:
        # 获取回调数据
        data = request.GET.dict() if request.method == 'GET' else request.POST.dict()
        logger.info(f"Received Alipay callback data: {data}")

        # 检查回调数据是否包含签名
        if "sign" not in data or "sign_type" not in data:
            logger.error("Missing 'sign' or 'sign_type' in callback data")
            return HttpResponse("failure", status=400)

        # 获取支付网关
        payment_gateway = PaymentFactory.get_payment_gateway("alipay")

        # 验证回调签名
        try:
            callback_data = payment_gateway.process_callback(data)
        except Exception as e:
            logger.error(f"Signature verification failed: {e}")
            return HttpResponse("failure", status=400)

        # 提取回调数据
        order_id = callback_data.get("order_id")
        transaction_id = callback_data.get("transaction_id")
        status = callback_data.get("status")

        # 查询订单
        try:
            order = RechargeOrder.objects.get(id=order_id)
        except RechargeOrder.DoesNotExist:
            logger.error(f"Order not found: Order ID={order_id}")
            return HttpResponse("failure", status=404)

        # 更新订单状态
        if status == "TRADE_SUCCESS":
            order.transaction_id = transaction_id
            order.status = "paid"
            order.save()
            
            logger.info(f"Order updated successfully: {order}")
            # return HttpResponse("success")  # 必须返回 success
            # 调用积分充值逻辑
            if order.process_recharge():
                logger.info(f"Recharge successful for Order ID={order_id}")
                return HttpResponse("success")  # 必须返回 success
            else:
                logger.error(f"Recharge failed for Order ID={order_id}")
                return HttpResponse("failure", status=500)
            
        logger.warning(f"Payment not successful for Order ID={order_id}, Status={status}")
        return HttpResponse("failure", status=400)

    except Exception as e:
        logger.error(f"Unexpected error in Alipay callback: {e}")
        return HttpResponse("failure", status=500)
    

@login_required
def payment_success(request):
    """支付成功页面"""
    return render(request, 'a_order/payment_success.html')

@login_required
def payment_failed_recharge(request):
    """积分充值失败页面"""
    return render(request, 'a_order/payment_failed_recharge.html')