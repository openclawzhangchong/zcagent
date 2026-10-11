# z08 实施方案 · 新手第一分钟

目标版本：`1.0.2b6+z08`，tag `v1.0.2b6-z08`。
主题不是加功能，而是**让一个没用过的人能在不查资料的情况下把知识库用起来**。

上游基线不变（`v1.0.2b6` / `0c5a46a`）。交接快照见 [`HANDOVER.md`](./HANDOVER.md)，
写代码前读 [`CONVENTIONS.md`](./CONVENTIONS.md)。

---

## 0. 已定的四个决策

| # | 决策 | 选定的做法 |
|---|---|---|
| D1 | 默认向量模型什么时候下载 | **空闲预下载 + 失败回退**：客户端启动后延迟探测网络，静默下 `BAAI/bge-small-zh-v1.5`；失败不打扰用户，等用户打开知识库设置时自动重试并显示进度；设置里留「提前准备向量模型」开关 |
| D2 | 知识库默认名称/描述 | **真默认值，可改**：输入框预填，用户直接点确定就能建 |
| D3 | 默认值推广范围 | **全部 11 处，但分主次**：高频 4 处给真默认值，中低频 7 处只补有效示例提示 |
| D4 | z08 范围 | **4 项 + 首启三步行事历**（错误文案收口推到 z09） |

---

## 1. 现状事实（全部实测或带位置，不是推测）

### 1.1 模型目录

- 目录**只在后端一处**：`src/octop/infra/agents/providers/onnx_catalog.py`，
  presets `:8-12`、extras `:17-27`、兜底体积 `:30-43`、HF 源别名 `:46-59`。
- `_model_entry` `:62-78` 只产出 `id / name / recommended / size_gb / hf_source`。
  **没有任何"这个模型适合什么"的字段**，要做优缺点说明必须新增。
- `list_onnx_catalog_models` `:129-179` 会与真实 `fastembed.TextEmbedding.list_supported_models()` 合并。
- **实测：`?all_onnx=true` 返回 41 个模型**（本机 z07 客户端 `GET /api/knowledge-bases/embedding-options`），
  不是我们以为的 12 个。`_onnx_options_for_knowledge` `knowledge_bases.py:256-271` 在 `include_all` 时
  直接返回整个 fastembed 列表，里面包括 `Qdrant/clip-ViT-B-32-text` 这种**给知识库用完全错误**的 CLIP 模型。
  → 用户点「展开更多」看到的是 41 行陌生英文模型名，这是本次最严重的信息不对称。

### 1.2 中文可用的模型只有 6 个（实测 fastembed 41 个里筛出来的）

| 模型 | 维度 | 上下文 | 体积 | 语言 |
|---|---|---|---|---|
| `BAAI/bge-small-zh-v1.5` | 512 | 512 token | 0.09 GB | 中文 |
| `jinaai/jina-embeddings-v2-base-zh` | 768 | **8192 token** | 0.64 GB | 中英混排 |
| `intfloat/multilingual-e5-large` | 1024 | 512 token | 2.24 GB | ~100 语言 |
| `minishlab/potion-multilingual-128M` | — | — | 0.512 GB | 多语种（**不在我们目录**） |
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 384 | **128 token** | 0.22 GB | ~50 语言 |
| `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` | 768 | 512 token | 1.0 GB | ~50 语言（**不在我们目录**） |

**结论：中文场景实际只有前三个是正经选择。** 目录里其余 9 个精选模型全是英文模型。

### 1.3 已确认的两个真缺陷

**缺陷 A：e5-large 是静默质量陷阱。**
fastembed 自己的模型描述写着 `Prefixes for queries/documents: necessary`——e5 系列要求查询端加 `query:`、
文档端加 `passage:`，不加会明显掉召回。
实测 `grep -rn "passage:" src/octop/` **零命中**，全仓没有任何地方加前缀。
→ 用户选了「推荐」里那个 1.2 GB 的大模型，检索质量反而不如 92 MB 的小模型，而且**没有任何报错**。

**缺陷 B：`_FALLBACK_SIZE_GB` 有 6 条比真实值小一半以上。**
`onnx_catalog.py:30-43` 的兜底值 vs fastembed 实际元数据（本机逐条核对）：

