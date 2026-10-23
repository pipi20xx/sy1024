# SYTMDB 媒体库管理系统

为 [StrmAssistant.Releases](https://github.com/sjtuross/StrmAssistant.Releases) PRO 版本提供高级元数据管理增强功能，专注于 Emby 媒体库的本地元数据刮削源构建与管理。

## 项目简介

本项目是专为 **StrmAssistant PRO 用户** 设计的高级元数据管理系统，用于增强 [StrmAssistant 的"构建本地元数据刮削源"](https://github.com/sjtuross/StrmAssistant/wiki/%E6%9E%84%E5%BB%BA%E6%9C%AC%E5%9C%B0%E5%85%83%E6%95%B0%E6%8D%AE%E5%88%91%E5%89%8A%E6%BA%90) 功能。

通过本系统，用户可以：

- 构建属于自己的 TMDB 元数据刮削源（"本地 TMDB"）
- 在覆盖缓存中自定义不符合心意的、被恶意修改的或被锁定的在线元数据
- 支持剧集组刮削，入库即按照指定的剧集组刮削
- 自动刷入覆盖缓存中的图片，入库即有符合心意的海报、剧照等
- 重建媒体库时利用缓存极速刮削 TMDB
- 统一内容分级，自定义特别篇集的播出顺序
- 从网络搜索并下载 TMDB/Emby 图片（包括剧集季海报和集剧照）
- 标签管理：基于规则自动生成标签，或从 Bangumi 获取标签并写入 `tags.json`
- Bangumi 标签集成：将 Bangumi 的分类、类型等标签自动写入 Emby 媒体库
- 动态封面生成：为电影、剧集生成多种风格的媒体封面
- AI 辅助翻译：利用大语言模型翻译元数据简介、演员名等
- 工作流自动化：批量执行标签写入、封面生成等任务
- 外部 API 控制：通过 Token 认证的 REST API 实现自动化集成
- 界面外观自定义：壁纸、主题色、圆角、阴影等可视化定制，Liquid Glass 玻璃质感界面

**注意**：本项目仅支持 **Emby** 媒体服务器，且需要 StrmAssistant PRO 版本才能使用完整功能。

> ⚠️ **安全提示**：本项目主要由 AI 辅助开发，代码未经独立安全审计，**不建议映射到公网使用**，仅建议在**内网环境**中部署使用。若确需外网访问，请自行配置反向代理、防火墙等防护措施，修改默认密码并开启 2FA，风险自负。

## 核心功能

### 📺 本地元数据管理

- 直接操作 StrmAssistant 的覆盖缓存（Override Cache）和被动缓存（Primary Cache）
- 支持电影、电视节目、合集的元数据 JSON 文件编辑
- 支持自定义海报、徽标、壁纸、横幅图等多种图片类型
- 从网络搜索并下载 TMDB 图片（海报、剧照、徽标等），支持季海报和集剧照
- 从 Emby 拉取现有图片到覆盖缓存
- 内容分级统一：支持 US/JP 内容分级映射
- 剧集组管理：自定义剧集组（EPG），锁定特别篇播出顺序
- 特别篇插入：自定义特别篇的播出顺序
- 外部 ID 管理：为项目配置 IMDb、TVDB、Bangumi 等外部 ID
- 固定名称：为演员、作品设定固定中文名，避免刮削结果不一致
- 项目备份与恢复：支持单项目的元数据备份与恢复

### 🏷️ 标签与 Bangumi 集成

- **自动标签生成**：基于可配置的标签规则（国家、类型、年份等）批量生成标签，支持合并/覆盖模式
- **从 BGM 生成标签**：从已关联的 Bangumi 条目获取标签，可选使用全局白名单过滤，支持合并/覆盖模式
- **自定义标签预设**：支持用户定义自定义标签组合及其表情符号
- Bangumi 离线数据库集成与 ID 关联管理
- 往 Emby 写入 Bangumi 标签：将 Bangumi 的分类、类型等标签自动写入 Emby 媒体库
- 自动匹配 TMDB 与 Bangumi 之间的 ID 映射
- 支持季度结构计算和番外归类
- Bangumi 数据同步与增量更新
- Bangumi Provider 统一入口：L1 内存缓存 → DB 永久/临时缓存 → API，三层缓存策略

### 🎨 封面与预览生成

- **动态媒体封面生成**：支持为电影、剧集生成多种风格的封面
  - 内置样式：圆环聚焦、扇形、单图、3D 浮动、赛博故障、水墨风、流媒体英雄、撕裂纸等
  - 实时预览与高精度合成
- **合集海报生成**：支持多种布局的合集海报
- **视频预览截图**：从视频文件截取预览图
- 自动封面生成与封面配置管理

### 🤖 AI 实验室

- 基于 OpenAI 兼容 API 的大语言模型集成
- 简介翻译：将 TMDB 英文简介翻译为中文
- 演员名批量翻译
- 可配置的 AI 预设模板

### ⚙️ 自动化与集成

- **工作流引擎**：批量执行标签写入、封面生成、元数据同步等任务，支持定时调度
- **Webhook 自动化**：监听 Emby 事件并自动更新元数据
- **外部控制 API**：通过 Token 认证的 REST API 实现自动化集成，支持审计日志
- **神医配置**：Emby 用户级别的元数据策略管理
- **定时任务调度**：基于 APScheduler 的后台定时任务管理
- **文件监控**：自动监控覆盖缓存目录变化并刷新数据库
- **WebSocket 实时推送**：工作流执行日志实时推送到前端页面

## 技术架构

### 后端

| 技术 | 说明 |
|------|------|
| FastAPI | Python 3.11 异步 Web 框架 |
| SQLAlchemy | 异步 ORM，支持 PostgreSQL / SQLite |
| APScheduler | 定时任务调度 |
| Pillow | 图片处理与封面合成 |
| httpx | 异步 HTTP 客户端 |
| OpenAI | AI 翻译服务集成 |
| JWT + 2FA | 用户认证（TOTP 双因素） |
| watchdog | 文件系统监控 |

### 后端模块结构

```
app/
├── main.py                      # 应用入口
├── globals.py                   # 全局服务实例
├── middleware.py                # 外部控制中间件
├── logger.py                    # 审计日志系统
├── common.py                    # 通用工具函数
├── database.py                  # 数据库引擎与会话
├── query_parser.py              # 查询参数解析
├── emby_client.py               # Emby API 客户端
├── emby_metadata_updater.py     # Emby 元数据写入器
├── emby_collection_service.py   # Emby 合集服务
├── backup_service.py            # 备份与恢复
├── resource_service.py          # Webhook 资源处理
├── web_image_service.py         # 网络图片搜索（TMDB/Emby）
├── webhook_service.py           # Emby Webhook 自动化处理
├── websocket_manager.py         # WebSocket 实时日志推送
├── definitions/                 # 静态定义文件
│   ├── tmdb_mapping.json        # TMDB 字段映射
│   ├── ai_presets.json          # AI 预设模板
│   └── subject_*.yml            # Bangumi 关系定义
├── migrations/                  # 数据库迁移脚本
├── models/                      # ORM 模型（用户、会话）
├── schemas/                     # Pydantic 请求/响应模型
├── utils/                       # 认证、限流、时间等工具
├── routers/                     # API 路由
│   ├── items.py                 # 项目 CRUD 与详情
│   ├── tags.py                  # 标签管理
│   ├── emby.py                  # Emby 集成
│   ├── bangumi.py               # Bangumi 数据
│   ├── bangumi_sync.py          # Bangumi 同步
│   ├── bangumi_data_sync.py     # Bangumi 数据同步
│   ├── tmdb_bgm_mapping.py      # TMDB-BGM 映射
│   ├── tmdb_metadata.py         # TMDB 元数据更新
│   ├── tmdb_proxy.py            # TMDB 代理
│   ├── covers.py                # 封面生成
│   ├── collection_posters.py    # 合集海报
│   ├── previews.py              # 预览截图
│   ├── workflow.py              # 工作流
│   ├── tasks.py                 # 定时任务
│   ├── ai.py                    # AI 翻译
│   ├── actors.py                # 演员管理
│   ├── backups.py               # 备份管理
│   ├── auth.py                  # 认证
│   ├── external_control.py      # 外部控制
│   ├── shenyi.py                # 神医配置
│   ├── appearance.py            # 外观与壁纸
│   └── system.py                # 系统配置
├── services/                    # 业务服务层
│   ├── editor/                  # 编辑器 Mixin
│   │   ├── base.py              # 编辑器基类
│   │   ├── crud.py              # 元数据 CRUD
│   │   ├── details.py           # 详情获取
│   │   ├── external_updates.py  # 从外部源更新元数据
│   │   ├── ai_translate.py      # AI 翻译
│   │   ├── actors.py            # 演员管理
│   │   ├── delete.py            # 删除操作
│   │   ├── file_ops.py          # 文件操作
│   │   └── special_files.py     # 特别篇/剧集组
│   ├── auth.py                  # 认证服务
│   ├── actor.py                 # 演员服务
│   ├── bangumi.py               # Bangumi 服务
│   ├── bangumi_data_sync.py     # Bangumi 数据同步
│   ├── bangumi_provider.py      # Bangumi 统一入口（三层缓存）
│   ├── metadata_mapper.py       # BGM→TMDB 数据映射
│   ├── metadata_definition.py   # 元数据字段定义
│   ├── patches.py               # Patches 字段锁定处理
│   ├── relation.py              # TMDB↔BGM 关联管理
│   ├── images.py                # 图片保存与管理
│   ├── scanner.py               # 数据库扫描器
│   ├── cover_generator.py       # 封面生成器
│   ├── cover_config_manager.py  # 封面配置管理
│   ├── collection_poster_service.py # 合集海报服务
│   ├── preview_generator.py     # 预览截图生成
│   ├── llm_service.py           # 大语言模型服务
│   ├── configuration.py         # 配置管理
│   ├── scheduler_service.py     # 定时任务调度
│   ├── file_watcher.py          # 文件监控
│   ├── emby_integration.py      # Emby 集成
│   ├── emby_tag_writer.py       # Emby 标签写入
│   ├── shenyi_config.py         # 神医配置
│   ├── system.py                # 系统服务
│   ├── tmdb_cache.py            # TMDB 缓存
│   ├── tmdb_metadata.py         # TMDB 元数据更新服务
│   ├── tmdb_update_config.py    # TMDB 更新字段配置
│   ├── tmdb_bgm_mapping_service.py # TMDB-BGM 映射服务
│   └── styles/                  # 封面样式
│       ├── circle_focus.py      # 圆环聚焦
│       ├── fan.py               # 扇形
│       ├── single.py            # 单图
│       ├── style_3d_float.py    # 3D 浮动
│       ├── cyber_glitch.py      # 赛博故障
│       ├── ink_brush.py         # 水墨风
│       ├── streaming_hero.py    # 流媒体英雄
│       └── torn_paper.py        # 撕裂纸
└── tag_management/              # 标签管理
    ├── tag_service.py           # 标签服务（规则生成、CRUD）
    └── constants.py             # 国家/语言映射

```

### 前端

| 技术 | 说明 |
|------|------|
| Vue 3.5 + TypeScript 5.9 | Composition API + `<script setup>` |
| Vuetify 4.1 | Material Design 组件库，Liquid Glass 主题 |
| Vite 8 | 构建工具 |
| Pinia 4 | 状态管理 |
| Vue Router 5 | 路由管理 |
| @vueuse/core 14 | 组合式工具库 |
| Three.js | Liquid Glass 光学渲染（流光/涟漪效果） |
| PWA | 渐进式 Web 应用支持 |

### 前端页面结构

```
frontend/src/
├── layouts/                     # 页面布局（DefaultLayout）
├── glass/                       # Liquid Glass 渲染引擎（Three.js 光学效果）
├── plugins/                     # 插件注册
├── views/                       # 页面视图
│   ├── HomeView.vue             # 首页：浏览电影/电视剧
│   ├── ItemDetailView.vue       # 项目详情：元数据编辑
│   ├── CollectionsView.vue      # 合集列表
│   ├── CollectionDetailView.vue # 合集详情
│   ├── ActorsView.vue           # 演员库
│   ├── ActorDetailView.vue      # 演员详情
│   ├── TmdbBgmMappingView.vue   # TMDB-BGM 映射
│   ├── TmdbBgmMappingDetailView.vue # TMDB-BGM 映射详情
│   ├── TagRulesView.vue         # 标签规则
│   ├── TasksView.vue            # 定时任务
│   ├── BangumiView.vue          # Bangumi 同步
│   ├── CoverGeneratorView.vue   # 封面生成器
│   ├── PreviewGeneratorView.vue # 预览截图
│   ├── ShenYiConfigView.vue     # 神医配置
│   ├── ExternalControlView.vue  # 外部控制
│   ├── SettingsView.vue         # 系统设置
│   └── LoginView.vue            # 登录
├── components/
│   ├── details/                 # 项目详情子组件（头部、简介、演职员、图片、季集、标签、操作、弹框等）
│   ├── media/                   # 媒体展示组件（MediaCard、MediaGrid、FilterBar）
│   ├── home/                    # 首页组件（内容分级、生成 Override、指定刮削）
│   ├── collections/             # 合集组件（海报生成、Emby 导入/应用等）
│   ├── bangumi/                 # Bangumi 组件
│   └── common/                  # 通用组件（确认框、JSON 编辑器、路径浏览器、壁纸与主题定制等）
├── stores/                      # Pinia 状态管理
├── composables/                 # 组合式函数（认证、通知、WebSocket、主题等）
├── api/                         # API 客户端
├── router/                      # 路由配置
└── utils/                       # 前端工具函数

```

### 前端设计语言

采用 **Apple Liquid Glass** 流动玻璃设计语言：

- 深色渐变背景，多层玻璃面板（半透明 + 高斯模糊 + 饱和度增强）
- 彩虹折射边框（红橙黄绿青蓝紫光谱渐变）
- 紫色 `#a855f7` 为主强调色，青色 `#4ecdc4` 为霓虹描边色，品红 `#ff2d92` 为渐变填充色
- 全局超大圆角 + 流体过渡动画

### 部署

- Docker 多阶段构建（前端构建 → 运行时镜像）
- 支持 `linux/amd64` + `linux/arm64` 多架构
- 非 root 用户运行（`gosu` 权限降级）
- 运行时包含 FFmpeg（用于预览截图生成）

## 快速开始

### 使用 Docker 镜像部署

```yaml
services:
  tmdb-editor:
    image: pipi20xx/sy1024:latest
    container_name: emby-sytmdb
    network_mode: bridge
    ports:
      - "8121:8000"
    volumes:
      - ./data:/data                       # 数据库及配置文件存放路径
      - /vol1/1000/NVME:/vol1/1000/NVME    # 映射 StrmAssistant 的 cache/override 根目录
    environment:
      - PUID=1000                          # 运行用户的 UID
      - PGID=1000                          # 运行组的 GID
      - TZ=Asia/Shanghai
      - DATA_PATH=/data
    restart: always
```

保存为 `docker-compose.yml` 后运行：

```bash
docker compose up -d
```

服务将在 `http://localhost:8121` 启动。

### 从源码构建镜像

```bash
git clone <本项目仓库地址>
cd sy1024
docker build -t sy1024 .
```

构建完成后，参考上方 Docker 部署示例运行即可（将 `image` 换成 `sy1024`）。

构建过程包含两个阶段：前端使用 Node.js 22 构建静态资源，后端基于 Python 3.11 直接运行源码。国内网络环境可按需传入构建参数加速：

```bash
docker build \
  --build-arg NPM_REGISTRY=https://registry.npmmirror.com \
  --build-arg APT_MIRROR=mirrors.aliyun.com \
  --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
  -t sy1024 .
```

### 本地开发

**方式一：Docker 开发环境（仓库自带的 `docker-compose.yml`，前后端分离，双热重载）**

```bash
docker compose up -d
```

- 前端：`http://localhost:5273`（Vite Dev Server，改代码 HMR 即时生效）
- 后端：`http://localhost:8121`（uvicorn `--reload`，改代码自动重启，Swagger 可直接访问）
- 前后端源码均以 volume 挂载进容器，改代码无需重新构建镜像

**方式二：手动启动**

```bash
# 安装后端依赖
pip install -r app/requirements.txt

# 启动后端服务
uvicorn app.main:app --reload --port 8000

# 前端开发（另开终端）
cd frontend
npm install
npm run dev
```

前端开发服务器默认在 `http://localhost:5173` 启动，API 请求代理到 `http://localhost:8000`（Docker 开发环境中由 compose 注入 `VITE_PROXY_TARGET` 指向后端容器）。

> 提示：预览截图功能依赖 FFmpeg，本地开发时请确保系统已安装。

## 页面导航

| 页面 | 路径 | 功能 |
|------|------|------|
| 首页 | `/` | 浏览电影/电视剧，筛选、扫描、工作流操作 |
| 项目详情 | `/item/:itemType/:tmdbId` | 单个电影/剧集的详细元数据编辑 |
| 合集 | `/collections` | 管理自定义合集 |
| 演员库 | `/actors` | 演员信息与固定名称管理 |
| TMDB-BGM 映射 | `/tmdb-bgm-mapping` | TMDB 与 Bangumi 的 ID 关联管理 |
| 标签规则 | `/tag-rules` | 配置自动标签生成规则 |
| 定时任务 | `/tasks` | 管理后台定时调度任务 |
| Bangumi | `/bangumi` | Bangumi 数据同步与管理 |
| 封面生成器 | `/cover-generator` | 动态封面生成与配置 |
| 预览截图 | `/preview-generator` | 视频预览截图生成 |
| 神医配置 | `/shenyi` | Emby 用户级元数据策略管理 |
| 外部控制 | `/external-control` | API Token 管理与审计日志 |
| 设置 | `/settings` | 系统配置（Emby 连接、代理、AI 等） |

## 项目详情页功能

项目详情页（`/item/:itemType/:tmdbId`）是核心编辑界面，包含以下标签页和功能：

### 标签页

| 标签页 | 功能 |
|--------|------|
| 概览 | 编辑标题、简介、状态、评分、日期等基本信息 |
| 演职员 | 管理演员和幕后人员（翻译、增删、排序） |
| 图片 | 搜索网络图片、从 Emby 下载、管理本地图片 |
| 季与集 | 管理季元数据、集元数据、季/集图片、剧集组、特别篇 |
| 标签 | 自动生成标签、从 BGM 生成标签、手动管理标签 |
| 操作 | 从 TMDB/Bangumi/Emby 更新元数据、备份恢复、文件管理等 |

### 标签管理

- **自动生成标签**：根据标签规则（国家、类型、年份）自动生成，支持合并/覆盖模式选择
- **从 BGM 生成标签**：从已关联的 Bangumi 条目获取标签，可选使用白名单过滤，支持合并/覆盖模式
- **手动标签**：在操作页面的"从 Bangumi 更新"中选择 `tags` 字段，也可通过 API 直接添加
- 标签存储在 Override 目录的 `tags.json` 中，独立于主元数据文件

### Patches（字段锁定）

`patches/` 用于「只覆盖部分字段」，无需复制整份 JSON：

```
{override}/{tmdb-tv | tmdb-movies2}/{tmdb_id}/
├── series.json / all.json        # 可选：完整覆盖
├── season-1.json                 # 可选
├── season-1-episode-1.json       # 可选
└── patches/
    ├── series.json               # 只写要锁定的字段，例如 {"name": "..."}
    └── season-1.json
```

读取优先级（TMDB 模拟器）：

1. Override 主 JSON
2. 远程 TMDB（受「启用远程回退」控制，获取结果同样叠加 patches 与本地图片）
3. 只有 patches、没有主 JSON 时用 patch 兜底（不受远程回退开关影响）
4. 叠加 `patches/` 中同名 JSON：深合并、list 整体替换、优先级最高

> 注意：模拟器只读取 Override + patches，不读主缓存（primary cache）——
> 那是 StrmAssistant 的刮削缓存，不属于本服务的元数据。
> 关闭远程回退后，Override 主 JSON 与 patches 都没有的条目才返回 404；
> 图片不受此开关影响，始终按「本地覆盖图 → 磁盘缓存 → 远程拉取」三级查找。

本地图片（`images/poster.jpg` 等）在 patch 之后注入，因此「本地图片 > patch」。开启「剧集组模式」时，季/集的列表结构与虚拟编号由剧集组决定，patch 只能覆盖名称、简介、海报等字段。

「锁定名称」就是在 `patches/` 中写入 `name` / `title` 字段；之后在网页端修改名称会自动同步到 patch。

## 数据流与缓存机制

本系统与 StrmAssistant 的缓存机制完全兼容：

```
Emby → (Primary Cache) → (Override Cache) → Emby
```

### 缓存优先级

| 模式 | 覆盖缓存行为 | 覆盖缓存优先级 | 联网刮削优先级 | 被动缓存优先级 | 被动缓存行为 |
|------|------------|--------------|--------------|--------------|------------|
| 优先使用缓存 | 仅读取 | P1 | P3 | P2 | 读写 |
| 在线刮削并缓存 | 仅读取 | P1 | P2 | - | 仅写入 |
| 仅使用覆盖缓存 | 仅读取 | P1 | P2 | - | 不使用 |
| 关闭 | 不使用 | - | P1 | - | 不使用 |

### 使用场景

- **在线刮削并缓存**：一般情况下选择此模式
- **优先使用缓存**：重建媒体库时，尽可能避免在线请求
- **仅使用覆盖缓存**：使用别人分享的自定义元数据时
- **自定义元数据**：将对应的 tmdbid 目录从 cache 复制到 override 目录后开始自定义

支持单项目/合集的 Zip 导入导出，方便数据迁移与备份。

## 配置说明

### StrmAssistant 配置

确保在 StrmAssistant 中完成以下配置：

1. **元数据根目录**：指定元数据缓存目录（包含 cache 和 override 子目录）
2. **刮削器设置**：确保元数据和图片刮削器都选择了 TheMovieDb，且为第一优先级
3. **缓存模式**：根据使用场景选择合适的缓存模式（见上方缓存优先级表）
4. **可选图片类型设置**：在 `Strm Assistant_MetadataEnhanceOptions.json` 中设置 `MetadataCacheOptionalImageTypes` 避免不必要的图像 API 请求

### 本系统配置

主要配置文件位于 `data/` 目录：

- `tmdb_browser_config.json` — 系统主配置（Emby 连接、代理设置、AI 配置等）
- `bgm_manager.json` — Bangumi 服务配置（自动同步、筛选规则、允许标签白名单等）
- `tmdb_update_config.json` — TMDB 元数据更新字段配置
- `cover_generator_config.json` — 封面生成器配置
- `tag_rules.json` — 自动标签生成规则
- `custom_tags.json` — 自定义标签预设

### 数据库配置

本项目使用 SQLAlchemy ORM，支持 PostgreSQL 和 SQLite。

**SQLite 配置**（默认，适合小型部署）：

默认使用 SQLite 数据库，无需额外配置，数据文件存储在 `data/` 目录下。

**PostgreSQL 配置**（推荐，适合大型部署）：

```yaml
# docker-compose.yml 中添加 PostgreSQL 服务
services:
  postgres:
    image: postgres:15-alpine
    container_name: emby-sytmdb-postgres
    environment:
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=your_password
      - POSTGRES_DB=sytmdb
      - TZ=Asia/Shanghai
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: always
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
```

然后在环境变量中配置数据库连接：

```yaml
environment:
  - DB_TYPE=postgresql
  - POSTGRES_HOST=postgres
  - POSTGRES_PORT=5432
  - POSTGRES_USER=postgres
  - POSTGRES_PASSWORD=your_password
  - POSTGRES_DB=sytmdb
```

### 认证配置

系统内置用户认证，首次启动默认管理员账号：

- 用户名：`admin`
- 密码：`admin123`

> ⚠️ 请在首次登录后立即修改密码。系统支持 TOTP 双因素认证（2FA），可在设置页面开启。

## 如何避免 TMDB 请求

为了减少对 TMDB API 的依赖，可以采取以下措施：

1. **文件夹命名规范**：确保文件夹带上 tmdbid，避免入库时的 search 请求
2. **完整元数据**：在 override 中提供所有所需的 JSON 元数据
3. **可选图片类型设置**：在 `Strm Assistant_MetadataEnhanceOptions.json` 中设置 `MetadataCacheOptionalImageTypes: "Logo,Backdrop"`，只要提供了主海报 poster，就不会产生图像 API 请求
4. **使用缓存模式**：选择"优先使用缓存"模式，充分利用 cache 中的 JSON 数据

## 系统要求

- **StrmAssistant PRO 版本**：必须使用 PRO 版本才能使用本地元数据刮削源功能
- **Emby 媒体服务器**：本项目仅支持 Emby，不支持 Jellyfin
- **Docker**：推荐使用 Docker 部署（可选）
- **Python 3.11+**：本地开发环境需要
- **Node.js 22+**：前端开发环境需要

## 相关链接

- [StrmAssistant.Releases](https://github.com/sjtuross/StrmAssistant.Releases)
- [构建本地元数据刮削源 - StrmAssistant Wiki](https://github.com/sjtuross/StrmAssistant/wiki/%E6%9E%84%E5%BB%BA%E6%9C%AC%E5%9C%B0%E5%85%83%E6%95%B0%E6%8D%AE%E5%88%91%E5%89%8A%E6%BA%90)

## 许可证

本项目为 StrmAssistant.Releases 的配套服务，遵循相关开源协议。
