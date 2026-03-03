# TACO-X 本地大模型部署指南

> 基于 Qwen3-32B + 2×L20 GPU (TP2) 的实际部署经验编写，记录了官方文档未涵盖的配置细节与常见陷阱。
>
> **当前镜像版本**：`v0.0.1-260302-default`
>
> 历史版本归档见 `local_llm/` 下按日期命名的子目录。

## 1. 概述

TACO-X 是腾讯推出的高性能 LLM 推理引擎，提供 OpenAI 兼容的 API 接口。本文档以 **Qwen3-32B** 为例，详细说明如何通过 docker-compose 部署本地大模型服务。

### 支持的模型

| 模型 | model_type | 配置目录名 | 镜像内置配置 |
|------|-----------|-----------|:----------:|
| InternVL2.5-2B | `intern2_5_vl_2b` | `internvl2.5_2b_taco_x_config` | 是 |
| Qwen2.5-VL-7B | `qwen2_5_vl_7b` | `qwen2.5_vl_7b_taco_x_config` | 是 |
| Qwen3-32B | `qwen3_32b` | `qwen3_32b_taco_x_config` | **否** |
| Qwen3-VL-8B | `qwen3_vl_8b` | `qwen3_vl_8b_taco_x_config` | **否** |

> **重要发现**：官方文档声称所有模型的配置文件都在镜像的 `/workspace` 目录下，但实际上 `v0.0.1-260302-default` 镜像**只内置了 InternVL2.5-2B 和 Qwen2.5-VL-7B 的配置**。Qwen3 系列需要自行创建配置文件并 mount 到容器中。

## 2. 前置要求

- Docker + docker-compose
- NVIDIA 驱动 + nvidia-container-toolkit
- 足够的 GPU 显存（Qwen3-32B 约需 2×24GB）
- 预下载的模型权重

### 安装 nvidia-container-toolkit

```bash
# Ubuntu/Debian
distribution=$(. /etc/os-release; echo $ID$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

### 下载模型权重

```bash
pip install huggingface_hub
huggingface-cli download Qwen/Qwen3-32B
```

默认下载路径：`~/.cache/huggingface/hub/models--Qwen--Qwen3-32B/`

## 3. 镜像

```bash
docker pull taco-0.tencentcloudcr.com/taco/taco_x_prod:v0.0.1-260302-default
```

镜像内部关键路径：
- Python 环境：`/usr/local/miniconda/lib/python3.12/site-packages/taco_x/`
- 内置配置目录：`/workspace/`
- 推理引擎核心：`taco_x/taco_x_engine.so`（C++ 实现）

## 4. 配置文件详解

每个模型需要 3 个 JSON 配置文件，放在一个目录中。配置文件统一存放在项目的 `local_llm/` 目录下：

```
local_llm/
├── deploy.md                          # 本文档（最新版）
├── qwen3_32b_taco_x_config/          # 当前使用的引擎配置
│   ├── scheduler_config.json
│   ├── kv_cache_config.json
│   └── lookahead_cache_config.json
└── 2026-03-03_v0.0.1-260302/         # 历史归档
    ├── deploy.md
    ├── local_llm_service.md
    └── qwen3_32b_taco_x_config/
