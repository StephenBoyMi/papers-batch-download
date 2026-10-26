# 文献批量下载 v2.1

Windows 桌面工具，把题录清单批量下载成 PDF。IEEE Xplore 与知网 CNKI 两个来源，界面上一个单选钮切换。

- **IEEE**：清单自动识别 5 种题录格式；有 URL 直接下，只有 DOI 时自动解析 arnumber；校验响应是真 `%PDF`，拦截页删除重下。
- **知网**：Playwright 驱动系统 Edge，按题名检索后从详情页取 PDF；检索偶发失败会自动重试。
- **下载监控内嵌在主窗口**：成功 / 失败 / 已存在统计、进度条、队列逐条状态、实时日志。
- **失败可一键重试**：只重跑失败的那几条，不碰已完成的。
- 两个来源共用同一套「保存文件夹」与「年份前缀」设置。

## 运行

Python 3.9+，仅 Windows。

```
pip install -r requirements.txt
pythonw main_ui.py
```

用 `python main_ui.py` 启动可以看到控制台输出。

也可以双击 `重建快捷方式.py`，在开始菜单生成「文献批量下载」。

## 用法

1. 选「下载来源」。
2. 填「论文保存文件夹」和「URL文件路径」（清单文件）。
3. 需要时勾「论文保存时自动添加年份前缀」，前缀取当前系统年份。
4. 点「开始下载」。面板实时显示统计、进度、队列状态和日志；有失败项时「重试失败」按钮可用。

两个路径输入框只能显示一段，鼠标停在框上会浮出完整路径。

## 清单格式

**IEEE**：按内容自动识别下列任一格式，每条至少要有标题。

| 格式 | 识别依据 |
| --- | --- |
| IEEE Citation | 引号标题行 + `URL:` 行（见 `url.txt` 样例） |
| BibTeX | 含 `@article` |
| RIS | 行首 `TY  - ` |
| EndNote | 行首 `%` + 大写字母 |
| NE 题录 | 行首 `题录类型：` |

**知网**：纯文本，每行 `题名<TAB>作者<TAB>年份`，只取题名检索。

## 前提与凭证

- **IEEE**：需要有下载权限的机构网络。程序强制直连（不走代理），每篇之间等待 3 秒。
- **知网**：需 `pip install playwright` 且系统已装 Microsoft Edge。凭证放在本目录的 `cnki_cookie.txt`（浏览器登录 www.cnki.net 后从 F12 的 Network 复制 Cookie）。失败提示分 `未检索到该题名`（清单里的标题要改）和 `检索页加载失败`（网络或页面问题，可直接重试）两种。失败清单落盘到本目录的 `知网失败清单_<时间>.txt`。

`cnki_cookie.txt` 已在 `.gitignore` 中，不会入库。

## 文件

| 文件 | 职责 |
| --- | --- |
| `main_ui.py` | 界面、下载流程调度 |
| `download_paper_by_URLfile.py` | 题录清单解析（5 种格式） |
| `utils.py` | IEEE 下载循环、DOI→arnumber 解析、进度共享变量 |
| `cnki_core.py` | 知网检索与 PDF 落盘 |
| `url.txt` | IEEE Citation 格式样例 |
| `重建快捷方式.py` | 在开始菜单生成快捷方式 |
| `img/` | 界面图与程序图标 |

## 图标

`img/app-icon-rounded.ico` 的目录项按尺寸从大到小排列，索引 0 是 256×256。快捷方式的 `IconLocation` 与 Tk 的 `iconbitmap` 都按索引 0 取图，顺序不要调整。

## 致谢

本项目的起点参考了 Yong Cao 的 [IEEE_downloader](https://github.com/yongcaoplus/IEEE_downloader)，`utils.py` 与 `download_paper_by_URLfile.py` 保留其原始署名。

界面中的 IEEE、CNKI 标识与米奇图标版权归各自所有者，本项目与 IEEE、中国知网无关联，非官方工具。
