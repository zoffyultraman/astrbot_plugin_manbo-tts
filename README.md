# 曼波语音插件
![GitHub release](https://img.shields.io/github/v/release/zoffyultraman/astrbot_plugin_manbo-tts)  
基于外部API：https://api.milorapart.top/apis/mbAIsc
提供曼波语音信息生成

## 命令说明

|命令|说明|
|----|----|
|manbo|提交语音生成|
-------------------------
格式/manbo <内容>
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

