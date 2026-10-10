# 更新日志

本文件记录 **智策 / zcagent 相对上游的改动**。上游自己的历史在 [`CHANGELOG.upstream.md`](./CHANGELOG.upstream.md)。

## 版本号规则

`<上游基线版本>+z<N>`，例如 `1.0.2b6+z1`。

- `+` 前是所基于的上游版本，追版时只改这一段；
- `z<N>` 是我们的补丁序号，每次发布 +1；
- 用 PEP 440 local version，因此这类包**不能**上传 PyPI（我们不发布公共包，内网分发正合适）。

---

## [1.0.2b6+z1] — 2026-10-10

基于上游 `v1.0.2b6`（commit `0c5a46a`，2026-10-08）。首个自有品牌版本。

### 发布记录

| 项 | 值 |
|---|---|
| tag | `v1.0.2b6-z1` → commit `5dbff1b`（其后的提交均为纯文档） |
| GitHub Release | <https://github.com/openclawzhangchong/zcagent/releases/tag/v1.0.2b6-z1>，标记 **prerelease**（基线本身是上游 beta） |
| 产物 | `zcagent-desktop-windows-amd64-1.0.2b6+z1.exe`（192 MB）、`zcagent-portable-windows-amd64-1.0.2b6+z1.zip`（197 MB），由 `zcagent Desktop Package` 作业产出并挂到 Release |
| `Frontend` 门禁 | 绿：ESLint 0 error、`prettier --check` 通过、`tsc -b` + vite build 通过 |
| vitest 基线（CI，非阻塞） | 6 failed / 1147 passed，218 文件，92.7s。这 6 个失败所在的测试文件与其被测模块相对上游基线**零改动**，故不属品牌改动引入；本机在干净上游树上稳定红 6–8 个 |
| 签名 | 未签名（刻意，见 `docs/PLAN.md` P5-4） |
| tag 重打说明 | 首次构建（run `38019377417`）成功但对应 tag 落在门禁变绿之前，故把 tag 移到 `5dbff1b` 重打一次，让**产物 = 被测过的提交**；`Attach zips` 作业靠 `overwrite_files: true` 原地替换同名产物 |


### 新增：OEM 品牌层

- `brand/brand.yaml` —— 品牌单一真源：`name.en=zcagent`、`name.zh=智策`、`colors.brand=#3D5A80`、`identity` 反写域名 `cn.jiuyeke.zcagent`、清扫/排除清单、图标产物映射。
- `scripts/rebrand.py` —— `--apply` / `--check` / `--revert` / `--status` 四个动作：
  - 文本层：大写品牌词按 ASCII 边界替换（`OctopError`、`X-Octop-*`、`octop-harness`、i18n key 等一律不命中），中文 locale 用中文名、其余用英文名；固定说法走 `phrases` 表。
  - 颜色层：把默认主题指向上游已有的 `custom` 派生通道（运行时生成全套 CSS 变量 + AntD token，含深色模式），只动 2 行，**8 套预设配色保持可切换**。
  - 图标层：从 `brand/assets/icon-1024.png` 自动裁方、抠平色背景，产出 PWA 512/192、apple-touch、favicon、竖版 SVG；横版 logo 用 PIL + 系统 CJK 字体合成"图形 + 中文名 + 英文名"字标（不用 AI 生成文字），深浅两版按主题输出。
  - 吉祥物：`brand/assets/mascot-{peek,typing,empty}.png` 三个姿势 → 自动抠平色背景、裁方、按上游原尺寸输出；动画 WebP 由 PIL 生成（`bob` 上下浮动 / `nod` 轻微点头两种模式，无需 ffmpeg），帧数与尺寸对齐上游资产（peek 352×320、type 856×812、empty 2048²）。
  - `--check` 除了断言目标文件无残留，还会报告"含旧品牌但根本没被清扫覆盖"的文件——避免 glob 写错导致的假绿。

### 变更：应用自有品牌

- 全量清扫 **2347 个文件**，覆盖后端、前端、测试、桌面壳、fnOS/Docker 打包与安装脚本。
- 桌面身份：`desktop/src/build/config.yml`、`windows/info.json`、`darwin/Info.plist{,.dev}`、`windows/wails.exe.manifest` 的 product/company/identifier 全部改为 `zcagent` / `cn.jiuyeke.zcagent`。
- 反写域名替换同时覆盖正则里的转义写法（`com\.tencent\.octop`），否则 `stamp_version.py` 会在打包时 `SystemExit`。
- 上游文档改名保留：`README.md → README.upstream.md`、`CHANGELOG.md → CHANGELOG.upstream.md`。追版时这两个文件按"ours"解冲突。

