# z10 实施方案 · 从「三栏专家制」改成「一栏助手制」

目标版本：`1.0.2b6+z10`（本期只装 M1/M2/M4a/M5a/M6/M7），tag `v1.0.2b6-z10`。
主题不是加功能，而是**让一个没用过的人打开就能聊、聊起来不用选专家、左边只看到自己需要的东西**。

上游基线不变（`v1.0.2b6` / `0c5a46a`）。交接快照见 [`HANDOVER.md`](./HANDOVER.md)，
写代码前读 [`CONVENTIONS.md`](./CONVENTIONS.md)。本文所有位置都是 `D:\otp\Octop` 下核对过的
`file:line`；§1.1 的布局表与 §1.8 的三处缺陷由 `scripts/verify/layout_probe.py` 在 1280×800
真实渲染量出来的（截图与 `report.json` 落在 `.zc-verify/layout/`，未跟踪）。

---

## 0. 七个决策

| # | 决策 | 选定的做法 |
|---|---|---|
| D1 | 中间那一栏要不要留 | **默认不留**。两栏模式（`minimal`）早就写好了，只是默认值是 `classic`。本期把默认翻过来，开关从头像下拉搬进「设置」。不删中间栏的能力，让它成为可选项 |
| D2 | 会话列表按什么排 | **按活跃度、跨专家、扁平**。专家降级为条目上的头像徽标 + 顶部筛选 chip。需要新后端查询与一条索引（M3，z11） |
| D3 | 「对话中切换专家」怎么实现 | **不原地改 agent_id，做 fork-to-agent 接手**。复用已存在的 fork 机制，只把硬绑的目标专家放开 |
| D4 | 专家概念要不要对用户消失 | **不消失，但降级为可选**。会话、线程、workspace、checkpointer 全部以 agent 为轴（见 1.6），删它是重写后端。改成"首启只有一个 `main`，其余专家你随时可加" |
| D5 | 内置 API key 免费先用 | **做，但拆两半**：z10 只做首启文案与两条入口（体验 / 粘 Key）；真内置 key（M5b）必须有 CI 注入 + 掩码 + 每-provider 限额 + 换 key 路径，四件齐了才进版本 |
| D6 | 左栏精简多少项 | **6 项**：对话、专家、知识库、技能、任务、设置。其余全部收进「设置」二级页；角色不够的条目**隐藏**而不是禁用 |
| D7 | 本期范围 | M1+M2+M4a+M5a+M6+M7 进 z10；M3+M4b 进 z11；M5b 进 z12 |

**为什么这么切**：M1/M2/M4a/M5a/M6 全是默认值与前端改动，可单独回退、不碰数据库；
M3 要加 migration（schema v20→v21），M4b 要动 fork 与 harness，M5b 要动 CI secret 与限额。
把不可回退的和可回退的混在一个版本里，出问题只能整版回滚。

---

## 1. 现状事实（逐条实测，含推翻我们自己直觉的两条）

### 1.1 三栏不是设计出来的，是默认值没翻

- `dashboard/src/layouts/layoutModeStorage.ts:11-19`：`loadLayoutMode()` 在无存储时返回 `"classic"`。
  注释 `:1` 自己写着 `classic (dual rail) vs minimal (single nav with settings/records)`。
- `dashboard/src/layouts/MainLayout/index.tsx:236`：中间那栏（`CHAT_HISTORY_RAIL_ID`）**只在 `!isMinimalLayout` 时渲染**。
- `dashboard/src/layouts/Sidebar.tsx:614-685`：`minimal` 分支里，同一个左栏下半部就是 records pane
  （`:677-683` 把 `CHAT_HISTORY_RAIL_ID` 挂在侧栏内），`:654-670` 是 settings pane，二者由 `paneToggle` 切换。

→ **结论：用户说的「中间多了一列」，我们的仓库里已经有一个把这列合掉的布局，只是默认关着、开关藏在头像下拉**
（`components/AvatarDropdown.tsx:602-615`，`account.layoutMode` / `layoutModeHint`）。
本期最高杠杆的一行改动就是这个默认值。

**已实测（`scripts/verify/layout_probe.py`，1280×800，HEAD 构建，报告在 `.zc-verify/layout/report.json`）**：

