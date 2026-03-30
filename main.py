import os
from typing import Optional

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register


@register("astrbot_plugin_LLMsupport", "雷诺哈特", "用户打赏请客支持时发送打赏二维码", "1.1.0")
class SupportImagePlugin(Star):
    MAX_FILE_SIZE = 10 * 1024 * 1024
    ALLOWED_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.gif', '.webp']
    KNOWN_PLATFORM_PREFIXES = {'qq', 'wechat', 'weixin', 'telegram', 'tg', 'discord', 'slack'}
    DEFAULT_THANK_TEXT = "已成功发送打赏二维码，十分感谢！"
    DEFAULT_IMAGE_NAME = "support_image.png"
    
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.plugin_dir = os.path.dirname(os.path.abspath(__file__))
        
        self.support_image_path: Optional[str] = self._load_and_validate_image_path()
        self.support_thank_text: str = self._load_and_validate_thank_text()
        
        self._log_initialization_status()
    
    def _load_and_validate_image_path(self) -> Optional[str]:
        """加载并校验图片路径"""
        image_path = self.config.get("support_image_path", self.DEFAULT_IMAGE_NAME)
        abs_plugin_dir = os.path.realpath(self.plugin_dir)
        
        if not os.path.isabs(image_path):
            temp_path = os.path.join(abs_plugin_dir, image_path)
        else:
            temp_path = image_path
        
        abs_image_path = os.path.realpath(temp_path)
        
        try:
            common = os.path.commonpath([abs_plugin_dir, abs_image_path])
            if common != abs_plugin_dir:
                logger.error(f"打赏二维码路径不在允许的目录内")
                return None
        except ValueError:
            logger.error(f"打赏二维码路径不在允许的目录内")
            return None
        
        if os.path.islink(abs_image_path):
            logger.warning(f"打赏二维码文件是符号链接，已拒绝")
            return None
        
        ext = os.path.splitext(abs_image_path)[1].lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            logger.error(f"打赏二维码文件扩展名不允许")
            return None
        
        if not os.path.exists(abs_image_path):
            logger.error(f"打赏二维码文件不存在")
            return None
        
        if not os.path.isfile(abs_image_path):
            logger.error(f"打赏二维码路径不是文件")
            return None
        
        if not os.access(abs_image_path, os.R_OK):
            logger.error(f"打赏二维码文件不可读")
            return None
        
        if not self._validate_image_file(abs_image_path):
            logger.error(f"打赏二维码文件不是有效的图片格式")
            return None
        
        file_size = self._get_file_size(abs_image_path)
        if file_size > self.MAX_FILE_SIZE:
            logger.error(f"打赏二维码文件过大（{file_size / 1024 / 1024:.2f}MB，最大允许 {self.MAX_FILE_SIZE // 1024 // 1024}MB）")
            return None
        
        if file_size == 0:
            logger.error(f"打赏二维码文件为空")
            return None
        
        return abs_image_path
    
    def _load_and_validate_thank_text(self) -> str:
        """加载并校验感谢文本"""
        thank_text = self.config.get("support_thank_text", self.DEFAULT_THANK_TEXT)
        
        if not thank_text or not isinstance(thank_text, str):
            logger.warning("感谢文本配置无效，使用默认值")
            return self.DEFAULT_THANK_TEXT
        
        if not thank_text.strip():
            logger.warning("感谢文本为空，使用默认值")
            return self.DEFAULT_THANK_TEXT
        
        return thank_text
    
    def _log_initialization_status(self) -> None:
        """记录初始化状态日志"""
        logger.info("打赏支持二维码插件初始化完成，等待消息事件触发")
        if self.support_image_path:
            image_filename = os.path.basename(self.support_image_path)
            logger.info(f"打赏二维码文件：{image_filename}")
        else:
            logger.warning("打赏二维码文件未配置或无效")
        logger.info(f"感谢文本：{self.support_thank_text}")

    @filter.llm_tool(name="send_support_image")
    async def handle_support_image_request(
        self, event: AstrMessageEvent
    ):
        """处理打赏请客支持的意图，发送打赏二维码"""
        logger.info("收到打赏支持意图，准备发送打赏二维码...")
        
        try:
            # 解析发送者 ID，增加空值保护
            raw_sender_id = None
            if hasattr(event, 'message_obj') and event.message_obj:
                if hasattr(event.message_obj, 'sender') and event.message_obj.sender:
                    if hasattr(event.message_obj.sender, 'user_id'):
                        raw_sender_id = event.message_obj.sender.user_id
            
            sender_id = self._normalize_user_id(raw_sender_id)
            masked_id = self._mask_user_id(sender_id)
            logger.debug(f"打赏支持意图发送者：原始 ID={raw_sender_id}, 规范化 ID={sender_id}")
            logger.info(f"打赏支持意图发送者：{masked_id}")
            
            # 检查图片路径是否有效
            if not self.support_image_path:
                logger.error("打赏二维码路径无效，无法发送")
                yield event.plain_result("抱歉，打赏二维码配置无效，无法发送")
                return
            
            # 发送打赏二维码
            async for result in self._send_support_image(event):
                yield result
            logger.info(f"已向用户 {sender_id} 发送打赏二维码")
            
            # 返回提示，让 LLM 表示感谢
            yield event.plain_result(self.support_thank_text)
        except FileNotFoundError:
            logger.exception(f"发送打赏二维码时发生错误：文件不存在")
            yield event.plain_result("抱歉，发送打赏二维码时发生错误，请稍后重试")
        except PermissionError:
            logger.exception(f"发送打赏二维码时发生错误：权限不足")
            yield event.plain_result("抱歉，发送打赏二维码时发生错误，请稍后重试")
        except Exception as e:
            logger.exception(f"发送打赏二维码时发生错误：{e}")
            yield event.plain_result("抱歉，发送打赏二维码时发生错误，请稍后重试")

    async def _send_support_image(self, event: AstrMessageEvent):
        """发送打赏二维码"""
        try:
            image_filename = os.path.basename(self.support_image_path)
            yield event.image_result(self.support_image_path)
            logger.debug(f"打赏二维码已发送：{image_filename}")
        except FileNotFoundError:
            logger.exception(f"发送图片失败：文件不存在")
            raise
        except PermissionError:
            logger.exception(f"发送图片失败：权限不足")
            raise
        except OSError as e:
            logger.exception(f"发送图片失败：{e}")
            raise
        except Exception as e:
            logger.exception(f"发送图片失败：{e}")
            raise

    def _mask_user_id(self, user_id: Optional[str | int]) -> str:
        """对用户 ID 进行脱敏处理，仅保留后 4 位"""
        if user_id is None:
            return "未知"
        user_id_str = str(user_id)
        if len(user_id_str) <= 4:
            return user_id_str
        return "****" + user_id_str[-4:]
    
    def _normalize_user_id(self, user_id: Optional[str | int]) -> str:
        """统一用户 ID 格式（处理整数/字符串）"""
        original = user_id
        if isinstance(user_id, int):
            normalized = str(user_id)
        elif isinstance(user_id, str):
            parts = user_id.split("_")
            if len(parts) == 2 and parts[0].lower() in self.KNOWN_PLATFORM_PREFIXES and parts[1]:
                normalized = parts[-1].strip()
            else:
                normalized = user_id
        else:
            normalized = str(user_id)
        logger.debug(f"用户 ID 规范化：原始={original} → 规范化后={normalized}")
        return normalized
    
    def _validate_image_file(self, file_path: str) -> bool:
        """验证文件是否为有效的图片格式（通过文件头魔法字节）"""
        try:
            with open(file_path, 'rb') as f:
                header = f.read(12)
            
            if not header:
                return False
            
            if header[:8] == b'\x89PNG\r\n\x1a\n':
                return True
            
            if header[:3] == b'\xff\xd8\xff':
                return True
            
            if header[:6] in (b'GIF87a', b'GIF89a'):
                return True
            
            if header[:4] == b'RIFF' and header[8:12] == b'WEBP':
                return True
            
            return False
        except FileNotFoundError:
            logger.debug(f"图片文件头验证失败：文件不存在")
            return False
        except PermissionError:
            logger.debug(f"图片文件头验证失败：权限不足")
            return False
        except OSError as e:
            logger.debug(f"图片文件头验证失败：{e}")
            return False
        except Exception as e:
            logger.exception(f"图片文件头验证发生未预期错误：{e}")
            return False
    
    def _get_file_size(self, file_path: str) -> int:
        """获取文件大小（字节）"""
        try:
            return os.path.getsize(file_path)
        except FileNotFoundError:
            logger.debug(f"获取文件大小失败：文件不存在")
            return 0
        except PermissionError:
            logger.debug(f"获取文件大小失败：权限不足")
            return 0
        except OSError as e:
            logger.debug(f"获取文件大小失败：{e}")
            return 0
        except Exception as e:
            logger.exception(f"获取文件大小发生未预期错误：{e}")
            return 0