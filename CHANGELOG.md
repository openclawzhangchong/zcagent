# 更新日志

本文件记录 **智策 / zcagent 相对上游的改动**。上游自己的历史在 [`CHANGELOG.upstream.md`](./CHANGELOG.upstream.md)。

## 版本号规则

`<上游基线版本>+z<两位序号>`，例如 `1.0.2b6+z01`。**序号必须零填充。**

- `+` 前是所基于的上游版本，追版时只改这一段；
- `z<NN>` 是我们的补丁序号，每次发布 +1，**写成 `z01`…`z99` 而不是 `z1`…`z99`**：PEP 440 对 local 版本段按**字符串**比较，所以 `+z10` 会排在 `+z9` **下面**——不填充的话第 10 次发布在 pip 眼里是降级（已实测：`Version("1.0.2+z10") < Version("1.0.2+z9")`）。
- 用 PEP 440 local version，因此这类包**不能**上传 PyPI（我们不发布公共包，内网索引正合适）。
- 更新检查的比较器 `self_update.parse_version` 已按 PEP 440 处理 local 段，与 pip 的判序**一致**——故意不做"更聪明"的自然排序：按钮承诺了而 pip 装不了，比没有按钮更糟。
- **同一个坑有两份实现**：客户端 `desktop/src/version.go` 里另有一个 Go 版 `compareVersions`（决定要不要替换已解压的运行时），它曾把 local 段整个丢掉，导致 z02 之后所有版本的客户端都在跑第一次解压出来的旧包。改 Python 那个时必须同时改 Go 这个（z04 修复，两边判序现已一致）。

## 内网更新源怎么配

上游与 devpi 的"查版本"接口**既不同 URL 也不同 JSON 形状**（对着真实 devpi-server 实测，不是照文档写的）：

| 索引 | URL | 响应 |
|---|---|---|
| PyPI / Warehouse | `GET {host}/pypi/{name}/json` | `{"info": …, "releases": …}` |
| devpi | `GET {host}/{user}/{index}/{name}/`（`Accept: application/json`） | `{"result": {版本号: …}}` |

所以只有 `OCTOP_UPDATE_INDEX_URL` 时走 Warehouse 形状；自建 devpi 要显式给模板：

```bash
OCTOP_UPDATE_JSON_URL=http://devpi.internal:3111/zcagent/prod/{name}/     # 查版本
OCTOP_UPDATE_SIMPLE_URL=http://devpi.internal:3111/zcagent/prod/+simple/  # 装包
```

配了自有索引后，安装候选**只**包含该索引，不再探测公共镜像、也不回落 pypi.org——否则"立即更新"可能把别人的 `octop` 包装进内网机器。

---

## [1.0.2b6+z10] — 2026-10-12

### 修掉：桌面包里没有 Node，连接器一律装不上

普通用户装完客户端后打开任何 npm 类连接器（agently 邮件 / 飞书 / 企微），都会撞到
「未找到 npm，请先在 zcagent 主机安装 Node.js，然后执行：npm install -g …」
（`src/octop/infra/connectors/gateway/cli_install.py`）。这条指令对普通用户不可执行。

关键判断：**这些 CLI 本身就是 Node 程序**，所以"安装时临时联网下载 npm"解决不了运行期——
Node 运行时必须常驻。而我们的主叙事是内网部署（`README.md`「内网批量部署」），
装时联网恰好在最需要它的场景最容易失败。于是改成**构建时内置便携 Node.js**，
与已有的 python-build-standalone 完全同构：

| 环节 | 改动 |
|---|---|
| 下载 | `_common.sh` 钉 `NODE_VERSION=22.20.0`，走 npmmirror；`bootstrap-runtime.sh` 新增 `bootstrap_node`，解压进 `runtimes/<plat>-node`，并校验 `node_modules/npm` 载荷存在（npm 的 shim 靠它） |
| 打包 | `package.sh` 把该目录复制成 `<root>/node`，缺目录直接失败并说明原因（静默漏掉就是重新制造这个 bug）；`VERSION.txt` 多一行 `node=` |
| 启动 | `start.bat` / `start.sh` / `desktop/src/process.go` 三处都把 `<root>/node`（Windows）或 `<root>/node/bin` 前置进子进程 PATH，并设 `OCTOP_BUNDLED_NODE`。**不写系统 PATH、不在用户机器上装东西** |
| 消费 | `cli_install.ensure_cli_path()` 读 `OCTOP_BUNDLED_NODE` 前置进进程 PATH，使 `shutil.which("npm")` 与后续子进程都能命中 |

实测（本机没有全局 node，正是复现条件）：过滤掉 PATH 里所有 node 后
`which("npm") = None`；设上 `OCTOP_BUNDLED_NODE` 并调 `ensure_cli_path()` 之后
解析到包内 `npm.CMD`，`npm -v` 返回 **10.9.3**（rc=0）。
真跑了一次 `package.sh windows-amd64`：产物 zip 里 `node/` 有 2872 个条目，
含 `node/node.exe` 与 `node/npm.cmd`，打包出的 `start.bat` 带着 PATH 前置那三行。
体积实测：**zip 从 196,615,752 → 233,921,049 字节（+37.3 MB，+20%）**，解压 +100 MB
（其中 node.exe 占大头，`node_modules/npm` 17 MB、corepack 2 MB，裁剪省不了多少，没做）。

### 顺带修掉：打包在没有 `zip` 的 Windows 上会静默产不出 zip

`package.sh` 建 zip 时若没有 `zip` 命令就退回 `python3`，而**未装过 Python 的 Windows 10/11
上 `python3` 是 App Execution Alias 占位程序：什么都不打印、退出码 0**。
于是打包"成功"、日志照写 `wrote …`、zip 根本不存在——下游 Wails 嵌入、NSIS 载荷、
下载页的字节数全在描述一个没有产出的文件。改成：候选解释器必须**证明自己真能跑**
（`"$py" -c "print(1)"` 要回显 `1`），并且子 shell 之后硬检查 `[[ -s "$zip_path" ]]`，
没有就失败退出。本机正是这个组合（无 zip、`python3` 是 stub），修完才第一次产出真 zip。

### CI：补 node 的下载源、缓存与冒烟断言

`octop-desktop.yml` 里加 `NODE_VERSION` / `NODE_BASE_URL`（runner 上走 nodejs.org 上游，
与 PBS 的约定一致），新增一步 **Smoke bundled node**：从产物目录里真跑
`node -v` 与 `npm -v`，跑不起来就红——打包回归不会再变成一个能下载但没有连接器的包。
顺带修一个一直在空转的步骤：缓存路径写的是 `green/.cache`，而 `_common.sh` 实际用的
是 `desktop/portable/.cache`（workflow 从没设过 `GREEN_ROOT`），所以那个缓存永远 miss；
key 里现在也带上 `NODE_VERSION`。

### 交互：展开对话历史时自动折叠最左导航栏

`MainLayout` 里 `EXPAND_CHAT_RAIL_EVENT` 的处理原本写的是"两个栏都打开"，与预期相反。
现在 rail 接管宽度、导航栏收成 56px 图标条。`scripts/verify/layout_probe.py` 加了真的点击断言
（rail 可见 + 通过栏内按钮宽度判导航已折叠）。

### 交互：导航栏顶部加独立「新建对话」按钮

原来发起新对话只有会话卡片上那个 hover 才出现的图标按钮。现在导航栏顶部有一个
整宽实心主色按钮（折叠态退成 40px 图标），复用聊天页同一个目标 `/chat/<agent>`
（`useChatSessionActions.ts`），没有第二套导航逻辑；颜色走 `var(--fn-primary)`，多套配色仍可切换。

---

## [1.0.2b6+z09] — 2026-10-11

主题：**镜像下载的向量模型其实根本加载不了**。z08 的空闲预下载是把它逼出来的——
因为它是整条发版链上第一个问"这个模型你现在真的能用吗"的检查。

### 修复：94 MB 正确权重摆在机器上，客户端回 "Could not load model"

本机实测（装好的 z08，不动代码只改缓存目录名就能复现两边）：

| | 结果 |
|---|---|
| `POST /api/knowledge-bases/onnx-test`（修之前） | `{'ok': false, 'error': 'Could not load model BAAI/bge-small-zh-v1.5 from any source'}` |
| 磁盘 | `~/.octop/embedding_models/models--Qdrant--bge-small-zh-v1.5/snapshots/cos-mirror/`，`model_optimized.onnx` = 94,781,076 字节，文件齐全 |
| `POST …/onnx-test`（把同一批文件改成下面的布局后） | `{'ok': true, 'latency_ms': 219, 'dim': 512}` —— **同一个 exe、同一批文件** |