| 状态 | 可见列数 | 会话栏位置 | 会话列表可见 | 左栏主导航 |
|---|---|---|---|---|
| `classic`（今天的默认） | **3** | 独立中列 | 是 | 3 项 + 设置/控制/管理 10 项 = **13 项** |
| `minimal` + 任务 pane | **2** | 收进左栏下半部 | 是 | 3 项（对话/专家/自动化） |
| `minimal` + 设置 pane | **2** | 左栏内，但被 `hidden` | **否** | 13 项 |

→ 两栏目标**不需要新写布局**，`minimal` 已经是"左栏 3 项 + 下方任务 pane"的形状。
→ 1.1 开头那个担心**已被证实为真缺陷**：切到设置 pane 时 `Sidebar.tsx:680` 把 records pane 整个 `hidden`，
**历史会话与"新对话"入口一起消失**（输入框还在内容列，所以"发起新对话"仍可打字，但"找回旧对话"做不到）。
M1 的验收门因此不是"能不能两栏"，而是"pane 切换会不会让人丢历史"。

### 1.2 中间栏是「专家手风琴」，不是任务列表

`pages/Chat/components/SessionList.tsx:556-654`：`expandedAgentId` 只展开**一个**专家的会话（`ActiveAgentCard`），
其余专家全是 `InactiveAgentRow`（`:643-653`）。会话数据来自 `pages/Chat/hooks/useSessions.ts:3-5`
→ `octopThreadsApi.list`，即 **per-agent 查询**。

→ 用户的真实感受是「每个专家各有一套对话，换专家等于换世界」，而不是「我在跟一个助手继续聊」。
这是「对话有点乱」的第二根因，比列数更本质。

### 1.3 左栏项目数与「设置」的语义过载

- 目录 `layouts/sidebarNav.tsx:51-71`：**19 个 key**；分组 `:73`（settings / control / admin）；
  装配 `buildNavSections` `:134-315`。
- 精简开关 `branding/navSimplicity.ts:13-23`：默认只藏 **5 项**（bridge / remote-desktop / acp / token-usage / admin-storage），
  而它自己的开关在 **`/admin/advanced`**（`pages/Admin/BrandingSettings.tsx:190`）——普通用户根本进不去那个页面。
  结果：想精简的人精简不了，管理员反而默认看得最全。
- 「设置」这个词在本产品里同时指：个人化、频道、连接器、技能包、知识库（个人）+ 模型、用户、存储、插件、安全、高级（管理）。
  两类东西在同一条栏里，是"设置太多了"的直接来源。
- 两处会咬人的锁：`layouts/sidebarNav.test.ts:47-60` 钉死精确 key 集合与分组顺序；
  后端镜像 `src/octop/infra/users/preferences.py:22-44` 的 `SIDEBAR_NAV_KEYS`。**改 key 集合必须同时改这两处**，
  否则用户自定义导航（`SidebarNavCustomizer.tsx`）会漂。

### 1.4 对话里的能力开关被两道门挡住 —— 用户要的「对话中切换专家」其实已经存在

`pages/Chat/components/ChatInputActionsRow.tsx`：

- `:266-287`：连接器、技能、**专家**、子代理 四个 picker 的前置条件都是 `allowWriteTools = conversationMode === "craft"`。
  模式只有 ask / plan / craft 三种（`pages/Chat/index.tsx:862`，`utils/conversationMode.ts`）。
  **普通用户默认停在 ask，永远看不到"可以 @ 别的专家"。**
- `:609-766` + `:839-871`：这 7 个 picker 在桌面端也全部收进一个 `+` 弹层（`data-testid="composer-plus"`），
  输入框常显行上没有模型、没有专家、没有任何持久选择器。
- `:717-740`：专家 picker 选中后走的是 mention（`mentionedExperts`），
  后端对应 `ChatTurnBody.target_agent_ids` —「Optional agent ids to involve via @mention (same user only)」
  （`src/octop/api/routers/chat/models.py:64-67`，落地 `turn.py:284-288,356-358`，
  键法 `gateway/process/message_keys.py:32,49-50`，UI `components/MentionPickerMenu.tsx:19,61,130`）。

→ **结论：「像 WorkBuddy 那样在对话里切专家」不是要新造能力，是要把已有能力从 craft-only + `+` 后面挪出来。**

### 1.5 推翻一条：「专家还要新建才能对话」已经不成立

- `/setup/finish` 会自动创建默认专家：`api/routers/setup.py:440-446` → `_bootstrap_default_agent` `:155-172`
  → `infra/agents/experts/default_agent.py:48-83`（钉住 `agent_id="main"` `:24`，模板 `general-assistant` `:23`，fail-soft），
  邀请注册走同一条 `api/routers/invites.py:154-167`。测试已钉：`tests/integration/test_setup_bootstrap.py:28,42,111`。
