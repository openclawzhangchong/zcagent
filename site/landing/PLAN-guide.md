# 官网 /guide 文档站方案

目标：在 `https://zcagent.jiuyeke.cn/guide` 落一个**面向最终用户的中文指南**，
覆盖面与信息架构对标 `https://docs.octop.cloud/guide/`，但内容与截图全部是我们自己的。

状态：方案（未开工）。执行前请先读 §1 的来源边界——它决定了这件事怎么做才是合法的，
也决定了为什么"照抄改名"无论如何都要被打回去。

---

## 1. 来源边界（先说清楚，避免白干）

**不做**：把 `docs.octop.cloud` 的正文逐句搬过来、只把 octop 换成 zcagent。
那份站点文案是对方独立撰写的作品，替换品牌词不改变"复制"的性质。

**做**：三样合法且质量更高的原料——

| 原料 | 来源 | 许可/依据 |
|---|---|---|
| 上游技术文档正文 | 本仓库 `docs/*.md`（随 fork 一起带过来的上游文件，仓库根 `LICENSE` = MIT） | MIT 允许再分发与改编；保留版权声明即可 |
| 产品事实 | 代码与接口本身：`src/octop/**`、`dashboard/src/**`、`GET /api/*` 实测返回 | 我们自己的分支 |
| 截图 | `site/landing/screens/*.html` → `shot_screens.py` 渲染的静态复刻屏 | 我们自己画的，不含真实账号与真实对话 |

参照对象只取**信息架构**（有哪些章节、什么顺序、读者是谁）——章节清单属于事实性安排，
不是受保护的表达。

而且照抄对我们**内容上就是错的**：他们的 guide 里有「在腾讯云中使用」「远程手机」
「从 LightClaw 迁移」「macOS 安装未签名 App」，我们根本没有这些形态；
反过来他们完全没有我们真正要教的东西——**Windows 客户端双击安装、数据在 `~/.octop`、
知识库开箱默认值、本地向量模型与 90 秒空闲预下载、忘记密码自助重置、内网离线交付包**。
所以这份 §4 的目录是按智策重排的，不是他们的目录换个皮。

---

## 2. 站点工程：多页化的真实改动量

`site/landing/build.py` 现在是单页站，注释里写着 `# One page today`。好消息是**多页几乎免费**：

- `copy_static()`（build.py:309）遍历 `SRC.rglob("*")`，凡是 `TEXT_SUFFIXES`（含 `.html`）
  的文件都走 `render()` 做 `{{TOKEN}}` 替换后写到 `DIST` 同名相对路径。
  → 新增 `src/guide/index.html` 会自动产出 `dist/guide/index.html`，Cloudflare Pages 直接把它当 `/guide/` 服务。
- 未知 `{{token}}` 是硬错误，所以模板不可能带着空白发布版本号——这条保护对新页面同样生效。
- `check()`（build.py:447）把 dist 渲进 scratch 目录再逐字节 diff → 新页面自动进门禁。

需要真改的只有 4 处：

1. **sitemap**（build.py:424-431）：现在硬写一条 `<loc>{SITE_URL}/</loc>`。改成从一份页面清单生成，
   至少加 `{SITE_URL}/guide/`。清单就写死在 build.py 顶部 `PAGES = ["", "guide/"]`，
   新增页面时必须同时加它——`--check` 会拦住"页面在但 sitemap 没更新"。
2. **`src/_redirects`**：`/docs` 现在 302 到 GitHub 的 `README_CN.md`。`/guide` 上线后把
   `/docs` 改成指向 `/guide/`（站内文档优先于跳去仓库），并新增 `/guide → /guide/ 301`。
   ⚠️ 这个文件目前是对面那个并行 agent **新建且尚未提交**的（见 §7 协作）。
3. **样式**：`src/styles.css` 是落地页单页样式。文档页需要"侧栏目录 + 正文 + 右侧锚点"三栏布局，
   放 `src/guide/guide.css`，品牌色继续从 `brand/brand.yaml` 走 `{{BRAND_COLOR*}}` token，
   不要硬编码色值（`rebrand.py --check` 会扫残留）。
