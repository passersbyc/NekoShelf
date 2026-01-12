# NekoShelf 使用指南

NekoShelf 是一个萌萌的本地化漫画小说自动管理系统，支持从 Pixiv/Kemono 下载、自动归档、元数据管理和数据库维护。

## 🚀 快速开始

### 启动
```bash
python3 main.py
```

### 基础命令
- `help`: 查看所有命令
- `help <command>`: 查看具体命令帮助 (e.g. `help download`)
- `exit`: 退出系统

## 📚 常用功能

### 1. 下载书籍 (Download)
支持从 URL 下载文件，或从 Pixiv/Kemono 批量爬取。

**基本用法**:
```bash
download <URL> [选项]
```

**支持站点**:
- **Pixiv**: 输入用户主页链接 (e.g. `https://www.pixiv.net/users/12345`)
  - 自动爬取小说、漫画、插画
  - 漫画自动打包为 CBZ
  - 支持断点续传
- **Kemono**: 输入用户主页链接 (e.g. `https://kemono.su/service/user/id`)
  - 自动爬取帖子附件
  - `--image`: 仅下载内嵌图片并打包
  - `--txt`: 仅下载正文内容
  - 文件名包含签名信息，支持自动元数据解析

**常用选项**:
- `--dir=PATH`: 指定临时下载目录
- `--series=NAME`: 指定系列名称 (单文件)
- `--dup-mode=skip/overwrite/rename/ask`: 重复文件处理策略

### 2. 导入书籍 (Import)
将本地文件导入书库。

**用法**:
```bash
import <PATH> [--move/--copy] [--series=NAME]
```

- 支持文件或文件夹递归导入
- 自动识别文件名中的元数据 (Author - Title)
- 支持多种格式: txt, epub, pdf, cbz, zip, rar, mobi, azw3

### 3. 搜索书籍 (Search)
强大的搜索功能。

**用法**:
```bash
search <KEYWORD> [Filters]
```
- `search 东方`: 搜索标题或作者包含"东方"的书籍
- `search author:ZUN`: 搜索作者为 ZUN 的书籍
- `search series:Project`: 搜索系列包含 Project 的书籍
- `search tag:汉化`: 搜索包含"汉化"标签的书籍

### 4. 数据库维护 (Clean)
**重要**: 保持数据库与实际文件一致。

**检查模式 (默认)**:
```bash
clean [--dir=PATH]
```
- 扫描文件系统与数据库的差异
- **不修改任何数据**
- 报告缺失的文件和多余的记录

**修复模式**:
```bash
clean --fix [--yes]
```
- **自动备份数据库**
- 删除数据库中指向不存在文件的记录
- 补录未在数据库中的文件
- 修正元数据不一致的记录
- 使用事务保证安全

**选项**:
- `--dry-run`: 模拟执行
- `--type=EXT`: 仅处理特定类型文件
- `--since/--until`: 仅处理特定时间范围

## 🔧 高级功能

### 导出 (Export)
```bash
export <SELECTOR> --out=DIR [--zip]
```
- 将搜索结果导出到指定目录
- 支持打包为 ZIP

### 更新信息 (Update)
```bash
update <SELECTOR> author=NewName series=NewSeries
```
- 批量修改书籍信息
- 支持 `tags+=NewTag` 追加标签

## ❓ 常见问题

**Q: 下载中断了怎么办？**
A: 直接重新运行下载命令。NekoShelf 支持断点续传，会自动跳过已下载部分。

**Q: 移动了文件怎么办？**
A: 运行 `clean --fix`，系统会自动更新数据库中的文件路径（基于文件哈希匹配）。

**Q: 如何配置 Cookie？**
A: 编辑 `core/config.py` 文件，填入对应站点的 Cookie。
