# 验收脚本（verification tools）

这里放**可以反复跑**的验收工具。每次发版不要再另写一份脚本——历史上 `verify-z04.py`、
`verify-client.py`、`fetch-z06.py`、`verify-z06.py` 就是同一件事抄了四遍，
差别只有版本号，而真正抓出产物的那些断言反而在抄写中走样了。

## client_release.py —— 装完到底对不对

一条命令回答"Release 页上那个产物，装到这台机器上是不是真的对"。

```bash
# 完整链路：解析 Release → 下载并校验 → 静默安装 → 启动 → 断言
.venv/Scripts/python.exe scripts/verify/client_release.py --version 1.0.2b6+z07

# 只下载并校验字节与哈希（不出网就别往下走）
.venv/Scripts/python.exe scripts/verify/client_release.py --version 1.0.2b6+z07 --stage fetch

# 已经装好了，只跑断言（会复用现有安装，不重装）
.venv/Scripts/python.exe scripts/verify/client_release.py --version 1.0.2b6+z07 --stage verify
```

它检查的东西，每一项都对应这个产品真实出过的缺陷：

| 断言 | 为什么在这 |
|---|---|
| 下载字节数与 SHA256 必须等于 Release 的 `digest` | `gh release download` 曾对 37% 完整的文件返回成功 |
| 启动后 `~/.octop/portable` 的版本必须等于目标版本 | z02–z04 的比较器丢掉 `+local`，新客户端永远跑第一次解压的旧包 |
| 服务的入口 chunk 必须含各版本引入的标记串 | z03 的中文修复确实在产物里，却因为上一条到不了用户手上 |
| 用 `navigator.language=en-US` + 空 localStorage 渲染，登录页必须中文 | WebView2 在中文 Windows 上报 en-US，界面开成了英文 |
| 从 z06 起：登录页要点名已有账号，「忘记密码」必须是表单而不是 shell 命令 | 装到已有数据的机器上，用户既不知道密码也打不出终端 |
| 从 z08 起：接口返回的默认向量模型 ≤4、展开后 ≤20，且每条必须带一句话优缺点 | `all_onnx=true` 曾把 fastembed 全部 41 个模型（含 CLIP 塔）直接倒进知识库设置页 |
| 从 z08 起：能力检查里必须带 `prefetch_enabled` / `prefetch_state` | 后台下载是"看不见的功能"，不在接口里露出来就没人知道它到底开没开 |
| 从 z08 起：**真的登录进去**（含拖过滑块验证码），侧边栏 logo 下方有短版本号；知识库开关是开着的话，新建弹窗的名称/描述必须已填好中文默认值 | 登录能不能走通、版本号显示成什么，都只有在装好的机器上才看得见；表单默认值在服务出来的 `zh` 语言分片里证明 |
| 从 z09 起：标着"已下载"的向量模型，必须让装好的客户端**真的加载并 embed 一次** | z08 的镜像下载写进了 huggingface_hub 寻不到址的目录，94 MB 正确权重摆在机器上而接口回"Could not load model"；只看下载成不成功永远发现不了 |
| 从 z10 起：装好的 `~/.octop/portable/node` 必须能 `node -v` / `npm -v`，`VERSION.txt` 要有 `node=`，`start.bat` 要把 node 前置进 PATH，且**用装好的 runtime 跑产品自己的检测代码**必须解析到包内 npm | 连接器 CLI 是从 npm 装的、本身就是 Node 程序；只看文件在不在证明不了"用户点得到连接器" |
| 从 exe 里抠出内嵌图标 | `.ico` 是构建时生成的，仓库里没有，`git diff` 看不出图标没换 |

`stage_bundled_node` 第 4 步必须用 `site.addsitedir(packages)`，不能 `sys.path.insert`——
便携包里的 pywin32 靠 `packages/` 下的 `.pth` 生效，`insert` 不处理 `.pth`，
报出来的会是 `ModuleNotFoundError: No module named 'pywintypes'`，看着像产物坏了其实是探针错了
（这正是 `launch.py` 存在的理由）。

