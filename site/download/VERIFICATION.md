# 发布记录（release record）

智策 Windows 客户端的实测记录。每次改动产物时追加一节，不覆盖历史。

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
