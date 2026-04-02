# 曼波语音插件
![GitHub release](https://img.shields.io/github/v/release/zoffyultraman/astrbot_plugin_manbo-tts)  
支持多个外部API提供商：
- milorapart: https://api.milorapart.top/apis/mbAIsc
- synapse: https://www.synapse.fan/api/ai/tts

提供曼波语音信息生成

## 命令说明

|命令|说明|
|----|----|
|/manbo|提交语音生成|
-------------------------
格式/manbo <内容>

## 配置说明

在插件配置中，可以设置以下选项：

| 配置项 | 类型 | 说明 | 默认值 | 可选值 |
|--------|------|------|--------|--------|
| cache_enabled | bool | 是否启用音频缓存功能 | true | true/false |
| api_provider | string | 选择TTS API提供商 | "milorapart" | "milorapart"（旧版API）或 "synapse"（新版API） |
| session_token | string | 当api_provider为synapse时需要的认证token（next-auth.session-token） | "" | 任意字符串 |

新版API (synapse) 使用POST请求，支持更稳定的服务。

**注意**：使用 synapse API 需要提供 `next-auth.session-token`。该 token 可以通过浏览器登录 https://www.synapse.fan 后，从开发者工具（F12）的 Application -> Cookies 中获取。将获取到的 token 值填入 `session_token` 配置项中。

### synapse API 响应格式
synapse API 支持两种响应格式：
1. 直接返回URL格式：`{"url": "音频文件URL"}`
2. 嵌套格式：`{"code": 1, "data": {"url": "音频文件URL"}}`

如果 API 返回错误，请检查日志中的响应信息进行调试。常见的错误包括：
- 认证失败（session_token 无效或过期）
- 文本长度超限
- API 服务暂时不可用

## 缓存相关
缓存目录
```
data/plugin_data/astrbot_plugin_manbo_tts/audio_cache/
```
缓存文件经过md5加密，如手动放入指定目录需修改为md5文件名
python3计算md5示例：
```
import hashlib

# 待计算 MD5 的文本
text = "我去，不早说"

# 编码为 UTF-8，然后计算 MD5
md5 = hashlib.md5(text.encode('utf-8')).hexdigest()

# 输出结果
print(f"文本: {text}")
print(f"MD5: {md5}")
```
输出文件名为 md5值.wav
本库中cache/audio包含一个.wav文件，内容为“我去，不早说”
文件名为计算后的md5数值，在mac/linux上应该通用，windows需要重新运算

