import requests
import os
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import astrbot.api.message_components as Comp

# Manbo TTS API 信息
MANBO_TTS_API_URL = "https://api.milorapart.top/apis/mbAIsc"  # API 地址

@register("manbo-tts", "YourName", "一个基于 Manbo TTS 的语音合成插件", "1.0.0")
class ManboTTSPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    async def initialize(self):
        """插件初始化，可以在此进行初始化工作"""
        pass

    # 注册指令改为 manbo
    @filter.command("manbo")
    async def manbo(self, event: AstrMessageEvent):
        """这是一个文本转语音（TTS）指令"""
        user_name = event.get_sender_name()
        message_str = event.message_str.strip()  # 获取用户发送的文本消息
        
        if not message_str:
            yield event.plain_result("请输入要转换为语音的文本！")
            return
        
        # 调用 Manbo TTS API，传递文本内容和音频格式
        try:
            response = requests.get(
                MANBO_TTS_API_URL,
                params={"text": message_str, "format": "wav"},  # 请求 WAV 格式
                timeout=30
            )

            if response.status_code == 200:
                # 解析返回的 JSON 数据
                data = response.json()

                if "url" in data:
                    audio_url = data["url"]  # 获取音频文件的 URL
                    
                    # 下载音频文件
                    audio_response = requests.get(audio_url)
                    if audio_response.status_code == 200:
                        # 保存音频文件到本地
                        filename = "output.wav"
                        with open(filename, 'wb') as f:
                            f.write(audio_response.content)

                        # 发送音频文件给用户
                        chain = [
                            Comp.Plain(f"Hello, {user_name}, 这是你请求的语音消息："),
                            Comp.Record(file=filename, url=filename)  # 使用 Record 组件发送音频
                        ]
                        yield event.chain_result(chain)

                        # 删除本地文件
                        os.remove(filename)
                    else:
                        yield event.plain_result("音频文件下载失败，请稍后再试。")
                else:
                    yield event.plain_result("无法获取音频文件，接口返回无效数据。")
            else:
                yield event.plain_result(f"请求失败，错误代码：{response.status_code}，请稍后再试。")

        except Exception as e:
            logger.error(f"请求 Manbo TTS API 时出错: {str(e)}")
            yield event.plain_result("发生了错误，请稍后再试。")

    async def terminate(self):
        """插件销毁时的清理工作"""
        pass