# 发布记录（release record）

智策 Windows 客户端的实测记录。每次改动产物时追加一节，不覆盖历史。

## 1.0.2b6+z09 · 2026-10-11（主题：镜像下载的向量模型其实加载不了）

修复的来龙去脉与"同一个 exe、同一批文件"的对照实验写在上面 z08 一节的最后，
根因分析在 `CHANGELOG.md` 的 z09 一节。本节只记发版后的产物验收。

| 项 | 结果 |
|---|---|
| 存量缓存修复 | `normalize_mirror_layout(~/.octop/embedding_models)` 返回 2（两个旧布局都改好），改完**不用重新下载** |
| 装机版加载校验（修复数据后、z08 的 exe） | `{'ok': true, 'latency_ms': 219, 'dim': 512}` |
| 新增验收断言 | 默认列表里每个标着"已下载"的模型都必须 `ok=true`，否则装机验收直接失败 |

### 装机验收（发版后，一条命令）

```
PENDING_Z09_ACCEPTANCE
```

### 空闲预下载两趟对照（z09 产物上重跑）

```
PENDING_Z09_PREFETCH
```

## 1.0.2b6+z08 · 2026-10-11（主题：新手第一分钟；方案见 `docs/PLAN-z08.md`）

```
resolved zcagent-desktop-windows-amd64-1.0.2b6+z08.exe: 192,197,498 bytes,
  sha256 ac66083ef7c54973…44056b
download verified: 192,197,498 bytes, hash matches the release digest
reusing the existing install at C:\Program Files\zcagent
stopped the client that was answering on 8088: pid 15348
server answering on 8088
unpacked runtime: 1.0.2b6+z08 -> 1.0.2b6+z08
  1.0.2b6+z03 carries 'function resolveInitialLocale{…': /assets/index.CTp--4pI.js
  1.0.2b6+z06 carries 'local-recovery':                  /assets/index.CTp--4pI.js
  1.0.2b6+z08 carries 'prefetch_enabled':                /assets/index.BeMijJdR.js
  1.0.2b6+z08 carries '智策科技公司制度知识库':            /assets/zh.BiN4yfW1.js
  default list: 3 models -> [BAAI/bge-small-zh-v1.5, jinaai/jina-embeddings-v2-base-zh,
                             sentence-transformers/paraphrase-multilingual-mpnet-base-v2]
  expanded list: 13 models        all_notated: True
  stored_locale: None
  login_is_chinese: True
  login_has_english_signin: False
  account_hint: 这台机器上已有智策数据，登录账号是 admin。
  recovery_form: True
  modal_shows_cli_command: False
  knowledge bases are off here -- create dialog not opened
  version_badge_under_logo: 1
  installed icon: .zc-verify/reports/icon-1.0.2b6+z08.png sha256 62a05850012c9506…
ALL ASSERTIONS HELD -- report at .zc-verify/reports/1.0.2b6+z08.json
```

本轮 `runtime_before` 与 `runtime_after` 都是 `+z08`：替换发生在前面那次**失败**的尝试里（见下文
"三个工具自身缺陷"）。"新版客户端会替换旧运行时"这条本身的证据在 z05 一节（`+z02 → +z05`）。

### 接口层实测（对着装好的客户端问接口，不是看代码）

`GET /api/knowledge-bases/embedding-options` 的默认列表就是**3 条，全是中文可用**，
每条带一句话优缺点；`?all_onnx=true` 展开是 **13 条而不是 41 条**，其中没有 CLIP 塔，
`intfloat/multilingual-e5-large` 已从推荐位降级到展开项。断言写在
`scripts/verify/client_release.py::stage_embedding_api`：默认 ≤4、展开 ≤20、无 clip、条条有注释。

### 登录后那两面

装机版是**真的能走通登录**的：用户名/密码 + 滑块验证码（`slide-captcha` 拖满，完成信号是轨道的
`aria-valuenow=100`）→ 进入 `/chat`，侧边栏 logo 下方出现短版本号 `v1.0.2b6+z08`（z07 的需求）。

新建知识库弹窗这一段**在这台机器上没有断言**，原因是它现在处于「未启用知识库」状态——页面上只有引导卡，
没有「创建知识库」按钮。为了跑断言而 `PUT /feature` 会把用户的设置改掉，所以工具如实记录"没打开弹窗"，
把默认值改到真正装载它的地方证明：服务出来的 `zh` 语言分片里确实带着「智策科技公司制度知识库」
（见上面的 bundle 输出），表单默认值本身由 `dashboard` 的组件测试覆盖。
首启行事历"老用户不该出现"同理：该不该出现取决于这台机器走到第几步，判据是纯函数，留在单元测试里。

