# douban-showcase
## 项目描述
豆瓣个人标记数据展示。

## 框架
- Python
- Flask
- Alpine.js
- TailwindCSS

## 特点
- 支持多种类型条目：movie、book、game、music、drama
- 筛选排序
- 统计功能
- 封面图下载
- 定期增量更新

## 注意事项

1. 首次运行前确保配置了正确的环境变量，特别是 `DOUBAN_USER_ID`
2. 数据库和封面目录会自动创建
3. 对于大量数据同步，建议使用增量同步 (`--sync-incremental`)，减少API负载
4. 图片同步可能需要较长时间，可单独运行也可在应用启动时指定 `--sync-images`

克隆项目后使用以下命令安装依赖：

```bash
pip install flask requests python-dotenv retrying
```

## 环境变量参考
参考下面的环境变量配置：
```env
# 豆瓣API设置
DOUBAN_USER_ID=123456789
DOUBAN_API_HOST=frodo.douban.com
DOUBAN_API_KEY=0ac44ae016490db2204ce0a042db2916
AUTH_TOKEN= 

SERVER_DOMAIN=http://localhost:5000

# 同步支持的类型: movie, book, music, game, drama
DOUBAN_SYNC_TYPES=movie,book  

# API服务设置
API_PORT=5000
API_HOST=0.0.0.0

# 时区设置
TIMEZONE=Asia/Shanghai

# 数据库设置
SQLITE_DB_PATH=data/douban.db

# 图片设置
DOWNLOAD_COVERS=false
LOCAL_COVER_PATH=data/covers
# 图片展示策略: original(原始链接), local(本地缓存), mixed(混合模式)
COVER_DISPLAY_STRATEGY=mixed
# 图片代理设置 当图片展示策略为 original 或者 mixed时生效
COVER_PROXY=false

# 同步设置
ENABLE_AUTO_SYNC=true
SYNC_INTERVAL_HOURS=24

# 日志设置
LOG_FILE=data/douban-sync.log
LOG_LEVEL=INFO
```

## 环境变量配置

配置选项可通过环境变量设置或在 .env 文件中定义：

| 环境变量 | 描述 | 默认值 |
|---------|------|---------|
| `DOUBAN_USER_ID` | 豆瓣用户ID | - |
| `SQLITE_DB_PATH` | SQLite数据库路径 | douban.db |
| `LOCAL_COVER_PATH` | 本地封面图片存储路径 | covers |
| `DOWNLOAD_COVERS` | 是否下载封面图片 | `false` |
| `LOG_LEVEL` | 日志级别 | `INFO` |
| `LOG_FILE` | 日志文件路径 | douban-sync.log |
| `DOUBAN_SYNC_TYPES` | 需要同步的内容类型，逗号分隔 | `movie,book` |
| `SERVER_DOMAIN` | 服务域名 | - |
| `COVER_DISPLAY_STRATEGY` | 封面显示策略 (local/original/mixed) | `mixed` |

## API 文档

### 主要 API 端点

| 端点                      | 方法 | 描述                        | 参数                                |
|--------------------------|-----|----------------------------|-------------------------------------|
| `/api/interests`         | GET | 获取兴趣列表                  | `type`, `status`, `year`, `sort_by`, `sort_order`, `limit`, `offset` |
| `/api/interests/:id`     | GET | 获取单个条目详情              | `id` (路径参数)                      |
| `/api/statistics`        | GET | 获取所有统计数据概览            | `skip_cache` (可选)                 |
| `/api/statistics/:type`  | GET | 获取特定内容类型的统计数据       | `type` (路径参数)                    |
| `/api/statistics/ratings`| GET | 获取评分统计                 | `type` (可选)                       |
| `/api/statistics/years`  | GET | 获取年份统计                 | `type` (可选)                       |
| `/api/statistics/genres` | GET | 获取标签/分类统计              | `type` (可选), `limit`              |
| `/api/statistics/trends` | GET | 获取收藏趋势数据              | `period`, `months`, `type` (可选)    |
| `/api/statistics/complete`| GET | 获取完整统计数据              | `skip_cache` (可选)                 |
| `/api/sync`              | POST | 触发数据同步                 | `incremental` (布尔值, 默认 true)     |
| `/api/sync/images`       | POST | 触发图片同步                 | `max_items` (可选)                  |
| `/api/sync/images/status`| GET | 获取图片同步状态              | 无                                 |
| `/api/status`            | GET | 获取同步状态信息              | 无                                 |
| `/api/service/status`    | GET | 获取所有服务组件的状态信息      | 无                                 |

### 参数说明

- `type`: 内容类型 (例如: movie, tv, book, music, game, drama)
- `status`: 观看/阅读状态 (wish, doing, done)
- `year`: 年份筛选
- `sort_by`: 排序字段 (create_time, year, douban_score, my_rating, title)
- `sort_order`: 排序方向 (asc, desc)
- `limit`: 返回条目数量限制
- `offset`: 分页偏移量
- `skip_cache`: 是否跳过缓存，强制重新计算统计数据
- `period`: 趋势数据周期 (day, week, month, year)
- `months`: 趋势数据月数
- `incremental`: 是否使用增量同步
- `max_items`: 图片同步的最大条目数

## 运行命令

### 1. 启动应用服务器

```bash
# 基本启动
python -m src.app

# 或者使用简写形式
python run.py

# 指定端口和主机
python -m src.app --port 8000 --host localhost

# 启动时执行全量同步
python -m src.app --sync

# 启动时执行增量同步
python -m src.app --sync-incremental

# 启动时同步封面图片
python -m src.app --sync-images

# 清除统计数据缓存
python -m src.app --clear-cache

# 组合使用
python -m src.app --port 8000 --sync-incremental --sync-images
```

### 2. 数据导出工具

```bash
# 导出特定类型和状态的数据
python -m scripts.export_json --type movie --status done

# 导出特定年份的数据
python -m scripts.export_json --type movie --year 2023

# 导出所有类型和状态的数据（多个文件）
python -m scripts.export_json --all

# 导出并包含原始JSON数据
python -m scripts.export_json --type book --status done --raw

# 指定输出目录或文件
python -m scripts.export_json --type movie --output ./exports/my_movies.json

# 指定最大条目数
python -m scripts.export_json --type movie --limit 100

# 紧凑输出格式
python -m scripts.export_json --type movie --compact

# 指定数据库路径
python -m scripts.export_json --type book --db ./custom/path/douban.db
```

## 免责声明
此项目（包括但不限于代码、文档、资源文件等）仅限用于个人学习、研究目的，如发现存在无意侵权的内容，请联系作者删除。



