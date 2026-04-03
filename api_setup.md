# GPT-SoVITS CPU 环境部署与恢复指南

本指南用于将已调优好的 GPT-SoVITS 环境迁移至新的 Ubuntu 24.04 (CPU) 服务器。

## 一、环境预检查（重要）

在开始之前，请确保目标服务器满足以下基础条件：

- **系统**：Ubuntu 22.04 / 24.04 (LTS)
- **Python**：3.9 - 3.12
- **内存**：如果物理内存小于 8G，必须配置虚拟内存（见第二步）

## 二、系统初始化（解决 Killed 问题）

由于 CPU 推理在加载模型时会瞬间占用大量内存，必须配置 Swap 缓冲。

```bash
# 建议在数据盘（如 /www）创建 8G 的虚拟内存
sudo fallocate -l 8G /www/swapfile
sudo chmod 600 /www/swapfile
sudo mkswap /www/swapfile
sudo swapon /www/swapfile

# 检查是否生效
free -h
```

## 三、解压与依赖安装

### 解压项目包
```bash
tar -xzvf gpt_sovits_cpu_backup.tar.gz
cd GPT-SoVITS
```

### 创建并激活虚拟环境
```bash
python3 -m venv venv
source venv/bin/activate
```

### 安装系统级依赖
```bash
sudo apt update
sudo apt install -y ffmpeg libsox-dev
```

### 根据清单恢复 Python 环境
```bash
pip install --upgrade pip
pip install -r requirements_cpu_stable.txt
```

## 四、常见报错修复（针对 CPU 环境）

###  屏蔽 CUDA 报错
如果启动时提示 `Failed to load libcublas.so` 或 `libnvrtc.so`，说明安装了 GPU 版本的插件。请执行：

```bash
pip uninstall -y torchcodec onnxruntime-gpu
pip install onnxruntime  # 确保只保留纯 CPU 推理引擎
```

## 五、启动 API 服务

使用 CPU 模式启动，并指定模型路径：

```bash
python3 api.py \
    -s "weights/my_model/manbo_e8_s168.pth" \
    -g "weights/my_model/manbo-e10.ckpt" \
    -dr "weights/my_model/40a4fb1be1d56efe3601fc6179dc9772.wav" \
    -dt "我要开始表演了，打开你们的摄像头" \
    -dl "zh" \
    -d "cpu" \
    -a "0.0.0.0" \
    -p 9880
```

## 六、维护注意事项

- **并发限制**：由于是 CPU 推理，建议同一时间只处理一个 TTS 请求，避免内存溢出。
- **模型热加载**：第一次推理会较慢（因为在加载模型到内存/Swap），之后的请求会变快。
- **持久化 Swap**：若需重启后自动开启虚拟内存，请将 `/www/swapfile swap swap defaults 0 0` 写入 `/etc/fstab`。