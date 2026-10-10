#!/usr/bin/env bash
# bjjl-imagegen-mcp 一键安装脚本
set -euo pipefail

RAW_BASE="${BJJL_IMAGE_MCP_RAW:-https://raw.githubusercontent.com/tang92-tech/bjjl-imagegen-mcp/main}"
INSTALL_DIR="$HOME/.codex/mcp/bjjl-imagegen-mcp"
CONFIG="$HOME/.codex/config.toml"
SERVER_FILE="$INSTALL_DIR/imagegen_mcp.py"

echo "=============================================="
echo " bjjl-imagegen-mcp 安装程序"
echo "=============================================="
echo ""

command -v python3 >/dev/null 2>&1 || { echo "❌ 需要 python3，请先安装。"; exit 1; }
echo "✅ python3: $(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')"

mkdir -p "$INSTALL_DIR"

if command -v curl >/dev/null 2>&1; then
  echo "→ 下载 imagegen_mcp.py ..."
  curl -fsSL "$RAW_BASE/imagegen_mcp.py" -o "$SERVER_FILE"
else
  echo "❌ 需要 curl 才能下载。请手动把 imagegen_mcp.py 放到 $INSTALL_DIR/"
  exit 1
fi
chmod +x "$SERVER_FILE"
python3 -c "import ast;ast.parse(open('$SERVER_FILE').read())" || { echo "❌ 下载文件语法校验失败"; exit 1; }
echo "✅ 已安装到: $SERVER_FILE"

echo ""
echo "请输入你的网关 API Key（输入不会回显）："
read -rsp "API Key: " API_KEY
echo ""
[ -n "$API_KEY" ] || { echo "❌ API Key 不能为空"; exit 1; }

MODEL="${BJJL_IMAGE_MODEL:-gpt-6-luna}"
GATEWAY="${BJJL_IMAGE_GATEWAY:-https://aigateway.evenbetter.tech:8443}"

SKIP_WRITE=0
if [ -f "$CONFIG" ]; then
  BAK="$CONFIG.bak-imagegen-$(date +%Y%m%d-%H%M%S)"
  cp "$CONFIG" "$BAK"
  echo "✅ 已备份原配置: $BAK"
  if grep -q "^\[mcp_servers\.imagegen\]" "$CONFIG"; then
    echo "⚠️  已存在 [mcp_servers.imagegen]，跳过写入以免重复。"
    echo "    如需更新密钥，请手动编辑: $CONFIG"
    SKIP_WRITE=1
  fi
else
  mkdir -p "$(dirname "$CONFIG")"
  : > "$CONFIG"
  echo "✅ 已创建新配置: $CONFIG"
fi

if [ "$SKIP_WRITE" != "1" ]; then
  cat >> "$CONFIG" <<EOF

[mcp_servers.imagegen]
command = "python3"
args = ["$SERVER_FILE"]
enabled = true
startup_timeout_sec = 20
tool_timeout_sec = 300

[mcp_servers.imagegen.env]
BJJL_IMAGE_API_KEY = "$API_KEY"
BJJL_IMAGE_MODEL = "$MODEL"
BJJL_IMAGE_GATEWAY = "$GATEWAY"
EOF
  echo "✅ 已写入 MCP 配置"
fi

echo ""
echo "→ 运行自检..."
RESULT=$(printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | \
  BJJL_IMAGE_API_KEY="$API_KEY" python3 "$SERVER_FILE" 2>/dev/null | head -1 || true)
if echo "$RESULT" | grep -q '"serverInfo"'; then
  echo "✅ 自检通过：MCP 服务器可正常启动"
else
  echo "⚠️  自检未通过，请把下面内容反馈给管理员："
  echo "$RESULT"
fi

echo ""
echo "=============================================="
echo " 安装完成！"
echo "=============================================="
echo "下一步：重启 Codex（或新建会话），然后说"
echo "  「生成一张小橘猫坐在窗台上的图片」"
echo "图片默认输出到: ~/.codex/generated_images/"
echo ""
echo "回滚：cp <上面的备份路径> $CONFIG"