- setup 向导 5 步 password→database→admin→model→finish（`pages/Setup/index.tsx:226-239`），
  其中**模型步本来就能跳过**（`steps/ModelStep.tsx:570-576` 的 `onSkip`，接到 `Setup/index.tsx:321-325`）。

→ 真正卡住首聊的只有一件事：**跳过了模型步，就没有任何兜底**。

- 兜底缺失的机制链：`providers/store.py:111-125` `iter_usable_rows` 要求
  `enabled AND base_url AND api_key AND ≥1 chat-eligible model`（已核对源码）；
  没有可用 provider 时 agent 落 `failed` + `NO_MODELS_CONFIGURED`（`infra/agents/manager.py:2561-2563`，
  文案 `i18n/domains/agents.py:9,52`）；Chat 首页据此判定 `noAgents` / `agentChatReady`
  （`pages/Chat/index.tsx:235,208`）并渲染 `ModelConfigEmpty`，按钮把用户赶去 `/admin/models`
  （`:1386-1393`，`components/ModelConfigEmpty.tsx:37`）。
- 顺带：`_apply_provider_draft` 直接拒绝空 key/base_url（`setup.py:177-182`）—— 所以"先留空、以后再说"在产品里是死路。

### 1.6 数据模型对「换专家」允许什么、禁止什么

| 事实 | 位置 | 对设计的含义 |
|---|---|---|
| `threads.agent_id TEXT NOT NULL REFERENCES agents(agent_id) ON DELETE CASCADE` | `infra/db/migrations/001_initial.sql:133-146` | 一个线程只能属于一个专家，这是 schema 级约束 |
| 索引 `idx_threads_agent_active ON (agent_id, last_active DESC)` | `001_initial.sql:145` | 现有一切查询都是"某专家的线程" |
| `thread_messages` **无 agent 列**；发言者在 `message_json.additional_kwargs.speaker_agent_id` | `010_thread_message_projection.sql:7-20`；序列化 `api/routers/chat/serialize.py:954-960,1020-1022` | 逐条发言者身份**已经存着**，只是没人用它做"换人" |
| 每个 harness 实例自带 checkpointer，线程状态物理存在该 agent 实例内 | `manager.py:1861`，`serialize.py:403-409` | **原地改 agent_id 会让历史读不到**，这不是加个 `set_agent_id` 能解决的 |
| rebind 显式拒绝跨专家 | `infra/gateway/threads.py:258-265`，`chat/turn.py:69-76`，`chat/ws.py:107,128`，`chat/history.py:86-96` | 报错点有四处，绕过它等于同时改四处校验 |
| **fork 已实现**：读全量转录→定位锚点→建新线程→把前缀写进新线程 checkpoint→复制 composer 偏好→重绑 session | `infra/agents/threads/fork.py:181-289`（`:236-238` 硬绑 `source.agent_id`，`:246` 用源 harness 写 checkpoint，`:269-274` 复制偏好，`:275-279` 重绑） | 换专家 = 让 fork 支持目标专家。改动集中且小 |
| 团队房已支持一条会话里多个专家发言（`ask_agent` + `speaker_agent_id` + 逐条气泡） | `infra/agents/teams/team_manager.py:807,819-823,870,900,1411-1417`；`components/MessageBubble.tsx:554-575`；`TeamChatBadge.tsx` | 多专家同框的**渲染能力已上线**，不用新造 |
| WS 按专家建连：`/agents/{agent_id}/chat/ws`；帧里只有 `thread_id` | `dashboard/src/api/modules/wsChat.ts:7`，`chat/models.py:30-37`，`hooks/useChatSend.ts:109` | 一次连接只能一个专家，所以"切人"必然伴随重连或新线程 |

`repos/threads.py` 只有 `list_by_agent:193` / `list_by_agent_user:207` / `list_by_session:220`，
**没有任何"我的全部线程按时间"的查询**（搜过 `list_by_user`、`FROM threads WHERE user_id`、`/sessions`）。
D2 要的扁平时间线，后端目前是缺的。

### 1.7 内置 key 的暴露面（实测，别自欺）