```

### 4.1 scheduler_config.json

这是最容易踩坑的配置文件。C++ 引擎会严格检查所有字段，缺一个都会直接报错退出。

```json
{
    "max_num_seqs": 8,
    "max_num_images": 0,
    "max_num_batched_tokens": 16384,
    "max_model_len": 16384,
    "long_prefill_token_threshold": 0,
    "max_num_encoder_input_tokens": 16384,
    "encoder_cache_size": 32768,
    "max_num_mm_embeds_per_batch": 0,
    "gpu_memory_utilization": 0.90,
    "max_num_image_windows": 0,
    "enable_cuda_graph": false,
    "enable_custom_all_reduce": false,
    "enable_vision_dp": false,
    "max_num_lora_models_reserved": 0
}
```

**字段说明：**

| 字段 | 说明 | 纯文本模型建议值 |
|------|------|:---:|
| `max_num_seqs` | 最大并发序列数 | 8 |
| `max_num_images` | 最大图片数（非 VL 模型设 0） | 0 |
| `max_num_batched_tokens` | 单批次最大 token 数 | 16384 |
| `max_model_len` | 模型最大序列长度 | 16384 |
| `long_prefill_token_threshold` | 长 prefill 阈值 | 0 |
| `max_num_encoder_input_tokens` | 编码器最大输入 token 数 | 16384 |
| `encoder_cache_size` | 编码器缓存大小 | 32768 |
| `max_num_mm_embeds_per_batch` | 每批次多模态嵌入数 | 0 |
| `gpu_memory_utilization` | GPU 显存利用率 | 0.90 |
| `max_num_image_windows` | 最大图片窗口数 | 0 |
| `enable_cuda_graph` | 启用 CUDA Graph 优化 | false |
| `enable_custom_all_reduce` | 启用自定义 AllReduce | false |
| `enable_vision_dp` | 启用视觉数据并行 | false |
| `max_num_lora_models_reserved` | 预留 LoRA 模型数 | 0 |

**踩坑记录：**

1. **字段缺失直接崩溃**：官方文档只展示了 VL 模型的参考配置（约 6 个字段），但 C++ 引擎实际上要求 **14 个字段全部存在**。每缺一个字段，引擎都会报 `[json.exception.out_of_range.403] key 'xxx' not found` 然后退出，只能逐个排查。

2. **`max_num_encoder_input_tokens` 约束**：必须 >= `max_num_batched_tokens`，否则报错：
   ```
   Configuration Error in scheduler_config.json!!!
   "max_num_encoder_input_tokens"(=0) must be greater or equal than "max_num_batched_tokens"(=16384)!
   ```
   即使纯文本模型不用 encoder，也不能设为 0。

3. **字段发现方法**：由于官方没有完整文档，可通过以下方法提取引擎支持的所有配置 key：
   ```bash
   docker run --rm --entrypoint bash <image> -c \
     'strings /usr/local/miniconda/lib/python3.12/site-packages/taco_x/taco_x_engine.so | grep -E "^(enable_|max_|gpu_|block_|disk_|kv_)" | sort -u'
   ```

### 4.2 kv_cache_config.json

```json
{
    "enable_caching": true,
    "block_size": 16,
    "gpu_memory_utilization": 0.1,
    "disk_cache_path": "disk_cache",
    "kv_layout_type": 1
}
```

| 字段 | 说明 |
|------|------|
| `enable_caching` | 是否启用 KV Cache |
| `block_size` | Cache block 大小 |
| `gpu_memory_utilization` | KV Cache 占用的 GPU 显存比例 |
| `disk_cache_path` | 磁盘缓存路径 |
| `kv_layout_type` | KV Cache 布局类型 |

### 4.3 lookahead_cache_config.json

投机解码（Speculative Decoding）相关配置，需要 `--opt-level >= 2` 才会生效。

```json
{
    "cache_mode": 2,
    "cache_size": 5000000,
    "copy_length": 1,
    "match_length": 2,
    "turbo_match_length": 7,
    "min_match_length": 2,
    "cell_max_size": 16,
    "voc_size": 151936,
    "max_seq_len": 32768,
    "eos_token_id": 151645,
    "top_k": 1,
    "threshold": 2.0,
    "decay": 0.5,
    "is_hybrid": true,
    "is_debug": false,
    "log_interval": 100,
    "target_parallelism": 512,
    "top_k_in_cell": 16,
    "token_paths_top_k": 2,
    "start_freq": 10.0,
    "num_threads": 8,
    "global_cache_switch": true,
    "decoding_max_mem": 0.1
}
```

**注意**：`voc_size` 和 `eos_token_id` 需要根据模型设置。可从模型的 `config.json` 和 `tokenizer_config.json` 中获取：

```bash
# 获取 vocab_size
python3 -c "import json; print(json.load(open('config.json'))['vocab_size'])"

# 获取 eos_token_id
python3 -c "import json; c=json.load(open('tokenizer_config.json')); print(c.get('eos_token_id'))"
```

Qwen3-32B 的值：`voc_size=151936`，`eos_token_id=151645`。

## 5. 启动命令

### 基本启动

```bash
python3 -m taco_x.api_server \
  --model_dir ${model_dir} \
  --model_type ${model_type} \
  --config_dir ${config_dir} \
  --port 18080 \
  --opt-level 3
```

### 带 Tensor Parallel + FP8 量化启动（推荐）

```bash
python3 -m taco_x.api_server \
  --model_dir ${model_dir} \
  --model_type ${model_type} \
  --config_dir ${config_dir} \
  --port 18080 \
  --tp 2 \
  --opt-level 3 \
  --quantization fp8
```

### 带 Tensor Parallel 启动（不量化）

```bash
python3 -m taco_x.api_server \
  --model_dir ${model_dir} \
  --model_type ${model_type} \
  --config_dir ${config_dir} \
  --port 18080 \
  --tp 2 \
  --opt-level 3
