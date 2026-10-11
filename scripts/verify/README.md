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
| 从 exe 里抠出内嵌图标 | `.ico` 是构建时生成的，仓库里没有，`git diff` 看不出图标没换 |

产物落在 `.zc-verify/reports/<版本>.json` 与同目录的截图；失败信息点名的是**断言**，不是阶段。

前置：项目 venv（已含 playwright、Pillow）、装有 Edge 的 Windows、以及 `GH_TOKEN`
（不设也能跑，但 api.github.com 的资产下载会慢）。下载走 `github.com` 与
`api.github.com` 交替——本机前者快但常连不通，后者稳但慢。

## 其它可复用的工具（不在本目录）

| 命令 | 用途 |
|---|---|
| `python scripts/rebrand.py --check` | 品牌残留与"未被清扫覆盖"的守卫 |
| `python scripts/classify_owned.py` | 重测冲突面积，重写 `brand/owned-files.txt` |
| `python scripts/sync_check.py` | 追版前试合并，看有没有可合的 stable tag |
| `python site/download/build.py --from-github` | 用 Release API 刷新下载页与 README 的产物表 |
| `python site/offline-kit/make_kit.py` | 生成内网离线交付包（含 SHA256SUMS 与运维说明） |