- `providers.api_key TEXT` —— **明文，无加密**（`001_initial.sql:52-63`）。`secrets` 表（`:224-229`）只放 JWT secret（`setup.py:369`）。
- `GET /api/providers` 与 `GET /api/admin/providers`（`api/routers/providers.py:189-195,203-208`）都经
  `_row_to_dict` **把 api_key 原样返回给浏览器**（`:134`，已核对），任何登录用户可取。
- 桌面产物是**未冻结源码**：Wails Go（`desktop/src/*.go`、`desktop/embed_portable.go`）+
  `python-build-standalone`（`desktop/portable/bootstrap-runtime.sh:2`）+ vendored wheels，
  site-packages 里的 `.py` 直接可读。
- `scripts/rebrand.py:1-30,49,60,63` 是**展示字符串**替换，且刻意不碰标识符（`:8-13`）——
  它是通用文本机制，**今天没有任何 secret 注入机制**。
- 限额现状：per-user `token_quota`（`infra/agents/middleware/token_quota.py:10,37`，接在 `manager.py:3213`，
  策略入口 `api/routers/users.py:170-176,196-197,356-359`）；限速只对向导密码（`setup.py:333-335`）和邀请（`invites.py:142,157`）。
  **无 per-provider、无全局 LLM 限速。**
- 仓库是**公共的**。

→ 内置 key **一定**会被提取。这不是可以靠工程藏住的事，只能靠"可吊销 + 限额 + 熔断"把它变成可运营的损失。
且红线不动：**任何文档/文案都不许写"密钥不落盘"**（providers 表就是明文落盘）。

### 1.8 截图里能看见、但读代码看不见的三处首启缺陷

探针跑出来的 `.zc-verify/layout/shots/*.png` 上直接可见：

1. **首启弹窗压在欢迎区正中**：「三步就能开始用」卡片浮在内容列中央，
   把欢迎语与示例问题挡住；它出现的时机是"还没发过消息"，也就是**每个新用户的第一眼**。
   它本身是 z08 M7 的产物，方向对，形态错——应该是输入框上方一条可关的窄提示，不是居中卡片。
2. **第 1 步「配置一个模型」是假绿灯**：探针只往 `providers` 表塞了一条指向
   `http://127.0.0.1:9/v1` 的死端点（创建 provider 不做任何探测，`providers.py:214-230`），
   这一步就打了勾。→ 行事历判的是"表里有行"，不是"模型能答"。这正是 z09 学过的教训
   （**验能力不验字节**）在首启引导里的复发：用户按引导走完三步，第一条消息照样失败。
3. **会话默认标题硬编码英文**：`pages/Chat/hooks/useSessions.ts:64,525,534` 写死 `"New Chat"`，
   中文界面里三条历史会话全叫 "New Chat"（截图可证），既不出中文也没法区分。
   后端标题是 `set_title_if_null` / `update_title`（`repos/threads.py`），首条消息前无标题 →
   需要本地化的占位标题 + 用第一条消息内容做区分。

---

## 2. 目标形态

```
现状（classic，默认）                     目标（z10 默认）
┌────┬──────────┬────────────────┐        ┌────────────┬──────────────────────┐
│导│  │ 专家 A ▼ │                │        │ 对话        │                      │
│航│  │  会话 1  │                │        │ 专家        │   一条时间线          │
│ 对 │  │  会话 2  │   消息区       │   →    │ 知识库      │   （跨专家按时间）     │
│ 话 │  │ 专家 B   │                │        │ 技能        │                      │
│ 专 │  │ 专家 C   │                │        │ 任务        │  [专家 chip ▾]       │
│ 家 │  │          │                │        │ 设置        │  ┌────────────────┐  │
│ 设 │  └──────────┘                │        └────────────┤  │ 输入…       ➤ │  │
│ 置 │                            │                        │  └────────────────┘  │
└────┴──────────┴────────────────┘                        └──────────────────────┘
 19 个 key，默认露 8~14 项            6 项 + 一个「设置」聚合页；会话不再按专家分组
```

输入框常显行上只放三样，其余进 `+`：**当前接手的专家**、**模型**、附件。
`+` 里剩连接器 / 技能 / 子代理 / 知识库 / 模式，且**不再要求 craft 模式**才出现。

心智模型一句话：**用户面对的是"一个助手 + 一堆会话"；专家是这个助手可以叫来的人，不是不同的登录账号。**

---

## 3. 改造项

### M1 · 默认两栏（工作量最小，收益最大）

改哪里：
1. `layouts/layoutModeStorage.ts:11-19` —— 无存储时返回 `"minimal"`。
   已存 `classic` 的老用户**不动**（不主动改别人的偏好）。