```

### 完整参数说明

| 参数 | 说明 | 示例 |
|------|------|------|
| `--model_dir` | 模型权重目录（HuggingFace snapshot） | `/models/Qwen3-32B/snapshots/xxxx` |
| `--model_type` | 模型类型标识符 | `qwen3_32b` |
| `--config_dir` | 引擎配置文件目录 | `/workspace/qwen3_32b_taco_x_config` |
| `--port` | API 监听端口 | `18080` |
| `--tp` | Tensor Parallel 并行数 | `2` |
| `--opt-level` | 优化等级（0-3），3 为最高 | `3` |
| `--quantization` | 量化类型 | `fp8`（推荐）、`awq`、`gptq` |
| `--lora-modules` | LoRA 模块路径（可选） | `name=path` |

**注意**：`--model_dir` 必须指向包含 `config.json` 和 safetensors 文件的目录。如果模型是通过 `huggingface-cli download` 下载的，路径格式为：
```
~/.cache/huggingface/hub/models--Qwen--Qwen3-32B/snapshots/<commit_hash>/
```

## 6. docker-compose 集成部署

以下是经过验证的 docker-compose 配置：

```yaml
tacox:
  image: taco-0.tencentcloudcr.com/taco/taco_x_prod:v0.0.1-260302-default
  container_name: teamgr-tacox
  restart: unless-stopped
  ipc: host                    # 必需：共享内存，TP 通信依赖
  ulimits:
    memlock: -1                # 必需：解除内存锁定限制
    stack: 67108864            # 必需：扩大栈空间（64MB）
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 2           # GPU 数量，需与 --tp 一致
            capabilities: [gpu]
  volumes:
    # 模型权重（读写挂载，FP8 量化需要写入缓存文件）
    - ~/.cache/huggingface/hub/models--Qwen--Qwen3-32B:/models/Qwen3-32B
    # 引擎配置文件（只读挂载，从 local_llm/ 目录）
    - ../local_llm/qwen3_32b_taco_x_config:/workspace/qwen3_32b_taco_x_config:ro
  expose:
    - "18080"
  entrypoint: >
    bash -c "python3 -m taco_x.api_server
    --model_dir /models/Qwen3-32B/snapshots/9216db5781bf21249d130ec9da846c4624c16137
    --model_type qwen3_32b
    --config_dir /workspace/qwen3_32b_taco_x_config
    --port 18080
    --tp 2
    --opt-level 3
    --quantization fp8"
  healthcheck:
    test: ["CMD", "python3", "-c", "import urllib.request,json; urllib.request.urlopen(urllib.request.Request('http://localhost:18080/v1/chat/completions',data=json.dumps({'messages':[{'role':'user','content':'hi'}],'max_tokens':1}).encode(),headers={'Content-Type':'application/json'}))"]
    interval: 30s
    timeout: 30s
    retries: 10
    start_period: 600s         # FP8 首次量化需 5-8 分钟，后续启动约 2-3 分钟
```

**docker-compose 关键配置解释：**

1. **`ipc: host`**：Tensor Parallel 需要共享内存进行进程间通信，必须设置。

2. **`ulimits`**：C++ 引擎需要大量内存锁定和栈空间，不设置会导致运行时崩溃。

3. **配置文件 mount**：由于镜像不包含 Qwen3 的配置，需要将 `local_llm/qwen3_32b_taco_x_config` 目录 mount 到 `/workspace/qwen3_32b_taco_x_config`。

4. **healthcheck**：不能使用 `/v1/models` 端点（TACO-X 未实现，返回 404）。必须发送一个实际的推理请求来检测就绪状态。

5. **模型权重读写挂载**：使用 `--quantization fp8` 时，引擎会将量化后的权重缓存到 model_dir（生成 `*_fp8.safetensors` 文件），因此不能用 `:ro`。首次启动需要在线量化（约 5-8 分钟），后续启动直接加载缓存文件会快得多。

6. **`start_period: 180s`**：BF16 模式约需 2-3 分钟。FP8 首次启动需 5-8 分钟（含在线量化），建议设为 `600s`。

## 7. API 调用

TACO-X 提供 OpenAI 兼容的 API，但有一些差异需要注意。

### 基本调用

```python
import httpx

