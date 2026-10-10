# 智策 / zcagent · Windows 离线交付说明

给实施人员的一页说明。拷到目标机器的U盘/内网共享里，配合本目录的两个安装包使用。

## 包里有什么

| 文件 | 用途 |
|---|---|
| `zcagent-desktop-windows-amd64-<版本>.exe` | 安装版：开始菜单图标 + 桌面窗口 |
| `zcagent-portable-windows-amd64-<版本>.zip` | 便携版：解压即用，自带 Python 运行时 |
| `SHA256SUMS.txt` | 两个包的校验值（由打包命令从 GitHub Release 的 digest 生成） |
| `guide.md` | 本页 |

## 第一步：先校验，再运行

在目标机器上（PowerShell，切到本目录）：

```powershell
Get-FileHash .\zcagent-desktop-windows-amd64-<版本>.exe -Algorithm SHA256
```

把结果与 `SHA256SUMS.txt` 对照，**不一致就不要装**（多半是传输被截断——本项目实测遇到过
`gh release download` 报告成功但只落了 37% 字节的情况）。

## 系统要求

- Windows 10 1903 及以上，x64（实测环境 Windows 10 10.0.19045）
- 磁盘：安装版占用约 199 MB，便携版解压后约 658 MB；运行数据另算
- 安装版需要 **Microsoft Edge WebView2 运行时**（较新的 Win10/Win11 已内置，缺失时安装器会提示）
- 便携版**不需要**安装 Python 或 Node
- 网络：只需要能访问你配置的模型 API；软件本身不外联

## 安装版

1. 双击 `.exe`。若 SmartScreen 拦一道蓝窗：点「更多信息」→「仍要运行」（安装包未做代码签名，
   上游同样未签名发布；内网复制过去的文件通常不带网络标记，不弹）。
2. 按向导装到当前用户目录，**不需要管理员权限**。
3. 从开始菜单启动「智策」。它会在本机起服务（默认 `127.0.0.1:8088`）并打开窗口。
4. 首次启动进入初始化向导：验证口令 → 数据库（默认本机 SQLite）→ 建管理员 → 配模型（可跳过）。
   一次性口令在服务器控制台黄框里，也写在 `%USERPROFILE%\octop-login.txt`。

静默安装（批量部署）：

```powershell
.\zcagent-desktop-windows-amd64-<版本>.exe /S /D=C:\zcagent
```

## 便携版

1. 解压到任意目录（路径含空格也可以）。
2. 双击 `start.bat`。换端口或数据目录：`start.bat --port 8090 --home D:\zcagent-data`。
3. 浏览器打开 `http://127.0.0.1:8088`，走同一套初始化向导。

## 数据、迁移与卸载

- 数据默认在 `%USERPROFILE%\.octop`（便携版为解压目录下的 `.\data`）：账号、专家、对话与记忆、
  技能、通道与模型配置都在里面。
- 迁移 = 拷走整个数据目录。
- 卸载：安装版从「应用和功能」卸载，便携版直接删目录；两者都不动数据，重装即可继续用。
- **一条要知道的残留**：桌面客户端首次运行会把绿色包解到 `~\.octop\portable\`（约 712 MB），
  卸载**不会**删除它（它位于数据目录内，卸载器按设计不动数据）。要彻底清理，卸载后手动删除
  `~\.octop\portable`。

## 更新

- 应用内：「应用设置 → 应用更新 → 检查更新」。**默认不检查公共源**，所以刚装好时这里不会提示新版本，
  这是刻意的——避免把别人的构建装进内网机器。
- 内网自建索引（devpi 等）时设这两个变量后才会启用，并且安装候选只来自该索引：

```powershell
set OCTOP_UPDATE_JSON_URL=http://<内网索引>/<user>/<index>/{name}/
set OCTOP_UPDATE_SIMPLE_URL=http://<内网索引>/<user>/<index>/+simple/
```

- 也可以直接换包：下载新版本，覆盖安装即可，数据保留。

## 已知限制

- **`工作台 / 终端` 在 Windows 上不可用**（上游按设计依赖 `pty`，仅 Linux/macOS 提供）。
- 只出 Windows x64 包；macOS / Linux / ARM64 未交付。
- 模型能力取决于接入的模型档位；技能是否被严格遵循与模型档位相关，交付时按实际模型评估。
- 专家可在工作区 `.octop\.env` 写明文凭据（用于接自己的 MCP/外部服务）。这是产品权衡后的选择，
  因此**不要向客户承诺"密钥不落盘"**；对合规要求高的客户单独评估。
