# SYTMDB/Dockerfile (生产镜像)

# 基础镜像前缀：默认官方 Docker Hub；走内网 registry 代理时用 --build-arg 覆盖：
#   --build-arg BASE_PREFIX=registry.example.com:5000/library/
ARG BASE_PREFIX=""

# --- 阶段 1: 前端构建 (Frontend Builder) ---
FROM ${BASE_PREFIX}node:22-slim AS frontend-builder

WORKDIR /frontend_src

# npm 源：默认官方源；国内线路慢时用 --build-arg NPM_REGISTRY=https://registry.npmmirror.com 切换
ARG NPM_REGISTRY=""
RUN if [ -n "${NPM_REGISTRY}" ]; then npm config set registry ${NPM_REGISTRY}; fi

# 复制依赖描述文件
COPY frontend/package.json ./

# 安装依赖
# 注意：不使用 npm ci 且不复制 package-lock.json，因为 npm ci 不会安装 lockfile 中
# 未锁定的平台特定可选依赖（如 @rolldown/binding-linux-arm64-gnu），导致多架构构建失败。
# 不带 lockfile 执行 npm install 可让 npm 根据当前平台自动解析 optionalDependencies。
# 参考：https://github.com/npm/cli/issues/4828
RUN npm install

# 复制前端源码并执行构建
COPY frontend/ .
RUN npm run build


# --- 阶段 2: 运行时镜像 (Runtime) ---
FROM ${BASE_PREFIX}python:3.11-slim

WORKDIR /app

# APT 源：默认官方源（走 CDN，通常比镜像站快）；国内线路慢时再切镜像站：
#   --build-arg APT_MIRROR=mirrors.aliyun.com   （或 mirrors.tuna.tsinghua.edu.cn 等）
ARG APT_MIRROR=""
RUN if [ -n "${APT_MIRROR}" ]; then \
        sed -i -e "s/deb.debian.org/${APT_MIRROR}/g" \
               -e "s/security.debian.org/${APT_MIRROR}/g" \
               /etc/apt/sources.list /etc/apt/sources.list.d/debian.sources 2>/dev/null || true; \
    fi

# 安装运行时依赖 (FFmpeg, gosu)
RUN apt-get update && \
    apt-get install -y ffmpeg gosu && \
    rm -rf /var/lib/apt/lists/*

# 创建非 root 用户 (稍后在 entrypoint 中切换)
RUN useradd --create-home appuser

# 先复制依赖列表，利用层缓存
COPY app/requirements.txt .

# Python 依赖：默认官方 PyPI；走内网/镜像源时用 --build-arg PIP_INDEX_URL 覆盖
ARG PIP_INDEX_URL=""
RUN if [ -n "${PIP_INDEX_URL}" ]; then \
        pip install --no-cache-dir -r requirements.txt -i ${PIP_INDEX_URL}; \
    else \
        pip install --no-cache-dir -r requirements.txt; \
    fi

# 复制后端源码
COPY --chown=appuser:appuser app ./app

# 用前端构建产物替换静态目录（fonts / style_previews 随后单独补回）
RUN rm -rf ./app/static/*
COPY --from=frontend-builder /frontend_src/dist ./app/static

# 复制字体文件 (确保 app/static/fonts 存在)
COPY --chown=appuser:appuser app/static/fonts ./app/static/fonts

# 复制样式预览图 (确保 app/static/style_previews 存在)
COPY --chown=appuser:appuser app/static/style_previews ./app/static/style_previews

# 复制 Entrypoint 脚本
COPY --chown=appuser:appuser app/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# 清理构建冗余文件
RUN rm -f ./requirements.txt ./app/requirements.txt

# 暴露端口
EXPOSE 8000

# 设置 Entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
