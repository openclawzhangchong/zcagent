# 官网（landing）

智策的对外官网。静态站点，无构建工具链依赖，只用标准库；Cloudflare Pages 直接把
`dist/` 当成产物目录即可。

```
site/landing/
├── build.py          渲染 dist/，并能直接从 GitHub Release API 刷新数字
├── site.json         这个站点自己的部署地址（与发布产物无关）
├── shot_screens.py   把 screens/ 渲染成官网用的界面图（开发期工具）
├── src/              模板与静态资源（index.html 里是 {{token}}）
├── screens/          静态演示界面 —— 官网截图的来源
└── dist/             生成物 = 发布的站点。不签入（仓库根 .gitignore 忽略 dist/）
```

## 日常操作

```bash
# 构建（改完模板或数据后跑这个）
python site/landing/build.py

# 本地预览
python -m http.server 8788 --directory site/landing/dist

# 断言 dist/ 与模板和数据一致（CI 用）
python site/landing/build.py --check

# 发版后：先从 Release API 取权威数字，再一起构建
GH_TOKEN=$(gh auth token) python site/landing/build.py --from-github

# 改了 screens/ 里的界面之后重出图
python site/landing/shot_screens.py
```

## 数字只有一个来源

版本号、字节数、SHA256、下载地址全部来自 `site/download/release.json`，品牌色来自
`brand/brand.yaml`，都没有手抄进模板。模板里出现任何一份数据都提供不了的 `{{token}}` 时，
`build.py` 直接报错而不是留个空位。

`--from-github` 按 `release.json` 里钉住的 tag 取那一版发布，不猜"最新"。它拿不到 `digest`
就失败退出——**没有校验值的下载页不如没有**，所以这里不允许静默降级。

`--check` 把 `dist/` 跟一份全新渲染逐字节对比。它不跟输入比：那样只会恒真，
等于把绿灯接在没有东西的线上。

## screens/：官网截图是怎么来的

`screens/*.html` 是**手工维护的控制台界面复刻**，不是实机截图。

为什么不做实机截图：实机里是真实账号、真实对话历史和内部记录，截出来的东西没法对外发
（`Demo Admin`、失败的 skill 调用、未定的产品决策……），而且改一句文案要起服务、登录、
跑一遍。复刻版内容完全可控，改文案就是改一个 HTML，再跑一次 `shot_screens.py`。

保真度怎么办：`screens/screen.css` 里的色值不是凭感觉挑的。注意
`dashboard/src/styles/theme-vars.css` 里默认品牌色**仍然是上游的玫瑰红**——钢蓝只在运行时
OEM 层推上去之后才成立。所以 token 是从运行中的实例解析出来的（`--fn-color-brand`
实测为 `#3d5a80`），不是从样式表抄的。改品牌时重新解析一次。

侧栏图标取自品牌管线产出的 `dashboard/public/pwa-512.png`，不手工复制——手工副本会漂移，
桌面启动屏挂上游章鱼就是这么来的。

## 部署到 Cloudflare Pages

- 构建命令：`python site/landing/build.py`
- 输出目录：`site/landing/dist`
- 环境变量：Python 3.12；`Pillow` 可选（缺了会跳过 `assets/og-cover.png`，其余不受影响）
- `_headers` 已配好缓存策略、安全头与 CSP；`dist/` 里不产生内联脚本与内联样式

接了自定义域名之后，把 `site.json` 的 `site_url` 改掉重新构建——canonical、og:url、
`sitemap.xml`、`robots.txt` 都从它来。

## 内容边界

只写**已实测**的事，实测记录在 `../download/VERIFICATION.md`。当前页面上刻意**没有**的东西：

- **Docker 部署**：仓库里有 compose 与镜像定义，但那是上游的，从没为智策构建并验收过。
- **pip 安装**：版本号带 PEP 440 的 local 段（`+zNN`），这类包不能上公共 PyPI。
- **一键安装脚本的远程 URL**：上游把 `install.sh` 放在自己的 COS 上，那条命令装的是上游
  Octop，不是智策。官网只给了「从源码安装」。
- **macOS / Linux / ARM64 客户端**：构建定义在仓库里，没逐平台走过安装验收。

宁可把这些写成「尚未验收」，也不要留一个点下去兑现不了的承诺。