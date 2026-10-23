#!/bin/bash

# 获取 PUID 和 PGID，默认为 1000
PUID=${PUID:-1000}
PGID=${PGID:-1000}

echo "Starting with UID: $PUID, GID: $PGID"

# 检查 appuser 是否存在 (Dockerfile 中已创建)
# 修改 appuser 的 UID 和 GID 以匹配宿主机
# suppress stdout/stderr for clean logs unless error, check return code manually if needed
groupmod -o -g "$PGID" appuser 2>/dev/null || echo "groupmod warning"
usermod -o -u "$PUID" appuser 2>/dev/null || echo "usermod warning"

# 确保数据目录存在
if [ ! -d "/data" ]; then
    mkdir -p /data
fi

# 修复 /data 目录权限
# 使用 || true 忽略错误，防止容器因挂载点不支持 chown (如 NFS/SMB/某些 NAS) 而启动失败
echo "Fixing permissions for /data..."
chown -R appuser:appuser /data || echo "WARNING: Failed to chown /data. This is common on network shares or restricted binds. Proceeding anyway..."

# 切换到 appuser 用户执行命令
exec gosu appuser "$@"
