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
| 从 exe 里抠出内嵌图标 | `.ico` 是构建时生成的，仓库里没有，`git diff` 看不出图标没换 |

产物落在 `.zc-verify/reports/<版本>.json` 与同目录的截图；失败信息点名的是**断言**，不是阶段。

前置：项目 venv（已含 playwright、Pillow）、装有 Edge 的 Windows、`GH_TOKEN`
（不设也能跑，但 api.github.com 的资产下载会慢），以及 z08 起需要 `ZC_VERIFY_PASSWORD`
——向量模型列表与「登录进去看弹窗」两段都要真的认证。口令是装机时你自己设的管理员口令，
**不要写进仓库**。
下载走 `github.com` 与 `api.github.com` 交替——本机前者快但常连不通，后者稳但慢。

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

## 其它可复用的工具（不在本目录）

| 命令 | 用途 |
|---|---|
| `python scripts/rebrand.py --check` | 品牌残留与"未被清扫覆盖"的守卫 |
| `python scripts/classify_owned.py` | 重测冲突面积，重写 `brand/owned-files.txt` |
| `python scripts/sync_check.py` | 追版前试合并，看有没有可合的 stable tag |
| `python site/download/build.py --from-github` | 用 Release API 刷新下载页与 README 的产物表 |
| `python site/offline-kit/make_kit.py` | 生成内网离线交付包（含 SHA256SUMS 与运维说明） |