resp = httpx.post("http://tacox:18080/v1/chat/completions", json={
    "messages": [{"role": "user", "content": "你好"}],
    "max_tokens": 100,
    "temperature": 0.7,
})
print(resp.json()["choices"][0]["message"]["content"])
```

### 与标准 OpenAI API 的差异

| 差异点 | 说明 |
|--------|------|
| **`model` 字段** | 不要传递 `model` 字段，或者传递完整的 `--model_dir` 路径。传递模型名（如 `"Qwen3-32B"`）会报 `Model mismatch` 错误 |
| **`/v1/models` 端点** | 未实现，返回 404 |
| **流式输出** | 支持，通过 `"stream": true` 开启 |
| **`stop` 字段** | 支持自定义 stop 序列 |
| **Usage 统计** | 在响应的 `usage` 字段中返回 token 用量 |

### model 字段踩坑

TACO-X 校验逻辑（源码摘录）：
```python
if model_name != model_dir and model_name not in lora_modules_map:
    callback(ERROR_TAG, True, f"Model mismatch: expected {model_dir} ...")
```

所以只有三种做法：
1. **不传 `model` 字段**（推荐）
2. 传入完整的 `model_dir` 路径（如 `/models/Qwen3-32B/snapshots/xxxx`）
3. 传入 LoRA 模块名

### Qwen3 思维链模式

Qwen3-32B 默认启用 thinking 模式，输出会包含 `<think>...</think>` 标签。如需关闭：
```json
{
    "messages": [
        {"role": "user", "content": "你好 /no_think"}
    ]
}
```

或通过 system prompt 控制：
```json
{
    "messages": [
        {"role": "system", "content": "请直接回答，不要输出思考过程。"},
        {"role": "user", "content": "你好"}
    ]
}
```

## 8. 启动过程解读

TACO-X 启动时会经历以下阶段：

```
阶段1: 解析模型定义文件 (llm.model)
阶段2: Linear TP rewrite (逐层优化，共 64 层)
  → "Process Linear tp rewrite on opt block: 0-63"
阶段3: 读取配置文件
  → 可能出现 warning: "Path .../layer_impl_config.json does not exist, allow missing, skip"
  → 可能出现 warning: "ModelType: qwen3 not supported, using DefaultWeightsProcessor"
  → 这两个 warning 不影响运行
阶段4: 加载模型权重到 GPU
阶段5: TileLang 编译优化 kernel
  → "TileLang begins/completes to compile kernel `main`"
阶段6: 引擎初始化完成
  → "TACO inference engine initialized."
阶段7: 启动 uvicorn HTTP 服务
  → "Uvicorn running on http://0.0.0.0:18080"