根因是 `onnx_download.py` 写缓存的方式不符合 `huggingface_hub` 的寻址规则，而且是**两处同时错**：

1. 快照写在 `snapshots/cos-mirror` 这种可读标签下，而 hub 只认 `refs/<分支>` 指向的
   **40 位提交哈希**目录；
2. `refs/main` 写的是 `"标签\n"`——hub 1.33 原样读取、**并不 strip**，多一个换行就等于
   整个快照看不见。

后果取决于网络：连得上 huggingface.co 的人等于把模型**下载两遍**（镜像一份、hub 再生成一份），
连不上的人（内网与国内网络的常态，也正是我们卖这个产品的场景）拿到的是一个永远起不来的知识库。
接口只报"字节数"和 `downloaded` 标志，所以两边都显示成功。

改法：`mirror_revision()` 用 `sha1(hf_repo)` 生成 40 位哈希；`hf_cache_snapshot_dir()`
只接受 40 位、按哈希目录写并把 `refs/main` 写成不带换行的哈希；
`normalize_mirror_layout()` 就地修复存量缓存（改名或重写 ref，幂等），
在 `_build_text_embedding()` 加载前调用——**已经下载过的老机器不用重新下载就能恢复**。

原有那条 `test_onnx_download` 断言本身就写死了错的布局，并且用 `.strip()` 读 `refs/main`，
换行这一半就是这么被遮住的；现在按精确相等比较，另加 `tests/unit/agents/test_onnx_cache_layout.py` 八条。

### 新增：装机验收必须真加载一次

`scripts/verify/client_release.py` 的 `stage_embedding_api` 现在会对默认列表里每一个标着
"已下载"的模型 `POST /knowledge-bases/onnx-test`，拿不到 `ok=true` 就失败。缺这条断言，
z08 才能带着上面那个缺陷出厂：下载成功、字节正确、界面显示"已下载"，全都对，
只有"用它"这一步没人问过。

### 顺带：这一轮装机验收拦下的都是工具自己的错

产物是对的，四次失败全在验收工具里，但每一条留着就会在下次真坏掉时看不见：
安装前没停掉在跑的客户端（句柄占用 → NSIS 静默留着旧构建）、用 mtime 判断装没装上
（NSIS 把打包时间戳原样盖到释放文件上，装好了反而更"旧"）、只读入口 chunk
（Vite 把路由级改动切进按需分片）、登录段没拖滑块验证码且把"知识库开关关着"当成断言目标。
细节与对照写在 [`site/download/VERIFICATION.md`](./site/download/VERIFICATION.md) 的 z08 一节。

### 空闲预下载：两趟对照已经跑通

`scripts/verify/prefetch_watch.py` 用临时 `OCTOP_HOME` + 备用端口跑装好的运行时刻：
开关打开时模型在启动约 130 秒后开始落地（>90 秒的空闲闸）、`attempts` 递增；
设成 `0` 时观察 135 秒，一个字节都没落、一行状态都没写。
`done` 那一条当时没出现，原因正是上面的加载缺陷——现在随 z09 一并验。

### 新增：官网 `/guide` 使用指南

`https://zcagent.jiuyeke.cn/guide/` 上线，18 章，从"装好"一路写到"内网交付"。
**内容是自己写的**：原料是仓库里随 fork 带来的上游文档（本仓库 `LICENSE` = MIT）、
代码与接口的实测事实，以及 `site/landing/screens` 的复刻屏；参照对象只取信息架构。
界面词一律取 `dashboard/src/locales/zh.json` 的真值，版本号 / 体积 / SHA256 全部走
`release.json` 的 token，模板里不写死任何会腐烂的数字。

站点因此从单页变成清单驱动的多页：`PAGES` 生成 sitemap，`verify_links()` 要求产物里
每个本地 `href/src` 都有对应文件、每个 `#锚点` 都命中同页真实 id（负向验证过：注入
一个坏文件引用 + 两个坏锚点，构建 `exit=1` 并逐条点名）。

这一节最值得留下的却是两条**只有干净检出才看得见**的耦合，完整过程记在
[`site/landing/PLAN-guide.md`](./site/landing/PLAN-guide.md) §7.1：正文引用的 token
与图片，有四个只存在于另一路**未提交**的并行改动里，工作区构建一切正常、干净检出直接失败。
结论是规矩：**"工作区能构建"不是证据**；以及构建与部署之间必须用 `&&`——
`build.py` 失败时 `dist/` 已被清空，用 `;` 会把半份站点推上线而工具照样回"成功"。

### 冲突面积重测（z09）

`scripts/classify_owned.py` 在 `0c5a46ab..bd7b003c` 上重跑：**437 = 294 纯生成 + 62 承载手工改动 + 81 我们新增**
（与 z08 那次同口径：两次都是"prettier ran over 53 rewritten dashboard file(s)"）。

z09 自己的足迹只有 **+2 个手工文件**：`onnx_download.py`（缓存寻址规则写在这里）与
`tests/unit/agents/test_onnx_download.py`（这条测试原来把错误布局当断言写死了，还把 `refs/main`
用 `.strip()` 读，换行那一半就是这么被遮住的）。新增那一栏 +27 里只有 2 个是 z09 的
（`scripts/verify/prefetch_watch.py`、`tests/unit/agents/test_onnx_cache_layout.py`），
其余 25 个是同一分支上并行落地的营销站 `site/landing/**`。

一条测量口径的教训，值得记下来：**第一次跑出来的数是 288 + 68 + 81**，看着像"手工又涨了 8 个"。
真相是那次基线 worktree 里 `format SKIPPED (no node/prettier)`（本机 `C:\Program Files\nodejs` 有 node
但不在 PATH 上），6 个纯生成的 dashboard 文件因此被误判成手工。把 node 加进 PATH 重跑才是可比数字。
以后凡是输出里出现"format SKIPPED"的测量，一律先当不可信，重来一遍再写进表格。

## [1.0.2b6+z08] — 2026-10-11

主题：**新手第一分钟**。方案与实测依据见 [`docs/PLAN-z08.md`](./docs/PLAN-z08.md)。

### 修复：`e5-large` 是个静默质量陷阱

`intfloat/multilingual-e5-large` 一直在「推荐」里，但 e5 系列要求查询端加 `query:`、文档端加
`passage:` 前缀，而**全仓 `grep "passage:"` 零命中**。后果不是报错，是选了它的人检索效果可能还不如
92 MB 的默认小模型——大模型反而更差且不提示，是最坏的一种缺陷。

`embed_texts` 现在带 `role` 参数（索引侧 `passage`、检索侧 `query`），前缀按模型集中分发；
`retrieve.py` 的测试从"容忍任意签名"改成**断言 role 必须是 query**。同时把它降级进高级选项
（2.24 GB 对桌面端本就不该占推荐位），推荐位换成 `paraphrase-multilingual-mpnet-base-v2`
（1.0 GB、768 维、约 50 语言、**不需要调用侧配合**）。中文推荐集变成 92 MB / 640 MB / 1.0 GB 三档。

### 修复：「展开更多」倒出 41 个模型，其中包括 CLIP

`include_all` 直接返回整个 fastembed 列表。实测 `GET /api/knowledge-bases/embedding-options?all_onnx=true`
返回 **41** 条，里面有 `Qdrant/clip-ViT-B-32-text`——图文模型，给知识库用是彻底错的；而 41 条中
**中文可用的只有 6 条**。现在取精选集与 fastembed 的交集，既不再泄漏 CLIP，也不会因为 fastembed
增删模型而让列表漂移。展开项改成真正的双向「高级选项」，并明确警示下面多为英文模型
（`all-MiniLM-L6-v2` 与默认中文模型同为 90 MB、名字最眼熟，是最容易被误选的一个）。

### 修复：体积兜底表 12 条里 6 条不准，方向还不一致

`_FALLBACK_SIZE_GB` 只在 fastembed 导入失败时生效——也就是**没人会去对照**的那条分支。实测偏差：
jina-zh 少报 2×、e5-large 少报 1.9×、`bge-small-en` 反而**多报** 1.9×。同一模型在不同机器上
显示的下载体积差一倍。已逐条按 fastembed 元数据校准，并加单测：偏差超过 20% 即失败。

### 新增：默认向量模型空闲预下载（含四道闸）

第一次打开「知识库设置」不该先干等 92 MB。服务端启动 90 秒后探测网络，可达则后台下载。
判据写成**一个纯函数** `decide_prefetch`，所以每道闸都能单独测：

| 闸门 | 内网/离线场景的意义 |
|---|---|
| 环境变量总开关 | 安装包与便携包默认开，内网离线交付包默认关 |
| 模型已存在 / 一次性状态 | 成功后不再评估 |
| 失败最多 3 次 | 不会每天重试打日志 |
| 磁盘剩余 ≥ 体积 ×2 | 半截模型会让功能永久不可用，比不下更糟 |
| 三源探测全失败即静默放弃 | 只留一行 INFO，界面完全不提示 |