| 模型 | 兜底显示 | 实际 | 偏差 |
|---|---|---|---|
| `BAAI/bge-small-en-v1.5` | 0.13 GB | **0.067 GB** | 多报 1.9× |
| `BAAI/bge-large-en-v1.5` | 0.53 GB | **1.2 GB** | 少报 2.3× |
| `jinaai/jina-embeddings-v2-base-zh` | 0.32 GB | **0.64 GB** | 少报 2.0× |
| `jinaai/jina-embeddings-v2-base-en` | 0.32 GB | **0.52 GB** | 少报 1.6× |
| `jinaai/jina-embeddings-v2-small-en` | 0.13 GB | **0.12 GB** | 基本正确 |
| `thenlper/gte-base` | 0.22 GB | **0.44 GB** | 少报 2.0× |
| `thenlper/gte-large` | 0.67 GB | **1.2 GB** | 少报 1.8× |
| `paraphrase-multilingual-MiniLM-L12-v2` | 0.12 GB | **0.22 GB** | 少报 1.8× |

（`bge-small-zh-v1.5` 0.09、`multilingual-e5-large` 1.2→2.24 也偏、`bge-base-en-v1.5` 0.21 与
`all-MiniLM-L6-v2` 0.09 正确。）
fastembed 能导入时用真实值、不能导入时用兜底值（`:140-142`），所以**同一模型在不同机器上显示的下载体积差一倍**。
用户截图里显示 328 MB / 1.2 GB，即那台机器走的是兜底分支——真实是 640 MB / 2.24 GB。
方向还不统一：有少报的也有多报的，说明这张表是早期凭印象填的。

### 1.4 下载链路（D1 要挂上去的地方）

- `POST /api/knowledge-bases/onnx-download` `knowledge_bases.py:467-477` →
  `DOWNLOAD_MANAGER.start_download` `onnx_service.py:487-535`。**非阻塞**（asyncio → `run_in_executor`），
  轮询 `GET /onnx-download-status` `:480-484`。
- 落盘：`~/.octop/embedding_models/models--<org>--<name>`（`onnx_service.py:188-196`）。
- 源：**COS / huggingface.co / hf-mirror.com 三源竞速**（`onnx_download.py:25-29,103-129`），
  4 秒 TTFB 探测，全失败抛 `RuntimeError`。内网机器三个都连不通——离线交付包就是为这个场景做的。
- **无校验和**（grep 无）、**无磁盘空间检查**、单文件原子但**跨文件不可续传**、失败留 `status=failed` 不清理。
- 已有后台任务先例可抄：`server.py:573-577` 的 `asyncio.create_task(_resume_bridges(), name="bridge-auto-resume")`。
- 桌面 Go 壳里**没有任何**模型预下载逻辑（`desktop/src/` 只有窗口定时器与应用自更新）。
- 前端已有"重新挂接进行中的下载"：`KnowledgeBases/index.tsx:1239-1248`。

### 1.5 开关与门禁

- 实例级开关是 settings KV：`knowledge_bases_enabled`（`infra/knowledge/gate.py:18`），
  全局唯一一行，无用户/专家维度 → 空状态文案"关闭后全实例都无法使用"**是准确的**。
- 关闭时 `assert_knowledge_usable` `:138-144` 抛 `KNOWLEDGE_FEATURE_DISABLED`（403）。
- 前置条件不满足时是 `KNOWLEDGE_PREREQUISITES_FAILED`（409），但实际抛的是裸
  `RuntimeError("ONNX embedding model is not configured or not downloaded")`
  （`knowledge_bases.py:279`、`onnx_service.py:371,374`），靠字符串匹配兜住（`:246-247`）。

### 1.6 首启路径与引导现状

- 向导步骤：密码→数据库→管理员→**模型（可跳过）**→完成（`Setup/index.tsx:226-239`、`ModelStep.tsx:575`）。
- 跳过后**不会**得到死对话：会 bootstrap 一个默认 `main` 专家（`setup.py:418-446`），
  专家起不来时对话页给引导卡片而非空输入框（`Chat/index.tsx:1384-1394`）。
- **全仓没有任何 onboarding**：无 AntD `Tour`、无 driver.js/intro.js/shepherd、无 checklist 组件。
  唯一的引导原语是各页静态三步卡 `components/StreamSetupGuide/`。
- 已配置模型时用户会看到 `ModelConfigEmpty`；未配置时 `AgentNotReadyScreen` 有「去配置模型」按钮——
  这两块是好的，缺的是**把它们串成一条路径**。

### 1.7 空白表单清单（D3 的输入）