2. 「显示全部功能」开关从 `/admin/advanced`（`branding` + `BrandingSettings.tsx:190`）搬到**用户级**设置页；
   与布局开关（`AvatarDropdown.tsx:602-615`）并排，都在「设置 → 界面」里出现。头像下拉里保留一份不删。
3. 补 1.1 实测到的真缺陷：`Sidebar.tsx:680` 在 pane 切到 `settings` 时把 records 整个 `hidden`，
   **历史会话与"新对话"一起消失**（探针三种状态各截一张图证实）。
   方案：records 不再被 `hidden`，而是让"设置"作为叠加层（浮层/右侧抽屉）盖在左栏上，关掉就回到会话；
   即"会话是底盘，设置是叠加"，不是两个互斥 pane。
4. `MainLayout/index.tsx:103,145-154` 里 `isMinimalLayout` 的两条 early-return 要跟着复核
   （它们跳过的是 classic 的自动展开与折叠持久化）。

会碰到的测试：`layouts/layoutModeStorage.test.ts`（钉了默认 `classic`，必须同步改，否则门禁假绿）。
验收门（前三条已实测，作为现状基线；改完复测）：
- `classic`：3 列、会话栏是独立列、左栏 13 项 —— 现状基线；
- 全新 profile 打开 `/chat`：2 列、会话栏在左栏内、左栏主导航 ≤ 6 项；
- **切到设置视图后，历史会话仍在** —— 现在是 FAIL，用
  `python scripts/verify/layout_probe.py --python .venv/Scripts/python.exe --port 8097 --expect-fixed`
  钉住：今天它退出码 1 并打印 `records pane is hidden …`，M1 做完必须变 0。
  （不带 `--expect-fixed` 的那趟是量现状、退出码 0，别把它读成"已修好"。）
- 已存 `classic` 的 profile 升级后仍是 classic（防"顺手改了老用户偏好"）。

### M2 · 左栏 6 项 + 「设置」聚合页

改哪里：
1. `layouts/sidebarNav.tsx:134-315`：顶层只留 chat / experts / knowledge-bases / skill-packages / tasks + 一个 `settings` 条目；
   其余 key 保留在 `SIDEBAR_NAV_KEYS`（`sidebarNav.tsx:51-71`）里——**不删 key，只改归属**，
   否则用户偏好与后端 `preferences.py:22-44` 的镜像会漂。
2. 新增「设置」页（路由 `/settings`）：一张分组清单，条目直接复用现有路由
   （`/admin/models`、`/connectors`、`/personalization/channels`、`/admin/users`、`/admin/security`、
   `/admin/backend`、`/admin/plugins`、`/token-usage`、`/bridge`、`/remote-desktop`、`/acp`、`/workbench`）。
   **不新建任何功能页**，只做收纳；权限不足的条目**隐藏**（沿用 `utils/permissions.ts` 的 `navAllowed`）。
3. `navSimplicity.ts:17-23` 的 5 项继续藏在「显示全部功能」后面，与 M1 的用户级开关合并成同一个机制，别留两套。
4. 同步 `sidebarNav.test.ts:47-60` 与 `sidebarNavLayout.test.ts`。

验收门：普通用户首屏左栏可见条目 ≤ 6；管理员 ≤ 7；`/settings` 里每一项都能跳到已有页面且无死链；
用户自定义导航（`SidebarNavCustomizer.tsx`）在旧偏好下不报错（key 未删，只移位）。

### M3 · 会话列表扁平化（z11）

改哪里：
1. 新 repo 方法 `ThreadsRepo.list_recent_for_user(user_id, *, q, limit, offset)` →
   `SELECT t.*, a.name, a.avatar, a.color FROM threads t JOIN agents a ON a.agent_id=t.agent_id
   WHERE t.user_id=? ORDER BY t.last_active DESC`，加在 `repos/threads.py:193-230` 附近。
2. 新 migration `idx_threads_user_active ON threads(user_id, last_active DESC)`（schema **v20→v21**）。
   ⚠ `tests/unit/db/test_db_pool.py` 钉了 `v == 20`，必须同步；迁移写法照 `004_thread_composer_preferences.sql` 的加列模式。