失败回退：用户打开设置对话框时若仍无模型且允许预下载，自动开始并显示进度——**打开对话框即视为同意下载**；
预下载被关掉的部署则永远不会自动重试。capability 里新增 `prefetch_enabled` / `prefetch_state`
两个字段来区分"还没下完"和"这台机器根本不允许多下"。
**刻意不放进桌面 Go 壳**：源竞速、落盘路径、状态机都在 Python 侧，再写一份就是这个仓库第三个
"同一条规则写两遍"。

### 新增：11 处空白表单补默认值或有效示例

实测发现「必须自己打字、既没默认值、placeholder 又只是把标签重复一遍」的输入框共 11 处。
按主次处理：

- **真默认值**：知识库名称 `智策科技公司制度知识库` + 描述（并在下方明说"这是示例，建议改成你自己的"）；
  专家名称 `我的专属助理`；团队名称 `协作团队`——团队抽屉原先**主动把 name 设成空串**，已停止。
- **有效示例**：知识库文件夹、发布专家、角色名称、工作区重命名，统一改成「例如：……」格式，
  对齐定时任务与连接器本来就做对的写法。
- 全部纯前端，不动 API 契约与数据库。

### 新增：首启三步行事历

产品原先**完全没有** onboarding（无 Tour、无 checklist，只有各页静态说明卡），而跳过向导里的模型步骤
会得到一个起不来的默认专家——正是新手卡住的地方。现在 `/chat` 欢迎区下方给出
「① 配置模型 → ② 建第一个专家 → ③ 发出第一条消息」，完成一步自动打勾。

判据全部复用页面已经在取的状态，不新增埋点；**空线程不算完成第三步**（否则一建会话就勾掉了，
用户其实还没打字）。关闭状态存 localStorage 而非服务端用户偏好。
实现上是给既有的 `StreamSetupGuide` 增加 `done` 与可关闭态，而不是新造一张卡片。

### 新增：两个"看不见的功能"各有一条命令可证

后台预下载与模型列表都是**界面看不到的东西**：列表是接口返回的数据，预下载是启动 90 秒后才发生的
一次网络动作。所以两件事分别做成了可反复跑的验收工具（`scripts/verify/README.md`）：

- `client_release.py` 加了 `stage_embedding_api`：登录后直接问接口，断言默认列表 ≤4 条、展开后 ≤20 条、
  不含 CLIP、每条带一句话优缺点，且能力检查里必须出现 `prefetch_enabled` / `prefetch_state`。
  需要 `ZC_VERIFY_PASSWORD`（装机时你自己设的管理员口令），**口令不写进仓库**。
- 新增 `prefetch_watch.py`：它**不碰共享的 `~/.octop`**，而是用装好的运行时刻配一个临时
  `OCTOP_HOME` 与备用端口启动，两趟对照——开关打开必须在启动约 90 秒后把模型落到磁盘并写
  `done`，设成 `0` 必须一个字节都不落、一行状态都不写。之所以要临时目录：机器上已经有模型时
  正确行为就是什么都不做，而"功能坏了"看起来一模一样。

顺带把 `prefetch.py` 里一句错的注释改直了——它写着"离线包通过生成的启动脚本显式传 0"，
而 `make_kit.py` 根本没有生成启动脚本；事实是 `guide.md` 让运维自己设。

### 顺带修掉

`StreamSetupGuide` 的 `.card` 没有 `position: relative`，任何绝对定位子元素都会锚到视口上。

### 冲突面积重测（z08）

`scripts/classify_owned.py` 在 `0c5a46ab..ad11a0b4` 上重跑：**408 = 294 纯生成 + 60 承载手工改动 + 54 我们新增**。
手工那一栏从 z07 的 39 涨到 60，**+21 是有记录以来单版最大增幅**：知识库这条链是
"catalog → service → 路由 → 前端类型 → 组件"贯穿式的，改一个事实要同时改五个上游文件。
结论不是"别这么做"，而是**下次贯穿前先数一遍**，能收敛成"新增文件 + 一处注册"的就收敛
（z06 的自助重置接口就是这么做的，只碰了 `app.py`/`deps.py` 各一行）。

---

## [1.0.2b6+z07] — 2026-10-11

### 修复：客户端启动动画还是上游的红色章鱼

`desktop/src/assets/index.html` 的启动页引用 `/octop-mascot-peek.webp` 与
`/octop-mascot-type.webp`，而这两个文件在 `desktop/src/assets/` 下有一份**独立副本**，
既不在 `asset_map` 也不在 `poses` 里——上游把副本放在那儿，我们的品牌管线从来没管过它。
于是网页端吉祥物是边牧、装出来的启动动画还是章鱼。`brand.yaml` 的 `poses` 现在多两条输出
指向 `desktop/src/assets/`，与网页端同图同参数（`box: [352, 320]`）。

**这是同一个坑第二次出现**：z03 修图标时 `asset_map` 漏了桌面端的 `.ico` 源图。凡是"构建时才生成/
被复制进另一个目录"的东西，`git diff` 和 `--check` 都看不见，只有装出来才看得见。

### 变更：图标形象重画成真正的边牧

原来的 `brand/assets/icon-1024.png` 是"白脸 + 大黑胡子"，更像英国古代牧羊犬。新形象补齐边牧的
三个特征：**深色头部 + 从额头到口鼻的白色白斑 + 半立且耳尖前折的耳朵**，口鼻收窄成白色。
派生资源由 `rebrand.py --apply` 一次性重生成 13 个文件（favicon、PWA、横竖版 logo、
`appicon.png`、托盘图标、四个吉祥物 webp）。实测缩到 16px 仍能认出是边牧。

### 变更：版本号移到 logo 下方

侧栏头部原本是 `logo | 版本徽章 | 更新徽章` 一行，`v1.0.2b6+z06` 被挤到截断。
`Sidebar.tsx` 的 `brandInner` 改成列：logo 在上、徽章行在下；收起侧栏时仍然只有 logo 并居中。

### 新增：客户端右键菜单改成「上一页 / 重新加载系统」

WebView2 内建右键菜单是 返回 / 刷新 / 另存为 / 打印，**标签由 Edge 运行时决定，既不能改名也不能
单独去掉某一项**。所以两个窗口都设 `DefaultContextMenuDisabled: true`，再用注入脚本画我们自己的
两项菜单（`desktop/src/context_menu.go`）。要点：

- 脚本不依赖 `_wails`，因为仪表盘是 `http://127.0.0.1:8088` 这个远程源，那里没有 `/wails/runtime.js`；
  菜单只用 `history.back()` 与 `location.reload()`。
- 文案跟着 `document.documentElement.lang` 走（仪表盘 `syncDocumentLang` 会设），中文
  「上一页 / 重新加载系统」，英文 "Back / Reload"。
- 「上一页」在 `history.length <= 1` 时置灰；点外面、滚轮、Esc、窗口失焦都会关掉。
- 测试用反向断言锁住"不许出现 save/print/另存/打印"，并断言两个窗口都关掉了内建菜单。

### 新增：`scripts/verify/` 收拢可反复跑的验收工具

历史上每个版本现抄一份脚本（`verify-z04.py`、`verify-client.py`、`fetch-z06.py`、
`verify-z06.py` 是同一件事的四份副本），真正抓缺陷的断言反而在抄写中走样。现在一条命令跑完
"解析 Release → 下载校验 → 静默安装 → 启动 → 断言"：

```bash
.venv/Scripts/python.exe scripts/verify/client_release.py --version 1.0.2b6+z07
```

它把这一路踩过的坑全部固化成断言：字节数与 Release `digest` 必须一致（`gh release download`
曾对残缺文件返回成功）、解压后的运行时版本必须等于目标版本（z02–z04 的比较器 bug）、入口 chunk
必须含各版本引入的标记串、强制 `en-US` + 空 localStorage 下登录页必须中文、z06 起必须有账号点名
与自助重置表单、以及从 exe 里抠出内嵌图标。`scripts/verify/README.md` 逐项写了每条断言对应的真实缺陷。

### 冲突面积重测（z07）

`scripts/classify_owned.py` 在 `0c5a46ab..3fe1ac9e` 上重跑：**386 = 295 纯生成 + 39 承载手工改动 + 52 我们新增**。
手工那一栏从 z05 的 33 涨到 39，涨的是 `desktop/src/main.go`（关内建右键菜单）、
`api/app.py` 与 `api/deps.py`（自助重置接口的注册与免鉴权）、`Sidebar.tsx` 的版本位等；
新增那一栏从 45 涨到 52，主要是 `scripts/verify/` 与桌面壳的测试文件。

