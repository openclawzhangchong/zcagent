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
python scripts/rebrand.py --apply    # 改名/换色/重出图标与字标，并对刚重写的 dashboard 文件跑 prettier
python scripts/rebrand.py --check    # 断言无残留，并报告未被覆盖的文件
python scripts/rebrand.py --revert   # 还原本工具改过的一切
```

`--check` 会额外报告"含旧品牌但没被清扫覆盖"的文件——只扫目标清单的检查在 glob 写错时会**空集假绿**，这个坑踩过。

**格式化属于 `--apply`，不是"记得手工 `npm run format`"。** 替换品牌词会改变字符串长度，prettier 于是要求重新换行（品牌色写成大写十六进制也会被判定未格式化）。把这一步写成口头约定，第一次追版之后 `Frontend` 的 Format check 就会红，而且没人能追溯到原因。

**换行由 `.gitattributes` 固定为 LF。** 仓库里所有文本 blob 都是 LF，但 Windows 检出配合 `core.autocrlf=true` 会给出 CRLF 工作树，`prettier --check .` 便把上千个干净文件报成脏。**遇到这种情况先信 CI**：CI 只报 9 个，本机报 1082 个，差额全是换行。别为此对整棵树跑 `--write`，更别在验证命令里顺手写 `git checkout -- .`（它会连你刚做的格式化一起清掉）。

## 5. 冲突面积纪律

`brand/owned-files.txt` 声明我们**承载手工改动**的上游文件（当前 25 个），另有 27 个"我们新增、没有上游 counterpart"的文件以注释形式列在同一份里。它由 `scripts/classify_owned.py` 生成：在基线的临时 worktree 里跑一次 `--apply`，再比对 **git 存储的内容**（忽略本机换行）。

当前读数：**相对基线 334 个文件 = 282 个纯生成物 + 25 个手工改动 + 27 个新增**。两条教训：

- 落在清扫 glob 里不等于纯生成物——`dashboard/src/**` 既被清扫也包含手写的运行时代码，用 glob 判断会把 P1b 全算成生成物。
- 用**逐字节**比对也不对——Windows 工作树是 CRLF，而 `--apply` 会跑 prettier 写 LF，于是约 230 个生成物会被误判成手工改动，冲突面积虚高十倍。

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

版本号规则见 `CHANGELOG.md`：`<上游基线>+z<两位序号>`，序号**零填充**（`z01`…`z99`）——PEP 440 对字母数字 local 段按字符串比较，`+z10` 会排在 `+z9` 下面。beta tag 一律不追。

## 7. 门禁与工具链陷阱

**`Frontend` workflow 是前端唯一的红绿灯**：`npm ci` → `eslint .` → `prettier --check .` → `npm run build`（含 `tsc -b`）→ vitest 汇总。上游 `ci.yml` 没有 Node job，所以这些检查在上游从不执行——它自己的树上就有 2 个 ESLint 错误。

- **不许为了让门禁变绿而 disable 规则或加 `// eslint-disable`**。上游带来的错误就改正它（改动会计入冲突面积，这是代价，也是信号）。
- vitest 暂时 `continue-on-error`：干净上游树在本机已稳定红 6–10 个（`pool: "threads"` + testing-library 1000ms 异步超时），先让 CI 建立自己的基线再转阻塞。
- 后端仍按上游 `make all`（Ruff + `mypy --strict` + pytest）；全量 pytest 在 Windows 上要几小时，改品牌时用 `rebrand.py --status` 找受影响的测试文件再跑。

**两个会让人误报"成功"的陷阱**（都踩过）：

- `git ls-remote origin <branch> <sha>` **不是**推送成功的判据：带 SHA 的 pattern 匹配不到任何 ref，而 branch 名总能匹配，检查恒真。要比对 `git ls-remote origin refs/heads/<branch>` 的输出与本地 HEAD。
- `gh` 会把这个 fork 解析成**上游仓库**：`gh repo view` / `gh run list` 默认给的是 `TencentCloud/Octop` 的数据。查自己的 Actions / Release 必须显式 `--repo openclawzhangchong/zcagent`。

