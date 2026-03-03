以下是本地部署LLM的方法

## 镜像
```bash
docker pull taco-0.tencentcloudcr.com/taco/taco_x_prod:v0.0.1-260302-default
```
容器启动命令示例

```bash
docker run -itd --gpus all --privileged --cap-add=IPC_LOCK --ulimit memlock=-1 --ulimit stack=67108864 --net=host --ipc=host --entrypoint /bin/bash --name=${container_name} taco-0.tencentcloudcr.com/taco/taco_x_prod:v0.0.1-260302-default
```
需替换${container_name}为希望的容器名称。容器中已安装TACO-X，可直接在容器内使用

## 部署方法
新框架taco-x在原模型的基础上有一些额外的配置文件。目前，这些配置文件位于容器的/workspace目录下。模型所对应的配置文件目录分别为

模型	配置文件目录
InternVL2.5-2B	/workspace/internvl2.5_2b_taco_x_config
Qwen2.5-VL-7B	/workspace/qwen2.5_vl_7b_taco_x_config
Qwen3-32B	/workspace/qwen3_32b_taco_x_config
Qwen3-VL-8B	/workspace/qwen3_vl_8b_taco_x_config
Qwen3-32B	/workspace/qwen3_32b_taco_x_config
使用模型对应的配置文件目录，替换下文所提及的${config_dir}。

### 服务启动命令
```bash
python3 -m taco_x.api_server --model_dir ${model_dir} --model_type 
${model_type} --config_dir ${config_dir} --port 18080 --opt-level  3
```
注意，需要开启--opt-level 3以体验最佳的吞吐性能。需替换${model_dir}与${config_dir}为实际值。其中，${model_dir}为模型权重目录，${config_dir}为上文所提及的模型配置文件所在目录，而${model_type}的取值随模型而定，可参考以下表格

模型	model_type取值
InternVL2.5-2B	intern2_5_vl_2b
Qwen2.5-VL-7B	qwen2_5_vl_7b
Qwen3-32B	qwen3_32b
Qwen3-VL-8B	qwen3_vl_8b

服务启动后，按照openai-compatible的api格式发送请求即可体验效果。

### Tensor Parallel使用方法
在启动命令中，添加--tp ${tp_size}参数即可。其中，${tp_size}需要替换为期望的并行数。完整命令如下。
```bash
python3 -m taco_x.api_server --model_dir ${model_dir} --model_type 
${model_type} --config_dir ${config_dir} --port 18080 --tp ${tp_size} --opt-level 3
```