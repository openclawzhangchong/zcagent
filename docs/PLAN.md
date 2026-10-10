# 计划表（P2 / P4 / P5）

> 截至 2026-10-10：**`v1.0.2b6-z1` 已发版**（Windows 安装包 + 便携包挂在 GitHub Release 上）。已定的四个决策：**P2 做换壳+信息架构（不重做 Chat 内部）**、**更新索引自建 devpi**、**代码签名列为可选后置（不做 macOS 公证）**、**Windows 优先**。
> 交接快照见 [`HANDOVER.md`](./HANDOVER.md)，历史见 [`../CHANGELOG.md`](../CHANGELOG.md)。

## 排期原则

P4 排在 P2 之前。理由很直接：P2 每多改一个上游文件，追版成本就永久上升，所以度量装置必须先就位，让每次结构改动都在"冲突面积"的读数下发生。

P5 的桌面与镜像产物**不能在本机做**（本机没有 `go` / `wails3` / `makensis` / `docker`），全部走 CI runner。

## P4 · 追版机制（第 1 周，1.5–2 人日）

| 任务 | 状态 | 实际出口条件 | 上游冲突面 |
|---|---|---|---|
| P4-1 自建 `frontend` CI job：`tsc -b` + eslint + prettier check + vitest + build | ✅ 完成 | `.github/workflows/frontend.yml`；首轮就抓到 2 个上游 ESLint 错误 + 9 个我们造成的格式化问题，全部清零 | 新增 workflow（需 `workflow` scope） |
| P4-2 每周"试 merge" job：fetch 最新 stable tag → 试 merge → 出报告，不推主线 | ✅ 完成 | `.github/workflows/sync-attempt.yml` + `scripts/sync_check.py`；含 migration 守卫与"工作树脏就拒绝" | 0 |
| P4-3 冲突面积基线 `brand/owned-files.txt` | ✅ 完成 | 334 = 282 生成 + 25 手工 + 27 新增，由 `classify_owned.py` 用真实管线测量 | 0 |
| P4-4 月度正式 merge SOP 脚本化 | ⬜ 未做 | SOP 已写进 `CONVENTIONS.md` 第 6 节，但"merge → 门禁 → 更新基线号 → 递增 `+z`"还没有一条命令；首次真实追版时再脚本化 | 0 |
| P4-5 migration 纪律检查 | ✅ 完成 | `sync_check.py` 的 `migration_guard()`，报告里直接点名 | 0 |

注意上游 `ci.yml` 已提供 `quality`（ubuntu py3.12 跑 `make install/lint/typecheck/test`）与 `test-windows`，后端门禁直接继承；**但它没有前端 job**，`Makefile` 也不跑 vitest，那 218 个前端测试文件在上游从不执行。

## P2 · 换壳与信息架构

| 任务 | 状态 | 说明 | 上游冲突面 |
|---|---|---|---|
| ~~P2-0 凭据强制走加密 `secrets`~~ | **不做（2026-10-09 决定）** | 把凭据收进加密存储会挡住普通用户"直接改工作区 `.env` 接自己的 MCP"这条主路径，带来的日常问题多于收益。保留现状，见 `HANDOVER.md` 第 6 节 | —— |
| P2-1 共享 `<AppLogo>` + logo 调用点接入 | ✅ 完成（并入 P1b） | 实际只有 4 处调用点（Header / Sidebar / Login / Setup），先前"12 处"把吉祥物引用也算了进去 | 4 个文件，已在 owned 清单内 |
| P2-2 管理页"品牌"编辑区 | ✅ 完成（并入 P1b） | 做成 `/admin/advanced` 的一个 tab，只碰 `index.tsx` + `permissions.ts` 各几行，没有新增路由 | 2 个文件 |
| P2-3 信息架构：隐藏本版本不交付的上游入口 | ✅ 以最小代价完成 | 做法是**渐进式披露**而不是重排：默认隐藏 5 项（云端协同 / 远程桌面 / ACP / Token 统计 / 存储后端），一个开关全开。只碰自有文件 `src/branding/navSimplicity.ts` 与 `Sidebar.tsx` 两行，**没有**动 `routes` / `sidebarNav` / `preferences` 铁三角 | 实测：默认无这 5 项 → 开关 `aria-checked: true` 后 5 项全部回来，`zcagent:nav-full=1` 落盘，刷新后保持 |
| P2-4 登录页 / 欢迎页重做（自有视觉） | ⬜ 未做，建议降级 | 登录页其实已经**没有上游视觉痕迹**：字标（牧羊犬 + 智策 + zcagent）、主色、文案、favicon 全是我们的，剩下只是布局风格。要在 `pages/Login` 与 `WelcomeScreen` 上做定制视觉，每次追版都得在这两个活跃区解冲突，收益不匹配 | 若真要做：2 个上游文件 |
| P2-5 划"禁改区"并写进仓库约定 | ✅ 完成 | `docs/CONVENTIONS.md` 第 1 节列出 5 个只读区与规模 | 0 |