真·空白墙（既无默认值、placeholder 也只是把标签重复一遍）：

| 优先级 | 位置 | 字段 | 现状 |
|---|---|---|---|
| **P0** | `KnowledgeBases/index.tsx:3012-3024` | 知识库名称 | 无 placeholder、无默认 |
| **P0** | `…:3025-3031` | 知识库描述 | 无 placeholder、无默认 |
| **P0** | `Experts/components/CreateFromExpertDrawer.tsx:659` | 专家名称 | 无 placeholder；只有从模板进入才预填（`:311-312`） |
| **P0** | `…:694-696` | 专家描述 | 同上 |
| **P1** | `Experts/components/TeamDrawer.tsx:229` | 团队名称 | 无 placeholder，且 `:111` 显式清空 |
| **P1** | `…:231-233` | 团队描述 | `:112` 清空（`:115` 的 welcome_message 倒是有默认） |
| **P1** | `KnowledgeBases/index.tsx:2946-2969` | 新建/重命名文件夹 | placeholder 只是「文件夹名称」 |
| **P2** | `Experts/components/PublishExpertDrawer.tsx:195,203` | 发布专家名称/描述 | 标签当 placeholder |
| **P2** | `Admin/Users/RolesPanel.tsx:613-620` | 角色名称 | 无 placeholder（隔壁 `:638` 描述却有） |
| **P2** | `Agent/Workspace/components/WorkspaceDrawer.tsx:1216` | 重命名输入 | 无 placeholder |

**已经做得不错、不要动**：定时任务（`CronJobs/.../JobDrawer.tsx:283` 有「例如：每日数据同步」）、
通道、连接器、模型提供商、技能包、记忆、子代理、管理员建用户、存储后端——全部有有效 placeholder。

可复用的好范式：`knowledgeBases.filenamePlaceholder` = 「例如 notes」（`TextDocumentEditorModal.tsx:195`）。

---

## 2. 工作项

### z08-1 · 每个向量模型一句话优缺点（P0）

**做法**：给目录条目加 `note_zh` 字段（一句话，说清"什么时候选它 / 什么时候别选"），
随 `embedding-options` 下发，前端在模型行下方渲染成第二行灰字。

必须四处协同（缺一处就会静默丢字段）：
1. `onnx_catalog.py:62-78` `_model_entry` 增加 `note_zh`；文案表放在 `:30` 附近与 `_FALLBACK_SIZE_GB` 同级。
2. `api/routers/onnx_models.py:31-37` `OnnxCatalogItem` 加字段。
3. `dashboard/src/api/modules/knowledgeBases.ts:81-87` `KnowledgeOnnxModel` 加字段。
4. `KnowledgeBases/index.tsx:3238-3247` 渲染（那里已有 `onnxModelMeta` 一行，加第二行）。

**注意**：文案是**品牌内容**，走 `brand.yaml` 的 text 清扫范围，不要写死英文。
建议放 `dashboard/src/locales/{en,zh}.json` 的 `knowledgeBases.modelNotes.<slug>`，
这样自动受 `test_dashboard_en_and_zh_share_leaf_keys` 约束。

**文案见第 3 节表格**（已按实测维度/上下文/体积写好）。

验证：`GET /embedding-options?all_onnx=true` 每条都带 `note_zh`；前端截图；`uv run pytest tests/unit/i18n -q`。

### z08-2 · 只推荐中文可用的，其余收进「高级选项」（P0）

现状是「3 个精选 + 展开出 41 个」，跨度太大且 41 里含 CLIP 这类错误选项。

**做法**：
- 默认列表 = **中文可用的 3 个**（`bge-small-zh-v1.5` / `jina-embeddings-v2-base-zh` / `multilingual-e5-large`），
  按 z08-4 的调整后推荐集为准。
- 「高级选项」展开后 = 现有 12 个精选（`_EXTRA_CATALOG_IDS`），
  **不再**把 fastembed 的 41 个全倒出来：`_onnx_options_for_knowledge(include_all=True)`
  改为返回 `presets + _EXTRA_CATALOG_IDS` 与 fastembed 的**交集**，保持顺序。
  这样既不会显示 CLIP，也不会因为 fastembed 版本变化而漂移。
- 展开/折叠沿用仓库既有风格：`Button type="link" size="small"` + ChevronDown/Up
  （范式见 `Setup/steps/DatabaseStep.tsx:200-218` 与 `ModelListEditor.tsx:587-607`），
  复用 `KnowledgeBases/index.module.less` 的 `.showMoreOnnx`。
