# 客户端下载页

智策 Windows 客户端的对外下载页。静态站点，无构建工具链依赖，只用标准库。

## 目录

```
site/download/
├── release.json      # 唯一的数字来源：版本、tag、每个产物的名字/字节数/SHA256/链接
├── build.py          # 渲染 dist/，并能直接从 GitHub Release API 刷新 release.json
├── src/              # 模板与静态资源（index.html 里是 {{token}}）
└── dist/             # 生成物，也是发布出去的站点（签入仓库，便于直接托管）
```

## 发版后更新这一页

```bash
# 1) 从 Release API 取权威数字（名字、大小、digest、下载地址），再渲染
GH_TOKEN=$(gh auth token) python site/download/build.py --from-github

# 2) 确认 dist 与模板+数据一致（可用于 CI 断言）
python site/download/build.py --check
```

`--from-github` 按 `release.json` 里的 `tag` 取那一版发布，不猜"最新"。它拿不到 `digest`
就直接失败退出——**没有校验值的下载页不如没有**，所以这里不允许静默降级。

发新 tag 时改 `release.json` 的 `version` / `tag` / `date` / `release_url`，并把上一版挪进
`previous`（含废弃原因）。

## 为什么数字不直接写在 HTML 里

这页存在的意义就是"版本、大小、SHA256 和你点下去的那个文件一致"。手抄数字是它唯一会撒
谎的方式，所以：数字只有一份（`release.json`），且那份可以由命令从 GitHub 重新生成。模板
里出现 `release.json` 没提供的 token 时，`build.py` 直接报错而不是留个空位。

## 页面内容边界

只写**已实测**的事：便携版跑通过首启向导（解压约 658 MiB、内嵌 CPython、`start.bat` 起服务）；
安装版需要 WebView2 这条来自 NSIS 脚本 `!insertmacro wails.webview2runtime`，未在新机器上实跑。
新增声明前先补实测，否则宁可写进「已知限制」。