### 空闲预下载：两趟对照

`scripts/verify/prefetch_watch.py`。**不碰共享的 `~/.octop`**：那台机器上默认模型早就下载好了，
此时正确行为是"什么都不做"，而"功能坏了"看起来一模一样——所以工具用装好的运行时刻配一个
临时 `OCTOP_HOME` 与备用端口启动，空缓存里落下的任何字节都只能是这一次运行干的。

| 趟 | 观察 | 结果 |
|---|---|---|
| 开关打开（默认） | 首批字节出现在启动后 **130.1 秒**（>90 秒空闲闸）；ONNX 权重 **94,781,076 字节**、单调增长；`knowledge_onnx_prefetch_attempts=1` | 下载确实由空闲预下载触发 |
| `OCTOP_KNOWLEDGE_MODEL_PREFETCH=0` | 观察 135 秒：0 字节、0 行状态；控制面库确实建起来了（`booted=true`） | 开关真的关得掉 |

同一次运行还多问了一句"这个模型现在能用吗"（`POST /knowledge-bases/onnx-test`），
答案是 `{'ok': false, 'error': 'Could not load model …'}` —— 于是查出下一节那个更严重的缺陷：
**`done` 之所以没写，是因为下载完的加载校验起不来**，不是预下载没跑。

写这个工具时抓到一个会**假绿**的结构：全新目录没有控制面库时，`start()` 会把控制面推迟到
首启向导选完后端，而预下载任务是在 `_boot_runtime` 里创建的——第一次跑"开关关掉"那一趟
确实什么都没下载，但那是"服务还没走到那一步"，不是开关生效。工具因此显式给
`OCTOP_DATABASE_SQLITE_PATH`，并把"控制面库是否建起来"当成所有断言的前置。
副产品是一条真实产品事实：**全新安装的 90 秒计时从走完向导那一刻开始**，不是进程启动，
已写进 `prefetch.py` 的模块说明。

### 这一轮装机验收连续拦下的三个工具自身缺陷

产物都是对的，失败全在验收工具里——但每一条如果留着，下一次真坏掉时它就看不见：

| 现象 | 真相 |
|---|---|
| `PermissionError: C:\Program Files\zcagent\zcagent.exe` | 上一版客户端还在运行，句柄没放；安装阶段必须先按 PID 停掉自己的客户端。而原来"先删掉 exe 再装"的判断方式本身也是错的：NSIS 在 `/S` 下遇到占用不弹窗，只是原地留着旧构建 |
| "installer never produced a fresh zcagent.exe" | 装好了。注册表 `DisplayVersion` 已是 `1.0.2b6+z08`，可 NSIS 把**打包时存的时间戳**原样盖在释放出来的文件上，按"mtime 晚于本次安装"判断必然失败。判断依据改成读安装器自己写的注册表版本 |
| "served chunk 缺 prefetch_enabled" | 标记确实在产物里，只是不在入口 chunk：Vite 把路由级改动切进按需加载的 `index.BeMijJdR.js`，而入口是 `index.CTp--4pI.js`。断言改成顺着入口里的动态 import 字面量爬分片图（实测 13 个 chunk、0.2 秒），并报告每条标记落在哪个文件 |
| 登录段点不到「登录」按钮 | AntD 把两个汉字排成「登 录」，而且滑块验证码没过时按钮是 disabled。改成用 `slide-captcha` 的 `data-testid` 拖满，完成信号读轨道的 `aria-valuenow=100`（验证通过后滑块元素**不会**消失，别按"消失了"判） |
| 找不到「创建知识库」按钮 | 这台机器的知识库开关本来是关的，页面上只有「未启用知识库」引导卡。为了跑断言去 `PUT /feature` 会把用户设置改掉，所以改成如实记录"没打开弹窗"；表单默认值改由服务出来的 `zh` 语言分片证明 |

### 但这一轮也查出产物自己的一处真缺陷

上面四条是工具的错，下面这条是**产品的**：装好的 z08 客户端对已下载的
`BAAI/bge-small-zh-v1.5` 调 `POST /api/knowledge-bases/onnx-test` 回
`{'ok': false, 'error': 'Could not load model BAAI/bge-small-zh-v1.5 from any source'}`，
而磁盘上 `model_optimized.onnx` 有 94,781,076 字节、文件齐全。

对照实验（**同一个 exe、同一批文件**，只改缓存目录的写法）：

| 缓存写法 | 接口回答 |
|---|---|
| `snapshots/cos-mirror` + `refs/main = "cos-mirror\n"` | `ok=false`，"Could not load model …" |
| `snapshots/<40 位哈希>` + `refs/main` = 那个哈希、**不带换行** | `{'ok': true, 'latency_ms': 219, 'dim': 512}` |

