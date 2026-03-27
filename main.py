import os

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register


@register("astrbot_plugin_LLMsupport", "雷诺哈特", "用户打赏请客支持时发送打赏二维码", "1.1.0")
class SupportImagePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        
        # 获取插件目录的绝对路径
        self.plugin_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 从配置加载打赏二维码本地路径
        image_path = self.config.get("support_image_path", "support_image.png")
        
        # 构建完整的图片路径
        # 使用 realpath 解析所有符号链接，防止路径遍历攻击
        abs_plugin_dir = os.path.realpath(self.plugin_dir)
        
        # 无论绝对/相对路径，都先拼接再解析，确保路径安全
        if not os.path.isabs(image_path):
            # 相对路径：先拼接到插件目录
            temp_path = os.path.join(abs_plugin_dir, image_path)
        else:
            # 绝对路径：直接使用
            temp_path = image_path
        
        # 统一解析真实路径（解析符号链接）
        abs_image_path = os.path.realpath(temp_path)
        
        # 使用 commonpath 检查路径是否在插件目录内
        try:
            common = os.path.commonpath([abs_plugin_dir, abs_image_path])
            if common != abs_plugin_dir:
                logger.error(f"打赏二维码路径不在允许的目录内")
                self.support_image_path = None
            else:
                self.support_image_path = abs_image_path
        except ValueError:
            # commonpath 在不同驱动器下会抛出 ValueError
            logger.error(f"打赏二维码路径不在允许的目录内")
            self.support_image_path = None
        
        # 校验图片路径有效性
        if self.support_image_path:
            # 检查是否为符号链接（可选安全增强：拒绝符号链接）
            if os.path.islink(self.support_image_path):
                logger.warning(f"打赏二维码文件是符号链接，已拒绝")
                self.support_image_path = None
            
            # 校验文件扩展名
            allowed_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.webp']
            ext = os.path.splitext(self.support_image_path)[1].lower()
            if ext not in allowed_extensions:
                logger.error(f"打赏二维码文件扩展名不允许")
                self.support_image_path = None
            elif not os.path.exists(self.support_image_path):
                logger.error(f"打赏二维码文件不存在")
                self.support_image_path = None
            elif not os.path.isfile(self.support_image_path):
                logger.error(f"打赏二维码路径不是文件")
                self.support_image_path = None
            elif not os.access(self.support_image_path, os.R_OK):
                logger.error(f"打赏二维码文件不可读")
                self.support_image_path = None
            elif not self._validate_image_file(self.support_image_path):
                logger.error(f"打赏二维码文件不是有效的图片格式")
                self.support_image_path = None
            else:
                # 检查文件大小（最大 10MB）
                max_file_size = 10 * 1024 * 1024  # 10MB
                file_size = self._get_file_size(self.support_image_path)
                if file_size > max_file_size:
                    logger.error(f"打赏二维码文件过大（{file_size / 1024 / 1024:.2f}MB，最大允许 10MB）")
                    self.support_image_path = None
                elif file_size == 0:
                    logger.error(f"打赏二维码文件为空")
                    self.support_image_path = None
        
        # 从配置加载感谢文本
        self.support_thank_text = self.config.get(
            "support_thank_text", "已成功发送打赏二维码，十分感谢！"
        )
        
        # 校验感谢文本有效性
        if not self.support_thank_text or not isinstance(self.support_thank_text, str):
            logger.warning("感谢文本配置无效，使用默认值")
            self.support_thank_text = "已成功发送打赏二维码，十分感谢！"
        elif not self.support_thank_text.strip():
            logger.warning("感谢文本为空，使用默认值")
            self.support_thank_text = "已成功发送打赏二维码，十分感谢！"

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

    def _mask_user_id(self, user_id):
        """对用户 ID 进行脱敏处理，仅保留后 4 位"""
        if user_id is None:
            return "未知"
        user_id_str = str(user_id)
        if len(user_id_str) <= 4:
            return user_id_str
        return "****" + user_id_str[-4:]
    
    def _normalize_user_id(self, user_id):
        """统一用户 ID 格式（处理整数/字符串）"""
        original = user_id
        if isinstance(user_id, int):
            normalized = str(user_id)
        elif isinstance(user_id, str):
            # 只在明确检测到常见平台前缀格式时再拆分
            # 支持的平台前缀：qq, wechat, weixin, telegram, tg, discord, slack
            known_prefixes = {'qq', 'wechat', 'weixin', 'telegram', 'tg', 'discord', 'slack'}
            parts = user_id.split("_")
            if len(parts) == 2 and parts[0].lower() in known_prefixes and parts[1]:
                # 格式为"平台_ID"，如"qq_123456"或"wechat_789012"
                normalized = parts[-1].strip()
            else:
                # 其他情况保留原值，避免误伤合法 ID
                normalized = user_id
        else:
            normalized = str(user_id)
        logger.debug(f"用户 ID 规范化：原始={original} → 规范化后={normalized}")
        return normalized
    
    def _validate_image_file(self, file_path):
        """验证文件是否为有效的图片格式（通过文件头魔法字节）"""
        try:
            with open(file_path, 'rb') as f:
                header = f.read(12)  # 读取前 12 字节
            
            if not header:
                return False
            
            # 检查常见图片格式的魔法字节
            # PNG: 89 50 4E 47 0D 0A 1A 0A
            if header[:8] == b'\x89PNG\r\n\x1a\n':
                return True
            
            # JPEG: FF D8 FF
            if header[:3] == b'\xff\xd8\xff':
                return True
            
            # GIF: 47 49 46 38 37 61 or 47 49 46 38 39 61 (GIF87a or GIF89a)
            if header[:6] in (b'GIF87a', b'GIF89a'):
                return True
            
            # WebP: 52 49 46 46 xx xx xx xx 57 45 42 50 (RIFF....WEBP)
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
    
    def _get_file_size(self, file_path):
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