---

## [1.0.2b6+z06] — 2026-10-11

### 新增：忘记密码不再需要开终端

安装版复用 `%USERPROFILE%\.octop`，所以在**已经有数据的机器上**装新版，会直接落到一个登录页，
而那个账号是当初初始化向导建的、用户并不记得。此前唯一的提示是"去跑 `octop user passwd`"——
对普通用户就是死路。

现在登录页会说清两件事：**这台机器已有智策数据、账号叫什么**，「忘记密码」弹窗在可自助时显示
表单（账号 / 新密码 / 确认）而不是 shell 命令；不满足条件的服务端部署仍然显示原来的命令说明。

### 新增：`POST /api/auth/local-reset` 与其权限边界

这个接口**不做任何身份验证**就能改密码，所以它的成立条件被收窄到与 `octop user passwd` 完全等价——
能访问到 loopback 上这个服务的人，本来就能读写同一个 SQLite 文件，接口没有多给任何权限。三条拒绝：

| 条件 | 为什么必须拒 |
|---|---|
| TCP 对端不是 loopback | 用 `request.client.host`，**不用** `resolve_client_ip`（后者会信 `X-Forwarded-For`，否则一个头就能伪装成本机） |
| 服务绑定地址不是回环 | 绑 `0.0.0.0` 时同机反代会把所有远程访客都呈现成 127.0.0.1 |
| 账号数不等于 1 | 多用户实例上"按用户名重置"会变成互相夺号 |

重置成功后会顺带清掉登录锁定（忘了密码试出来的锁定，不该在重置之后还挡着）。
弱密码直接复用 `validate_password_policy` 抛 `OctopError`，因此错误文案走既有的本地化通道。

改动落在新文件 `api/routers/local_recovery.py`（`app.py` 注册 + `deps.py` 免 JWT 各一行），
没有去动 `auth.py`——它此前是干净的上游文件，不值得为这个功能增加冲突面。

### 实测

- 单元：`tests/unit/api/test_local_recovery_router.py` 10 条，覆盖上表三条拒绝、XFF 伪装、
  无 socket 对端、用户名不符、弱密码、以及"状态接口不向外人泄露账号名"。
- 全量 `tests/unit/api`：**340 passed / 10 skipped**，无回归。
- 前端：`src/pages/Login` **23 passed**（新增 `Login.localReset.test.tsx` 断言表单里**不出现**
  `octop user passwd`，并真的把新密码提交出去）。
- 活服务（本机 `octop run`，回环 + 单账号）：
  `GET /api/auth/local-recovery` → `{"available":true,"username":"admin"}`；
  错用户名 → `404 no_such_user`；弱密码 → `400` 且消息是中文的
  「密码过弱：至少 8 位，且同时包含字母和数字。」；正确重置 → `200`，
  随后**新密码登录 200、旧密码登录 401**，再重置回原密码确认恢复。

---

## [1.0.2b6+z05] — 2026-10-11

### 修复：托盘菜单与"首次启动正在解压…"仍是英文

`desktop/src/settings.go` 的 `defaultSettings()` 把 `Locale` 钉在 `LocaleEN`，而桌面壳的文案（托盘右键菜单、
设置窗、启动状态条、健康检查失败提示）在**任何网页出现之前**就要渲染，所以它拿不到前端的语言状态。
结果是：仪表盘已经中文了，托盘和"First launch: unpacking the bundled runtime…"还是英文。

**先量了再改**：本来准备按系统界面语言取默认值（`GetUserDefaultUILanguage`，`golang.org/x/sys/windows`
已是依赖，本机 Go 1.25.1 实测可编译）。探针跑出来这台中文 Windows 的**显示语言是 en-US**——照它走会得到
"仪表盘中文、外壳英文"的分裂状态，比现在更糟。所以最终决定与前端 `resolveInitialLocale()` 保持一致：
**默认中文**，用户在设置窗里选的语言写进 `desktop-settings.json` 后优先。实测本机此前根本没有
`desktop-settings.json`，即外壳一直在跑硬编码的英文默认值。

新增 `desktop_copy_locale_test.go` 三条守卫：中英文案表**键集合必须相同**（只加一头会静默回落英文，
正是"能汉化的都汉化"这条承诺无声失效的方式）、`%s` / `%d` 占位符数量两侧一致、默认 `Locale` 为 `zh`。
`go vet` + `go test ./...` 本机与 CI 均通过。

### 冲突面积重测（z05）

`scripts/classify_owned.py` 在 `0c5a46ab..39e13282` 上重跑：**374 个文件 = 296 纯生成 + 33 承载手工改动 + 45 我们新增**。
手工那一栏从 25 涨到 33，涨的全是桌面壳的 Go 文件与流水线：`desktop/src/version.go`（判序）、
`desktop/src/settings.go`（默认语言）、`desktop/src/download_test.go`（两条钉住旧判序的用例）、
`.github/workflows/octop-desktop.yml`（`go test` 步骤）等。逐条清单见 `brand/owned-files.txt`。

### 为什么紧接着 z04 又发一版

z04 只带上了运行时替换的修复；外壳语言是其后才提交的。而这两版对用户的表现是同一句话——"界面还是英文"——
所以合并成一次可验证的交付：z05 同时验证"新客户端会替换旧运行时"（z04 引入的比较器）与"外壳中文"。
实测见 [`site/download/VERIFICATION.md`](site/download/VERIFICATION.md)。**结果（本机实跑）**：
保留 `~/.octop/portable` 停在 `1.0.2b6+z02` 的状态，启动 z05 的安装产物后该目录被替换成
`1.0.2b6+z05`，`8088` 服务的入口 chunk 从 z02 的 `index.XAfRwQg_.js` 变成 `index.Scx49Zw2.js`，
其中 `resolveInitialLocale(){return readStoredUiLocale()??"zh"}` 确认在产物内；用强制
`navigator.language=en-US`、localStorage 为空的浏览器上下文渲染，登录页与"忘记密码"弹窗均为中文，
logo 是边牧犬。安装包字节数与 SHA256 与 Release 的 `digest` 完全一致。

---

## [1.0.2b6+z04] — 2026-10-11

**这一版修的是"升级"本身**：从 z02 之后，每一个新客户端装上去跑的都还是第一次解压出来的旧运行时。
用户报的"忘记密码弹窗还是英文"就是它的症状——z03 的修复确实在产物里，只是永远读不到。

### 修复：新版本客户端不会替换已解压的运行时

`desktop/src/version.go` 的 `compareVersions` 把 PEP 440 的 `+local` 段解析出来之后**丢掉不比**，
于是 `compareVersions("1.0.2b6+z03", "1.0.2b6+z02") == 0`。`ensurePortable` 的判据是
`compareVersions(bundled, installed) <= 0` 就沿用现有运行时，等号成立 ⇒ 直接返回，
连备份数据库那步都不会走到。

实测链条（本机，不是推演）：先装 z02 让它解压，再静默安装并启动 z03 的 exe，
`~/.octop/portable/VERSION.txt` 仍是 `octop_version=1.0.2b6+z02`，`8088` 上服务的仍是 z02 的
`index.XAfRwQg_.js`；而 z03 绿色包里的入口 chunk 已经是 `index.Scx49Zw2.js`，
其中 `resolveInitialLocale(){return readStoredUiLocale()??"zh"}` ——修复在包内，被这个等号挡在门外。

改动与验证：

- `version.go` 按 PEP 440 补齐 local 段比较（无 local < 有 local；数字段小于字母数字段；字母数字段
  按不区分大小写的字符串比；短前缀小于长）。与 `self_update.parse_version` 的判序一致。
- 上游 `TestCompareVersions` 里有两条用例把"local 不参与比较"当成了契约
  （`{"1.0.2+local.10", "1.0.2", 0}`），已改成 PEP 440 的正确期望；`TestEnsurePortablePrereleaseUpgrade`
  补 `+z02→+z03` 会替换、`+z03→+z03` 不动、`+z05→+z04` 不降级三条。
- 新增 `desktop/src/version_test.go`。对照实验：同一份测试跑在修复前的 `version.go` 上，
  11 条断言全红且**每个 `+zNN` 对都返回 0**；跑在修复后全绿，`go vet` 干净。

### 新增：desktop 的 Go 测试进 CI

上游写了 8 个 `_test.go` 却从未运行——全仓库 `.github/workflows/` 里 `grep "go test"` 零命中，
所以这个 bug 带着自己的单元测试存在了很久。本机确认 `desktop/src` 在 Windows 上能 `go vet` + `go test`
全绿，于是在 `octop-desktop.yml` 的打包步骤前加了一个 `Test desktop build` 步骤（Linux 依赖装完之后、
装 wails3 CLI 之前），让测试有机会在打包前拦住它。