任何一段失败，**已经通过的阶段仍会写进报告**（`_bail()`）：transcript 是要贴进
`site/download/VERIFICATION.md` 的证据，为一个 401 赔掉前面全部结果不合理。

产物落在 `.zc-verify/reports/<版本>.json` 与同目录的截图；失败信息点名的是**断言**，不是阶段。

前置：项目 venv（已含 playwright、Pillow）、装有 Edge 的 Windows、`GH_TOKEN`
（不设也能跑，但 api.github.com 的资产下载会慢），以及 z08 起需要 `ZC_VERIFY_PASSWORD`
——向量模型列表与「登录进去看弹窗」两段都要真的认证。口令是装机时你自己设的管理员口令，
**不要写进仓库**。
下载走 `github.com` 与 `api.github.com` 交替——本机前者快但常连不通，后者稳但慢。
z10 这一轮 `github.com:443` 连续几十分钟拒绝连接，改用资产端点才下下来：
`curl -H "Authorization: Bearer $GH_TOKEN" -H "Accept: application/octet-stream"
https://api.github.com/repos/…/releases/assets/<id>`（它重定向到 `objects.githubusercontent.com`，
绕开挂掉的 `github.com`）。**每条 curl 必须带 `--max-time` 与 `--speed-limit/--speed-time`**：
z10 第一次下载在 130 MB 处停滞，因为没有超时的 curl 就那样挂着，看起来像循环还在跑。

## prefetch_watch.py —— 空闲预下载到底有没有跑

`client_release.py` 在服务起来几秒内就跑完断言，而预下载故意等 90 秒才动，所以它需要自己的一次运行。
难点是**别把"什么都没发生"读成两种意思**：机器上已经有模型时，正确行为就是什么都不做，而"功能坏了"
看起来一模一样。于是这个脚本从不碰共享的 `~/.octop`：它用**装好的运行时刻**配一个临时
`OCTOP_HOME` 和一个备用端口启动，空缓存里落下的任何字节都只能是这一次的运行干的。

```bash
# 两趟：开关打开必须下载并写 done；设成 0 必须一个字节都不落、一行状态都不写
.venv/Scripts/python.exe scripts/verify/prefetch_watch.py

# 只跑其中一趟 / 用本仓库 venv 而不是装机产物快速自检
.venv/Scripts/python.exe scripts/verify/prefetch_watch.py --only off
.venv/Scripts/python.exe scripts/verify/prefetch_watch.py --runtime --home D:/tmp/prefetch
```

断言的东西：ONNX 权重 >90 MB、`knowledge_onnx_prefetch=done`、尝试次数有增加、磁盘增长单调、
**首批字节出现在启动约 90 秒之后**（这一条把"空闲预下载"和"开机就下载"区分开），
以及开关关闭时两趟都为空。报告写在 `<scratch>/prefetch-report.json`，旁边是两个服务各自的日志。

## layout_probe.py —— 桌面宽度下到底有几栏、切 pane 会丢什么

`PLAN-z10.md` M1 要把默认布局从三栏（导航 + 会话栏 + 内容）翻成两栏。两种布局早就存在，
差别只在 `octop:layout-mode` 的默认值，所以"翻默认值对不对"只能靠**真实渲染**回答，读代码答不了：
两栏下会话列表是左栏的下半部 pane，而 `Sidebar.tsx` 的
`hidden={isRailCollapsed || minimalPane !== "records"}` 意味着切到设置 pane 时它可能整个消失。

内置浏览器只有 465px 宽，看不到桌面布局；这个脚本因此自己起一个 scratch 控制面
（独立 `OCTOP_HOME`、备用端口、走完向导），在 1280×800 下逐个布局状态量：可见列数、
会话栏属于哪一列、pane 切换后还剩什么、左栏可见项数。

```bash
# 走完向导（默认塞一条假 provider 让专家真的 running，会话栏才有内容可量）
.venv/Scripts/python.exe scripts/verify/layout_probe.py --python .venv/Scripts/python.exe --port 8097

# 复现"新手跳过模型步"的死路：专家停在 failed，会话栏在任何布局下都是空的
.venv/Scripts/python.exe scripts/verify/layout_probe.py --no-model

# z10 M1 的验收门：切到设置视图后会话列表必须还在。今天退出码 1，M1 做完必须变 0
.venv/Scripts/python.exe scripts/verify/layout_probe.py --expect-fixed
```

