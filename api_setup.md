# GPT-SoVITS CPU 环境部署指南 (Ubuntu 24.04)

本指南针对 Ubuntu 24.04 (Python 3.12) 环境，提供完整的 GPT-SoVITS 部署方案，解决 CPU 服务器上的常见安装问题。

## 一、系统初始化（内存与编译准备）

### 1. 挂载 8G Swap 缓冲（解决内存溢出）

CPU 推理在模型加载阶段会有内存峰值，必须配置虚拟内存。

```bash
sudo fallocate -l 8G /www/swapfile
sudo chmod 600 /www/swapfile
sudo mkswap /www/swapfile
sudo swapon /www/swapfile
# 确认生效：free -h
```

### 2. 安装系统开发库（解决 C++ 编译报错）

```bash
sudo apt update
sudo apt install -y ffmpeg libsox-dev build-essential cmake g++ python3.12-dev libsndfile1-dev python3.12-venv
```

## 二、虚拟环境与核心组件安装

### 1. 创建纯净环境

```bash
tar -xzvf gpt_sovits_cpu_backup.tar.gz
cd /www/GPT-SoVITS
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
```

### 2. 安装核心依赖包

提前安装 CPU 专用版本，防止被后续自动化清单覆盖。

```bash
# 1. PyTorch CPU 核心
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# 2. ONNX CPU 推理引擎（确保不带 -gpu）
pip install onnxruntime

# 3. 推理框架与分词工具
pip install pytorch-lightning transformers jieba "Cython<3.0.0"

# 4. 日语编译支持（必须在安装完系统开发库后执行）
pip install pyopenjtalk --no-build-isolation
```

## 三、环境适配：jieba_fast 替代方案

由于 jieba_fast 不支持 Python 3.12 且难以编译，我们通过软链接让标准 jieba 替代 jieba_fast。

```bash
# 执行以下命令自动创建环境软链接（无需修改源码）
SITE_PACKAGES=$(python3 -c "import site; print(site.getsitepackages()[0])")
ln -s ${SITE_PACKAGES}/jieba ${SITE_PACKAGES}/jieba_fast

# 验证替代方案是否成功
python3 -c "import jieba_fast; print('jieba_fast 替代成功')"
```

## 四、依赖清单预处理

### 1. 预处理依赖清单

剔除所有已手动安装或有冲突的组件。

```bash
# 复制副本
cp requirements.txt requirements_cpu_final.txt

# 剔除已安装或有冲突的组件：torch, nvidia, onnxruntime, pytorch-lightning 以及 jieba_fast
sed -i '/torch/d' requirements_cpu_final.txt
sed -i '/nvidia/d' requirements_cpu_final.txt
sed -i '/onnxruntime/d' requirements_cpu_final.txt
sed -i '/pytorch-lightning/d' requirements_cpu_final.txt
sed -i '/jieba_fast/d' requirements_cpu_final.txt

# 去掉所有版本限制，允许适配 Python 3.12
sed -i 's/==.*//g' requirements_cpu_final.txt
```

### 2. 安装剩余依赖

```bash
pip install -r requirements_cpu_final.txt
```

## 五、验证与启动

### 1. 环境检查

```bash
python -c "import torch; import onnxruntime as ort; print(f'Torch-CPU: {not torch.cuda.is_available()} | ONNX-Providers: {ort.get_available_providers()}')"
```

### 2. 启动 API 服务

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

## 六、维护建议

**持久化虚拟内存配置**：
将 `/www/swapfile swap swap defaults 0 0` 写入 `/etc/fstab`。

**首次请求延迟**：
重启服务后的第一次请求涉及模型从 Swap 换入内存，耗时 10-30s 属于正常现象，后续请求将恢复正常速度。

**CPU 线程控制**：
若 CPU 占用过高导致系统卡顿，可在启动前运行 `export OMP_NUM_THREADS=4` 限制并行线程数。

**制作成服务**：
#### 1.创建Service配置文件
使用 sudo 创建一个名为 gpt-sovits.service 的文件：
```bash
sudo vi /etc/systemd/system/gpt-sovits.service
```

#### 2.写入配置内容
请根据你的实际路径修改 WorkingDirectory 和 ExecStart（假设你的项目在 /www/GPT-SoVITS）：
```ini
[Unit]
Description=GPT-SoVITS-API Service
After=network.target

[Service]
# 指定运行用户（建议用你的常用用户名，避免 root）
User=root
Group=root

# 项目根目录
WorkingDirectory=/www/GPT-SoVITS

# 启动命令：指向虚拟环境中的 python 解释器
# 注意修改 -s -g -dr 等参数为你真实的模型和音频路径
ExecStart=/www/GPT-SoVITS/venv/bin/python3 api.py \
    -s "weights/my_model/manbo_e8_s168.pth" \
    -g "weights/my_model/manbo-e10.ckpt" \
    -dr "weights/my_model/40a4fb1be1d56efe3601fc6179dc9772.wav" \
    -dt "我要开始表演了，打开你们的摄像头" \
    -dl "zh" \
    -d "cpu" \
    -a "0.0.0.0" \
    -p 9880

# 崩溃后自动重启，等待 10 秒
Restart=always
RestartSec=10

# 标准输出与错误日志
StandardOutput=append:/var/log/gpt_sovits.log
StandardError=append:/var/log/gpt_sovits.log

[Install]
WantedBy=multi-user.target
```

#### 3.激活并启动服务
```bash
# 1. 重新加载系统服务配置
sudo systemctl daemon-reload

# 2. 设置开机自启
sudo systemctl enable gpt-sovits

# 3. 立即启动服务
sudo systemctl start gpt-sovits
```