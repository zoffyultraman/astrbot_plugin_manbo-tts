import aiohttp
import asyncio
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import logger
from astrbot.core.message.components import Record
from urllib.parse import urlparse

# ========== 核心修改1：替换API配置 ==========
# 新的曼波TTS API信息
MANBO_TTS_API_URL = "https://www.synapse.fan/api/ai/tts"  # 新API地址
MAX_TEXT_LENGTH = 200  # 保持文本长度限制
# 新的允许域名（根据新API返回的音频URL域名更新）
ALLOWED_DOMAINS = ["synapse-space.oss-cn-beijing.aliyuncs.com"]  
TIMEOUT = aiohttp.ClientTimeout(total=30, connect=10, sock_connect=10, sock_read=20)


class ManboTTSPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.session = None
        self.lock = asyncio.Lock()

    @filter.on_astrbot_loaded()
    async def on_loaded(self):
        """插件初始化，创建全局session"""
        async with self.lock:
            if not self.session or self.session.closed:
                self.session = aiohttp.ClientSession()

    async def fetch_audio_url(self, text_to_convert):
        """
        核心修改2：适配新API的请求方式
        新API是POST请求，参数格式不同，返回格式也不同
        """
        if not self.session or self.session.closed:
            async with self.lock:
                if not self.session or self.session.closed:
                    logger.info("Session未初始化或已关闭，正在重新创建...")
                    self.session = aiohttp.ClientSession()

        try:
            if self.session.closed:
                logger.error("会话已关闭，无法发起请求")
                return None

            # ========== 核心修改3：改为POST请求 + 新参数格式 ==========
            async with self.session.post(
                MANBO_TTS_API_URL,
                json={"text": text_to_convert, "voice": "manbo"},  # 新API的请求体
                timeout=TIMEOUT,
                headers={"Content-Type": "application/json"}  # 显式指定JSON格式
            ) as response:
                if response.status != 200:
                    logger.error(f"API请求失败，状态码：{response.status}，响应内容：{await response.text()}")
                    return None

                try:
                    data = await response.json()
                    # ========== 核心修改4：适配新API的返回格式 ==========
                    # 新API返回格式：{"code":1,"data":{"url":"音频地址"}}
                    if isinstance(data, dict) and data.get("code") == 1:
                        audio_url = data.get("data", {}).get("url")
                        if audio_url and self.is_valid_url(audio_url):
                            return audio_url
                        else:
                            logger.error(f"音频URL不存在或无效：{audio_url}")
                            return None
                    else:
                        logger.error(f"API返回异常：{data}")
                        return None
                except aiohttp.ContentTypeError:
                    logger.error("响应内容不是有效的JSON格式")
                    return None
        except asyncio.TimeoutError:
            logger.error("请求音频URL超时")
            return None
        except aiohttp.ClientError as e:
            logger.error(f"HTTP请求异常：{str(e)}")
            return None
        except RuntimeError as e:
            logger.error(f"会话异常：{str(e)}")
            return None

    @staticmethod
    def is_valid_url(url):
        """
        核心修改5：更新URL校验逻辑（适配新的音频域名）
        """
        try:
            parsed_url = urlparse(url)
            # 校验协议和白名单域名
            if parsed_url.scheme in ["http", "https"] and parsed_url.netloc in ALLOWED_DOMAINS:
                return True
            logger.error(f"URL域名不在白名单内：{parsed_url.netloc}，允许的域名：{ALLOWED_DOMAINS}")
            return False
        except Exception as e:
            logger.error(f"URL校验失败：{str(e)}")
            return False

    @filter.command("manbo")
    async def manbo(self, event: AstrMessageEvent, text: str):
        """manbo指令处理逻辑（无需修改）"""
        text_str = " ".join(text).strip()

        if not text_str:
            yield event.plain_result("请输入要转换为语音的文本！")
            return

        if len(text_str) > MAX_TEXT_LENGTH:
            yield event.plain_result(f"文本长度超过限制（{MAX_TEXT_LENGTH} 字符）。请缩短文本再试。")
            return

        try:
            audio_url = await self.fetch_audio_url(text_str)
            if audio_url:
                chain = [Record.fromURL(audio_url)]
                yield event.chain_result(chain)
            else:
                yield event.plain_result("无法获取音频文件，接口返回无效数据。")
        except Exception as e:
            logger.error(f"处理manbo指令时出错: {str(e)}")
            yield event.plain_result("发生了错误，请稍后再试。")

    async def terminate(self):
        """插件销毁清理（无需修改）"""
        async with self.lock:
            if self.session:
                await self.session.close()
                self.session = None