不带 `--expect-fixed` 的那趟只是**量现状**（把"设置 pane 会藏掉 records"当作期望值，退出码 0），
别把它读成"已经修好"。

专家没到 `running` 时**所有布局都量出空栏**，那种 verdict 没有意义，所以脚本会先等它起来
（`agentError.ts` 判的是 `state === "running"`），起不来就直接失败退出。
假 provider 能骗过就绪判定，是因为创建 provider 不做任何探测、`iter_usable_rows` 只看
`enabled + base_url + api_key + 至少一个 chat 模型`——顺带说明：**首启行事历第 1 步的绿灯
不代表模型能用**（`PLAN-z10.md` §1.8 第 2 条）。

除了量静态布局，它还**真的点两个控件**（`[4/5]`）：点「展开对话历史」后必须同时满足
rail 可见 + 导航栏折叠（导航宽度通过栏内的 `nav-new-chat` 按钮量，展开 ~192px / 折叠 40px），
点「新建对话」后必须落在 `/chat/<agent>`。这两条是 2026-10-12 两项改动的回归门。

> 选导航栏元素**不要**用 `[class*="sidebar" i]`：CSS Modules 会给侧栏每个类都生成
> `Sidebar-module__*`，大小写不敏感的匹配命中的是 DOM 里最先出现的那个类，而不是那一列——
> 这个坑真实地把 `railInNav` 和 `navItems` 量成了 0。正确做法是从内容列
> （`[class*="page-container"]`）往上找**第一个同时包含导航按钮、但按钮不在它自己子树里**的祖先，
> 那个祖先才是并排列的父级。

产物：`<out>/report.json` 与 `<out>/shots/{classic,minimal-records,minimal-settings}.png`，
默认落在已被 gitignore 的 `.zc-verify/layout/`。

## fetch_asset.py —— 大产物在这台机器上怎么下得动

本机到 GitHub 资产主机是**每连接限速**（实测单连接 ~42 KB/s，同时开第二条各自还有 ~50 KB/s），
所以 234 MB 的便携包用一条 curl 要 25 分钟。这个脚本把剩余字节切成 N 段并发 `Range:` 拉，
z10 实测 10 段 → 约 7 分钟。

```bash
.venv/Scripts/python.exe scripts/verify/fetch_asset.py \
  --out .zc-verify/zcagent-portable-windows-amd64-1.0.2b6+z10.zip \
  --asset-id 635744912 --bytes 233968336 \
  --sha 1aa3f015c5da16e52a339e82ce8b3f20dc8a11471116cc5f08c846460ebff8d4
```

`--asset-id` 走 `api.github.com`（这台机器上 `github.com:443` 经常连不通，API 主机是通的）。
已有的半截文件保留作前缀，只补下尾部；拼完必须**同时**核对字节数与 Release 里那条 SHA256——
`gh release download` 曾对 37% 完整的文件返回成功。

两个坑脚本里都判了：服务器若回 `200` 而不是 `206`，说明它忽略了 `Range`，
把响应体追加进去会静默毁掉那一段；以及不带 `--max-time` 的 curl 在流停滞时会**看起来还在下**，
实际挂死（z10 这一轮就这么白等了 4 分钟，是文件大小没变才暴露的）。

## 其它可复用的工具（不在本目录）

| 命令 | 用途 |
|---|---|
| `python scripts/rebrand.py --check` | 品牌残留与"未被清扫覆盖"的守卫 |
| `python scripts/classify_owned.py` | 重测冲突面积，重写 `brand/owned-files.txt` |
| `python scripts/sync_check.py` | 追版前试合并，看有没有可合的 stable tag |
| `python site/download/build.py --from-github` | 用 Release API 刷新下载页与 README 的产物表 |
| `python site/offline-kit/make_kit.py` | 生成内网离线交付包（含 SHA256SUMS 与运维说明） |