### 变更：更新源可配置

`src/octop/infra/setup/self_update.py` 的索引地址改为读 `OCTOP_UPDATE_INDEX_URL`（默认仍是 `https://pypi.org`），UI 上的来源标签随之显示真实主机名。分发名保持 `octop`，因为它同时是 pip 升级目标与已安装发行版查询名。

### 变更：一处上游测试修正

`dashboard/src/utils/expertColor.test.ts` 把写死的 `"rose"` 改为引用 `DEFAULT_PALETTE` 常量——改默认配色的正当后果，且这样上游再怎么调色板都不会误报。

### 新增：运行时 OEM 品牌覆盖层

构建期品牌决定"装出来是什么样"，这一层让**客户管理员装完之后不改代码就能改**：

- `GET /api/branding`（免鉴权，登录页也要能读）+ `PUT /api/branding`（`admin_console` 权限），值存 `settings` KV 的 `branding` 行，**不加 migration**。
- 字段：`name` / `name_zh` / `tagline` / `color` / `logo_url`；空字段回落到构建期品牌，未配置的部署行为不变。
- `logo_url` 只接受 `https://` 或 `data:image/` URI（上限 300KB），**不接受文件路径**，避免把宿主文件变成可被 `<img src>` 读回来的出口。
- 前端在 `main.tsx` 首次渲染前 `await loadBranding()`，所以标题、主色不会闪一下构建期默认值；`color` 存在时复用上游已有的 `custom` 调色板派生（AntD token + CSS 变量 + 深浅两套），并且**部署级主色优先于用户自选配色**。
- 验证：把覆盖设成 `#0F766E` 后，不重新构建，焦点环与复选框即变青绿；清空覆盖后回落钢蓝。`tests/unit/api` + `test_scalar` 305 passed / 10 skipped。
- **已完成**：`logo_url` 接入 `src/branding/AppLogo.tsx`，替换 Header / Sidebar / Login / Setup **4 处**调用点（先前估计的"12 处"把吉祥物引用也算进去了，实际只有 4 处）；`loadBranding()` 同时改写 `link[rel=icon]` 与 `apple-touch-icon`，浏览器标签页图标跟着换。管理页新增「品牌」tab（`/admin/advanced?tab=branding`），可填中英文名、标语、主色、粘贴 https 链接或上传图片，保存后自动刷新生效。
- 已知边界：`index.html` 里 JS 之前的启动屏仍用构建期 logo —— 运行时覆盖发生在 React 挂载前的一次 fetch，早于它也就要把品牌写进 HTML 模板，那属于构建期职责。

### 新增：P2 换壳 —— 导航渐进式披露

默认侧栏只保留内网单机助手用得上的 14 项，把**云端协同、远程桌面、ACP、Token 统计、存储后端**这 5 项收进一个开关（应用设置 → 品牌 → 界面）。选择"隐藏"而不是"删除"：删掉每次追版都要冲突一次，而且会真的拿走能力；开关放在我们自己的文件里，上游零冲突。

实测（无头驱动真实点击开关）：默认 14 项 → 打开后 19 项，5 个入口全部回来，`aria-checked: false → true` 且侧栏实时响应。

### 新增：P3 首个自有能力 —— 决策留痕 skill 插件

`plugins/zcagent-decision-log/`（`kind: skill`）。刻意**不自己实现文件写入**：插件 API 没有"当前专家工作区"入口，硬写会重复 harness 的能力并随其演进而漂移；改为教专家用它已有的文件工具，把决定按固定小节写进 `decisions/YYYY-MM.md`。

管线已验证：`octop plugin install` → 运行时 `loaded: True` → 技能同步进 `.octop/skills/decision-log/` → `octop skills list` 显示 `enabled=True`。

### 变更：更新检查默认关闭

`/admin/advanced?tab=updates` 之前会去查公共 PyPI 上的 `octop` 包，于是我们自己的部署会弹"新版本已就绪 → 立即更新"，点下去装的是别人的构建。现在默认不检查：`OCTOP_UPDATE_CHECK=1` 显式打开，或配置了 `OCTOP_UPDATE_INDEX_URL`（指向自家内网索引）时自动打开。实测 `/api/update/status` 返回 `has_update:false`、`latest_version:null`、无 error。

### 变更：发布产物名与桌面流水线