P2-1、P2-2 已在 P1b 完成，P2-0 取消，P2-3 用最小代价完成，P2-5 已成文 —— **P2 净剩余只有 P2-4，而它建议不做**。

**本档明确不做**：对话页内部布局与输入区重做。Chat 是上游最活跃的区域，动它的长期冲突成本远高于收益。

加一个全新页面要同时改 6 个文件（routes、sidebarNav、permissions、后端 preferences key、两份 locale、页面本体）——这是上游的设计。所以**新功能优先走插件的 `tool` + `ui/dist` 卡片**，把页面留在上游形态。

## P5 · 产物链

| 任务 | 状态 | 出口条件 / 卡点 |
|---|---|---|
| P5-1 产物矩阵（Windows 优先） | ✅ 已定并已执行 | 首批 = Windows 安装包 + 便携包；`octop-desktop.yml` 里平台定义仍保留，`product_only = {"windows-amd64"}` 一处过滤，放开是一行改动。Linux 服务端镜像后置 |
| P5-2 Windows 桌面 CI 构建 | ✅ 完成 | 打 tag 出 `zcagent-desktop-windows-amd64-<ver>.exe` 与 `zcagent-portable-windows-amd64-<ver>.zip`，两者由 `Attach zips to GitHub Release` 挂到 Release（`overwrite_files: true` 让重跑幂等）。踩过的坑：产物前缀 `Octop-` → `zcagent-` 必须与 workflow 的上传 glob 同步改，否则 `if-no-files-found: error` 直接让发版作业失败 |
| P5-3 自建 devpi 内网索引 + CI 推 wheel | ⬜ 未做 | `OCTOP_UPDATE_INDEX_URL` 已可配、更新检查默认已关，但还没有真的索引。**第一天先实测**端点形状是否为 `<host>/pypi/<name>/json`，否则要调 `self_update.py` 的 URL 拼接 |
| ~~P5-4 Windows 代码签名证书~~ | **降级为可选后置（2026-10-09）** | 对照证据：上游 `octop-desktop.yml` 里**没有任何签名 / 证书 / 公证步骤**，就是 `wails3` + NSIS 直接发，所以同类产品的 exe 本来就未签名可交付。签名只影响一次 SmartScreen 蓝窗要不要点"仍要运行"，企业内网分发（无 Mark of the Web）通常根本不弹。**不是构建阻塞项。** |
| P5-5 版本号打通 | ✅ 完成 | `1.0.2b6+z1`：`pyproject.toml` = `src/octop/__init__.py` = 产物名 = 更新页显示 = CHANGELOG 五处一致。实测 local version 对打包无害（`four_part_version("1.0.2b6+z1")` → `1.0.2.0`，显示串保留后缀）。注意 PEP 440 local version 不能上 PyPI，内网 devpi 可以 |
| P5-6 Linux 服务端 Docker 镜像 | ⬜ 未做 | 上游 `docker-publish.yml` 推的是 `ghcr.io/tencentcloud/octop`，必须换 registry 并改 `fnos/*/manifest` 里的镜像地址 |

## 下一步（按价值排序）

1. **干净机器验收**：在一台没装过 Python / Node 的 Windows 机器上跑安装版与便携版，确认内嵌运行时、数据目录、SmartScreen 话术、卸载残留。这是目前唯一"没人验证过"的环节，而它正是客户第一面。
2. **P5-3 devpi**：起索引 + 推 wheel，让更新页报我们的版本。
3. **首次真实追版**：等上游出 stable tag，按 `CONVENTIONS.md` 第 6 节走一遍，顺手把 P4-4 脚本化。
4. **P5-6 镜像**：有 Linux 服务端需求时再做。

## 待确认（不阻塞开工）

1. macOS 产物出不出——与签名无关（上游未签名未公证也照发），纯粹是"要不要支持 macOS"的产品决定。
2. devpi 托管在哪台机器、由谁运维。
3. 代码签名：默认**不买**。只有出现"用户从公网下载后大量反馈 SmartScreen 蓝窗"或某客户合同要求时再评估（OV 靠下载量攒信誉、EV 立即免弹，差别只在这个弹窗）。
4. ~~P2-3 要隐藏哪些上游入口~~ —— 已定：云端协同、远程桌面、ACP、Token 统计、存储后端 5 项，判据是"内网单机部署用不到或是死路"。要放开就在「应用设置 → 品牌 → 界面」里打开开关。
5. 用户头像与「云端协同 BETA」角标仍是玫红（上游的语义提醒色 / 头像配色板），要不要一并纳入品牌层——目前判断是不动，它是语义色不是品牌色。
