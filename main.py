import aiohttp
import asyncio
import hashlib
import os
import pathlib
from urllib.parse import urlparse
from typing import Optional
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import logger, AstrBotConfig
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
import astrbot.core.message.components as Comp

# Manbo TTS API 信息
MANBO_TTS_API_URL = "https://api.milorapart.top/apis/mbAIsc"
MAX_TEXT_LENGTH = 200  # 设置最大文本长度，避免请求过长
ALLOWED_DOMAINS = ["api.milorapart.top"]  # 允许的音频 URL 域名白名单
TIMEOUT = aiohttp.ClientTimeout(total=30, connect=10, sock_connect=10, sock_read=20)  # 全局超时设置


class ManboTTSPlugin(Star):
    PLUGIN_NAME = "astrbot_plugin_manbo_tts"

    def __init__(self, context: Context, config: Optional[AstrBotConfig] = None):
        super().__init__(context)
        self.config = config or {}
        self.cache_enabled = self.config.get("cache_enabled", True)

        # 根据AstrBot规范，大文件存储在 data/plugin_data/{plugin_name}/ 目录下
        # 不再提供自定义缓存目录选项，所有缓存文件统一存储到规范目录
        data_path = pathlib.Path(get_astrbot_data_path())
        self.cache_dir = str((data_path / "plugin_data" / self.PLUGIN_NAME / "audio_cache").resolve())

        logger.info(f"缓存功能启用: {self.cache_enabled}")
        logger.info(f"缓存目录（规范路径）: {self.cache_dir}")

        self.session = None
        self.lock = asyncio.Lock()

    @filter.on_astrbot_loaded()  # 插件加载完成后初始化 session
    async def on_loaded(self):
        """插件初始化，创建一个全局的 session"""
        async with self.lock:
            if not self.session or self.session.closed:
                self.session = aiohttp.ClientSession()

        # 确保缓存目录存在
        if self.cache_enabled:
            cache_path = pathlib.Path(self.cache_dir)
            cache_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"缓存目录已准备：{cache_path.absolute()}")

    def _get_cache_key(self, text: str) -> str:
        """生成文本的缓存键（MD5哈希）"""
        return hashlib.md5(text.encode('utf-8')).hexdigest() + ".wav"

    def _get_cache_path(self, text: str) -> pathlib.Path:
        """获取缓存文件路径"""
        cache_key = self._get_cache_key(text)
        return pathlib.Path(self.cache_dir) / cache_key

    def _is_cached(self, text: str) -> bool:
        """检查音频是否已缓存"""
        cache_path = self._get_cache_path(text)
        exists = cache_path.exists()
        if exists:
            logger.info(f"缓存命中: {cache_path}")
        else:
            logger.info(f"缓存未命中: {cache_path}")
        return exists

    async def _download_to_cache(self, audio_url: str, text: str) -> bool:
        """下载音频文件到缓存目录"""
        # 确保 session 已初始化
        if not self.session or self.session.closed:
            async with self.lock:
                if not self.session or self.session.closed:
                    self.session = aiohttp.ClientSession()

        cache_path = self._get_cache_path(text)
        try:
            async with self.session.get(audio_url, timeout=TIMEOUT) as response:
                if response.status != 200:
                    logger.error(f"下载音频失败，状态码：{response.status}")
                    return False

                # 保存音频文件
                with open(cache_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        f.write(chunk)

                logger.info(f"音频已缓存：{cache_path}")
                return True
        except Exception as e:
            logger.error(f"下载音频到缓存失败：{str(e)}")
            # 删除可能部分下载的文件
            if cache_path.exists():
                cache_path.unlink()
            return False

    async def fetch_audio_url(self, text_to_convert):
        """异步获取音频 URL，带有超时设置，使用 GET 请求"""
        # 双重检查锁定：首先检查 session 状态，只有在未初始化或已关闭时才加锁
        if not self.session or self.session.closed:
            async with self.lock:
                if not self.session or self.session.closed:
                    logger.info("Session 未初始化或已关闭，正在初始化...")
                    self.session = aiohttp.ClientSession()

        try:
            # 检查 session 是否已关闭，避免抛出 RuntimeError
            if self.session.closed:
                logger.error("会话已关闭，无法继续请求。")
                return None

            async with self.session.get(
                MANBO_TTS_API_URL,
                params={"text": text_to_convert, "format": "wav"},
                timeout=TIMEOUT,  # 使用全局 timeout
            ) as response:
                if response.status != 200:
                    logger.error(f"接口请求失败，状态码：{response.status}")
                    return None

                try:
                    data = await response.json()
                    # 校验 data 格式和 'url' 字段
                    if isinstance(data, dict) and "url" in data:
                        audio_url = data["url"]
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
        except asyncio.TimeoutError:
            logger.error("请求超时")
            return None
        except aiohttp.ClientError as e:
            logger.error(f"请求异常：{str(e)}")
            return None
        except RuntimeError as e:
            logger.error(f"会话已关闭，无法请求音频：{str(e)}")
            return None

    @staticmethod
    def is_valid_url(url):
        """校验 URL 是否为有效的外部 URL，避免 SSRF"""
        try:
            parsed_url = urlparse(url)
            # 校验是否为允许的 http/https 协议和域名
            if parsed_url.scheme in ["http", "https"] and parsed_url.netloc in ALLOWED_DOMAINS:
                return True
            logger.error(f"不允许的域名或协议：{parsed_url.netloc}")
            return False
        except Exception as e:
            logger.error(f"URL 校验失败：{str(e)}")
            return False

    @filter.command("manbo")
    async def manbo(self, event: AstrMessageEvent, text: str):
        """这是一个文本转语音（TTS）指令"""
        # 处理文本参数：如果text是字符串，直接使用；如果是列表，拼接
        if isinstance(text, str):
            text_str = text.strip()
        else:
            # 假设是列表或其他可迭代对象
            text_str = " ".join(text).strip()
        logger.info(f"原始text类型: {type(text)}, 内容: {text}")
        logger.info(f"处理后的文本: {text_str}")

        # 校验文本是否为空字符串
        if not text_str:
            yield event.plain_result("请输入要转换为语音的文本！")
            return

        # 输入文本长度限制
        if len(text_str) > MAX_TEXT_LENGTH:
            yield event.plain_result(f"文本长度超过限制（{MAX_TEXT_LENGTH} 字符）。请缩短文本再试。")
            return

        try:
            logger.info(f"处理文本: {text_str}")
            logger.info(f"缓存功能状态: {self.cache_enabled}")

            # 检查缓存
            if self.cache_enabled:
                logger.info("正在检查缓存...")
                if self._is_cached(text_str):
                    cache_path = self._get_cache_path(text_str)
                    logger.info(f"使用缓存音频：{cache_path}")
                    # 发送本地音频文件
                    chain = [Comp.Record(file=str(cache_path))]
                    yield event.chain_result(chain)
                    return
                else:
                    logger.info("未找到缓存，将请求API")
            else:
                logger.info("缓存功能已禁用，直接请求API")

            # 获取音频 URL
            audio_url = await self.fetch_audio_url(text_str)
            if not audio_url:
                yield event.plain_result("无法获取音频文件，接口返回无效数据。")
                return

            # 如果启用缓存，下载到本地
            if self.cache_enabled:
                download_success = await self._download_to_cache(audio_url, text_str)
                if download_success:
                    cache_path = self._get_cache_path(text_str)
                    chain = [Comp.Record(file=str(cache_path), url=str(cache_path))]
                else:
                    # 下载失败，直接发送原始 URL
                    logger.warning("缓存下载失败，使用原始 URL")
                    chain = [Comp.Record(url=audio_url)]
            else:
                # 未启用缓存，直接发送原始 URL
                chain = [Comp.Record(url=audio_url)]

            yield event.chain_result(chain)

        except Exception as e:
            logger.error(f"处理请求时发生错误: {str(e)}")
            yield event.plain_result("发生了错误，请稍后再试。")

    async def terminate(self):
        """插件销毁时的清理工作"""
        async with self.lock:  # 添加锁来确保资源清理的并发安全
            if self.session:
                await self.session.close()  # 关闭 session
                self.session = None  # 清空 session