import aiohttp
import os
import tempfile
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import logger
from astrbot.core.message.components import Record

# Manbo TTS API 信息
MANBO_TTS_API_URL = "https://api.milorapart.top/apis/mbAIsc"

class ManboTTSPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.session = None  # 初始化 session

    async def initialize(self):
        """插件初始化，创建一个全局的 session"""
        self.session = aiohttp.ClientSession()

    async def fetch_audio_url(self, text_to_convert):
        """异步获取音频 URL，带有超时设置，使用 GET 请求"""
        if not self.session:
            logger.error("Session 未初始化")
            return None

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
                        if "url" in data:
                            audio_url = data["url"]
                            # 校验 URL 协议和格式
                            if audio_url.startswith("http://") or audio_url.startswith("https://"):
                                return data
                            else:
                                logger.error(f"非法的音频 URL：{audio_url}")
                                return None
                    except Exception as e:
                        logger.error(f"JSON 解析错误: {str(e)}")
                        return None
                else:
                    logger.error(f"接口请求失败，状态码：{response.status}")
                    return None
        except aiohttp.ClientError as e:
            logger.error(f"请求异常：{str(e)}")
            return None

    @filter.command("manbo")
    async def manbo(self, event: AstrMessageEvent):
        """这是一个文本转语音（TTS）指令"""
        message_str = event.message_str.strip()

        # 优化提取 text_to_convert
        parts = message_str.split(maxsplit=1)
        text_to_convert = parts[1].strip() if len(parts) > 1 else ""

        if not text_to_convert:
            yield event.plain_result("请输入要转换为语音的文本！")
            return

        try:
            # 异步获取音频 URL
            data = await self.fetch_audio_url(text_to_convert)
            if data and "url" in data:
                audio_url = data["url"]
                # 直接使用 Record.fromURL 来传递音频 URL
                chain = [
                    Record.fromURL(audio_url)  # 使用 URL 直接传递
                ]
                yield event.chain_result(chain)
            else:
                yield event.plain_result("无法获取音频文件，接口返回无效数据。")
        except Exception as e:
            logger.error(f"处理请求时发生错误: {str(e)}")
            yield event.plain_result("发生了错误，请稍后再试。")

    async def terminate(self):
        """插件销毁时的清理工作"""
        if self.session:
            await self.session.close()  # 关闭 session