- 产物前缀 `Octop-` → `zcagent-`（`desktop/portable/_common.sh` 等 51 个文件同步）。这条必须做：NSIS 的产物名来自 `productName`（已是 `zcagent`），而 workflow 的上传 glob 还写着 `Octop-desktop-*`，配上 `if-no-files-found: error` 会让发版作业直接失败。token 规则为保护 `X-Octop-*` 跳过了后接连字符的情况，所以单列一条字面量规则。
- `octop-desktop.yml` 裁剪为只构建 `windows-amd64`（保留其余平台定义，放开是一行改动）；内嵌的 python 平台筛选块已做语法校验。

### 版本

`pyproject.toml` 与 `src/octop/__init__.py` 升到 `1.0.2b6+z1`。实测该 local version 对打包无害：`stamp_version.four_part_version("1.0.2b6+z1")` → `1.0.2.0`，显示串保留后缀。

### 仓库与流水线

- 远端：`origin = github.com/openclawzhangchong/zcagent`，`upstream = TencentCloud/Octop`。
- 分支：`upstream-main`（零改动跟踪）、`product/main`（产品分支）。
- 上游 7 条 tag 触发流水线（release / docker-publish / octop-desktop / fnos-build-fpk / auto-tag / sync-main-to-develop / anti-spam）在仓库设置中禁用，保留 CI 与 CodeQL。

### 验证

| 检查 | 结果 |
|---|---|
| `rebrand.py --check` | 2347 个文件已清扫，无旧品牌残留 |
| 后端：28 个被清扫改动的测试文件 + `tests/unit/i18n` | 通过，除 `test_system_archive::test_restore_repairs_old_physical_schema_with_current_watermark` |
| 上述例外做基线对照 | 未改名的干净树上**同样失败** → 上游既有问题，非本次改动引入 |
| 前端 vitest 全量（改名后，空闲） | 8 / 6 个用例失败 |
| 前端 vitest 全量（干净上游基线，两次） | 8 / 8 个用例失败 |
| 结论 | 改名与改色造成的确定性失败 **0**；该套件在本机 ±2 抖动（`pool: "threads"` + testing-library 1000ms 异步超时），CPU 争用时会升到 9–10 |
| 前端 ESLint（`npx eslint .`） | 0 error / 68 warning（上游树上原有 2 error，已修；warning 不阻塞，`eslint .` 无 `--max-warnings`） |
| 前端 Prettier（`prettier --check .`） | 本地与 CI 均通过；CI 只报 9 个文件，本地一度报 1082 个 —— 差额是 `core.autocrlf` 的换行噪声，已由 `.gitattributes` 消除 |
| 前端 `npm run build`（= `tsc -b` + vite + PWA） | 通过 |
| 标识符未被误改 | `X-Octop-*`、`prefixCls="octop"`、`OCTOP_HOME`、`octop-harness` 依赖名、i18n key 均已核对原样 |
| 运行期冒烟 | 登录 → 建专家 → 真实对话（OpenAI 兼容 provider）→ 工具调用写文件并落盘核对，全通过 |

### 新增：P4 追版度量

- `.github/workflows/frontend.yml`：lint + prettier check + `tsc -b`/build + vitest 汇总。**vitest 暂不阻塞**——上游 CI 从不跑它，干净上游树在本机已红 6–10 个，先让 CI 建立自己的基线再转阻塞。
- `.github/workflows/sync-attempt.yml` + `scripts/sync_check.py`：每周一试 merge 最新 stable tag（不提交不推送），报告"上游领先多少 / 哪些文件冲突 / 是否踩了我们的规矩"，冲突或违规时退出码非零。含两条守卫：不许私自新增编号 migration；工作树有未提交改动时拒绝试 merge（回滚用 `reset --hard`）。
- `scripts/classify_owned.py`：用真实管线量冲突面积——在基线的临时 worktree 里跑一次 `--apply`，再逐文件比对 git 存储的内容，得出 `brand/owned-files.txt`。首轮读数是 285 个改动文件 / 260 个纯生成物 / 25 个手工改动；格式化进入管线后重新测量为 334 / 282 / 25 + 27 个新增，见下一节。先前按"是否落在清扫 glob 内"分类会把 P1b 的运行时代码误判成生成物，故改用内容比对。
- 验证：用从基线分叉、在同一位置插入不同行的合成分支实测 `sync_check.py`，正确报出 1 个冲突、退出码非零、且工作树完整还原。真实 upstream 试 merge 因本机 `github.com:443` 中断未跑成，留给首次 CI。

### 首轮 CI：门禁确实会红，红的是我们

`Frontend` workflow 上线后第一次跑就给出三个可核对的事实：

