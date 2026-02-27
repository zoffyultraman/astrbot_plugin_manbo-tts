import aiohttp
import asyncio
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import logger
from astrbot.core.message.components import Record
from urllib.parse import urlparse

# Manbo TTS API 信息
MANBO_TTS_API_URL = "https://api.milorapart.top/apis/mbAIsc"
MAX_TEXT_LENGTH = 100  # 设置最大文本长度，避免请求过长
ALLOWED_DOMAINS = ["api.milorapart.top"]  # 允许的音频 URL 域名白名单

class ManboTTSPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.session = None  # 初始化 session
        self.lock = asyncio.Lock()  # 锁，防止并发创建 session

    @filter.on_astrbot_loaded()  # 插件加载完成后初始化 session
    async def on_loaded(self):
        """插件初始化，创建一个全局的 session"""
        async with self.lock:
            if not self.session or self.session.closed:
                self.session = aiohttp.ClientSession()

    async def fetch_audio_url(self, text_to_convert):
        """异步获取音频 URL，带有超时设置，使用 GET 请求"""
        # 如果 session 未初始化或已关闭，进行懒加载初始化
        if not self.session or self.session.closed:
            logger.info("Session 未初始化或已关闭，正在初始化...")
            async with self.lock:
                if not self.session or self.session.closed:
                    self.session = aiohttp.ClientSession()

        timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_connect=10, sock_read=20)  # 设置超时
        try:
            async with self.session.get(
                MANBO_TTS_API_URL,
                params={"text": text_to_convert, "format": "wav"},
                timeout=timeout,
            ) as response:
                if response.status == 200:
                    try:
                        data = await response.json()
                        if isinstance(data, dict) and "url" in data:
                            audio_url = data["url"]
                            # 校验 URL 协议和格式，避免 SSRF
                            if self.is_valid_url(audio_url):
                                return audio_url
                            else:
                                logger.error(f"非法的音频 URL：{audio_url}")
                                return None
                        else:
                            logger.error(f"返回的 JSON 格式无效，或缺少 'url' 字段：{data}")
                            return None
                    except aiohttp.ContentTypeError:
                        logger.error("响应内容不是有效的 JSON")
                        return None
                else:
                    logger.error(f"接口请求失败，状态码：{response.status}")
                    return None
        except aiohttp.ClientError as e:
            logger.error(f"请求异常：{str(e)}")
            return None

    def is_valid_url(self, url):
        """校验 URL 是否为有效的外部 URL，避免 SSRF"""
        try:
            parsed_url = urlparse(url)
            # 检查 URL 协议是否为 http/https，且域名在白名单中
            if parsed_url.scheme in ["http", "https"] and parsed_url.hostname in ALLOWED_DOMAINS:
                return True
            return False
        except Exception as e:
            logger.error(f"URL 校验失败：{str(e)}")
            return False

    @filter.command("manbo")
    async def manbo(self, event: AstrMessageEvent):
        """这是一个文本转语音（TTS）指令"""
        message_str = event.message_str.strip()

        # 优化提取 text_to_convert
        parts = message_str.split(maxsplit=1)
        text_to_convert = parts[1].strip() if len(parts) > 1 else ""

        # 输入文本长度限制
        if len(text_to_convert) > MAX_TEXT_LENGTH:
            yield event.plain_result(f"文本长度超过限制（{MAX_TEXT_LENGTH} 字符）。请缩短文本再试。")
            return

        if not text_to_convert:
            yield event.plain_result("请输入要转换为语音的文本！")
            return

        try:
            # 异步获取音频 URL
            audio_url = await self.fetch_audio_url(text_to_convert)
            if audio_url:
                # 直接使用 Record.fromURL 来传递音频 URL
                chain = [
                    Record.fromURL(audio_url)  # 使用 URL 直接传递
                ]
                yield event.chain_result(chain)
            else:
                yield event.plain_result("无法获取音频文件，接口返回无效数据。")
        except aiohttp.ClientError as e:
            logger.error(f"网络请求异常：{str(e)}")
            yield event.plain_result("网络异常，请稍后再试。")
        except Exception as e:
            logger.error(f"处理请求时发生错误: {str(e)}")
            yield event.plain_result("发生了错误，请稍后再试。")

    async def terminate(self):
        """插件销毁时的清理工作"""
        if self.session:
            await self.session.close()  # 关闭 session
            self.session = None  # 清空 session