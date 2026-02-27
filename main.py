import aiohttp
import os
import uuid
import tempfile
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import astrbot.api.message_components as Comp

# Manbo TTS API 信息
MANBO_TTS_API_URL = "https://api.milorapart.top/apis/mbAIsc"

@register("manbo-tts", "YourName", "一个基于 Manbo TTS 的语音合成插件", "1.0.0")
class ManboTTSPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    async def initialize(self):
        """插件初始化，可以在此进行初始化工作"""
        pass

    async def fetch_audio_url(self, text_to_convert):
        """异步获取音频 URL"""
        async with aiohttp.ClientSession() as session:
            async with session.get(MANBO_TTS_API_URL, params={"text": text_to_convert, "format": "wav"}) as response:
                if response.status == 200:
                    if "application/json" in response.headers.get("Content-Type", ""):
                        try:
                            return await response.json()
                        except Exception as e:
                            logger.error(f"JSON 解析错误: {str(e)}")
                            return None
                    else:
                        logger.error("非 JSON 响应")
                        return None
                else:
                    return None

    @filter.command("manbo")
    async def manbo(self, event: AstrMessageEvent):
        """这是一个文本转语音（TTS）指令"""
        user_name = event.get_sender_name()
        message_str = event.message_str.strip()
        
        # 使用 split 来提取命令后的文本
        text_to_convert = message_str.split(maxsplit=1)[1].strip() if len(message_str.split(maxsplit=1)) > 1 else ""

        if not text_to_convert:
            yield event.plain_result("请输入要转换为语音的文本！")
            return

        try:
            # 异步获取音频 URL
            data = await self.fetch_audio_url(text_to_convert)
            if data and "url" in data:
                audio_url = data["url"]
                async with aiohttp.ClientSession() as session:
                    audio_response = await session.get(audio_url)
                    if audio_response.status == 200:
                        # 使用 tempfile 创建临时文件
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_file:
                            filename = temp_file.name
                            with open(filename, 'wb') as f:
                                f.write(await audio_response.read())

                        # 发送音频文件
                        chain = [
                            Comp.Record(file=filename, url=filename)
                        ]
                        yield event.chain_result(chain)
                    else:
                        yield event.plain_result("音频文件下载失败，请稍后再试。")
            else:
                yield event.plain_result("无法获取音频文件，接口返回无效数据。")
        except Exception as e:
            logger.error(f"请求 Manbo TTS API 时出错: {str(e)}")
            yield event.plain_result("发生了错误，请稍后再试。")
        finally:
            if os.path.exists(filename):
                os.remove(filename)  # 清理文件

    async def terminate(self):
        """插件销毁时的清理工作"""
        pass