- 修一个既有小毛病：`openSettings` `:1217-1218` 每次打开都重置展开态且**无法折回**，改成可双向。
- 英文模型行必须带明确警示（见第 3 节），避免中文用户误选 `all-MiniLM-L6-v2`——
  它 92 MB、名字最眼熟、和默认推荐同体积，是最容易踩的。

验证：默认请求只回 3 条；展开后 ≤12 条且不含 `clip`；前端截图两条路径。

### z08-3 · 空闲预下载默认模型 + 失败回退（P0，D1）

**触发**：服务端启动后延迟（建议 90 s，避开首屏与 bridge 自动恢复）→ 探测网络可达 →
若知识库未启用且默认模型未下载 → 静默 `start_download`。

**必须有的四道闸**（内网场景是硬约束，不是洁癖）：
1. **网络探测**：复用 `onnx_download.py:132-144` 的 TTFB 探测，三源都探不到就**直接放弃且不报错**，
   只在日志留一行。绝不能让内网机器每次启动弹一个红条。
2. **一次性**：用 settings KV 记 `onnx_prefetch_state`（`skipped|running|done|failed`），
   成功或明确跳过就不再自动尝试；失败允许下次启动重试，但要带次数上限（建议 3）。
3. **可关**：设置里加「提前准备向量模型」开关，默认开；**离线交付包与便携包默认关**
   （用现有 `OCTOP_*` 环境变量或 `config.json` 键，实施时按 CONVENTIONS 选一种并写进 `docs/configuration.md`）。
4. **磁盘**：下载前检查 `~/.octop` 所在卷剩余空间 ≥ 模型体积 ×2，不足则跳过并记状态。
   （顺带补上第 1.4 节说的"完全没有磁盘检查"。）

**失败回退**：用户打开知识库设置时，若默认模型仍未下载，自动发起下载并显示现有进度 Modal
（`:3435-3455` 已有），而不是等用户去点。

**关键约束**：这条**不能**改成"客户端 Go 壳去下载"。下载逻辑、源竞速、落盘路径、状态机全在 Python 侧，
Go 壳重新实现一份就是第二个"判序逻辑写两遍"的坑（见 HANDOVER 第 4 节两条同类记录）。

验证：
- 单元：状态机四道闸各一条（网络不可达 / 已成功 / 次数耗尽 / 磁盘不足），断言**没有**发起下载。
- 集成：清掉 `~/.octop/embedding_models` → 起服务 → 等待 → 断言目录出现且状态 `done`。
- 离线用例：设 `OCTOP_ONNX_COS_BASE` 指向不可达地址 + 断网 → 断言启动日志无红错、UI 无报错弹层。
- 装机：`scripts/verify/client_release.py` 加一步断言默认模型已就位。

### z08-4 · 修 e5 前缀陷阱与体积显示（P0，缺陷 A/B）

两件事，都不大但都会静默坑人：

1. **e5 前缀**：`intfloat/multilingual-e5-large` 需要查询 `query:` / 文档 `passage:` 前缀。
   两条路选一，**实施前定**：
   - (a) 在 embedding 调用处按模型自动加前缀（一处集中，推荐）；
   - (b) 把 e5-large 从推荐集里摘掉，中文推荐集换成 `bge-small-zh-v1.5` + `jina-v2-base-zh`
     + 新增 `paraphrase-multilingual-mpnet-base-v2`（1.0 GB，多语种但**不需要前缀**）。

   建议 **(a) + 同时把它从"推荐"降级**：前缀补上是对的，但 2.24 GB 对桌面客户端太重，
   不该占据推荐位。若选 (a)，必须加回归测试锁住"查询与文档用了不同前缀"。
2. **体积兜底表**：按 1.3 节实测把 `_FALLBACK_SIZE_GB` 校准（jina 0.64 / e5 2.24 / MiniLM-L12 0.22），
   并加一条单测：兜底值与 fastembed 元数据的偏差不得超过 20%，防止下次再漂。

验证：前缀单测；体积校准单测（导入 fastembed 时对比）；`GET /embedding-options` 三条推荐体积与 UI 一致。

### z08-5 · 知识库默认名称与描述（P0，D2）