### 一条必须说清的交付话术

比较器在 **exe 里**，不在解压出来的运行时里。所以已经装了 z02/z03 的机器**不会**被自己的更新检查修好——
必须重新下载并运行一次新安装程序。给老用户的说法就一句：换 z04 的安装包重装，界面语言、图标才会对。

### 实测：登录凭据与"英文"的边界

安装版复用 `~/.octop`，那台机器上的账号是验收时自建的管理员（用户名 `admin`，口令是本次验收临时设定的
演示口令，不再在此记录——仓库是公开的）。`POST /api/auth/login` 实测返回 JWT，`user.locale` 已是 `zh`。
也就是说**登录之后**本来就是中文，英文只出现在登录页与"忘记密码"弹窗
这类游客界面——正是 `applyGuestLocale()` 那条路径。

> 该演示口令曾出现在本节的历史提交里，公开仓库的历史不可撤销，所以按"已泄露"处理：装机组请用
> z06 的本地重置流程改成用户自己的口令，后续版本不再在任何文档/提交里写出口令明文。

---

## [1.0.2b6+z03] — 2026-10-10

三处"源码里看不出来、装出来才发现"的问题：客户端图标是上游的、安装版默认开英文、更新页教用户跑
上游的安装命令。加上客户端下载卡与 README 重写。

### 新增：应用更新页里的「客户端下载」

`/admin/advanced?tab=updates` 底部多一张卡片，指向 Windows 客户端的下载地址。地址来自品牌层新增的
`download_url`（`PUT /api/branding` 可改，`http://` 允许，因为内网下载站就是 http；`javascript:` /
`data:` / 相对路径被拒），留空回落到本项目的 Releases 页。**下一节讲为什么默认不是那个更好看的下载页。**

改动：`branding.py` 字段与校验、`branding/runtime.ts` 的 `downloadUrl()`、新组件
`ClientDownloads.tsx`（复用 `UpdateConfig.module.less` 的面板类，视觉与旁边面板一致）、
`BrandingSettings.tsx` 的输入框、两份 locale。已实测整条 OEM 回路：默认 → 在「品牌」里填
`http://10.20.30.40/zcagent/` 保存 → 卡片按钮与提示语随之切换 → 清空后回落默认。

### 移除：更新页里上游的一键安装命令

`UpdateConfig` 的「按安装方式更新」原来教用户执行

```
curl -fsSL https://finnie-1258344699.cos.ap-guangzhou.myqcloud.com/octop/install.sh | bash
irm https://finnie-1258344699.cos.ap-guangzhou.myqcloud.com/octop/install.ps1 | iex
```

在智策的安装包里跑这两条，装的是**上游的 Octop**——正是更新检查默认关闭所要防的那件事，却以"升级说明"
的形式摆在页面上。已从 `GUIDE_METHOD_ORDER` 去掉 `installer` 一项，由上面的客户端下载卡替代；`cli` /
`pip` / `source` / `docker` 保留（它们操作的是本机已装的那一个）。

### 实测：安装版第一次真跑（含卸载）

见 [`site/download/VERIFICATION.md`](site/download/VERIFICATION.md)。要点：SHA256 与 Release digest
一致；`ProductName/CompanyName=zcagent`、`FileVersion=1.0.2b6+z02`；静默安装 → WebView2 起窗口 → 应用把
绿色包解到 `~/.octop/portable` 并以 `launch.py run --port 8088` 起服务（HTTP 200）；卸载后安装目录与控制
面板条目都干净。**一条要写进交付话术的残留**：`~/.octop/portable` 约 **712 MB** 不被卸载删除（它在数据目录
内，卸载器按设计不动数据）。

顺带记录一个只在源码开发安装上出现的现象：更新页的 `current_version` 取自已安装的发行版元数据
（`importlib.metadata`），不是 `src/octop/__init__.py`，所以改完版本号不重装就会显示旧值；打包安装的产物
实测显示正确。

### 新增：客户端下载页纳入仓库

`site/download/`：`release.json`（版本、每个产物的名字/字节数/SHA256/链接的唯一来源）+
`src/`（模板与资源）+ `build.py`（渲染 `dist/`，`--from-github` 直接从 Release API 刷新数字，拿不到
`digest` 就失败退出；`--check` 用于断言 `dist/` 是否过期）。已发布并设为公开访问。

### 修复：桌面客户端的图标一直是上游的

`brand.yaml` 的 `asset_map` 覆盖了 PWA / favicon / 字标 / 竖版 SVG，**唯独没有桌面端的三张**：
`desktop/src/build/appicon.png`、`appicon-macos.png`、`desktop/src/assets/tray-icon.png`。
`wails3 generate icons -input appicon.png -windowsfilename windows/icon.ico` 在构建时把
`appicon.png` 变成 `.ico`（仓库里没有 `.ico`），再由 `wails3 generate syso` 嵌进 exe ——
所以**装完之后文件图标、任务栏、开始菜单、系统托盘显示的还是上游的 Octop 图标**。已把三张纳入
`asset_map`（512 / 1024 / 96，`keep_bg`），`--apply` 后 `appicon.png` 与 `pwa-512.png` 字节一致，
托盘图在 96px 下仍清晰。这条只有真装一次才看得见，源码里看不出问题。

### 修复：安装版客户端默认开成英文

现象：安装版首页登录页是 "Sign in / Forgot password?"，而浏览器里同一套界面是中文。原因不在翻译——
`zh.json` 里 `login.forgotPassword*` 这些 key 的值本来就是中文——而在语言初始化：

- WebView2 在中文 Windows 上把 `navigator.language` 报成 `en-US`，`detectBrowserLocale()` 于是选英文；
- 更糟的是 `applyGuestLocale()` 会把这个**猜出来的**语言 `storeUiLocale()` 写进 localStorage，
  于是"第一次打开是英文"变成"以后都是英文"。

修法：`resolveInitialLocale()` 改为「已存偏好优先，否则中文」（智策是中文优先产品），
`applyGuestLocale()` 不再自动落盘——自动猜的语言不是用户的选择。用户在安装向导 / 账户里显式选的
English 仍然生效并保留。实测：`navigator.language = en-US` + 空 localStorage 的新浏览器上下文里，
登录页与「忘记密码」弹窗全部中文，只剩命令与 Linux/macOS/Windows/Docker 这些名字是拉丁字
（这正是"除了命令没办法"的边界）。`localePrefs.test.ts` 补两条断言（无偏好→zh、显式 en→保留）。

### 文档：README 顶部改成产品介绍 + 客户端获取

原来 README 第一句就是"基于上游做自有品牌"，那是**给我们自己看的**；现在顶部先讲智策是什么
（专家 / 技能 / 工具插件 / 知识库 / 连接器 / 通道 / 定时任务 / 多用户的各自用途）、实测过什么、
明确不做什么，然后是 Windows 客户端怎么拿。fork 与追版的内容下移，仍然全在。

客户端表格用 `<!-- client-downloads:start/end -->` 标记，由 `site/download/build.py` 从
`release.json` 生成——**和下载页共用同一份数字**。反向验证过：手改 README 里一个字节数，
`build.py --check` 退出码 2 并提示重跑；恢复后为 0。

---

## [1.0.2b6+z02] — 2026-10-10

修的是**已经发出去的 z01 产物里**的两处品牌缺陷，以及一处指向错误的外链。触发点很朴素：你指出侧栏「帮助与反馈」不该指向上游官网。

### 修复：协议头被产物名规则改名（z01 已带病发布）

`Octop-` → `zcagent-` 这条字面量是为**发布产物名**写的，但字面量没有边界，于是它顺手改掉了线上协议头：`X-Octop-Agent-Id` → `X-zcagent-Agent-Id`、`X-Octop-Access-Token` 同理，共 13 个文件（API、中间件、前端请求层）。**所有冒烟测试都过**，因为一条链路的两端都在我们树里；真正会断的是边界上那头——对端是上游实例，或照上游文档写的客户端。而 `README.md` 的"绝对不要改的标识符"表里第一条就是它。

- 规则改为带左边界的 pattern：`(?<![A-Za-z0-9_-])Octop-`，产物名照改、`X-Octop-*` 不动。
- 13 个文件里的头名全部还原。
- `tests/unit/scripts/test_rebrand_transform.py` 5 例锁住两侧：产物前缀必须仍被重写，协议头必须不被重写。

### 修复：`--check` 的守卫看不见这些文件类型

`uncovered_hits()`（本意是防"glob 写错导致空集假绿"）只读 `.py/.ts/.tsx/.json/.less`。因此这三类**既没被清扫、也没被报告**：

