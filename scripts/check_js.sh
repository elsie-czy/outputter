#!/bin/bash
# scripts/check_js.sh
# 检查所有 JS 文件语法，node 已安装在本机

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
JS_DIR="$SCRIPT_DIR/static/js"
ERRORS=0

for f in "$JS_DIR"/*.js; do
  if ! node -c "$f" 2>/dev/null; then
    echo "❌ $f 语法错误"
    ((ERRORS++))
  fi
done

if [ $ERRORS -gt 0 ]; then
  echo ""
  echo "共 $ERRORS 个 JS 文件有语法错误，请修复后重试"
  exit 1
fi
echo "✅ 所有 JS 文件语法检查通过"
exit 0
