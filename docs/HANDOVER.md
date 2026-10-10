# 交接说明

> 状态快照，截至 **2026-10-09**。不是教程：工作流看 [`README.md`](../README.md)，逐版本改动看 [`CHANGELOG.md`](../CHANGELOG.md)。

## 1. 这个项目在判断什么

起点是一个 go/no-go 问题：**能不能拿 MIT 的 [TencentCloud/Octop](https://github.com/TencentCloud/Octop) 做出一款自有品牌的智能助手产品**。结论是可以，路线选了 **B 薄 fork**：改界面结构、做独立品牌，同时定期 merge 上游 stable tag。

支撑这个判断的量化事实（自己测的，不是猜的）：

- 上游 12 周 **615 次提交**、3 周内发 **9 个版本**（含 6 个 beta）、684 个 open issue —— 这就是为什么必须"只 merge stable tag + 把定制外置"，手工改源码会在一个月内变成孤岛。
- 四个子运行时 `octop-harness` / `-gateway` / `-memory` / `-browser` 都是**独立 MIT 仓库 + PyPI 包**，主仓通过依赖消费它们。这是与上游之间最稳定的边界，**永远不要 fork 它们**，升级 = 改版本约束 + 跑回归。
- 上游把"个人助理"形态当一等公民，不是我们硬加的：每个专家的工作区会自动种下 `SOUL.md` / `USER.md` / `MEMORY.md` / `AGENTS.md` / `PROACTIVE.md` 这组人格与记忆文件，记忆落在专家自己的 `.octop/memory.sqlite`，随工作区迁移。

## 2. 现在到哪了

| 阶段 | 状态 | 怎么验证的 |
|---|---|---|
| P0 fork 骨架 | 完成 | `upstream` / `origin` 双远端，`upstream-main` 零改动 + `product/main` 产品分支；上游 7 条 tag 触发流水线已在仓库设置禁用 |
| P1a 构建期品牌 | 完成 | `rebrand.py --check` 覆盖 2347 文件无残留；标识符逐项核对未误改 |
| P1c 吉祥物 | 完成 | 三姿势生成动画 WebP，帧级校验（24 帧中 23/24 帧不同），404 页实景确认 |
| P1b 运行时 OEM | 完成 | 名称/标语/主色/logo 四项均可在装完后改；对照实验：塞入一张明显不同的测试 logo，登录页与侧栏同步替换且未重新构建 |
| P4 追版度量 | 完成（首次追版待网络） | `frontend.yml` + `sync-attempt.yml` + `scripts/sync_check.py`；合成冲突分支实测能识别冲突、非零退出、并完整还原工作树 |
| P2 换壳与信息架构 | 未开始（4–6 人日） | P2-1 / P2-2 已并入 P1b 完成；P2-0 凭据加密**已否决，不重做**（见第 6 节） |
| P5 自有产物链 | 未开始 | — |

### 冲突面积的真实测量（重要）

我们分支相对基线一共动了 **285 个已有文件**，但按"是否在 `rebrand.py --apply` 的再生成范围内"分类后：

| 类别 | 数量 | 合并时怎么处理 |
|---|---|---|
| 纯工具生成（与再生成结果**逐字节相同**） | **260** | 机械处理：取上游版本，然后重跑 `--apply` |
| 承载手工改动 | **25** | 真正需要人看的冲突面，逐条列在 `brand/owned-files.txt` |

这 25 个就是 P1b 运行时层（`App.tsx`、`main.tsx`、`branding` 路由与模块、`AdvancedSettings`、4 处 logo 调用点、两份 locale、`permissions.ts`）+ `self_update.py` 的索引可配 + 一处测试修正 + 我们的文档。

测量方法本身也值得记一笔：先前用"是否落在清扫 glob 里"来分类是**错的**（`dashboard/src/**` 既是清扫范围也包含手工写的运行时代码，会把 P1b 全算成生成物）。`scripts/classify_owned.py` 改成跑真实管线——在基线的临时 worktree 里执行一次 `--apply`，再逐文件字节比对——这才是地面真值。



## 3. 下一步

排期、出口条件与人力估算在 [`PLAN.md`](./PLAN.md)，已按四个已定决策展开（P2 做换壳+信息架构、更新索引自建 devpi、代码签名列为可选后置、Windows 优先）。

一句话原则：**P4 排在 P2 之前**——P2 每多改一个上游文件，追版成本就永久上升，度量装置必须先就位。P4 已完成，P2 现在只剩 4–6 人日的换壳与信息架构工作。

## 4. 这次真踩过的坑（别重复踩）

- **`pathlib.glob` 不支持 `{a,b}` 大括号展开**，静默匹配 0 个文件。`rebrand.py` 里有 `expand_braces()` 处理。
- **`--check` 只扫目标清单会假绿**：glob 写错时目标集是空集，检查自然通过。现在 `--check` 会额外报告"含旧品牌但根本没被清扫覆盖"的文件。
- **工具会扫到自己**：`scripts/rebrand.py` 里正则含字面量品牌词，被自己改写后，下一次 `--check` 拿新品牌当旧品牌找，报出 244 个假阳性。已把工具自身与 `brand/**` 排除。
- **正则里的转义域名**：`stamp_version.py` 写的是 `com\.tencent\.octop`，纯字面量替换匹配不到，导致 manifest 改了、正则没改，打包时 `SystemExit`。现在字面量替换会自动带转义变体。
- **仓库 slug 会被品牌词规则改坏**：`TencentCloud/Octop` → 不存在的 `TencentCloud/zcagent`，波及安装脚本、镜像标签、"查看更新"链接共 11 个文件。已作为 identity 字面量处理。
- **测试里有大量写死的品牌断言**（约 388 处），所以 `tests/**` 必须和源码同一规则一起扫，否则改一半必红。
- **颜色有三个真源**：`themePalettes.ts`、`theme-vars.css`、以及 `index.html` 里 JS 之前的启动屏硬编码。只改一处会不一致或闪色。
- **`i18n` 的 key 不能动**（如 `askOctopHint`），只改 value；改 key 会破前后端 key 奇偶校验测试。

## 5. 验证基线（别去追的鬼）

- 前端 vitest 全量在**干净上游树上稳定红 8 个用例**（两次跑完全一致）。改名+改色后空闲跑是 8 / 6，CPU 争用时 9–10。原因是 `pool: "threads"` 加 testing-library 默认 1000ms 异步超时，`ChannelsPanel` 那几条最先抖。**结论：品牌改动造成的确定性前端失败为 0。**
- 上游 `ci.yml` **没有 Node job**，`Makefile` 也不跑 vitest —— 这 218 个前端测试文件在上游 CI 里从不执行。别假设它们是绿的。
- 后端全量 `pytest -m "not live"` 在 Windows 上要好几个小时（每个用例起 SQLite/嵌入式服务）。改品牌时的正确做法：用 `rebrand.py --status` 找出受影响测试文件，只跑那些。
- `tests/unit/backup/test_system_archive.py::test_restore_repairs_old_physical_schema_with_current_watermark` 在**未修改的上游树上同样失败**，是既有问题，别当成我们改坏的。
- 上游文档里写的 `cli/init_cmd.py` 这类路径与实际 `cli/commands/init.py` 不一致，`AGENTS.md` 存在文档漂移。

## 6. 安全相关：一条已做的决定 + 一条底线

**决定：不把 Agent 凭据强制收进加密存储（2026-10-09）。** 评估时发现 Agent 可以往 `{workspace}/.octop/.env` 写凭据（含 `Bearer` token），并提议改为强制走 `infra/connectors/` 的加密 `secrets`。**该提议已否决，不要重做。** 理由：普通用户接自己的 MCP / 外部服务时，"直接编辑工作区里的 `.env`"就是主路径；加一层加密会把这条路径变成工单来源，日常损失大于风险收益。

这条是**产品权衡后的接受项**，不是遗漏。若将来面向强合规客户，再按客户名单独评估，不要默认改。

仍然有效的两条：

- **不要给"密钥不落盘"这类保证。** 现状是落盘的，任何提示词或文案都不许声称相反——错误的保证比没有保证更糟。
- `PUT /api/branding` 的 `logo_url` 只接受 `https://` 与 `data:image/`，**不要放开文件路径**，否则品牌设置会变成一个能把宿主文件读出来的口子。
- 评估期间发现的上游自身问题，走 `SECURITY.md` 渠道负责任披露，不在本仓库公开文档描述细节。

## 7. 本机环境备注（与项目无关，换机器即作废）

- 没有系统 Node，用本机另一台工具自带的那份 v22（每个 shell 调用前临时加 PATH）。
- 没有 `make`，仓库里的 Makefile 目标要读出来手工翻译成直接命令。
- `files.pythonhosted.org` 本机只有约 75 KB/s；用腾讯 PyPI 镜像（约 2 MB/s）。tuna 返回 403，aliyun 只有 52 KB/s。
- `github.com:443` 间歇性连不通，但 `api.github.com` 正常；`git push` 失败就重试几次。
- 该 GitHub 账号的 token 默认没有 `workflow` scope，任何触碰 `.github/workflows/**` 的 push 都会被拒；补 scope 用 `gh auth refresh --hostname github.com -s workflow` 的设备码流程。
- 无头截图：npmmirror 没有托管新版 Chrome-for-Testing 构建（404），直接用系统 Edge 通道 `p.chromium.launch(channel="msedge")`。
- 演示实例的登录口令是本地初始化时设的，**没有写进仓库，也不要写进来**。