| 文件 | 后果 |
|---|---|
| `desktop/portable/templates/README.txt` | 便携包解压后用户读到的第一行是 "Octop green portable package"（z01 的 zip 里实测读到） |
| `desktop/src/assets/index.html` | 桌面壳自己的窗口标题、托盘设置窗、"显示 Octop" 按钮 |
| `desktop/src/build/windows/nsis/wails_tools.nsh` | NSIS 的 `INFO_PRODUCTNAME` / `INFO_COMPANYNAME` / `INFO_COPYRIGHT`。它是**手写签入**的助手文件，`!ifndef` 里的值是构建没传 `-D` 时的兜底（本地 `makensis` 与手工打包路径就会用到）；正式构建走 `config.yml` 的 `productName` / `companyName`，那两处早已是我们品牌。现在兜底与真值一致 |

清扫覆盖面从 **2356 → 3258 个文件**，守卫改为读所有文件（跳过二进制与 >2MB），并覆盖 `dashboard/public/*.html`、`src/octop/**/*.{md,sh,js,json}`、`desktop/**/*.{md,txt,html,nsh}`、`scripts/*.md`、`dashboard/src/**/*.css`。

### 变更：帮助与反馈指向我们自己

`AvatarDropdown` 的 `HELP_FEEDBACK_URL` 从 `https://octop.cloud` 改为仓库地址，并**下沉为品牌字面量**（OEM 交付时改 `brand/brand.yaml` 的 `to` 即可换成客户自己的文档/工单入口）。这条必须用 pattern：`https://octop.cloud` 是通道服务地址 `https://octop.cloud.tencent.com` 的前缀，纯字面量会把腾讯的 OctoBot 端点一起改坏——测试里同时锁了这两条。

`transform()` 因此支持 `pattern:` 字面量；三条 identity 规则里有两条需要边界。

### 便携包在全新状态下的实测

下载 `zcagent-portable-windows-amd64-1.0.2b6+z01.zip`（196,531,087 B，逐字节核对；`gh release download` 曾在只落 72 MB 的情况下返回成功）→ 解压 658 MB → `start.bat --port 8090`：内嵌 CPython 3.12.12 直接起来，打印一次性首启口令 → 走完向导（验证密码 → 数据库默认 SQLite → 建管理员 → 模型可跳过）→ 登录进 `/chat`。实测：标题「智策 - 懂你、帮你、陪你成长的智能伙伴」、`--fn-color-brand = #3d5a80`、版本角标 `v1.0.2b6+z01`、侧栏默认 14 项、可见文案里**没有** "Octop"。唯一读回来的不符项就是上面那个帮助链接 `https://octop.cloud/`，本版修掉。

### 发布与验证

| 项 | 值 |
|---|---|
| tag | `v1.0.2b6-z02` → commit `cb2d1d6`（其后的提交只有本段发布记录） |
| Release | <https://github.com/openclawzhangchong/zcagent/releases/tag/v1.0.2b6-z02>（prerelease） |
| 产物 | `zcagent-desktop-windows-amd64-1.0.2b6+z02.exe` 192,376,329 B；`zcagent-portable-windows-amd64-1.0.2b6+z02.zip` 196,531,309 B |
| `Frontend` 门禁 | tag 之前在该提交上跑绿：Lint / Format check / Typecheck and build / Unit tests 全 success |
| **产物内实检** | 下载 CI 产出的 `dashboard-dist` 直接 grep 打包后的 JS：`https://octop.cloud` 只剩通道端点 `octop.cloud.tencent.com` 一处；我们的仓库地址在 `assets/index.*.js` 里；头名是 `X-Octop-Agent-Id`（9 处）与 `X-Octop-Access-Token`（1 处），**没有** `X-zcagent-*`；主色 `3d5a80` 在包内，JS 里已无 `e85d75` |
| 旧版处置 | `v1.0.2b6-z01` 未删除，改标题为「⚠️ 已废弃 · 请勿安装」并在说明首段写明它带着哪两处缺陷——留证比抹掉有用，但必须挡住误装 |
| 冲突面积 | 350 = 295 纯生成 + **26 手工改动（不变）** + 29 新增。清扫覆盖面从 2356 提到 3257 个文件，手工面一个都没涨 |

`rebrand.py --check` 3257 文件无残留；`tests/unit/scripts` 5 passed；`tests/unit/api` + `tests/unit/agents` **1009 passed / 13 skipped**；前端 `prettier --check` 与 `eslint`（0 error）通过；`request.authToken.test.ts` 6 passed（这条直接读头名）。


---

## [1.0.2b6+z01] — 2026-10-10

基于上游 `v1.0.2b6`（commit `0c5a46a`，2026-10-08）。首个自有品牌版本。

### 发布记录

| 项 | 值 |
|---|---|
| tag | `v1.0.2b6-z01` → commit `6b68ad3`；其后的提交只有测试与文档，不影响产物 |
| GitHub Release | <https://github.com/openclawzhangchong/zcagent/releases/tag/v1.0.2b6-z01>，标记 **prerelease**（基线本身是上游 beta） |
| 产物 | `zcagent-desktop-windows-amd64-1.0.2b6+z01.exe`（192,374,876 B）、`zcagent-portable-windows-amd64-1.0.2b6+z01.zip`（196,531,087 B），由 `zcagent Desktop Package` 作业产出并挂到 Release |
| 为什么重切版本号 | 首版按 `+z1` 发布；实测 PEP 440 对 local 段按字符串比较，`+z10 < +z9`，即第 10 次自有发布会被判为降级。序号从 `z01` 起零填充是代价最小的修法（改 4 个文件的版本串 + 重打一次 tag 重跑一次构建），比让比较器去"比 pip 聪明"安全 |
| `Frontend` 门禁 | 绿：ESLint 0 error、`prettier --check` 通过、`tsc -b` + vite build 通过 |
| vitest 基线（CI，非阻塞） | 6 failed / 1147 passed，218 文件，92.7s。这 6 个失败所在的测试文件与其被测模块相对上游基线**零改动**，故不属品牌改动引入；本机在干净上游树上稳定红 6–8 个 |
| 签名 | 未签名（刻意，见 `docs/PLAN.md` P5-4） |
| 追版现状 | 上游 `main` 自基线后未前进（`0c5a46a` 就是当天的 main tip），`develop` 反而**落后于** main（上游用 sync-main-to-develop 单向同步），所以 `sync_check.py` 报"无可 merge"是真结论而非装置失效；最新 stable tag 仍是 `v1.0.1`，比我们的 beta 基线旧，下一个追版窗口是上游出 `v1.0.2` 稳定版 |


### 新增：OEM 品牌层

- `brand/brand.yaml` —— 品牌单一真源：`name.en=zcagent`、`name.zh=智策`、`colors.brand=#3D5A80`、`identity` 反写域名 `cn.jiuyeke.zcagent`、清扫/排除清单、图标产物映射。
- `scripts/rebrand.py` —— `--apply` / `--check` / `--revert` / `--status` 四个动作：
  - 文本层：大写品牌词按 ASCII 边界替换（`OctopError`、`X-Octop-*`、`octop-harness`、i18n key 等一律不命中），中文 locale 用中文名、其余用英文名；固定说法走 `phrases` 表。
  - 颜色层：把默认主题指向上游已有的 `custom` 派生通道（运行时生成全套 CSS 变量 + AntD token，含深色模式），只动 2 行，**8 套预设配色保持可切换**。
  - 图标层：从 `brand/assets/icon-1024.png` 自动裁方、抠平色背景，产出 PWA 512/192、apple-touch、favicon、竖版 SVG；横版 logo 用 PIL + 系统 CJK 字体合成"图形 + 中文名 + 英文名"字标（不用 AI 生成文字），深浅两版按主题输出。
  - 吉祥物：`brand/assets/mascot-{peek,typing,empty}.png` 三个姿势 → 自动抠平色背景、裁方、按上游原尺寸输出；动画 WebP 由 PIL 生成（`bob` 上下浮动 / `nod` 轻微点头两种模式，无需 ffmpeg），帧数与尺寸对齐上游资产（peek 352×320、type 856×812、empty 2048²）。
  - `--check` 除了断言目标文件无残留，还会报告"含旧品牌但根本没被清扫覆盖"的文件——避免 glob 写错导致的假绿。

### 变更：应用自有品牌

- 全量清扫 **2347 个文件**，覆盖后端、前端、测试、桌面壳、fnOS/Docker 打包与安装脚本。
- 桌面身份：`desktop/src/build/config.yml`、`windows/info.json`、`darwin/Info.plist{,.dev}`、`windows/wails.exe.manifest` 的 product/company/identifier 全部改为 `zcagent` / `cn.jiuyeke.zcagent`。
- 反写域名替换同时覆盖正则里的转义写法（`com\.tencent\.octop`），否则 `stamp_version.py` 会在打包时 `SystemExit`。
- 上游文档改名保留：`README.md → README.upstream.md`、`CHANGELOG.md → CHANGELOG.upstream.md`。追版时这两个文件按"ours"解冲突。