根因与修法见 `CHANGELOG.md` 的 z09 一节：`huggingface_hub` 只认 40 位提交哈希那种寻址，
且 1.33 读 `refs/main` 时不会 strip 换行——两条都错了，所以"镜像下载成功"之后加载仍然
要连 huggingface.co。连得上的机器等于下载两遍，连不上的机器知识库永远起不来。
z09 修下载写法，并加 `normalize_mirror_layout()` 在加载前就地修好存量缓存。

### 门禁（z09 这一轮）

- `ruff check` / `ruff format`：改动文件全绿（上游 `bridge.py`、`update.py` 按既定原则不动）。
- `scripts/rebrand.py --check`：**3274 文件扫过，无旧品牌残留**。
- `pytest tests/unit/agents tests/unit/knowledge`：**811 passed / 3 skipped**，其中
  `tests/unit/agents/test_onnx_cache_layout.py` 8 条是这次新增的。
- 前端本轮没有改动，z08 发版时的门禁数字（`tsc -b` 通过、后端 533 passed、
  受影响文件 vitest 44 passed、全量 vitest 与干净树对照无回归）仍然成立。

### 一条必须说的安全事实

`CHANGELOG.md` 的 z04 一节曾写有验收用的管理员口令明文，公开仓库的历史不可撤销，
现在那一行只描述账号、不写口令。装机后请用 z06 的本地重置流程换成用户自己的口令；
后续任何文档与提交都不再写出口令明文（验收工具改成从 `ZC_VERIFY_PASSWORD` 读）。

## 1.0.2b6+z07 · 2026-10-11（首次用 `scripts/verify/client_release.py` 一条命令跑完）

```
resolved zcagent-desktop-windows-amd64-1.0.2b6+z07.exe: 192,187,491 bytes, sha256 b1b5effeda882464...
download verified: 192,187,491 bytes, hash matches the release digest
reusing the existing install at C:\Program Files\zcagent
unpacked runtime: 1.0.2b6+z05 -> 1.0.2b6+z07
  bundle carries the 1.0.2b6+z03 change: True
  bundle carries the 1.0.2b6+z06 change: True
  stored_locale: None
  login_is_chinese: True
  login_has_english_signin: False
  account_hint: 这台机器上已有智策数据，登录账号是 admin。
  recovery_form: True
  modal_shows_cli_command: False
  installed icon: .zc-verify/reports/icon-1.0.2b6+z07.png sha256 62a05850012c9506...
ALL ASSERTIONS HELD
```

要点：**升级链在真机上恢复了**——这台机器停在 `+z05` 的解压运行时，装上 z07 后被替换成 `+z07`。
图标从**装好的 exe** 里抠出来确认是边牧（z02 那台是上游红章鱼）。登录页点名账号、
「忘记密码」是表单且不含 `octop user passwd`。

### 过程中被工具拦住的一次假验收

第一次跑链条时，负责"释放 8088"的 PowerShell 里 `$_` 被 bash 展开掉了，开发实例没被杀，
`8088` 仍在应答。工具的启动前置检查直接拒绝：

> `8088 already answers -- an older client or the dev server is running, and every check below
> would read its bundle instead of the new one`

没有这条断言，那一轮会**全绿**——因为读的是旧服务的 chunk。这正是当初 z03 修复"在产物里却看不见"
的同型问题，工具把它变成了硬失败。

### 仍未自动验证的一项（已于 z07 人工确认）

WebView2 里右键菜单**实际弹出来的样子**没有自动化验证（原生窗口截图在这台机器拿不到有效画面）。
`context_menu.go` 的内容、"不许出现 save/print/另存/打印"、以及两个窗口都关掉内建菜单，
都由 Go 测试锁住。装机后人工右键看过：**只剩「上一页 / 重新加载系统」两项**，与断言一致。
这条靠眼睛而不是自动化，所以以后动右键菜单仍需人工看一眼。

## 1.0.2b6+z05 · 2026-10-11（装机全流程，含"新客户端能否替换旧运行时"的验收）

这一节验的是 z04 那个比较器修复：**保留一台机器上第一次解压出来的旧运行时，再装新版，看它会不会换掉。**