3. 新端点 `GET /api/threads?scope=mine`（返回 thread + agent 摘要，一次 JOIN，避免前端 N× 扇出）。
4. 前端 rail：顶部常驻「新对话」→ 默认落到 `main`（`default_agent.py:24` 的 `SETUP_DEFAULT_AGENT_ID`）；
   列表条目 = 标题 + 相对时间 + 左侧专家头像徽标（复用 `utils/expertColor.ts` / `expertAvatar`）；
   顶部一行筛选 chip（全部 / 各专家）。`SessionList.tsx:556-654` 的手风琴分支替换掉，
   但 `InactiveAgentRow` 的"隐藏专家"能力保留（`:602-613,655-665`）。
5. 保留逃生舱：`GET /api/agents/{id}/threads`（`chat/history.py:99-140`）不动，专家详情页仍看该专家会话。

性能约束：`useChatSidebarState.ts:110-116` 的注释记录过"每帧 setState 导致 rail 卡顿"的教训，
新列表同样要避开 pointermove 期间的 React 重渲染。

验收门：3 专家 × 20 会话 → `GET /api/threads` 返回 60 条且 `last_active` 单调不增；
分页 + 搜索走单测；点击条目不触发整列重渲染（用现有 vitest + 一次真实 1280px 观察）。

### M4 · 对话中换专家

**M4a（z10，纯前端）：把已有能力挪出来**
1. 专家 chip 常驻输入框常显行（现在 `ChatInputActionsRow.tsx:717-740` 在 `+` 里，且 `:276-281` 要求 craft）。
   去掉 `showExpertPicker` / `showSubagentPicker` 的 `allowWriteTools` 前置——mention 与写工具无关。
2. 模型 picker 同样提到常显行（`:263-265`）。
3. 文案：`chat.expertPicker` 改成「请谁来答」而不是"专家"术语；ask/plan/craft 三个模式名保留但补一句人话解释
   （`utils/conversationMode.ts`，`i18n/zh.json`）。
4. 空状态重写：`ModelConfigEmpty` 的按钮现在把人赶去 `/admin/models`（`ModelConfigEmpty.tsx:37`）。
   改成页面内直接给两条入口（接 M5a），别再跳管理页。

**M4b（z11，后端）：fork-to-agent「由 X 接手」**
1. `ForkThreadBody`（`chat/models.py:152-165`）加 `dest_agent_id`；路由 `chat/history.py:419-456` 校验
   **目标 agent 属于同一 user**（与 `target_agent_ids` 的 same-user 规则一致，`models.py:64-67`）。
2. `fork_dashboard_thread`（`fork.py:181-289`）：把 `:236-238` 的 `source.agent_id` 换成解析后的目标 agent；
   `write_checkpoint_messages`（`:159-178`、调用点 `:246`）的 `harness` 换成**目标 agent 的 harness**
   （从 manager 取，`_start_agent` `manager.py:2558-2600`）。目标 agent 未启动 → 先 bootstrap；
   `failed`（无模型）→ 返回明确错误码，不要静默半成功。
3. session key 用目标专家重建（`ThreadRegistry.dashboard_key(agent_id=…, user_id=…)` `:236`）；
   `archive.begin(source.agent_id, dest_id)`（`:247-251`）也要跟着换成目标 agent，否则归档段记错人。
4. 呈现：新线程第一条位置渲染分隔卡「⤷ 由 <专家X> 接手 · 原会话《…》保留」（点得回原文）。
   复用团队房已有的逐条发言者渲染（`MessageBubble.tsx:554-575`）。
   顺手补 `parent_thread_id`：现在 fork 不留父线程，只有标题后缀（`fork.py:25-30`），加一列才能可靠"点回原文"。

**明确不做**：原地 rebind `threads.agent_id`。schema FK（`001:135`）+ checkpointer 物理绑在 agent 实例
（`manager.py:1861`）+ 四处校验（`threads.py:258-265` 等），绕过它的代价是把历史读断，得不偿失。
用户视觉上"接着聊"用 fork + 接手卡就够了，语义上仍是两个线程——**这一点在 UI 上要说实话**（写"接手"不写"切换"）。

### M5 · 首启零配置能聊

**M5a（z10）：把"跳过之后没有兜底"变成"跳过即进体验"**
1. `Setup/steps/ModelStep.tsx` + `Setup/index.tsx:321-325`：模型步从"填表"改成两张大卡——
   **「先免费试试」**（零输入）与**「我来粘贴 Key」**（选厂商 → 粘 key → 自动 test → 自动写 `active_model`）。
   厂商列表用已存在的无鉴权 presets 接口（`GET /api/setup/presets`，`setup.py:215`）。
