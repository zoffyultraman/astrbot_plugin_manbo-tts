import aiohttp
import asyncio
import hashlib
import json
import os
import pathlib
from urllib.parse import urlparse, urlencode, urlunparse, parse_qs
from typing import Optional, Dict
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
        self.custom_api_url = self.config.get("custom_api_url", "")
        # 提取自定义API的域名用于URL验证
        self.custom_api_domain = ""
        if self.custom_api_url:
            try:
                parsed = urlparse(self.custom_api_url)
                self.custom_api_domain = parsed.netloc
            except Exception as e:
                logger.warning(f"解析自定义API URL失败: {e}")

        # 根据AstrBot规范，大文件存储在 data/plugin_data/{plugin_name}/ 目录下
        # 不再提供自定义缓存目录选项，所有缓存文件统一存储到规范目录
        data_path = pathlib.Path(get_astrbot_data_path())
        self.cache_dir = str((data_path / "plugin_data" / self.PLUGIN_NAME / "audio_cache").resolve())
        self.mapping_file = str(pathlib.Path(self.cache_dir) / "md5_mapping.json")

        logger.info(f"缓存功能启用: {self.cache_enabled}")
        logger.info(f"缓存目录（规范路径）: {self.cache_dir}")
        logger.info(f"映射文件路径: {self.mapping_file}")

        self.session = None
        self.lock = asyncio.Lock()  # 用于session管理的锁
        self.mapping_lock = asyncio.Lock()  # 用于映射文件管理的锁

    @filter.on_astrbot_loaded()  # 插件加载完成后初始化 session
    async def on_loaded(self):
        """插件初始化，创建一个全局的 session"""
        logger.info(f"插件加载完成，开始初始化")
        logger.info(f"缓存功能状态: {self.cache_enabled}")

        async with self.lock:
            if not self.session or self.session.closed:
                logger.info("初始化aiohttp session")
                self.session = aiohttp.ClientSession()
                logger.info("aiohttp session初始化完成")

        # 确保缓存目录存在
        if self.cache_enabled:
            logger.info("缓存功能已启用，准备缓存目录")
            cache_path = pathlib.Path(self.cache_dir)
            logger.info(f"缓存目录路径: {cache_path.absolute()}")
            cache_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"缓存目录已准备：{cache_path.absolute()}")

            # 初始化映射文件并迁移现有缓存
            logger.info("开始初始化映射文件")
            await self._init_mapping_file()
            logger.info("映射文件初始化完成")
        else:
            logger.info("缓存功能未启用，跳过映射文件初始化")

    async def _init_mapping_file(self):
        """初始化映射文件并迁移现有缓存"""
        logger.info(f"开始初始化映射文件: {self.mapping_file}")
        mapping_path = pathlib.Path(self.mapping_file)
        cache_dir_path = pathlib.Path(self.cache_dir)

        logger.info(f"映射文件路径: {mapping_path}, 是否存在: {mapping_path.exists()}")
        logger.info(f"缓存目录路径: {cache_dir_path}, 是否存在: {cache_dir_path.exists()}")

        if not mapping_path.exists():
            # 创建空的映射文件
            logger.info(f"映射文件不存在，创建新的映射文件")
            await self._save_mapping({})
            logger.info(f"创建新的映射文件完成: {self.mapping_file}")
        else:
            # 加载现有映射
            logger.info(f"映射文件已存在，加载现有映射")
            mapping = await self._load_mapping()
            logger.info(f"加载现有映射文件完成，包含 {len(mapping)} 条记录")

        # 迁移现有缓存文件（扫描.wav文件，确保所有文件都在映射中）
        logger.info("开始迁移现有缓存文件")
        await self._migrate_existing_cache()
        logger.info("迁移现有缓存文件完成")

    async def _load_mapping(self) -> Dict[str, str]:
        """加载映射文件"""
        mapping_path = pathlib.Path(self.mapping_file)
        if not mapping_path.exists():
            return {}

        try:
            async with self.mapping_lock:
                with open(self.mapping_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"加载映射文件失败: {e}")
            return {}

    async def _save_mapping(self, mapping: Dict[str, str]):
        """保存映射文件"""
        try:
            async with self.mapping_lock:
                with open(self.mapping_file, 'w', encoding='utf-8') as f:
                    json.dump(mapping, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error(f"保存映射文件失败: {e}")

    async def _add_to_mapping(self, md5_hash: str, text: str):
        """添加新的映射记录"""
        mapping = await self._load_mapping()
        mapping[md5_hash] = text
        await self._save_mapping(mapping)
        logger.debug(f"添加映射记录: {md5_hash} -> {text[:50]}...")

    async def _remove_from_mapping(self, md5_hash: str):
        """从映射中移除记录"""
        mapping = await self._load_mapping()
        if md5_hash in mapping:
            del mapping[md5_hash]
            await self._save_mapping(mapping)
            logger.debug(f"移除映射记录: {md5_hash}")

    async def _migrate_existing_cache(self):
        """迁移现有缓存文件，确保所有.wav文件都在映射中，并清理不存在的映射条目"""
        cache_dir_path = pathlib.Path(self.cache_dir)
        mapping = await self._load_mapping()
        updated = False
        cleaned = False

        # 获取所有.wav文件的MD5哈希
        existing_files = {wav_file.stem for wav_file in cache_dir_path.glob("*.wav")}

        # 1. 添加缺失的映射条目
        for md5_hash in existing_files:
            if md5_hash not in mapping:
                # 添加未知文本标记
                mapping[md5_hash] = "[unknown]"
                updated = True
                logger.info(f"迁移现有缓存文件: {md5_hash}.wav -> [unknown]")

        # 2. 清理不存在的映射条目
        mapping_keys = list(mapping.keys())
        for md5_hash in mapping_keys:
            if md5_hash not in existing_files:
                del mapping[md5_hash]
                cleaned = True
                logger.info(f"清理不存在的映射条目: {md5_hash}")

        if updated or cleaned:
            await self._save_mapping(mapping)
            if updated:
                logger.info(f"新增 {len([k for k, v in mapping.items() if v == '[unknown]' and k in existing_files])} 条未知记录")
            if cleaned:
                logger.info(f"清理了 {len([k for k in mapping_keys if k not in existing_files])} 个不存在的映射条目")

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

                # 添加映射记录
                md5_hash = cache_path.stem  # 移除.wav扩展名获取MD5哈希
                await self._add_to_mapping(md5_hash, text)

                return True
        except Exception as e:
            logger.error(f"下载音频到缓存失败：{str(e)}")
            # 删除可能部分下载的文件
            if cache_path.exists():
                cache_path.unlink()
            return False

    def _build_custom_api_url(self, text: str) -> str:
        """构建自定义API的完整URL"""
        parsed = urlparse(self.custom_api_url)
        # 获取现有查询参数
        existing_params = parse_qs(parsed.query)
        # 添加或覆盖参数
        existing_params['text'] = [text]
        existing_params['text_language'] = ['zh']
        # 构建新查询字符串
        new_query = urlencode(existing_params, doseq=True)
        # 重建URL
        new_parsed = parsed._replace(query=new_query)
        # 确保路径部分不为空（避免http://example.com?query形式）
        if not new_parsed.path:
            new_parsed = new_parsed._replace(path='/')
        return urlunparse(new_parsed)

    async def fetch_audio_url(self, text_to_convert):
        """异步获取音频 URL，带有超时设置"""
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

            # 根据配置选择 API
            if self.custom_api_url:
                logger.info(f"使用自定义 API，文本长度：{len(text_to_convert)}")
                # 构建自定义 API 请求 URL
                audio_url = self._build_custom_api_url(text_to_convert)
                # 验证 URL 是否允许
                if self.is_valid_url(audio_url):
                    return audio_url
                else:
                    logger.error(f"自定义 API URL 未通过验证：{audio_url}")
                    return None
            else:
                logger.info(f"使用 milorapart API，文本长度：{len(text_to_convert)}")
                async with self.session.get(
                    MANBO_TTS_API_URL,
                    params={"text": text_to_convert, "format": "wav"},
                    timeout=TIMEOUT,  # 使用全局 timeout
                ) as response:
                    if response.status != 200:
                        logger.error(f"milorapart接口请求失败，状态码：{response.status}")
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

    def is_valid_url(self, url):
        """校验 URL 是否为有效的外部 URL，避免 SSRF"""
        try:
            parsed_url = urlparse(url)
            logger.info(f"URL 校验: 原始URL={url}, 协议={parsed_url.scheme}, 域名={parsed_url.netloc}")
            allowed_domains = ALLOWED_DOMAINS.copy()
            if self.custom_api_domain:
                allowed_domains.append(self.custom_api_domain)
            logger.info(f"允许的域名列表: {allowed_domains}")
            # 校验是否为允许的 http/https 协议和域名
            if parsed_url.scheme in ["http", "https"] and parsed_url.netloc in allowed_domains:
                logger.info("URL 校验通过")
                return True
            logger.error(f"不允许的域名或协议：{parsed_url.netloc}")
            return False
        except Exception as e:
            logger.error(f"URL 校验失败：{str(e)}")
            return False

    @filter.command("manbo-list")
    async def manbo_list(self, event: AstrMessageEvent):
        """列出所有缓存的音频文件及其对应的文本"""
        logger.info(f"执行manbo-list命令")

        if not self.cache_enabled:
            logger.warning("缓存功能未启用，无法列出缓存文件")
            yield event.plain_result("缓存功能未启用，无法列出缓存文件。")
            return

        try:
            # 确保映射文件已初始化
            await self._init_mapping_file()

            mapping = await self._load_mapping()
            logger.info(f"加载映射文件，包含 {len(mapping)} 条记录")

            if not mapping:
                yield event.plain_result("缓存目录为空，暂无缓存文件。")
                return

            # 统计信息
            total_files = len(mapping)
            known_files = len([text for text in mapping.values() if text != "[unknown]"])
            unknown_files = total_files - known_files

            # 构建输出消息
            output = f"📊 缓存统计:\n"
            output += f"• 总缓存文件数: {total_files}\n"
            output += f"• 已知文本文件: {known_files}\n"
            output += f"• 未知文本文件: {unknown_files}\n\n"

            if known_files > 0:
                output += "📋 缓存内容列表:\n"
                for i, (md5_hash, text) in enumerate(mapping.items(), 1):
                    if text != "[unknown]":
                        # 截断长文本
                        display_text = text if len(text) <= 50 else text[:47] + "..."
                        output += f"{i}. {display_text}\n"

            if unknown_files > 0:
                output += f"\n⚠️  有 {unknown_files} 个缓存文件缺少文本信息（可能是旧版本创建的缓存）\n"
                output += f"   这些文件的MD5哈希为: {', '.join([md5 for md5, text in mapping.items() if text == '[unknown]'][:10])}"
                if unknown_files > 10:
                    output += f" 等（共{unknown_files}个）"

            yield event.plain_result(output)

        except Exception as e:
            logger.error(f"列出缓存文件时发生错误: {str(e)}")
            yield event.plain_result("列出缓存文件时发生错误，请查看日志。")

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

        # 特殊处理：如果文本是"list"，提示使用manbo-list命令
        if text_str.lower() == "list":
            yield event.plain_result("请使用 '/manbo-list' 命令查看缓存列表，或输入其他文本进行语音转换。")
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

                    # 确保映射记录存在（处理旧缓存或未知文本）
                    md5_hash = cache_path.stem  # 移除.wav扩展名获取MD5哈希
                    await self._add_to_mapping(md5_hash, text_str)

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