| 项 | 结果 |
|---|---|
| 下载完整性 | `zcagent-desktop-windows-amd64-1.0.2b6+z05.exe` = **192,372,790 字节**，本机重算 SHA256 = `d0a36437f25259e8…`，与 Release API 的 `digest` 一致（`gh release download` 曾在本项目对残缺文件返回 0，所以用 curl 续传 + 字节数核对） |
| 起始状态 | `~\.octop\portable\VERSION.txt` = `octop_version=1.0.2b6+z02`（就是复现 bug 的那个状态）；`8088` 服务的是 z02 的 `index.XAfRwQg_.js` |
| 静默安装 | NSIS **忽略**了正斜杠形式的 `/D=D:/otp/...`，装到默认位置 `C:\Program Files\zcagent`（注册表 `DisplayVersion=1.0.2b6+z05`）。要装到别处必须用反斜杠 |
| 替换旧运行时 | 启动 `C:\Program Files\zcagent\zcagent.exe` 后 `VERSION.txt` 变成 **`octop_version=1.0.2b6+z05`** —— z02 之后一直卡住的升级链恢复 |
| 产物内容 | `8088` 的入口 chunk 变为 `index.Scx49Zw2.js`，其中 `resolveInitialLocale(){return readStoredUiLocale()??"zh"}` 确认在包内 |
| 界面语言 | 用强制 `navigator.language=en-US`、localStorage 为空的浏览器上下文渲染（模拟 WebView2 在中文 Windows 上的表现）：登录页中文、无 "Sign in"、"忘记密码"弹窗中文 |
| 图标 | 从 exe 里抠出内嵌图标：z05/z03 = 边牧犬（钢蓝）；对照 z02 的 `C:\Program Files\zcagent` 旧产物 = 上游红色 Octop 图标 |

### 一个必须写进交付话术的事实

判断"要不要替换运行时"的比较器在 **exe 里**，不在解压出来的运行时里。所以**装了 z02/z03 的机器不会
被自己的更新检查修好**，必须重新下载并运行一次新安装程序。

### 顺带修掉的第二个英文来源

`desktop/src/settings.go` 的 `defaultSettings()` 把外壳语言钉在 `LocaleEN`，于是托盘菜单与
"First launch: unpacking the bundled runtime…"在仪表盘已经中文的情况下仍然英文。
z05 起默认中文，用户在设置窗里选的语言（`desktop-settings.json`）优先。
曾考虑按系统显示语言取默认值，实测本机 `GetUserDefaultUILanguage` 返回 `en-US`（中文 Windows
装了英文显示语言），照它走反而会造成"网页中文、外壳英文"的分裂，所以放弃。

## 1.0.2b6+z02 · 2026-10-10

| 项 | 结果 |
|---|---|
| 下载完整性 | `zcagent-desktop-windows-amd64-1.0.2b6+z02.exe` 本机重算 SHA256 = `434c71d9…80332f`，与 GitHub Release 的 `digest` 一致 |
| 内嵌元数据 | `ProductName=zcagent`、`CompanyName=zcagent`、`FileVersion=ProductVersion=1.0.2b6+z02`、`FileDescription=zcagent Installer`（PowerShell `VersionInfo` 读回） |
| 静默安装 | `installer.exe /S /D=D:\otp\deliver\installed` → 得到 `zcagent.exe` + `uninstall.exe`，共 199 MB，不需要管理员权限 |
| 启动 | WebView2 环境创建成功；应用把绿色包解到 `%USERPROFILE%\.octop\portable\`，再以 `portable\runtime\python.exe portable\launch.py run --host 127.0.0.1 --port 8088` 起服务；`GET /` 200，`GET /api/branding` 正常应答 |
| 卸载 | `uninstall.exe /S` 后安装目录清空、控制面板无残留条目 |
| **残留** | `~\.octop\portable\` **712 MB 不会被卸载删掉**（它在数据目录里，卸载器按设计不动数据目录）。交付话术里要说清楚，或给实施人员一条清理命令 |

### 开发版才有的一个坑（不是产物问题）

源码 editable 安装时，「应用更新」页显示的 `current_version` 取自 **已安装的发行版元数据**
（`importlib.metadata`），不是 `src/octop/__init__.py`。所以改完版本号没重新 `uv pip install -e .`
之前，页面会一直显示旧版本（实测显示 `1.0.2b6+z1` 而源码已是 `+z02`）。装好的 wheel / 便携包没有
这个问题——实测安装版显示的就是 `1.0.2b6+z02`。

## 1.0.2b6+z01 · 便携包（已被 z02 取代，记录保留）

解压 658 MB → `start.bat --port 8090` → 内嵌 CPython 3.12.12 起服务 → 首启向导全流程走通
（口令 → SQLite → 建管理员 → 模型可跳过）→ 登录进 `/chat`；主色 `#3d5a80`、标题「智策 …」、
可见文案无 "Octop"。当时读回的下载地址是 `https://octop.cloud/`，且包内 `README.txt` 仍写着
"Octop green portable package" —— 两处都在 z02 修掉。
