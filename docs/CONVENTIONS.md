# 仓库约定

> 面向在此仓库工作的工程师与 AI 编码代理。上游的 `AGENTS.md` 讲架构分层，本文件讲**作为 fork 我们额外遵守的规矩**。两者冲突时以本文件为准。

## 1. 只读区（不要改，改了就长期背债）

这些区域是上游迭代最活跃的地方，任何"顺手优化"都会变成每次追版的固定冲突：

| 路径 | 规模 | 为什么只读 |
|---|---|---|
| `dashboard/src/pages/Chat/` | 43,504 行 / 223 文件 | 上游最活跃区，消息流、输入区、轨迹渲染几乎每周动 |
| `dashboard/src/pages/Experts/` | 13,379 行 / 53 文件 | 专家库与市场是上游主打方向 |
| `dashboard/src/pages/Agent/Personalization/` | 含写死的 `PERSONALIZATION_TABS` 数组 | tab 顺序由上游决定 |
| `src/octop/infra/agents/` | 1,534 文件 | Agent 内核，且真正实现在 `octop-harness`（独立 MIT 包，**永不 fork**） |
| `src/octop/infra/db/migrations/` | 编号成对 SQL | 见第 3 条 |

需要这些区域的行为不同时，优先找扩展点（第 2 条），实在不行再改，并把它加进 `brand/owned-files.txt`。

## 2. 新功能优先落在这四处，不要写进上游源码

| 扩展点 | 位置 | 能做什么 |
|---|---|---|
| 插件 | `plugins/`，`kind` = `tool` / `skill` / `hook` / `tool`+`ui` | 注册工具、同步技能、在模型调用前后插桩、返回 `octop_ui` 让前端渲染交互卡片 |
| 专家库 | `src/octop/infra/agents/experts/library/` | 启动时扫描，加一个专家模板即被所有部署看到 |
| 技能包 / 连接器 | `infra/skills/`、`infra/connectors/` | 复用上游的目录与 OAuth/MCP 机制 |
| 品牌与主题 | `brand/brand.yaml` + `PUT /api/branding` | 名字、标语、主色、logo、导航详略 |

## 3. 三条硬红线

1. **不改标识符**。包名 `octop`、`OCTOP_HOME`、`~/.octop`、专家工作区 `.octop/`、`X-Octop-*` 头、AntD `prefixCls="octop"`、`octop:*` 存储键、19 个侧栏 nav key、i18n 的 **key**（只改 value）、第三方产品名（如 `OctopBot`）。这些要么已落盘要么已过线，改了就是数据/协议断裂。
2. **不自加编号 migration**。上游用 `00N_*.sql` + `00N_*.pg.sql` 成对文件并在单测里断言版本号，且未发布的改动会**折叠进当前未发布的 00N**。我们插一个编号，追版必冲突。私有数据放独立库文件。
3. **不 fork 四个子运行时**。`octop-harness` / `-gateway` / `-memory` / `-browser` 是独立 MIT 仓库 + PyPI 包，是我们与上游之间最稳定的边界，升级只改版本约束 + 跑回归。

## 4. 品牌改动一律走工具，不手改

```bash
python scripts/rebrand.py --apply    # 改名/换色/重出图标与字标
python scripts/rebrand.py --check    # 断言无残留，并报告未被覆盖的文件
python scripts/rebrand.py --revert   # 还原本工具改过的一切
```

`--check` 会额外报告"含旧品牌但没被清扫覆盖"的文件——只扫目标清单的检查在 glob 写错时会**空集假绿**，这个坑踩过。

## 5. 冲突面积纪律

`brand/owned-files.txt` 声明我们**承载手工改动**的上游文件（当前 25 个）。它由 `scripts/classify_owned.py` 生成：在基线的临时 worktree 里跑一次 `--apply`，再逐文件字节比对——落在清扫 glob 里不等于纯生成，别用 glob 判断。

改上游文件时：

- 能塞进 `brand/`、`src/branding/` 等自有路径的，就不要改上游文件；
- 必须改的，把改动压到最小（例如新品牌 tab 挂在已有 `AdvancedSettings` 里，而不是新增路由，避免碰 `routes`/`sidebarNav`/`preferences` 那套铁三角）；
- 改完跑 `python scripts/classify_owned.py` 更新清单。

## 6. 追版 SOP

```bash
git fetch upstream --tags
python scripts/sync_check.py --report /tmp/sync.md   # 试 merge，看冲突面积，不提交
# 报告干净或有冲突都可继续：
git checkout product/main && git merge upstream/v1.0.2   # 只 merge stable tag
python scripts/rebrand.py --apply                    # 纯生成文件：取上游后重跑
# 手工文件按 owned-files.txt 逐个复核
python scripts/classify_owned.py                     # 更新冲突面积清单
```

版本号规则见 `CHANGELOG.md`：`<上游基线>+z<N>`。beta tag 一律不追。
