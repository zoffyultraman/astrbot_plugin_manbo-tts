# 曼波语音插件
![GitHub release](https://img.shields.io/github/v/release/zoffyultraman/astrbot_plugin_manbo-tts)  
支持milorapart API或自定义TTS API：
- milorapart: https://api.milorapart.top/apis/mbAIsc
- 自定义API：直接返回音频文件的HTTP接口，支持text和text_language参数（[部署指南](api_setup.md)）

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
| custom_api_url | string | 自定义TTS API地址，如果设置则使用此接口，否则使用默认的milorapart API。自定义接口应直接返回音频文件，支持text和text_language参数。如需自建API服务，请参考[API部署指南](api_setup.md)。 | "" | 任意有效的HTTP URL |

## api相关
目前不提供公共API服务，但会发布预训练模型供用户自行部署。详细的GPT-SoVITS环境部署指南请参考 [API部署文档](api_setup.md)。

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