2. `setup.py:177-182` 目前直接拒绝空 key/base_url；改成：provider_draft 为空时落"体验 provider"（M5b）或
   留一个明确的"待配置"状态（而不是把 agent 打成 `failed`）。
3. `NO_MODELS_CONFIGURED` 的文案（`i18n/domains/agents.py:9,52`）从错误语气改成引导语气，并给出下一步按钮。
4. 首启三步行事历（z08 M7 已建）接上第 0 步「说第一句话」。

**M5b（z12）：真内置 key —— 四个条件缺一就不做**
| 条件 | 现状缺口 | 要做 |
|---|---|---|
| key 不进公共仓库 | 今天无 secret 注入机制（`rebrand.py:1-30` 只换展示文本） | CI 构建时从 secret 写进产物的独立 `trial_key` 文件；源码树里恒为占位符；加一条 CI 检查：仓库内搜不到该 key 指纹 |
| key 不回吐给浏览器 | `providers.py:134` 原样返回 | trial provider 走掩码分支；普通 provider 不变 |
| 花了多少能止血 | 只有 per-user `token_quota`，**无 per-provider 限额**（`token_quota.py:10,37`） | trial provider 单独日 token 上限 + 并发上限 + **运行时可关的熔断开关**（不发版就能停） |
| 能换 key | 客户端有自更新（`self_update.parse_version` / `desktop/src/version.go`） | 换 key 走一次小版本（`+z12.1`）推下去；CHANGELOG 里写明"体验额度可能被滥用，不承诺长期免费" |

文案红线：**任何地方不写"密钥不落盘"**；不写"永久免费"。

**并行低成本路线**：把 Ollama 做成"本地免费"卡片。`kind` 里已有 ollama（`store.py:22`、`infra/utils/ollama_manager.py`），
但 `iter_usable_rows`（`store.py:111-125`）要求 `api_key` 非空 → ollama 需要允许哨兵值（**一处校验改动**，
且要同步 `tests/unit/agents/test_provider_store.py:55`）。
诚实边界：**没有 chat-capable 的本地模型路径**（ONNX 只做 embedding，`onnx_service.py:1-5`），
所以离线场景只能引导用户自己装 Ollama，不许写"完全离线也能聊"。

### M6 · 建专家从 11 个字段降到 1 个动作

- 现状：`pages/Experts/components/CreateFromExpertDrawer.tsx:655-834` 有 11 个 Form.Item、2 个必填；
  而 `AgentCreateBody`（`api/routers/agents.py:43-59`）只要 `name`；
  一键模板 API 已存在：`POST /api/agents/from-expert/{expert_id}`（`api/routers/experts.py:841-886`）；
  库里有 18 个模板（`src/octop/infra/agents/experts/library/`）。
- 改：专家页首屏改成模板卡（一张卡一句话 +「用」按钮直接调 from-expert），完整表单折叠进"自定义创建"。
- 内容工作（比代码更重要）：现有模板里 `cvm-ai-doctor` / `tencentcloud-api` / `wechat-ops` / `meituan-living-assistant`
  等与 zcagent「企业内个人助手」场景无关，**要挑 4~6 个面向普通办公的重写**（制度问答、会议纪要、周报、合同要点、数据表清洗）。
  模板是仓库文件，改它们属于我们的 OEM 层，不影响上游合并。

### M7 · 修掉截图里那三处（z10，工作量小但都扎眼）

对应 1.8：
1. 「三步就能开始用」从居中卡片改成输入框上方一条可关的窄提示，不再挡欢迎语与示例问题。
2. 第 1 步的判定从"providers 表有行"改成**真的探一次**：复用已有的 1-token `ainvoke("ping")`
   探测（`infra/agents/providers/probe.py:249`），失败就显示"配了但连不上"而不是打勾。
   这是 z09「验能力不验字节」原则在引导流程里的落地。
3. `"New Chat"` 占位标题本地化（`useSessions.ts:64,525,534`），并在列表里用第一条消息内容做区分。

---

## 4. 明确不做的事

1. **不删专家概念**。threads / workspace / checkpointer / 知识默认值全部以 agent 为轴
   （`001:135`、`manager.py:3338-3385`、`processor.py:1534`），删它等于重写后端。
2. **不原地改线程的 agent_id**（理由见 M4 末）。
3. **不把 key 藏进客户端**。提取是必然（1.7），只做可运营的止血，不做伪装成安全的工程。
4. **不在 z10 动 schema**。migration 与 UI 默认值分版本，回滚粒度才够细。
5. **不在公共仓库提交任何真实凭证**（含体验 key、演示管理员口令）。