### 变更：更新源可配置（并实测过真实 devpi）

`src/octop/infra/setup/self_update.py` 的索引地址改为读 `OCTOP_UPDATE_INDEX_URL`（默认仍是 `https://pypi.org`），UI 上的来源标签随之显示真实主机名。分发名保持 `octop`，因为它同时是 pip 升级目标与已安装发行版查询名。

先前这里写过一句"devpi 提供同样的 `/pypi/<name>/json`"——**实测是错的**：本地起 devpi-server、建私有 index、把我们真正的 wheel 传上去之后，`/pypi/octop/json` 返回 404（那条路由只服务 `root/pypi` 镜像），devpi 的形状是 `GET /{user}/{index}/{name}/` + `Accept: application/json`，响应还换成 `{"result": {版本号: …}}`。于是：

- 新增 `OCTOP_UPDATE_JSON_URL`（含 `{name}` 的模板）与 `OCTOP_UPDATE_SIMPLE_URL`（装包地址，devpi 是 `+simple`）；请求头补 `Accept: application/json`。
- `_as_warehouse_shape()` 把 devpi 的 project / 单版本视图归一化成 Warehouse 的 `info`/`releases`，下游一处都不用分支。
- **配了自有索引后，安装候选只包含该索引**，不再探测公共镜像、也不回落 pypi.org。原来的写法会把四个公共镜像排在前面并始终把 pypi.org 追加为兜底——内网部署点"立即更新"就可能装上别人的 `octop`，正是这条更新检查默认关闭所要防的事。
- 端到端实测：devpi 里放 `1.0.2b6+z01` → 读出 `latest_any=1.0.2b6+z01`、`source=127.0.0.1`；再传一个更高版本 → 判序正确。

### 修复：`+z` 补丁序号此前对更新检查不可见

`parse_version()`（上游手写的 PEP 440 排序键）正则里**捕获了** `local` 段却从不使用它，于是 `1.0.2b6+z1` 与 `1.0.2b6+z9` 的键完全相同：`is_newer()` 恒为 False，**我们自己的补丁序列在更新页上永远不会亮**。实测：

```
is_newer("1.0.2b6+z9", "1.0.2b6+z1") -> False     # 修复前
```

修法是把 local 段按 PEP 440 的规则纳入排序键（数字段按数值、字母数字段按小写字符串、有 local 高于无 local），**故意不做自然排序**：判序必须和 pip 一致，否则按钮承诺了而 pip 装不了。上游测试里 `parse_version("1.0.2+local.10") == parse_version("1.0.2")` 这条断言正是被忽略 local 的结果，已按 PEP 440 改正并加注释。

顺带测出 scheme 本身的坑：PEP 440 对字母数字 local 段按**字符串**比较，`Version("1.0.2+z10") < Version("1.0.2+z9")`。所以序号从 `z01` 起零填充，本版随之从 `+z1` 重切为 `+z01`（`1.0.2b6+z1` → `1.0.2b6` 的打包等价性已复核：`four_part_version("1.0.2b6+z01")` → `1.0.2.0`）。

### 变更：一处上游测试修正

`dashboard/src/utils/expertColor.test.ts` 把写死的 `"rose"` 改为引用 `DEFAULT_PALETTE` 常量——改默认配色的正当后果，且这样上游再怎么调色板都不会误报。

### 新增：运行时 OEM 品牌覆盖层

构建期品牌决定"装出来是什么样"，这一层让**客户管理员装完之后不改代码就能改**：

- `GET /api/branding`（免鉴权，登录页也要能读）+ `PUT /api/branding`（`admin_console` 权限），值存 `settings` KV 的 `branding` 行，**不加 migration**。
- 字段：`name` / `name_zh` / `tagline` / `color` / `logo_url`；空字段回落到构建期品牌，未配置的部署行为不变。
- `logo_url` 只接受 `https://` 或 `data:image/` URI（上限 300KB），**不接受文件路径**，避免把宿主文件变成可被 `<img src>` 读回来的出口。
- 前端在 `main.tsx` 首次渲染前 `await loadBranding()`，所以标题、主色不会闪一下构建期默认值；`color` 存在时复用上游已有的 `custom` 调色板派生（AntD token + CSS 变量 + 深浅两套），并且**部署级主色优先于用户自选配色**。
- 验证：把覆盖设成 `#0F766E` 后，不重新构建，焦点环与复选框即变青绿；清空覆盖后回落钢蓝。`tests/unit/api` + `test_scalar` 305 passed / 10 skipped。
- **已完成**：`logo_url` 接入 `src/branding/AppLogo.tsx`，替换 Header / Sidebar / Login / Setup **4 处**调用点（先前估计的"12 处"把吉祥物引用也算进去了，实际只有 4 处）；`loadBranding()` 同时改写 `link[rel=icon]` 与 `apple-touch-icon`，浏览器标签页图标跟着换。管理页新增「品牌」tab（`/admin/advanced?tab=branding`），可填中英文名、标语、主色、粘贴 https 链接或上传图片，保存后自动刷新生效。
- 已知边界：`index.html` 里 JS 之前的启动屏仍用构建期 logo —— 运行时覆盖发生在 React 挂载前的一次 fetch，早于它也就要把品牌写进 HTML 模板，那属于构建期职责。

### 新增：P2 换壳 —— 导航渐进式披露

默认侧栏只保留内网单机助手用得上的 14 项，把**云端协同、远程桌面、ACP、Token 统计、存储后端**这 5 项收进一个开关（应用设置 → 品牌 → 界面）。选择"隐藏"而不是"删除"：删掉每次追版都要冲突一次，而且会真的拿走能力；开关放在我们自己的文件里，上游零冲突。

实测（无头驱动真实点击开关）：默认 14 项 → 打开后 19 项，5 个入口全部回来，`aria-checked: false → true` 且侧栏实时响应。

### 新增：P3 首个自有能力 —— 决策留痕 skill 插件

`plugins/zcagent-decision-log/`（`kind: skill`）。刻意**不自己实现文件写入**：插件 API 没有"当前专家工作区"入口，硬写会重复 harness 的能力并随其演进而漂移；改为教专家用它已有的文件工具，把决定按固定小节写进 `decisions/YYYY-MM.md`。

管线已验证：`octop plugin install` → 运行时 `loaded: True` → 技能同步进 `.octop/skills/decision-log/` → `octop skills list` 显示 `enabled=True`。

### 变更：更新检查默认关闭

`/admin/advanced?tab=updates` 之前会去查公共 PyPI 上的 `octop` 包，于是我们自己的部署会弹"新版本已就绪 → 立即更新"，点下去装的是别人的构建。现在默认不检查：`OCTOP_UPDATE_CHECK=1` 显式打开，或配置了 `OCTOP_UPDATE_INDEX_URL`（指向自家内网索引）时自动打开。实测 `/api/update/status` 返回 `has_update:false`、`latest_version:null`、无 error。

### 变更：发布产物名与桌面流水线

- 产物前缀 `Octop-` → `zcagent-`（`desktop/portable/_common.sh` 等 51 个文件同步）。这条必须做：NSIS 的产物名来自 `productName`（已是 `zcagent`），而 workflow 的上传 glob 还写着 `Octop-desktop-*`，配上 `if-no-files-found: error` 会让发版作业直接失败。token 规则为保护 `X-Octop-*` 跳过了后接连字符的情况，所以单列一条字面量规则。
- `octop-desktop.yml` 裁剪为只构建 `windows-amd64`（保留其余平台定义，放开是一行改动）；内嵌的 python 平台筛选块已做语法校验。

### 版本

`pyproject.toml` 与 `src/octop/__init__.py` 升到 `1.0.2b6+z01`。实测该 local version 对打包无害：`stamp_version.four_part_version("1.0.2b6+z01")` → `1.0.2.0`，显示串保留后缀。

### 仓库与流水线

- 远端：`origin = github.com/openclawzhangchong/zcagent`，`upstream = TencentCloud/Octop`。
- 分支：`upstream-main`（零改动跟踪）、`product/main`（产品分支）。
- 上游 7 条 tag 触发流水线（release / docker-publish / octop-desktop / fnos-build-fpk / auto-tag / sync-main-to-develop / anti-spam）在仓库设置中禁用，保留 CI 与 CodeQL。

### 验证