- **ESLint 红 2 个错误，且都在我们从未改过的文件里**（`chatStore.ts:1217` 多余的 `Boolean()`、`constants.test.ts:5` 未使用的 import）。用 `git diff --name-only upstream-main..HEAD` 证明这两处与 fork 无关 —— 上游前端**不过自己的 ESLint**，因为它的 CI 里没有 Node job。已修，不靠 disable：门禁必须能为我们关心的原因失败。
- **Prettier 红 9 个文件，全部由我们造成**：逐个用 `prettier --stdin-filepath` 比对基线版本与当前版本，基线 9 个文件里 6 个本来是干净的。根因是替换品牌词会改变字符串长度，于是 prettier 要求重新换行；`#3D5A80` 写成大写十六进制也被判为未格式化。
- **因此格式化进了 `--apply` 管线**（`format_written()`）：只对本工具刚重写的 dashboard 文件跑 prettier，且当它跑在临时 worktree 里时借用主检出那份 prettier，保证两边字节一致。若把这一步写成"记得手工跑 `npm run format`"，第一次追版之后就会静默变红，而没人能追溯到原因。
- 新增 `.gitattributes` 为前端文本固定 `eol=lf`。仓库里**没有任何文本 blob 带 CRLF**，所以这行对 Linux/CI 零影响；它只解决 Windows 检出（`core.autocrlf=true`）下 `format:check` 把 1000+ 个干净文件报成脏的假阳性——那是纯换行差异，不是代码问题。

### 变更：冲突面积重新测量（334 / 282 / 25 / 27）

`scripts/classify_owned.py` 原先硬编码了一个已不存在的仓库路径、用 `read_bytes()` 逐字节比对、并且把"我们新增的文件"和"上游也拥有的文件"混在一张表里。修正后：从所在检出自动取仓库根、解释器与基线 revision，比对**git 存储的内容**（忽略本机换行），并区分三类：

| 类别 | 数量 | 合并时怎么处理 |
|---|---|---|
| 相对基线改动的文件 | 334 | — |
| 与 `--apply` 再生成结果一致 | **282** | 机械处理：取上游，重跑 `--apply` |
| 承载手工改动（上游也拥有该文件） | **25** | 真实冲突面，逐条列在 `brand/owned-files.txt` |
| 我们新增（无上游 counterpart） | **27** | 不会撞，除非上游以后新增同路径文件 |

先前的"25"结果碰巧还对，但理由是错的：换行差异会让分类器把约 230 个生成物误判成手工改动，格式化一进管线就会立刻暴露。

### 已知问题

- **凭据存储：决定不改为强制加密（2026-10-09）。** Agent 可在工作区 `.octop/.env` 写入凭据，曾提议强制走 `connectors` 的加密 `secrets`，已否决：普通用户接自己的 MCP 就是靠直接编辑这个文件，加密会把主路径变成工单。这是权衡后的接受项，不要重做；详见 `docs/HANDOVER.md` 第 6 节。保留的底线只有一条：不许在任何文案或提示词里声称"密钥不落盘"。
- Windows 下 `工作台 / 终端` 不可用（上游按设计禁用，见 `src/octop/api/routers/terminal.py`）。
- 系统提示词里的 OS / 工作区路径在 Windows 上会被模型复述成 Linux 风格路径，属上游待修。
- **技能遵循度不足（模型侧，非接线问题）**：接好的 `decision-log` 技能在实测中没被走通——第一轮把决定写进了 `MEMORY.md`；第二轮显式点名 `decision-log`，模型却回"未命中 `totorosir-workbuddy-checkin`"（技能名串台）。当前模型是 flash 档，说明"装了技能"不等于"会用技能"，交付时要按模型档位评估。
- **模型会写错日期**：那次写入 `MEMORY.md` 的记录把日期写成 `2026-07-11`，实际是 2026-10-10。对"决策审计留痕"这类能力这是致命缺陷，已在技能里加了"日期必须取自运行环境"的硬约束，但根因在 harness 未把当前日期作为强约束注入。
- 侧栏「云端协同 BETA」角标仍用 `#ff4d4f`（`src/layouts/Sidebar.tsx:215`），用户头像也仍在上游的玫红配色板里（实测：对话流右侧的头像气泡、左下角用户菜单里的 "Demo Admin" 头像）。这些是语义"提醒"色与头像调色板，不是品牌主色，目前判断不改；要改就得动 `utils/expertColor.ts`，那是每次追版都要复核的文件。
- `octop-mascot-peek.webm`、`octop-mascot-type.webm`、`octop-mascot-tasks.png` 在代码里**无人引用**（前端只用 `.webp`），属上游死资产，仍随构建产物发布，暂未处理。