- 名称默认：`智策科技公司制度知识库`
- 描述默认：`智策科技公司制度汇总，方便 AI 对请假、报销等事项进行判断。`
- 实现：`KnowledgeBases/index.tsx` 打开创建抽屉时（`:324` / `:2990` 的 `resetFields` 处）
  `setFieldsValue` 预填，**纯前端**，不动 `CreateBaseBody`、不动数据库。
  文案进 locale（`knowledgeBases.defaultName` / `defaultDescription`），受奇偶校验测试约束。
- 引导"推荐用户改"：名称输入框下方一行灰字——
  「这是示例名称，建议改成你自己的部门或用途，方便以后区分」。
- **同名不去重**（用户选了"真默认值可改"而非"自动加序号"），但名称必填校验保持。

验证：Playwright 开抽屉断言两个字段非空且可编辑；改后提交成功；文案中英都有。

### z08-6 · 其余高频表单默认值与示例（P1，D3 分主次）

**P0 档（给真默认值）**：
- 知识库名称/描述（z08-5）
- 专家名称/描述：`CreateFromExpertDrawer.tsx:659,694` 无模板进入时预填
  名称 `我的专属助理`、描述留示例 placeholder（描述预填容易让用户以为已配置好，只给 placeholder）。

**P1 档（给真默认值）**：
- 团队名称/描述：`TeamDrawer.tsx:111,112` 停止清空，预填 `协作团队`。
- 知识库新建/重命名文件夹：placeholder 从「文件夹名称」改成「例如：人事制度、财务报销」。

**P2 档（只补 placeholder，不给默认值）**：
- 发布专家名称/描述、角色名称、工作区重命名——这些是专业操作，预填反而碍事，
  统一改成「例如：……」格式。

统一风格：示例一律 `例如：xxx`，与已有的 `filenamePlaceholder`、`cronJobs.jobNamePlaceholder` 一致。

验证：逐条 Playwright 断言 placeholder/初始值；改动的 locale key 过奇偶校验。

### z08-7 · 首启三步行事历（P1，D4）

产品现在**完全没有** onboarding。加一个轻量的、**可关闭、不遮挡**的进度条，而不是弹窗式向导。

- 步骤：**① 配置模型 → ② 建第一个专家 → ③ 试一次对话**（可选 ④ 建知识库）。
  顺序依据：模型是唯一硬依赖（跳过会得到起不来的专家），专家是对话载体，知识库是增值项。
- 判定完成用**已有状态**，不新增埋点：① provider 测试通过或有可用模型
  （`ModelConfigEmpty` 的判据）、② 专家数 > 0、③ 有任意 thread。
- 全部完成后自动收起；任何时候可点右上角关闭，关闭后不再出现（localStorage 记一次即可，
  **不要**存成服务端用户偏好——参见 z05 那条"自动检测不要当偏好存"的教训）。
- 放在 `/chat` 的 `WelcomeScreen` 区域内，复用 `StreamSetupGuide` 的三步卡视觉，避免新造一套样式。

冲突面积：主要落在 `Chat/index.tsx` 与新组件文件；`WelcomeScreen` 若已存在则改动很小。

验证：全新数据目录装机 → 断言三步依次点亮 → 完成后刷新不再出现；老用户（已有模型+专家+会话）断言**不显示**。

---

## 3. 模型优缺点一句话（z08-1 的文案，按实测数据写）

### 中文推荐区

| 模型 | 优点 | 缺点 |
|---|---|---|
| `BAAI/bge-small-zh-v1.5` | 92 MB、CPU 上秒级响应，中文短文档检索性价比最高，**默认推荐** | 模型小，长篇制度条款和专业术语的召回明显弱于大模型，超 512 token 会被截断 |
| `jinaai/jina-embeddings-v2-base-zh` | 支持 8192 token 超长上下文，整段规章制度不用切碎，中英混排也稳 | 640 MB，CPU 上索引大库比小模型慢好几倍 |
| `intfloat/multilingual-e5-large` | 1024 维、约 100 种语言，跨语言检索最强 | 2.24 GB 最重，且**必须**给查询/文档分别加 `query:` / `passage:` 前缀，否则精度悄悄下降（见 z08-4） |
| `paraphrase-multilingual-mpnet-base-v2`（建议新增） | 768 维、约 50 种语言，多语种质量标杆之一，且不需要任何前缀 | 1.0 GB，中文单语场景不如 bge 系列划算 |

### 「高级选项」区（英文为主，必须带警示）

