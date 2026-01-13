# NekoShelf

萌萌的本地化漫画小说自动管理系统 (Local Manga/Novel Manager)

## ✨ 特性
- **多源下载**: 支持 Pixiv (小说/漫画), Kemono (附件/图片), 通用文件下载
- **自动归档**: 自动识别元数据 (Author, Title, Series) 并按结构整理
- **断点续传**: 大文件下载更稳定
- **数据库管理**: 基于 SQLite 的高性能元数据管理
- **完整性保护**: `clean --fix` 命令确保数据库与文件系统一致
- **CLI 交互**: 友好的命令行界面，支持自动补全和彩色输出

## 🚀 快速开始
请查看 [使用指南](docs/usage.md) 获取详细说明。

```bash
# 一键部署 + 启动 (Windows/macOS/Linux)
python3 bootstrap.py

# 只安装不启动
python3 bootstrap.py --install-only

# 在 CLI 中输入 help 查看帮助
(萌萌) > help
```

### 环境变量配置

```bash
# Pixiv
export NEKOSHELF_PIXIV_COOKIE="..."

# Kemono
export NEKOSHELF_KEMONO_COOKIE="..."
```

## 🛠 开发
- 核心代码位于 `core/`
- 插件系统位于 `core/plugins/`