4. **导航**：`src/index.html` 顶部导航加一条「使用指南」→ `{{SITE_URL}}/guide/`；
   guide 页顶再回链首页。

**不加**：不要引入 MkDocs / VitePress / 任何构建工具链。现在整站是
"标准库 + 一条 `python build.py`"，Cloudflare 直传 `dist/`。加工具链会让 CI、
`--check` 门禁和接手的人全部变复杂，收益只有目录自动生成——那是 20 行 Python 能解决的事。

---

## 3. 页面形态

- URL：`/guide/`（单页长文档 + 左侧固定目录 + 章节锚点），而不是十几个子页面。
  理由：① 目标读者是"装完想跑起来"的人，一次滚动比多次跳转顺；
  ② 单页只有一份模板要维护、sitemap 只有一条、`--check` 简单；
  ③ 后续真要拆子页，`_redirects` 可以把老锚点重定向过去。
- 左侧目录在窄屏折叠成正文顶部的 `<details>`；`prefers-reduced-motion` 下不做滚动动画。
- 右侧 `On this page` 只做当前章节的小标题（纯 CSS + 少量原生 JS，`src/guide/app.js`）。
- 每章顶部一行「适用版本：`{{VERSION}}` · 更新日期：`{{RELEASE_DATE}}`」——
  用 token 注入，绝不手写版本号（手写必然腐烂）。

---

## 4. 章节表（覆盖面对标他们，内容按我们产品重排）

| # | 章节 | 智策要讲的实事 | 原料 | 需要的屏 |
|---|---|---|---|---|
| 1 | 智策是什么 | 装在自己机器上的多用户 AI 助手；数据全在 `~/.octop`；桌面客户端 / 绿色便携包 / 内网离线包三种交付 | `docs/architecture.md`、README.md | 无 |
| 2 | 十分钟装好 | 下载 exe → NSIS 静默装 → 首启向导一次性口令 → 登录进 `/chat` | README 交付表 + `scripts/verify/client_release.py` 实测结论 | `install-wizard.png`（新）|
| 3 | 界面地图 | 侧栏分组（对话/专家/自动化/设置/控制/管理）、版本号在 logo 下方、主题色可切 | `dashboard/src/layouts/sidebarNav.tsx` | 复用 `chat.png` |
| 4 | 配第一个模型 | 管理 → 模型；预设供应商、自定义 OpenAI 兼容端点、测试连接；**没有模型时对话起不来**（首启行事历① ② ③） | `docs/user-guide.md` §四、`dashboard/src/pages/Model*` | `models.png`（新）|
| 5 | 建第一个专家 | 模板市场 → 创建 → 人格/系统提示；工作区文件（SOUL/USER/MEMORY）与 `.env` 明文凭据的真实行为 | `docs/personas.md`、`docs/expert-teams.md` | 复用 `experts.png` |
| 6 | 对话与团队 | 会话、引用、专家协作 | `docs/agent-*.md` | 复用 `chat.png` |
| 7 | 知识库 | 开关 → 向量模型 → 建库 → 传文档 → 对话里引用；**默认向量模型 `BAAI/bge-small-zh-v1.5`（92 MB）+ 每个模型一句话优缺点 + 高级选项里才是全集**；空闲 90 秒后台预下载；**内网/离线路径怎么写**（连不通就静默放弃，最多 3 次） | `src/octop/infra/knowledge/*`、`onnx_catalog.py`、`prefetch.py` | 复用 `knowledge.png` + `kb-models.png`（新）|
| 8 | 技能包与插件 | 安装、启用、权限 | `docs/`（技能相关） | 无 |
| 9 | 通道 | 微信/企微/Discord 等接入与回调；跨端消息路由 | `docs/discord-channel.md`、`docs/connectors-*.md` | 复用 `channels.png` |
| 10 | 连接器与 MCP | 内置应用、MCP server、OAuth 状态 | `docs/connectors-qcc.md`、`acp.md` | 复用 `connectors.png` |
| 11 | 自动化：定时任务与远程执行 | cron 任务、ACP runner、远程桌面。**明确写「工作台/终端在 Windows 不可用（上游按设计依赖 pty）」**——照抄的人会照着点然后以为坏了 | `docs/cli.md`、`docs/bridge.md` | 复用 `tasks.png` |
| 12 | 账号、密码与备份 | 首启向导口令文件 `~/octop-login.txt` 是一次性的；**忘记口令走登录页「忘记密码」自助重置（仅本机回环可用，多账号机器拒绝）**；`~/.octop` 整目录迁移即备份；卸载不动数据、`~/.octop/portable` 需手动清理 | `src/octop/api/routers/local_recovery.py`、`site/offline-kit/guide.md` | `forgot-password.png`（新）|
| 13 | 内网部署 | 绿色包 `start.bat`、离线交付包、自建 devpi 索引的两个环境变量（URL 形状 devpi≠Warehouse）、更新检查默认不查公网 | `CHANGELOG.md`「内网更新源怎么配」、`site/offline-kit/guide.md` | 无 |
| 14 | 配置与环境变量 | `OCTOP_HOME`、`OCTOP_PORT`、`OCTOP_KNOWLEDGE_MODEL_PREFETCH=0`、数据库相关 `OCTOP_DATABASE_*` | `docs/configuration.md` | 无 |
| 15 | CLI 速查 | `octop run` / `octop user passwd` / 诊断类；只收 Windows 上真能跑的那些 | `docs/cli.md` | 无 |
| 16 | 常见问题 | 装完是英文界面（老包）、知识库模型显示"已下载"却加载不了（z08 及之前，z09 修）、模型列表为什么默认只有 3 个、怎么换口令 | VERIFICATION/CHANGELOG 里真出过的问题 | 无 |
| 17 | 版本与已知限制 | 只出 Windows x64；终端 POSIX-only；专家凭据落盘的产品权衡（**不得承诺"密钥不落盘"**） | `CHANGELOG.md`、`docs/HANDOVER.md` | 无 |

