# bjjl-imagegen-mcp

一个零依赖的 MCP (Model Context Protocol) 服务器，为桌面 Agent（如 Codex）提供**图像生成能力**，后端走自建的 OpenAI 兼容网关。

## 为什么需要它

部分桌面 Agent 的「内置图像生成工具」绑定在产品级授权（app connection）上，当 Agent 被指向第三方 OpenAI 兼容端点（自建网关 / API key 模式）时，这个内置工具**不可用**，会提示"连接需要重新授权"或"当前会话没有可调用的 imagegen 工具"。

本项目把该能力**重新实现为标准 MCP 工具**，因此：

- 任何支持 MCP 的客户端都能用（Codex、Claude Desktop 等）
- 走已付费的订阅额度，**不需要官方 API key**
- 所有人配置方式一致，只填各自的网关 key
- 不依赖客户端内部授权机制

## 安装（一键）

```bash
curl -fsSL https://raw.githubusercontent.com/tang92-tech/bjjl-imagegen-mcp/main/install.sh | bash
```

脚本会：下载服务器到 `~/.codex/mcp/bjjl-imagegen-mcp/`、提示输入网关 API Key、写入 `~/.codex/config.toml`（自动备份原配置）、并做启动自检。

## 安装（手动）

1. 把 `imagegen_mcp.py` 放到固定位置，例如 `~/.codex/mcp/bjjl-imagegen-mcp/`
2. 在 `~/.codex/config.toml` 追加：

```toml
[mcp_servers.imagegen]
command = "python3"
args = ["/Users/<用户名>/.codex/mcp/bjjl-imagegen-mcp/imagegen_mcp.py"]
enabled = true
startup_timeout_sec = 20
tool_timeout_sec = 300

[mcp_servers.imagegen.env]
BJJL_IMAGE_API_KEY = "你的网关 API Key"
BJJL_IMAGE_MODEL = "gpt-6-luna"
```

3. 重启客户端让 MCP 服务器加载。

## 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `BJJL_IMAGE_API_KEY` | ✅ | — | 网关 API Key |
| `BJJL_IMAGE_GATEWAY` | | `https://aigateway.evenbetter.tech:8443` | 网关地址 |
| `BJJL_IMAGE_MODEL` | | `gpt-6-luna` | 驱动图像生成的模型 |
| `BJJL_IMAGE_OUT_DIR` | | `~/.codex/generated_images` | 图片输出目录 |

## 使用

直接对 Agent 说：

```text
生成一张小橘猫坐在窗台上的图片
画一个蓝色渐变背景的应用图标
把这段描述做成海报插图
```

Agent 调用 `generate_image`，返回图片**绝对路径**。

## 工具定义

**`generate_image`**

| 参数 | 必填 | 说明 |
|---|---|---|
| `prompt` | ✅ | 图片描述（建议含主体、风格、构图、氛围） |
| `filename` | | 可选文件名（仅取 basename，防目录穿越） |

返回：图片绝对路径、文件大小、尺寸，以及上游优化后的提示词。

## 运维提示

- 生成**较慢**（约 30–60 秒），属正常；客户端工具超时建议设 300 秒。
- 上游会**自动优化提示词**，结果可能比原始描述更精细。
- 生成会**消耗订阅额度**；额度用尽时返回上游 429，等额度周期恢复即可。
- 本服务器**只做图像生成**，不处理文本对话。

## 依赖

Python 3.8+（macOS / 主流 Linux 自带），**仅标准库**，无需 pip 安装。

## 安全

- 不存储、不打印任何密钥；密钥只从环境变量读取。
- 输出文件限制在 `BJJL_IMAGE_OUT_DIR` 内，`filename` 参数做了路径穿越防护。
- 诊断日志走 stderr，不污染 stdio 协议。

## License

MIT · 半斤九两科技（苏州）有限公司 · https://tang92.com