| 模型 | 一句话 |
|---|---|
| `BAAI/bge-small-en-v1.5` | 67 MB 英文小模型标杆，**中文语料召回差，别拿它建中文知识库** |
| `BAAI/bge-base-en-v1.5` | 210 MB 英文精度更好，同样不适合中文 |
| `BAAI/bge-large-en-v1.5` | 1.2 GB 英文高精度，中文场景没有理由选它 |
| `jinaai/jina-embeddings-v2-base-en` | 520 MB 英文长上下文（8192 token），但语言不对 |
| `jinaai/jina-embeddings-v2-small-en` | 120 MB 英文小快，中文不适用 |
| `sentence-transformers/all-MiniLM-L6-v2` | 90 MB、社区最知名的轻量模型，但**仅英文 + 256 token**，且体积与默认推荐的中文模型几乎相同——**最容易被误选的一个** |
| `paraphrase-multilingual-MiniLM-L12-v2` | 220 MB 支持约 50 语言，但上下文只有 **128 token**，长段落会被切得极碎 |
| `thenlper/gte-base` | 440 MB 英文 MTEB 排名高，中文非其所长 |
| `thenlper/gte-large` | 1.2 GB 英文高精度，中文场景不划算 |

> 文案落 locale，不硬编码；每条控制在**一行内能显示完**，超长的拆成"优点/缺点"两小行。

---

## 4. 风险与回退

| 风险 | 处置 |
|---|---|
| 内网机器每次启动探测失败、刷日志或弹错 | z08-3 第 1 道闸：三源全不可达即静默放弃；离线包/便携包默认关预下载 |
| 92 MB 流量在按量计费的网络上意外产生 | 一次性状态 + 可关开关 + 进度可见；文档与下载页写清"首次会下载 92 MB" |
| 磁盘被模型占满 | 下载前 ×2 空间检查（现在完全没有） |
| 默认知识库名到处撞名 | 用户已选"真默认值可改"，配合输入框下的"建议改成你自己的"提示；不动后端唯一性约束 |
| 改了 `include_all` 语义导致 管理→模型 页受影响 | 那条路径用的是 `onnx_models.py` 的另一个端点（`LocalServiceCard.tsx:299` → `ProviderConfigModal`），实施时分别验证，不要顺手统一 |
| 首启行事历对老用户是噪音 | 三项都已完成时不渲染；关闭状态存 localStorage 而非服务端 |

---

## 5. 出口条件

**门禁**（每次提交前）
- `cd dashboard && npx tsc -b` + `npx eslint .` + `npx prettier --check`
- `npx vitest run src/pages/KnowledgeBases src/pages/Login src/layouts`
- `uv run pytest tests/unit/i18n -q`（新增 locale key 必须过奇偶校验）
- `uv run pytest tests/unit/api tests/unit/knowledge -q`
- 动了 Go 才需要：`cd desktop/src && go vet ./... && go test ./...`

**装机验收**（发版后，一条命令）
```bash
.venv/Scripts/python.exe scripts/verify/client_release.py --version 1.0.2b6+z08
```
并给 `client_release.py` 增加 z08 断言：默认模型已就位、知识库抽屉两字段非空、
模型列表默认 ≤3 条且展开后不含 `clip`、首启行事历在老用户上不出现。

**冲突面积**：发版后跑 `scripts/classify_owned.py` 重测并更新 `brand/owned-files.txt`、
`HANDOVER.md` 的表格与 `CHANGELOG.md`。预计手工那一栏从 39 增加 6–8
（`onnx_catalog.py`、`knowledge_bases.py` 路由、`onnx_models.py`、`KnowledgeBases/index.tsx`、
`CreateFromExpertDrawer.tsx`、`TeamDrawer.tsx`、`Chat/index.tsx`），新增文件 3–5。
**能放进 `brand.yaml` 或 locale 的绝不写进源码。**

---

## 6. 建议实施顺序

```
z08-4 (修 e5 与体积)  →  z08-1 (模型说明)  →  z08-2 (折叠+只推中文)
        ↓
z08-5 (知识库默认值)  →  z08-6 (其余表单)
        ↓
z08-3 (空闲预下载)  ←  单独一次提交，风险最高、要装实验离线场景
        ↓
z08-7 (首启行事历)
        ↓
发版 + 装机验收 + 文档同步
```

先修 z08-4 是因为它会改变"推荐哪三个"的结论，而 z08-1/z08-2 的文案和列表都依赖那个结论。