```

整个启动过程约 2-3 分钟。如果在阶段 3 之前崩溃，通常是配置文件缺少字段。

## 9. 常见错误与解决方案

### 9.1 配置字段缺失

```
[F] Path /workspace/qwen3_32b_taco_x_config/kv_cache_config.json does not exist.
Failed to initialize LLMEngine
```

**原因**：镜像中不包含该模型的配置目录。
**解决**：创建配置文件并 mount 到容器中。

### 9.2 scheduler_config 字段缺失

```
[json.exception.out_of_range.403] key 'max_num_images' not found
[json.exception.out_of_range.403] key 'enable_cuda_graph' not found
```

**原因**：scheduler_config.json 缺少必需字段。
**解决**：按照本文档第 4.1 节的完整字段列表补全。字段缺失时引擎只报告第一个缺失字段，需要反复修复重启直到所有字段补齐。

### 9.3 encoder token 约束错误

```
Configuration Error in scheduler_config.json!!!
"max_num_encoder_input_tokens"(=0) must be greater or equal than "max_num_batched_tokens"(=16384)!
```

**原因**：`max_num_encoder_input_tokens` 不能小于 `max_num_batched_tokens`。
**解决**：将 `max_num_encoder_input_tokens` 设置为 >= `max_num_batched_tokens` 的值。

### 9.4 Model mismatch

```
Model mismatch: expected /models/Qwen3-32B/snapshots/xxxx or one of the LoRA models: {}, received Qwen3-32B
```

**原因**：API 请求中的 `model` 字段不匹配。
**解决**：从请求 payload 中移除 `model` 字段，或设置为完整的 model_dir 路径。

### 9.5 healthcheck 使用 /v1/models 导致一直 unhealthy

```
GET /v1/models HTTP/1.1" 404 Not Found
```

**原因**：TACO-X 未实现 `/v1/models` 端点。
**解决**：healthcheck 改为发送一个最小化的推理请求（见第 6 节 docker-compose 配置）。

### 9.6 docker-compose 重命名服务后 ContainerConfig 错误

```
KeyError: 'ContainerConfig'
```

**原因**：旧版 docker-compose（1.x）在重命名服务后尝试迁移旧容器的 volume 数据时与 TACO-X 镜像的元数据格式不兼容。
**解决**：先手动停止并删除旧容器，再 `docker-compose down --remove-orphans && docker-compose up -d`。

### 9.7 FP8 量化时 Read-only file system 错误

```
safetensors_rust.SafetensorError: Error while serializing: IoError(Os { code: 30, kind: ReadOnlyFilesystem, message: "Read-only file system" })
```

**原因**：使用 `--quantization fp8` 时，引擎需要将量化后的权重缓存文件（`*_fp8.safetensors`）写入 model_dir，但模型 volume 以 `:ro` 只读方式挂载。
**解决**：将模型 volume 改为读写挂载（去掉 `:ro` 后缀）：
```yaml
# 错误（只读挂载，FP8 会报错）
- ~/.cache/huggingface/hub/models--Qwen--Qwen3-32B:/models/Qwen3-32B:ro
# 正确（读写挂载，FP8 可写入缓存）
- ~/.cache/huggingface/hub/models--Qwen--Qwen3-32B:/models/Qwen3-32B
```

## 10. 性能调优

### GPU 显存分配

`scheduler_config.json` 中的 `gpu_memory_utilization` 控制引擎占用显存比例（0-1）。推荐值：

| 场景 | 建议值 |
|------|--------|
| 独占 GPU | 0.90 - 0.95 |
| 与其他服务共享 GPU | 0.70 - 0.80 |

### 并发与吞吐

- `max_num_seqs`：增大可提高并发，但消耗更多显存
- `max_num_batched_tokens`：增大可提高吞吐，但增加延迟
- `max_model_len`：限制最大上下文长度，减小可节省显存

### FP8 量化

使用 `--quantization fp8` 可将模型权重从 BF16（16-bit）量化为 FP8（8-bit），减少显存占用并提高推理速度。

**实测性能对比**（Qwen3-32B, 2×L20, TP2, opt-level 3）：

| 指标 | BF16 | FP8 | 提升 |
|------|------|-----|------|
| 人才卡更新延迟 | ~3.4s | ~2.0s | 41% |

**注意事项：**
- 首次启动需在线量化，耗时约 5-8 分钟，会在 model_dir 中生成 `*_fp8.safetensors` 缓存文件
- 后续启动直接加载缓存，与 BF16 启动时间相当
- 模型 volume 必须以读写方式挂载（不能加 `:ro`），否则报 `Read-only file system` 错误
- 不影响输出质量，16 项集成测试全部通过

### opt-level

- `0`：无优化
- `2`：启用投机解码（lookahead cache）
- `3`：完整优化（推荐）

## 11. 调试技巧

### 查看引擎支持的所有配置项

```bash
docker run --rm --entrypoint bash <image> -c \
  'strings /usr/local/miniconda/lib/python3.12/site-packages/taco_x/taco_x_engine.so \
   | grep -E "^(enable_|max_|gpu_|block_|disk_|kv_)" | sort -u'
```

### 查看镜像内置了哪些模型配置

```bash
docker run --rm --entrypoint ls <image> /workspace/
```

### 查看 API Server 源码

```bash
docker run --rm --entrypoint cat <image> \
  /usr/local/miniconda/lib/python3.12/site-packages/taco_x/api_server.py
```

### 实时查看启动日志

```bash
docker logs -f teamgr-tacox
```

### 快速测试推理

```bash
curl -s http://localhost:18080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"hi"}],"max_tokens":10}' | python3 -m json.tool
```

## 12. 文件清单

最终部署所需的文件结构：

```
local_llm/
├── deploy.md                          # 本文档（最新部署指南）
├── qwen3_32b_taco_x_config/          # TACO-X 引擎配置（当前使用）
│   ├── scheduler_config.json          # 调度器配置（14 个必需字段）
│   ├── kv_cache_config.json           # KV Cache 配置
│   └── lookahead_cache_config.json    # 投机解码配置
└── <date>_<version>/                  # 历史归档目录
    ├── deploy.md
    ├── local_llm_service.md
    └── qwen3_32b_taco_x_config/

config/
└── config.yaml                        # 主配置文件（含 local_models 节）

docker/
└── docker-compose.yml                 # 含 tacox 服务定义

~/.cache/huggingface/hub/
└── models--Qwen--Qwen3-32B/          # 模型权重（HuggingFace 格式）
    └── snapshots/<commit_hash>/
        ├── config.json
        ├── tokenizer_config.json
        └── model-*.safetensors (×17)
```
