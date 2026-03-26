import time
import os

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Image
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star, register


@register("astrbot_plugin_SupportImage", "雷诺哈特", "用户打赏请客支持时发送打赏二维码", "1.1.0")
class SupportImagePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        
        # 获取插件目录的绝对路径
        self.plugin_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 从配置加载打赏二维码本地路径
        image_path = self.config.get("support_image_path", "support_image.png")
        
        # 构建完整的图片路径
        if not os.path.isabs(image_path):
            self.support_image_path = os.path.join(self.plugin_dir, image_path)
        else:
            self.support_image_path = image_path
        
        # 从配置加载感谢文本
        self.support_thank_text = self.config.get(
            "support_thank_text", "已成功发送打赏二维码，十分感谢！"
        )

        logger.info("打赏支持二维码插件初始化完成，等待消息事件触发")
        logger.info(f"打赏二维码路径: {self.support_image_path}")
        logger.info(f"感谢文本: {self.support_thank_text}")

    @filter.llm_tool(name="send_support_image")
    async def handle_support_image_request(
        self, event: AstrMessageEvent
    ):
        """处理打赏请客支持的意图，发送打赏二维码"""
        logger.info("收到打赏支持意图，准备发送打赏二维码...")
        
        # 解析发送者ID
        raw_sender_id = event.message_obj.sender.user_id
        sender_id = self._normalize_user_id(raw_sender_id)
        logger.info(f"打赏支持意图发送者: 原始ID={raw_sender_id}, 规范化ID={sender_id}")
        
        # 发送打赏二维码
        async for result in self._send_support_image(event):
            yield result
        logger.info(f"已向用户 {sender_id} 发送打赏二维码")
        
        # 返回提示，让LLM表示感谢
        yield event.plain_result(self.support_thank_text)

    async def _send_support_image(self, event: AstrMessageEvent):
        """发送打赏二维码"""
        # 使用 event.image_result 发送图片
        yield event.image_result(self.support_image_path)
        logger.debug(f"打赏二维码已发送，路径: {self.support_image_path}")

    def _normalize_user_id(self, user_id):
        """统一用户ID格式（处理整数/字符串）"""
        original = user_id
        if isinstance(user_id, int):
            normalized = str(user_id)
        elif isinstance(user_id, str):
            # 移除可能的前缀（如"qq_"）
            normalized = user_id.split("_")[-1].strip()
        else:
            normalized = str(user_id)
        logger.debug(f"用户ID规范化：原始={original} → 规范化后={normalized}")
        return normalized