# Seek：企业信息检索 RAG 助手

Seek 是一个桌面软件：给出企业名称和官网、新闻稿等公开资料，它会整理出这家企业的**业务线、产品类别和目标市场**，每条结论都标注来源，方便核实。

- 使用你自己的 API：大模型支持 Claude、DeepSeek、通义千问、OpenAI 以及任何兼容 OpenAI 接口的服务；向量化默认使用硅基流动的 bge-m3（免费，中文效果好）
- 界面参照 AI 助手类桌面软件：左侧是研究过的企业，右侧是阅读排版的画像，底部是输入框
- 支持 Windows 和 macOS，资料和密钥都只保存在本机

技术栈：Python、FastAPI、ChromaDB、pywebview、PyInstaller

## 下载安装

在 GitHub 仓库的 **Actions → Build desktop apps** 中打开最近一次成功的运行，在页面底部的 Artifacts 下载：

| 系统 | 文件 | 安装方式 |
|---|---|---|
| Windows 10/11 | `Seek-Windows-x64.zip` | 解压后双击 `Seek\Seek.exe` |
| macOS 11+（Apple 芯片） | `Seek-macOS-arm64.zip` | 解压后把 `Seek.app` 拖进「应用程序」 |

发布正式版本时（推送 `v*` 标签，如 `git tag v0.2.0 && git push origin v0.2.0`），安装包会自动出现在 **Releases** 页面。

**首次打开的提示**

- **Windows**：如果出现「Windows 已保护你的电脑」，点「更多信息 → 仍要运行」。软件依赖系统自带的 WebView2（Windows 11 和更新过的 Windows 10 都已内置）；如果窗口打开后是空白的，请安装 [WebView2 运行时](https://developer.microsoft.com/microsoft-edge/webview2/)。
- **macOS**：安装包没有经过苹果签名，第一次打开需要在 Finder 中**右键 → 打开**。如果提示「已损坏」，在终端执行 `xattr -cr /Applications/Seek.app` 后再打开。

## 使用方法

### 1. 设置 API

第一次打开会自动弹出「设置」（之后可以点左下角的 **设置** 修改）：

**大模型**（用于生成画像），任选一家：

| 服务商 | 获取密钥 | 说明 |
|---|---|---|
| Claude | console.anthropic.com | 默认 `claude-opus-5-5`，使用结构化输出，结果最稳定 |
| DeepSeek | platform.deepseek.com | `deepseek-chat` |
| 通义千问 | 阿里云百炼控制台 | `qwen-plus` / `qwen-max` |
| OpenAI | platform.openai.com | 模型名可自行填写 |
| 自定义 | — | 任何兼容 OpenAI 接口的服务，填写接口地址和模型名 |

**向量化**（用于检索资料）：

| 服务商 | 说明 |
|---|---|
| 硅基流动 bge-m3 | **推荐**。免费，中英文效果都好，在 cloud.siliconflow.cn 注册获取密钥 |
| 通义千问 / OpenAI / 自定义 | 兼容 OpenAI `/embeddings` 接口即可 |
| 本地小模型 | 不需要密钥、可离线，但以英文为主，中文效果一般；首次使用下载约 80MB |

填好后点 **测试连接**，两项都显示「连接成功」再点 **保存**。

### 2. 开始研究

在首页输入框中：

1. 第一行填**企业名称**
2. 下面粘贴**官网或新闻网址**，每行一个
3. 可选：点 **＋ 文本资料** 粘贴新闻稿、年报等抓取不到的内容
4. **深入抓取** 打开时，会顺着站内链接继续抓取「关于我们 / 产品 / 新闻」等页面（最多 10 页）
5. 点发送按钮（或按 Ctrl/⌘ + Enter）

Seek 会依次抓取网页、切分入库、检索资料、调用大模型，几十秒后在右侧显示画像。

### 3. 阅读和核实画像

- 画像分为**概况、业务线、产品类别、目标市场**四部分
- 每句话后面的蓝色数字是**引用**，点击会跳到文末的来源，展开「引用原文」可以看到依据的原文片段；来源链接会在浏览器中打开
- 资料里找不到依据的内容会被自动剔除，不会写进画像（文末会注明剔除了几处）
- 下方可以**复制**，或**导出 Markdown / JSON**

### 4. 补充资料、检索资料

打开一家企业后，底部输入框有两种模式：

- **补充资料**：再粘贴网址或文本，入库后自动重新生成画像
- **检索资料**：输入关键词（如「海外市场」），查看已入库资料中最相关的原文片段

右上角的 ↻ 可以直接重新生成画像。左侧列表悬停时出现删除按钮，会删除这家企业的全部资料和画像。

### 常见问题

| 问题 | 处理 |
|---|---|
| 提示「API Key 无效」或「请先在设置中填写」 | 点提示里的「打开设置」检查密钥、模型名和接口地址 |
| 很多网址抓取失败 | 有些网站会屏蔽程序访问，或者页面内容由脚本动态加载。把页面文字复制下来，用「＋ 文本资料」添加 |
| 换了向量化服务后企业列表变空 | 不同向量模型的数据互不兼容，需要重新入库；切换回原来的模型，旧资料仍然可用 |
| 画像某个部分是空的 | 已入库的资料没有覆盖这部分内容，补充相关页面或新闻稿后重新生成 |

### 数据保存在哪里

| 系统 | 位置 |
|---|---|
| Windows | `%APPDATA%\Seek` |
| macOS | `~/Library/Application Support/Seek` |

其中 `settings.json` 保存设置和 API Key（仅当前用户可读），`chroma/` 是向量库，`profiles/` 是生成过的画像，`seek.log` 是运行日志。删除这个文件夹即可清空所有数据。

## 开发

```bash
pip install -r requirements.txt
python desktop.py            # 打开桌面窗口
python desktop.py --server   # 只启动本地服务，在浏览器中打开显示的地址
pytest -q                    # 运行测试（完全离线）
```

本地打包（只能打当前系统的包）：

```bash
pip install pyinstaller
pyinstaller --noconfirm packaging/seek.spec
# Windows: dist/Seek/Seek.exe    macOS: dist/Seek.app
dist/Seek/Seek --self-test     # 冒烟测试
```

`.github/workflows/build.yml` 会在推送到 master 时运行测试，并在 Windows 和 macOS 上打包和自检；推送 `v*` 标签时发布 Release。

### 架构

```
desktop.py        桌面入口：后台线程启动 FastAPI，pywebview 打开窗口
app/static/       界面（原生 HTML/CSS/JS，不依赖外部资源，可离线使用）
app/main.py       接口：/api/settings /api/ingest /api/search /api/profile /api/companies
app/state.py      按用户设置构建向量库和大模型客户端，设置变更后自动切换
app/user_settings.py  服务商预设、设置的保存与脱敏
app/fetcher.py    抓取网页、抽取正文、同域爬取
app/chunking.py   按段落 / 句子切分，带重叠窗口
app/embeddings.py 向量化：兼容 OpenAI 的 API、本地 MiniLM、测试用哈希向量
app/vectorstore.py ChromaDB 封装，按企业隔离；每种向量模型一个集合
app/profiler.py   分维度检索 → 编号来源 → 大模型结构化输出 → 校验引用
app/llm.py        Claude（官方 SDK + JSON Schema 结构化输出）与兼容 OpenAI 的服务（JSON 模式 + 失败重试）
app/history.py    保存每家企业最近一次的画像
```
