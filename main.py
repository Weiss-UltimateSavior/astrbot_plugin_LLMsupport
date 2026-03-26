import os

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
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
            # 绝对路径需要检查是否在允许的目录内
            # 只允许插件目录内的文件
            abs_plugin_dir = os.path.abspath(self.plugin_dir)
            abs_image_path = os.path.abspath(image_path)
            
            # 检查是否在插件目录内
            if not os.path.commonpath([abs_plugin_dir]) == os.path.commonpath([abs_plugin_dir, abs_image_path]):
                logger.error(f"打赏二维码路径不在允许的目录内: {image_path}")
                self.support_image_path = None
            else:
                self.support_image_path = abs_image_path
        
        # 校验图片路径有效性
        if self.support_image_path:
            # 校验文件扩展名
            allowed_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.webp']
            ext = os.path.splitext(self.support_image_path)[1].lower()
            if ext not in allowed_extensions:
                logger.error(f"打赏二维码文件扩展名不允许: {ext}")
                self.support_image_path = None
            elif not os.path.exists(self.support_image_path):
                logger.error(f"打赏二维码文件不存在: {self.support_image_path}")
                self.support_image_path = None
            elif not os.path.isfile(self.support_image_path):
                logger.error(f"打赏二维码路径不是文件: {self.support_image_path}")
                self.support_image_path = None
            elif not os.access(self.support_image_path, os.R_OK):
                logger.error(f"打赏二维码文件不可读: {self.support_image_path}")
                self.support_image_path = None
        
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
        
        try:
            # 解析发送者ID，增加空值保护
            raw_sender_id = None
            if hasattr(event, 'message_obj') and event.message_obj:
                if hasattr(event.message_obj, 'sender') and event.message_obj.sender:
                    if hasattr(event.message_obj.sender, 'user_id'):
                        raw_sender_id = event.message_obj.sender.user_id
            
            sender_id = self._normalize_user_id(raw_sender_id)
            logger.info(f"打赏支持意图发送者: 原始ID={raw_sender_id}, 规范化ID={sender_id}")
            
            # 检查图片路径是否有效
            if not self.support_image_path:
                logger.error("打赏二维码路径无效，无法发送")
                yield event.plain_result("抱歉，打赏二维码配置无效，无法发送")
                return
            
            # 发送打赏二维码
            async for result in self._send_support_image(event):
                yield result
            logger.info(f"已向用户 {sender_id} 发送打赏二维码")
            
            # 返回提示，让LLM表示感谢
            yield event.plain_result(self.support_thank_text)
        except Exception as e:
            logger.error(f"发送打赏二维码时发生错误: {str(e)}")
            yield event.plain_result("抱歉，发送打赏二维码时发生错误，请稍后重试")

    async def _send_support_image(self, event: AstrMessageEvent):
        """发送打赏二维码"""
        try:
            # 使用 event.image_result 发送图片
            yield event.image_result(self.support_image_path)
            logger.debug(f"打赏二维码已发送，路径: {self.support_image_path}")
        except Exception as e:
            logger.error(f"发送图片失败: {str(e)}")
            raise

    def _normalize_user_id(self, user_id):
        """统一用户ID格式（处理整数/字符串）"""
        original = user_id
        if isinstance(user_id, int):
            normalized = str(user_id)
        elif isinstance(user_id, str):
            # 只在明确检测到"平台前缀_真实ID"格式时再拆分
            # 避免误伤包含下划线的合法ID
            parts = user_id.split("_")
            if len(parts) == 2 and parts[0].isalpha() and parts[1]:
                # 假设格式为"平台_ID"，如"qq_123456"或"wechat_789012"
                normalized = parts[-1].strip()
            else:
                # 其他情况保留原值
                normalized = user_id
        else:
            normalized = str(user_id)
        logger.debug(f"用户ID规范化：原始={original} → 规范化后={normalized}")
        return normalized