写作口径：每章「做什么 → 怎么点（真实路径）→ 会看到什么 → 出错了怎么办」，
步骤里出现的按钮/菜单名必须与 `dashboard/src/locales/zh.json` 一致——
这是能自动核对的，见 §6。

---

## 5. 截图

走现有复刻屏路线，**不要**去截真实运行实例：`shot_screens.py` 的注释写明了理由
（不含真实账号、真实对话内容与内部备注；改一句文案 = 改 HTML + 跑一条命令，无需服务器和登录）。

需要新增 4 屏：`install-wizard` / `models` / `kb-models` / `forgot-password`，
做法与既有 8 屏一致：`screens/<name>.html`（沿用 `screens/screen.css` 的 token）+
把 `<name>` 加进 `shot_screens.py` 的 `PAGES` 列表 + 输出到 `src/assets/screens/<name>.png`（1600×1000、SCALE=2）。
注意：本机内置浏览器视口只有 465px 宽，验证桌面布局要用同源 iframe 撑到 1280px 再判。

---

## 6. 门禁（每条都要能一键跑）

1. `python site/landing/build.py` → `python site/landing/build.py --check`（dist 与模板逐字节一致）。
2. **坏链检查**：`/guide/` 页面内每个 `href`/`src` 必须在 dist 里存在（新增约 25 行校验，写进 build.py 的 check 路径）。
3. **步骤名与 locale 对齐**：脚本抓 `dashboard/src/locales/zh.json` 的 value 集合，
   断言 guide 正文里写成按钮样式的词都在集合内 → 防止界面改名后文档悄悄失真。这条是本方案里最值钱的自动化。
4. `python scripts/rebrand.py --check`：品牌残留（新目录 `src/guide/**` 必须进清扫范围）。
5. 部署后线上核验（不是"上传返回成功"就算）：`curl https://zcagent.jiuyeke.cn/guide/` 取回内容，
   检查标题、章节数、以及页面里出现的版本号 == `site/download/release.json` 的 `version`。

---

## 7. 与并行 agent 的协作（当前真实风险）

