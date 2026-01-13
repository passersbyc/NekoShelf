# NekoShelf

萌萌的本地化漫画小说自动管理系统 (Local Manga/Novel Manager)

## ✨ 特性
- **多源下载**: 支持 Pixiv (小说/漫画), Kemono (附件/图片), 通用文件下载
- **智能搬运**: 
  - **Kemono 优化**: 200+ 并发连接池，多线程并行下载，极速更新
  - **自动去重**: 基于下载记录的智能去重，避免重复下载已有的文件
  - **静默模式**: 批量操作时自动隐藏冗余日志，保持界面清爽
- **自动归档**: 自动识别元数据 (Author, Title, Series) 并按结构整理
- **断点续传**: 大文件下载更稳定
- **数据库管理**: 基于 SQLite 的高性能元数据管理
- **完整性保护**: `clean --fix` 命令确保数据库与文件系统一致
- **CLI 交互**: 友好的命令行界面，支持自动补全和彩色输出

## 🚀 快速开始
```bash
# 一键部署 + 启动 (Windows/macOS/Linux)
python3 bootstrap.py

# 只安装不启动
python3 bootstrap.py --install-only

# 在 CLI 中输入 help 查看帮助
(萌萌) > help
```

## 🛠️ 常用命令

| 命令 | 说明 | 示例 |
| --- | --- | --- |
| `download` | 下载单本书籍或作者全部作品 | `download https://kemono.su/...` |
| `pull` | 检查并下载已关注作者的新作品 (多线程并行) | `pull` |
| `subscribe` | 关注作者 (自动添加到 pull 列表) | `subscribe https://pixiv.net/...` |
| `import` | 导入本地文件到书库 | `import /path/to/files` |
| `list` | 列出书库中的书籍 | `list --limit 20` |
| `clean` | 清理失效的数据库记录 | `clean --fix` |
| `serve` | 启动 Web 阅读服务 | `serve --port 8000` |

## ⚙️ 配置

配置文件： [core/config.py](core/config.py)

### 书库与数据库路径

在 `core/config.py` 中修改：
- `LIBRARY_PATH`：书库存放目录（默认 `library`）
- `DB_PATH`：数据库文件路径（默认 `library.db`）

也支持用环境变量覆盖：

```bash
export NEKOSHELF_LIBRARY_PATH="/path/to/library"
export NEKOSHELF_DB_PATH="/path/to/library.db"
```

Windows 示例：

PowerShell（当前窗口生效）：

```powershell
$env:NEKOSHELF_LIBRARY_PATH = "C:\\path\\to\\library"
$env:NEKOSHELF_DB_PATH = "C:\\path\\to\\library.db"
```

CMD（当前窗口生效）：

```bat
set NEKOSHELF_LIBRARY_PATH=C:\path\to\library
set NEKOSHELF_DB_PATH=C:\path\to\library.db
```

### Cookie（安全存储）
 
推荐通过环境变量配置：

- `NEKOSHELF_PIXIV_COOKIE`
- `NEKOSHELF_KEMONO_COOKIE`

Cookie 值可以是明文，也可以是加密字符串（`enc:` 前缀）。若使用加密串，解密密钥通过环境变量提供：
 
```bash 
export NEKOSHELF_SECRET_KEY="your-secret-key" 
python3 -c "from core.config import encrypt_secret; print(encrypt_secret('YOUR_COOKIE'))" 
``` 
 
把输出结果作为环境变量写入即可：

```bash
export NEKOSHELF_PIXIV_COOKIE="enc:..."
export NEKOSHELF_KEMONO_COOKIE="enc:..."
```

Windows 示例：

PowerShell（当前窗口生效）：

```powershell
$env:NEKOSHELF_SECRET_KEY = "your-secret-key"
$env:NEKOSHELF_PIXIV_COOKIE = "enc:..."
$env:NEKOSHELF_KEMONO_COOKIE = "enc:..."

python -c "from core.config import encrypt_secret; print(encrypt_secret('YOUR_COOKIE'))"
```

CMD（当前窗口生效）：

```bat
set NEKOSHELF_SECRET_KEY=your-secret-key
set NEKOSHELF_PIXIV_COOKIE=enc:...
set NEKOSHELF_KEMONO_COOKIE=enc:...

python -c "from core.config import encrypt_secret; print(encrypt_secret('YOUR_COOKIE'))"
```

Windows 永久写入（写入用户环境变量，需重开终端生效）：

```bat
setx NEKOSHELF_SECRET_KEY "your-secret-key"
setx NEKOSHELF_PIXIV_COOKIE "enc:..."
setx NEKOSHELF_KEMONO_COOKIE "enc:..."
```

## 🛠 开发
- 核心代码位于 `core/`
- 插件系统位于 `core/plugins/`
