# 发布记录（release record）

智策 Windows 客户端的实测记录。每次改动产物时追加一节，不覆盖历史。

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