| 检查 | 结果 |
|---|---|
| `rebrand.py --check` | 2347 个文件已清扫，无旧品牌残留 |
| 后端：28 个被清扫改动的测试文件 + `tests/unit/i18n` | 通过，除 `test_system_archive::test_restore_repairs_old_physical_schema_with_current_watermark` |
| 上述例外做基线对照 | 未改名的干净树上**同样失败** → 上游既有问题，非本次改动引入 |
| 前端 vitest 全量（改名后，空闲） | 8 / 6 个用例失败 |
| 前端 vitest 全量（干净上游基线，两次） | 8 / 8 个用例失败 |
| 结论 | 改名与改色造成的确定性失败 **0**；该套件在本机 ±2 抖动（`pool: "threads"` + testing-library 1000ms 异步超时），CPU 争用时会升到 9–10 |
| 前端 ESLint（`npx eslint .`） | 0 error / 68 warning（上游树上原有 2 error，已修；warning 不阻塞，`eslint .` 无 `--max-warnings`） |
| 前端 Prettier（`prettier --check .`） | 本地与 CI 均通过；CI 只报 9 个文件，本地一度报 1082 个 —— 差额是 `core.autocrlf` 的换行噪声，已由 `.gitattributes` 消除 |
| 前端 `npm run build`（= `tsc -b` + vite + PWA） | 通过 |
| 标识符未被误改 | `X-Octop-*`、`prefixCls="octop"`、`OCTOP_HOME`、`octop-harness` 依赖名、i18n key 均已核对原样 |
| 运行期冒烟 | 登录 → 建专家 → 真实对话（OpenAI 兼容 provider）→ 工具调用写文件并落盘核对，全通过 |
| 更新链路端到端 | 用本仓库构建的 `octop-1.0.2b6+z01-py3-none-any.whl` 装进**全新 venv**、以**全新数据目录** `octop init` 起服务：登录成功、侧栏显示 `v1.0.2b6+z01`、`is_editable:false`；在真实 devpi 私有 index 放一个更高版本后点「检查更新」→ `has_update:true`、`latest_version:1.0.2b6+z9`、`source:127.0.0.1`。源码 editable 安装则正确拒绝自更新并提示 `git pull` |
| 本轮新增测试 | `tests/unit/api/test_branding_router.py` 20 例（含 `logo_url` 白名单与 300KB 上限）；`test_self_update.py` 增加 devpi 形状、`+z` 判序、默认关闭守卫共 12 例 |

### 新增：P4 追版度量

- `.github/workflows/frontend.yml`：lint + prettier check + `tsc -b`/build + vitest 汇总。**vitest 暂不阻塞**——上游 CI 从不跑它，干净上游树在本机已红 6–10 个，先让 CI 建立自己的基线再转阻塞。
- `.github/workflows/sync-attempt.yml` + `scripts/sync_check.py`：每周一试 merge 最新 stable tag（不提交不推送），报告"上游领先多少 / 哪些文件冲突 / 是否踩了我们的规矩"，冲突或违规时退出码非零。含两条守卫：不许私自新增编号 migration；工作树有未提交改动时拒绝试 merge（回滚用 `reset --hard`）。
- `scripts/classify_owned.py`：用真实管线量冲突面积——在基线的临时 worktree 里跑一次 `--apply`，再逐文件比对 git 存储的内容，得出 `brand/owned-files.txt`。首轮读数是 285 个改动文件 / 260 个纯生成物 / 25 个手工改动；格式化进入管线后重新测量为 334 / 282 / 25 + 27 个新增，见下一节。先前按"是否落在清扫 glob 内"分类会把 P1b 的运行时代码误判成生成物，故改用内容比对。
- 验证：用从基线分叉、在同一位置插入不同行的合成分支实测 `sync_check.py`，正确报出 1 个冲突、退出码非零、且工作树完整还原。真实 upstream 试 merge 因本机 `github.com:443` 中断未跑成，留给首次 CI。

### 首轮 CI：门禁确实会红，红的是我们

`Frontend` workflow 上线后第一次跑就给出三个可核对的事实：

- **ESLint 红 2 个错误，且都在我们从未改过的文件里**（`chatStore.ts:1217` 多余的 `Boolean()`、`constants.test.ts:5` 未使用的 import）。用 `git diff --name-only upstream-main..HEAD` 证明这两处与 fork 无关 —— 上游前端**不过自己的 ESLint**，因为它的 CI 里没有 Node job。已修，不靠 disable：门禁必须能为我们关心的原因失败。
- **Prettier 红 9 个文件，全部由我们造成**：逐个用 `prettier --stdin-filepath` 比对基线版本与当前版本，基线 9 个文件里 6 个本来是干净的。根因是替换品牌词会改变字符串长度，于是 prettier 要求重新换行；`#3D5A80` 写成大写十六进制也被判为未格式化。
- **因此格式化进了 `--apply` 管线**（`format_written()`）：只对本工具刚重写的 dashboard 文件跑 prettier，且当它跑在临时 worktree 里时借用主检出那份 prettier，保证两边字节一致。若把这一步写成"记得手工跑 `npm run format`"，第一次追版之后就会静默变红，而没人能追溯到原因。
- 新增 `.gitattributes` 为前端文本固定 `eol=lf`。仓库里**没有任何文本 blob 带 CRLF**，所以这行对 Linux/CI 零影响；它只解决 Windows 检出（`core.autocrlf=true`）下 `format:check` 把 1000+ 个干净文件报成脏的假阳性——那是纯换行差异，不是代码问题。

### 变更：冲突面积重新测量（334 / 282 / 25 / 27）

`scripts/classify_owned.py` 原先硬编码了一个已不存在的仓库路径、用 `read_bytes()` 逐字节比对、并且把"我们新增的文件"和"上游也拥有的文件"混在一张表里。修正后：从所在检出自动取仓库根、解释器与基线 revision，比对**git 存储的内容**（忽略本机换行），并区分三类：

| 类别 | 数量 | 合并时怎么处理 |
|---|---|---|
| 相对基线改动的文件 | 334 | — |
| 与 `--apply` 再生成结果一致 | **282** | 机械处理：取上游，重跑 `--apply` |
| 承载手工改动（上游也拥有该文件） | **25** | 真实冲突面，逐条列在 `brand/owned-files.txt` |
| 我们新增（无上游 counterpart） | **27** | 不会撞，除非上游以后新增同路径文件 |

先前的"25"结果碰巧还对，但理由是错的：换行差异会让分类器把约 230 个生成物误判成手工改动，格式化一进管线就会立刻暴露。

> 这张表是**当时**的快照。z05 之后重测为 **374 = 296 生成 + 33 手工 + 45 新增**，见本文最上方 z05 一节。

### 已知问题

- **凭据存储：决定不改为强制加密（2026-10-09）。** Agent 可在工作区 `.octop/.env` 写入凭据，曾提议强制走 `connectors` 的加密 `secrets`，已否决：普通用户接自己的 MCP 就是靠直接编辑这个文件，加密会把主路径变成工单。这是权衡后的接受项，不要重做；详见 `docs/HANDOVER.md` 第 6 节。保留的底线只有一条：不许在任何文案或提示词里声称"密钥不落盘"。
- Windows 下 `工作台 / 终端` 不可用（上游按设计禁用，见 `src/octop/api/routers/terminal.py`）。
- 系统提示词里的 OS / 工作区路径在 Windows 上会被模型复述成 Linux 风格路径，属上游待修。
- **技能遵循度不足（模型侧，非接线问题）**：接好的 `decision-log` 技能在实测中没被走通——第一轮把决定写进了 `MEMORY.md`；第二轮显式点名 `decision-log`，模型却回"未命中 `totorosir-workbuddy-checkin`"（技能名串台）。当前模型是 flash 档，说明"装了技能"不等于"会用技能"，交付时要按模型档位评估。
- **模型会写错日期**：那次写入 `MEMORY.md` 的记录把日期写成 `2026-07-11`，实际是 2026-10-10。对"决策审计留痕"这类能力这是致命缺陷，已在技能里加了"日期必须取自运行环境"的硬约束，但根因在 harness 未把当前日期作为强约束注入。
- 侧栏「云端协同 BETA」角标仍用 `#ff4d4f`（`src/layouts/Sidebar.tsx:215`），用户头像也仍在上游的玫红配色板里（实测：对话流右侧的头像气泡、左下角用户菜单里的 "Demo Admin" 头像）。这些是语义"提醒"色与头像调色板，不是品牌主色，目前判断不改；要改就得动 `utils/expertColor.ts`，那是每次追版都要复核的文件。
- `octop-mascot-peek.webm`、`octop-mascot-type.webm`、`octop-mascot-tasks.png` 在代码里**无人引用**（前端只用 `.webp`），属上游死资产，仍随构建产物发布，暂未处理。
