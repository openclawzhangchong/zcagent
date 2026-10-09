# 更新日志

本文件记录 **智策 / zcagent 相对上游的改动**。上游自己的历史在 [`CHANGELOG.upstream.md`](./CHANGELOG.upstream.md)。

## 版本号规则

`<上游基线版本>+z<N>`，例如 `1.0.2b6+z1`。

- `+` 前是所基于的上游版本，追版时只改这一段；
- `z<N>` 是我们的补丁序号，每次发布 +1；
- 用 PEP 440 local version，因此这类包**不能**上传 PyPI（我们不发布公共包，内网分发正合适）。

---

## [1.0.2b6+z1] — 2026-10-09

基于上游 `v1.0.2b6`（commit `0c5a46a`，2026-10-08）。首个自有品牌版本。

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
| 标识符未被误改 | `X-Octop-*`、`prefixCls="octop"`、`OCTOP_HOME`、`octop-harness` 依赖名、i18n key 均已核对原样 |
| 运行期冒烟 | 登录 → 建专家 → 真实对话（OpenAI 兼容 provider）→ 工具调用写文件并落盘核对，全通过 |

### 已知问题（待 P2 处理）

- **凭据存储是本产品的一条硬性要求**：Agent 侧写入的凭据一律走 `infra/connectors/` 的加密 `secrets` 存储，工具输出不得声称"未落盘"。已列为 P2-0，排在界面重构之前。
- Windows 下 `工作台 / 终端` 不可用（上游按设计禁用，见 `src/octop/api/routers/terminal.py`）。
- 系统提示词里的 OS / 工作区路径在 Windows 上会被模型复述成 Linux 风格路径，属上游待修。
- 侧栏「云端协同 BETA」角标仍用 `#ff4d4f`（`src/layouts/Sidebar.tsx:215`），这是语义"提醒/危险"红而非品牌色，暂未改。
- `octop-mascot-peek.webm`、`octop-mascot-type.webm`、`octop-mascot-tasks.png` 在代码里**无人引用**（前端只用 `.webp`），属上游死资产，仍随构建产物发布，暂未处理。