同一个检出目录里现在有另一路工作在改 `site/landing/**`：`build.py`、`site.json`、
`src/index.html`、`src/styles.css`、`screens/*` 均为**未提交修改**，
`src/_redirects`、`screens/*.html`、`PLAN-brand-and-links.md` 等为**未跟踪新文件**。
本方案要动的共享文件恰好撞上其中三个：`build.py`（sitemap）、`src/index.html`（导航）、
`src/_redirects`（`/docs` 目标）。

规则：
- 新文件（`src/guide/**`、`screens/guide-*.html`）随我这条线独立提交，零冲突。
- 三个共享文件只做**最小 one-line 修改**，且提交前先 `git status --short site/landing` 确认对面不在写同一文件；
  发现同一文件有未提交改动就先停下协调，不覆盖对方工作、不 `stash`、不 `checkout --`。
- 不用 `git add -A`/`git add .`，逐文件 add。

---

## 8. Cloudflare Pages 事实与命令（复用备忘）

**这些记进 `site/landing/DEPLOY.md`（已有该文件，本节的 token 类信息一律不落跟踪文件）。**

| 项 | 值 |
|---|---|
| 站点 | `https://zcagent.jiuyeke.cn`（`production_branch = main`）|
| 域名归属 | `zcagent.pages.dev` + `zcagent.jiuyeke.cn` 都在项目 domains 里 |
| Cloudflare Account ID | `b945f659e7168126d8c819670695bd9f` |
| Pages 项目名 | `zcagent` |
| 直传产物目录 | `site/landing/dist`（含 `_redirects`、`_headers`、`sitemap.xml`、`install.ps1`）|
| API 令牌 | 只放 `site/landing/.cloudflare.env`（已被 `site/landing/.gitignore:10` 忽略），键名 `CLOUDFLARE_API_TOKEN` |

构建 + 部署（本机 node 不在 PATH 上，必须显式加）：

```bash
cd /d/otp/Octop
PATH="/c/Program Files/nodejs:$PATH" .venv/Scripts/python.exe site/landing/build.py
set -a && . site/landing/.cloudflare.env && set +a
PATH="/c/Program Files/nodejs:$PATH" npx --yes wrangler@4 pages deploy site/landing/dist \
  --project-name zcagent --branch main
```

核验与回滚：

```bash
# 读 API 而不是信上传回显
curl -sS -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/pages/projects/zcagent" | jq .result.production_branch
curl -sSL https://zcagent.jiuyeke.cn/guide/ | head
```

踩过的坑（照抄进 DEPLOY.md，别下次再试）：
- **`npx wrangler` 必须先有 node**：本机 `which node` 是空的，但 `C:\Program Files\nodejs\node.exe` 存在（v24.20.0）。
- Pages 会压缩 HTML：线上字节数与本地 `dist/index.html` 不同（36,145 → 16,867），
  **别用 sha 比在线内容**，比结构标记（title、版本号、摘要串）。
- 部署生效有几十秒延迟：轮询到出现新标记为止，不要 sleep 一次就下结论。
- 直传时带 `--branch main` 才会进 production；不带会变成 preview 别名，线上看不出来。
- 令牌在本次对话里以明文出现过，按已暴露处理：建议轮换一次（只需说一次，之后不再提）。
  轮换后只更新 `site/landing/.cloudflare.env`，不要写进任何 .md / 提交 / 聊天粘贴。

---

## 9. 开工顺序

1. `src/guide/index.html` 骨架 + `guide.css` + 目录/锚点（先空文案，跑通多页与 `--check`）。
2. `build.py`：`PAGES` 清单、sitemap、坏链检查；`src/_redirects` 两条。
3. 按 §4 逐章写正文（1→17），每章写完立刻跑 locale 对齐检查。
4. 4 张新屏（复刻屏 HTML + `shot_screens.py`）。
5. 门禁全跑（§6）+ `rebrand.py --check`。
6. 构建 → 直传 → 线上核验（§8）。
7. 首页导航与 `CHANGELOG.md` 补一条，`docs/HANDOVER.md` 的"官网"段更新。

预估：正文 1–2 天，截图 0.5 天，工程改造与门禁 0.5 天。
第一版可以先只交 §1–§4 + §12–§14（装好、配模型、知识库、账号口令、内网），
那是新用户真会卡住的四段；后面章节按同一骨架补。
