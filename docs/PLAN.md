# 计划表（P2 / P4 / P5）

> 截至 2026-10-09。已定的四个决策：**P2 做换壳+信息架构（不重做 Chat 内部）**、**更新索引自建 devpi**、**只做 Windows 代码签名、不做 macOS 公证**、**Windows 优先**。
> 交接快照见 [`HANDOVER.md`](./HANDOVER.md)，历史见 [`../CHANGELOG.md`](../CHANGELOG.md)。

## 排期原则

P4 排在 P2 之前。理由很直接：P2 每多改一个上游文件，追版成本就永久上升，所以度量装置必须先就位，让每次结构改动都在"冲突面积"的读数下发生。

P5 的桌面与镜像产物**不能在本机做**（本机没有 `go` / `wails3` / `makensis` / `docker`），全部走 CI runner。

## P4 · 追版机制（第 1 周，1.5–2 人日）

| 任务 | 出口条件 | 粗估 | 上游冲突面 |
|---|---|---|---|
| P4-1 自建 `frontend` CI job：`tsc -b` + eslint + prettier check + vitest + build | PR 上能看到前端红绿灯 | 0.5 人日 | 新增 workflow（需 `workflow` scope） |
| P4-2 每周"试 merge" job：fetch 最新 stable tag → merge 到 `vendor/try-merge` → 跑全门禁 → 出报告，不推主线 | 一条命令回答"上游动了什么 / 我们哪些文件冲突 / 测试是否绿" | 1 人日 | 0 |
| P4-3 冲突面积基线 `brand/owned-files.txt`：登记有意改过的上游文件，报告按它过滤 | 面积数字可比较、不增长 | 0.5 人日 | 0 |
| P4-4 月度正式 merge SOP 脚本化：merge → 门禁 → 更新 CHANGELOG 基线号 → 递增 `+z` 序号 | 一次 merge 全程不超过半天 | 0.5 人日 | 0 |
| P4-5 migration 纪律检查：断言我们没有私自新增 `00N` 编号 | CI 一条断言 | 0.2 人日 | 0 |

注意上游 `ci.yml` 已提供 `quality`（ubuntu py3.12 跑 `make install/lint/typecheck/test`）与 `test-windows`，后端门禁直接继承；**但它没有前端 job**，`Makefile` 也不跑 vitest，那 218 个前端测试文件在上游从不执行。

## P2 · 换壳与信息架构（第 2–6 周，9–14 人日）

| 任务 | 出口条件 | 粗估 | 上游冲突面 |
|---|---|---|---|
| **P2-0 凭据存储**：Agent 侧写入的凭据一律走 `connectors` 的加密 `secrets`；工具输出禁止声称"未落盘" | 该要求有回归测试锁住 | 3–5 人日 | ~4 文件（`infra/agents/`、`infra/connectors/`） |
| ~~P2-1~~ | 共享 `<AppLogo>` + logo 调用点接入 | —— | —— | **已完成，并入 P1b**。实际只有 4 处调用点（Header / Sidebar / Login / Setup），先前"12 处"把吉祥物引用也算了进去 |
| ~~P2-2~~ | 管理页"品牌"编辑区 | —— | —— | **已完成，并入 P1b**。做成 `/admin/advanced` 的一个 tab，因此只碰了 `index.tsx` + `permissions.ts` 各几行，没有新增路由 |

P2 剩余净工作量因此降到 **7–11 人日**。
| P2-3 信息架构重排：导航分组按客户场景收敛，隐藏本版本不交付的上游入口（远程手机、fnOS 专属项等） | 新导航走通；冲突面积 ≤ 基线 + 4 文件 | 3–4 人日 | `routes/index.tsx`(63 条)、`layouts/sidebarNav.tsx`(19 key)、`utils/permissions.ts`、`locales/{en,zh}.json`(6488 行) |
| P2-4 登录页 / 欢迎页重做（自有视觉，复用上游表单与验证码逻辑） | 首屏无上游视觉痕迹 | 2 人日 | `pages/Login`、`pages/Chat/components/WelcomeScreen` |
| P2-5 划"禁改区"并写进仓库约定 | `pages/Chat`(43504 行 / 223 文件)、`pages/Experts`、`pages/Agent/Personalization` 只读 | 0.2 人日 | 0 |

**本档明确不做**：对话页内部布局与输入区重做。Chat 是上游最活跃的区域，动它的长期冲突成本远高于收益。

加一个全新页面要同时改 6 个文件（routes、sidebarNav、permissions、后端 preferences key、两份 locale、页面本体）——这是上游的设计。所以**新功能优先走插件的 `tool` + `ui/dist` 卡片**，把页面留在上游形态。

## P5 · 产物链（第 7 周起，7–12 人日 + 外部周期）

| 任务 | 出口条件 | 粗估 | 卡点 |
|---|---|---|---|
| P5-1 产物矩阵（按"Windows 优先"定）：首批 = Windows 安装包 + Linux 服务端 Docker 镜像；macOS 与 fnOS 后置 | 一句话能说清交付什么 | 0.2 人日 | 已定 |
| P5-2 Windows 桌面 CI 构建：`windows-latest` 装 Go + wails3 + NSIS | 打 tag 出 `.exe` / 便携包 | 3–5 人日 | `config.yml` 改完必须 `wails3 task common:update:build-assets` 重生成 nsis，否则 `productName` 与 `windows/info.json` 两处不一致；`nsis/project.nsi:5-6` 写死了 `bin\Octop.exe` |
| P5-3 自建 devpi 内网索引 + CI 推 wheel | 更新页报的是我们的版本 | 1–2 人日 | **第一天先实测**：我们的代码假设索引形状是 `<host>/pypi/<name>/json`（与 PyPI 一致），devpi 需验证确实提供该端点，否则要调整 `self_update.py` 的 URL 拼接 |
| P5-4 Windows 代码签名证书 | 下载不再触发 SmartScreen 拦截 | 1 人日 + **采购周期数周** | 外部依赖，要最早启动；macOS 公证按决策**不做**，因此 macOS 产物也一并后置 |
| P5-5 版本号打通：`pyproject` 版本 = 上游基线 + `+z` 序号，产物命名对齐 `release_download_links.py` | 更新页 / 安装包名 / CHANGELOG 三处一致 | 1 人日 | PEP 440 local version 不能上 PyPI，但内网 devpi 可以 |
| P5-6 Linux 服务端 Docker 镜像 | 内网可拉、可 `docker compose up` | 1–2 人日 | 上游 `docker-publish.yml` 推的是 `ghcr.io/tencentcloud/octop`，必须换 registry 并改 `fnos/*/manifest` 里的镜像地址 |

## 时间线

| 周 | 内容 |
|---|---|
| 1 | P4-1 ～ P4-3；同时启动 P5-4 证书采购（外部周期最长，先跑起来） |
| 2 | P2-0 安全项 |
| 3 | P2-1 + P2-2（把 P1b 的两块尾巴收掉） |
| 4–6 | P2-3 信息架构 + P2-4 首屏；每次合并前看冲突面积读数 |
| 7–9 | P5-2 Windows 构建 → P5-3 devpi → P5-5 版本号 → P5-6 镜像 |

## 待确认（不阻塞开工）

1. macOS 是否彻底不出（当前按"不做公证所以后置"处理）。
2. devpi 托管在哪台机器、由谁运维。
3. Windows 签名证书预算与采购渠道（OV / EV 差别影响 SmartScreen 表现）。
4. P2-3 要隐藏哪些上游入口——需要一份"本版本不交付的功能清单"。