---

## 5. 分期

| 版本 | 内容 | 回滚方式 |
|---|---|---|
| **z10** | M1 默认两栏、M2 左栏 6 项 + 设置聚合页、M4a 专家/模型 chip 常显 + 空状态重写、M5a 首启两条入口、M6 模板一键、M7 三处观感 | 逐项可退：M1 是一行默认值；M2 只改归属；M4a/M5a/M6/M7 是前端 |
| **z11** | M3 扁平会话（含 schema v21 索引）、M4b fork-to-agent + `parent_thread_id` | 新端点与新索引不改旧行为；旧 rail 可切回 |
| **z12** | M5b 内置体验 provider + 掩码 + per-provider 限额 + 熔断 + CI 注入 | 熔断关 → 行为退回 z11 |

---

## 6. 验证方法（我们踩过的坑，写死在这）

1. **布局用 `scripts/verify/layout_probe.py`，不要用内置浏览器**。
   内置浏览器只有 465px 宽，看不到桌面两栏；探针自己起一个 scratch 控制面
   （独立 `OCTOP_HOME` + 空闲端口 + 走完向导），在 1280×800 下逐个布局状态量列数、
   会话栏归属、pane 切换后还剩什么，并出 PNG + `report.json`。
   1.1 那张表就是它跑出来的，M1 的验收门复用它。
   约定仍然是：**断言 className / DOM 存在性，不断言过渡动画中途的 inline style**。
2. **版本徽章读的是发行元数据，不是源码**。`self_update.get_local_version()`
   （`infra/setup/self_update.py:137-143`）走 `importlib.metadata.version("octop")`，
   而 `.venv` 里的 editable 元数据长期停在 `1.0.2b6+z02`，源码 `src/octop/__init__.py:7` 已是 `+z09`
   —— 探针第一次跑出来的截图上徽章就写着 z02。**任何以版本徽章为证据的验收，先确认元数据**：
   `python -c "import octop,importlib.metadata as m; print(octop.__version__, m.version('octop'))"`
   两个值不一致就 `uv pip install -e . --no-deps` 刷新（本机 venv 无 pip，只能用 uv）。
   刷新后同一份源码、同一张截图，徽章变成 z09 —— 控制实验做完了。
3. 前端门禁四条都要绿：`npm run lint`、`npm run test`（vitest）、`npx tsc -b`、`npm run build:prod`。
   本机 node **不在 PATH**；实测可用的是
   `/c/Users/Administrator/.workbuddy-ai/binaries/node/versions/22.22.2-2`（v22.22.2 + npm 10.9.7，
   `npm run build:prod` 全绿），`C:\Program Files\nodejs` 也有一份 v24。每次 Bash 都要重新 prepend。
   `format` 跳过（无 node/prettier）的测量结果**不可信**，别拿它当"格式已过"。
   `src/octop/dashboard/` 是**未跟踪的构建产物**（`git ls-files` 为 0），重建它不会脏化工作树。
4. Python 单测只跑改到的文件，全量 pytest 在这台机器上要几小时。
5. 装机验收继续用 `scripts/verify/client_release.py` 的既有阶段，本期新增两条真能力断言
   （**验能力不验字节**，z09 的教训）：
   - 全新 profile 首启 → 跳过模型步 → 仍能发出第一条消息并拿到回复；
   - 会话里点「请谁来答」选另一个专家 → 新线程里有接手卡、原会话仍在、历史可读。
6. 每次改 `SIDEBAR_NAV_KEYS` 同时跑 `sidebarNav.test.ts`（`:47-60` 用
   `toEqual(new Set(SIDEBAR_NAV_KEYS))` 钉死集合，已核对）和后端
   `infra/users/preferences.py:22-44` 的镜像，防两侧漂移。

---

## 7. 与并行 agent 的耦合

`git status` 实测：工作树里对面未提交的是 **21 个 `site/landing` 文件**（含新增的
`connectors/skill-market/tasks/expert-market` 四张复刻屏），**dashboard 侧一个都没有**，
所以本期动 `sidebarNav.tsx` / `SessionList.tsx` / `ChatInputActionsRow.tsx` 不与之冲突。
共享文件仍按 z09 的做法：`git hash-object -w` + `git update-index --cacheinfo` 只提交自己的 hunk，
不 `git add -A`、不 `git stash`；只取 token 交集。

