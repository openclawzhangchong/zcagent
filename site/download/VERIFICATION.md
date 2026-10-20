# 发布记录（release record）

智策 Windows 客户端的实测记录。每次改动产物时追加一节，不覆盖历史。

## 1.0.2b6+z12 · 2026-10-20（主题：公网访问 / Cloudflare 隧道）

功能本身与门槛的设计写在 `CHANGELOG.md` 的 z12 一节与 `docs/public-access.md`。
本节记发版后的产物验收，以及**这一版第一次把"交付物里到底有没有这个功能"变成一个需要单独测的问题**。

### CI 与产物

tag `v1.0.2b6-z12` → Desktop Package run `39408749951` 与 Frontend 门禁 `39408749892` 全 success
（`Select platforms` / `Build dashboard` / `windows-amd64` / `Attach zips to GitHub Release` /
`Dashboard gates` 逐个绿）。

| 文件 | 字节 | SHA256 |
|---|---|---|
| `zcagent-desktop-windows-amd64-1.0.2b6+z12.exe` | 228,329,078 | `ff550c2a…fa4cd3` |
| `zcagent-portable-windows-amd64-1.0.2b6+z12.zip` | 233,990,800 | `d2ae53a0…39a842` |

相对 z11 涨 14,992 B / 22,447 B——与"新增一个设置页 + 五个 Python 模块"相符。

### 先问了一句"它会不会根本没被打进包里"

z12 是第一次往 `src/octop/infra/` 下加**新子包**（`infra/tunnel/`）。读 `pyproject.toml`
能看到 `[tool.hatch.build] include` 里有 `src/octop/**/*.py`，推断它会被带上——但
z03 那次的教训正是"代码在产物里，却因为另一环到不了用户手上"，所以直接建了一次 wheel 数文件：

```
tunnel modules in wheel: 5
   octop/api/middleware/tunnel_guard.py
   octop/api/routers/tunnel.py
   octop/infra/tunnel/__init__.py
   octop/infra/tunnel/binary.py
   octop/infra/tunnel/manager.py
chunks carrying tunnel-switch: ['octop/dashboard/assets/index.DNWBSfeK.js']
```

### 下载页线上核验

`curl https://zcagent-download-igdker4k5y4.qoder.website/` → HTTP 200：
`1.0.2b6+z12` 7 次、`1.0.2b6+z11` 1 次（"上一版"那行）、`1.0.2b6+z10` 0 次，
`228,329,078` / `233,990,800` / `ff550c2a` / `d2ae53a0` 各自都在。

（Qoder 站点内容变了必须换 actionId，沿用旧的会把**旧草稿**重新发布一次并回 `succeeded`。
本轮 actionId `ce0b17ae-8a75-4127-a3cf-f7035a4bca3a`，`descriptorStatus` 从 `pending`
重试到 `written` 才 publish。）

### 装机升级（`client_release.py --stage all`）

```
installed: C:\Program Files\zcagent\zcagent.exe (245527040 bytes), registry 1.0.2b6+z12
unpacked runtime: 1.0.2b6+z11 -> 1.0.2b6+z12
  1.0.2b6+z11 carries 'modelsCountEnabled': /assets/zh.Ck1yls5i.js
  1.0.2b6+z12 carries 'tunnel-switch': /assets/index.DnuYi6TH.js
bundled node: v22.20.0 / npm 10.9.3 / VERSION.txt node=22.20.0
ALL ASSERTIONS HELD
```

升级前先取了一次对照：**z11 上 `GET /api/admin/tunnel` 返回 404**，升级后 200。
没有这个对照，"chunk 里有 tunnel-switch" 也可能只是缓存或别的东西。

### 交付物上真开了一次隧道——并当场抓到两个 bug

装好的客户端被**口令强度门正确拒绝**了：这台机器的管理员口令是负责人指定的
`18596950010`，全数字，`validate_password_policy` 不放行（`PASSWORD_TOO_WEAK`）。
这是设计生效，不是故障——但也意味着"公网访问在这台机器上到底能不能跑起来"
没法在装机实例上回答。于是改用**便携版 zip 本身**（它就是交付物）在独立数据目录上，
用它自带的 `start.bat` 起服务，走完真实的向导口令第一跳（`octop-login.txt` →
`/setup/verify-password`，开发实例是设 `OCTOP_REQUIRE_SETUP_PASSWORD=0` 绕过去的，
这条路只有交付物会走），再开真隧道：

```
preflight -> 200 ready=True (accounts/captcha/api_docs/platform/safe_mode 全 ok)
all-digit password -> HTTP 400 PASSWORD_TOO_WEAK      ← 负向对照
POST /api/admin/tunnel -> 200
status=live url=https://ingredients-…-cuisine.trycloudflare.com
public /api/health -> 200
filesystem: tunnel=403 local=200
chat data reachable over the tunnel -> 200
cloudflared 落在 D:\otp\.z12-data\tunnel\bin\，同目录有 LICENSE.cloudflared.txt
DELETE -> 200；status=off，url 清空
verdict: OK（12/12）
```

**抓到的两个 bug（都不在 dev-tree 探针的覆盖范围内，只有拿交付物跑才暴露）：**

1. **`is_ready()` 只认自己写的 `.verified` 边车。** 下载失败的提示语让内网实施人员
   "把文件手动放到 `<home>\tunnel\bin\`"——照做了**并不被接受**。等于产品写了一条
   自己做不到的指令。改成**永远按钉住的 SHA-256 重算文件本身**（53 MB 实测 0.07 秒），
   边车整个删掉：第一版修复还留着"边车匹配就跳过重算"的快路径，测试当场把它判成失败——
   那种边车会给被篡改的字节背书。
2. **两次并发"开启"会撞同一个 `.download` 临时文件**，第二个直接
   `WinError 32 另一个程序正在使用此文件`。触发方式很平常：双击、或界面在下载没完成时重试。
   修成临时文件带 PID+时间戳，且 `_starting` 期间重复 start 直接返回当前状态。

两条都补了单测（`test_a_bare_file_never_counts_as_verified`、
`test_a_hand_placed_binary_is_accepted_by_its_own_digest`），
连同原有的 `test_download_that_does_not_match_the_release_is_rejected` 一起，
`tests/unit/infra/tunnel` 29 项全过。

**3（最严重）. 被"关闭"的 start 在下载完成后照样把隧道开起来了。**
装机实例上实测：点开启 → 因为这台机器到 github.com 是死的，组件下载爬了四分钟 →
期间点关闭，接口返回 200、状态变 `off`、`enabled=False` → **四分钟后隧道仍然建立并拿到公网地址**，
而 `start()` 在 `ensure_binary` 之后没有重新检查 `enabled`。
更糟的是安全模式的生效条件是 `state.enabled and safe_mode and url`，
所以这条孤儿隧道是**在没有公网安全模式的情况下对外服务**——实测直接坐实：

```
GET https://allows-…-exclusion.trycloudflare.com/api/filesystem/dirs?path=.
  -> HTTP 200      ← 本机文件浏览，对互联网开放，且 UI 显示"未开启"
```

这正是 `docs/PLAN-tunnel.md` 里点名的最坏形态（"我以为关了其实还开着"），
只不过反了过来：UI 说关了，它真的开着。两处修复：`start()` 在 spawn 前重新检查
`enabled`；**守卫的生效条件改成只看"有没有活着的公网地址"，不再看意图标志**
（`guard_is_active(url, safe_mode)`，单独抽出来以便测试）。

回归测试在未修复的代码上验过是红的：

```
fix reverted for the control
FAILED test_a_cancelled_start_does_not_spawn_after_the_download_finishes
restored -> 31 passed
```

> 这三处修复**都不在已发布的 z12 产物里**。z12 从发布到发现只隔了一次验收，
> 没有任何用户下载过，所以直接续 z13 而不是移动已公开的 tag。

### 已知未做

landing 仍停在 z10，原因与 z11 相同：`site/landing/` 有 18 个未提交文件，
干净检出构建不出来（模板要的五个 token 与四张截图都只在未提交的工作区）。
详见 `site/landing/DEPLOY.md` 末节。

---

## 1.0.2b6+z11 · 2026-10-20（主题：模型配好了却说"没有可用模型"）



改动来龙去脉写在 `CHANGELOG.md` 的 z11 一节。本节只记发版后的产物验收，
以及**这一轮被验收工具自己绊到的两次**。

### CI 与产物

tag `v1.0.2b6-z11` → run `39386274334`（Desktop Package）与 `39386273977`（Frontend 门禁）
全部 success。产物形状与 z10 一致（Windows 安装版 + Windows 便携版）：

| 文件 | 字节 | SHA256 |
|---|---|---|
| `zcagent-desktop-windows-amd64-1.0.2b6+z11.exe` | 228,314,086 | `ab3bf3c8…6bacad` |
| `zcagent-portable-windows-amd64-1.0.2b6+z11.zip` | 233,968,853 | `22196211…663ba9` |

相对 z10 只涨 4,113 B 与 517 B——与"只改前端表述加一个按钮"相符；
如果哪一版涨了几十 MB，那说明带上了别的东西，要问。

### 下载页线上核验（不信发布回显，直接读线上）

`curl https://zcagent-download-igdker4k5y4.qoder.website/` → HTTP 200，
`1.0.2b6+z11` 出现 7 次、`1.0.2b6+z10` 1 次（就是"上一版"那一行），
`228,314,086` / `233,968,853` / `ab3bf3c8` / `22196211` 各自都在。

### 装机验收（`client_release.py --stage all`，本机覆盖安装）

```
resolved zcagent-desktop-windows-amd64-1.0.2b6+z11.exe: 228314086 bytes, sha256 ab3bf3c89f7189d5...
download verified: 228314086 bytes, hash matches the release digest
installing silently into C:\Program Files\zcagent ...
installed: C:\Program Files\zcagent\zcagent.exe (245505024 bytes), registry 1.0.2b6+z11
unpacked runtime: 1.0.2b6+z10 -> 1.0.2b6+z11
  1.0.2b6+z10 carries 'nav-new-chat': /assets/index.DpyY-vfK.js
  1.0.2b6+z11 carries 'modelsCountEnabled': /assets/zh.B-Qr-Bee.js
bundled node: v22.20.0 / npm 10.9.3 / VERSION.txt node=22.20.0
  detector resolves npm -> C:\Users\Administrator\.octop\portable\node\npm.CMD
  local load probe BAAI/bge-small-zh-v1.5: {'ok': True, 'latency_ms': 154.6, 'dim': 512}
ALL ASSERTIONS HELD
```

`modelsCountEnabled` 落在 `zh.*.js` 语言分片里——它同时被组件和语言包引用，
所以拿旧 chunk 冒充过不了这一关。

### 修好之前，先说两次"失败"各是什么

**1）自助重置表单断言失败——是工具的错，不是产物的错。**
`expected the self-service reset form in the dialog`。查下来：这台机器上有
`admin` 与 `zc` 两个账号（`zc` 是早先做多用户测试建的），而
`_recovery_state()` 在账号数不等于 1 时**按设计**返回不可用
（`src/octop/api/routers/local_recovery.py:62`），于是对话框回落到终端指令。
实测两边都对得上：

```
GET /api/auth/local-recovery -> {"available":false,"username":null}
accounts on this install: [('admin','admin'), ('zc','user')]
```

断言原来硬假设"单账号机器"，在用过多次用户测试的机器上必然假失败，
在干净机器上又可能因为别的原因假通过。改成**问同一个接口、要求界面与它一致**：
可用却没表单 = 失败；不可用却连能用的命令都不给 = 失败。两种形态现在都测得到。

**2）landing 这一版没上线，卡在仓库自身不可构建。**
`python site/landing/build.py` 在**干净检出**上两条硬失败：模板用了五个只有未提交
工作区才提供的 token，又引用四张只有未提交工作区才生成的截图（死链门禁报 4 个）。
根因是我上一轮 `bb409021` 把"线上那一版"的模板抄进仓库、没带上配套 builder 与资源。
线上五枚短链逐个实测仍正确（`/repo`、`/issues`、`/changelog`、`/docs`、`/install` 全 302），
所以访问者没有坏链，只是官网版本号停在 z10。详细处置写在 `site/landing/DEPLOY.md`。

### 顺手纠正的一处体积口径

`portable_extracted_mib: 724` 是真数：把 z11 便携版完整解压实测 **758 MB（≈723 MiB）**。
但离线指南里"首次运行解到 `~\.octop\portable` 约 811 MB"这个数会误导实施人员——
本机同一目录实测 **946 MB**。拆开看不是残留也不是重复解压（只有一份
`octop-1.0.2b6+z11.dist-info`，无 `.old/.bak`）：`runtime\Lib` 从 32 MB 涨到 172 MB，
多出来的 151 MB 是知识库真跑过之后装进 `site-packages` 的
onnxruntime / numpy / Pillow / tokenizers / huggingface_hub。
指南已按 z11 实测改写，并明确"内网批量部署这一项按 ≈1 GB 预留"。

### 离线包

`make_kit.py --local`（先用 `fetch_asset.py` 九段并发把 462 MB 拉下来，
单连接在这台机器上要一个多小时）：两份产物都按 Release 的 digest 校验通过才装箱。
桌面 `zcagent-1.0.2b6+z11-windows-offline-kit`（441 MB），z10 已移入
`智策-旧版本存档`，与 z03/z07/z08/z09 并列。

---

## 1.0.2b6+z10 · 2026-10-13（主题：桌面包内置 Node，连接器不再要求用户自己装）


改动来龙去脉与体积实测写在 `CHANGELOG.md` 的 z10 一节。本节只记发版后的产物验收。

### 装机验收（一条命令，`--stage all`）

```
resolved zcagent-desktop-windows-amd64-1.0.2b6+z10.exe: 228309973 bytes, sha256 0b7f6ea8ec6deec4...
download verified: 228309973 bytes, hash matches the release digest
stopped the running client first: pid 17604
installing silently into C:\Program Files\zcagent ...
installed: C:\Program Files\zcagent\zcagent.exe (245504512 bytes), registry 1.0.2b6+z10
server answering on 8088
unpacked runtime: 1.0.2b6+z09 -> 1.0.2b6+z10
  1.0.2b6+z03 carries 'function resolveInitia': /assets/index.BASFQJW-.js
  1.0.2b6+z06 carries 'local-recovery': /assets/index.BASFQJW-.js
  1.0.2b6+z08 carries 'prefetch_enabled': /assets/index.BxELVbHj.js
  1.0.2b6+z08 carries '智策科技公司制度知识库': /assets/zh.BiN4yfW1.js
  1.0.2b6+z10 carries 'nav-new-chat': /assets/index.BASFQJW-.js
bundled node: v22.20.0 / npm 10.9.3 / VERSION.txt node=22.20.0
  detector resolves npm -> C:\Users\Administrator\.octop\portable\node\npm.CMD
```

`nav-new-chat` 是导航栏那个新按钮的 `data-testid`——它出现在**被服务的 chunk** 里，
才说明装机版真的带上了这一版的界面，而不是只更新了 Python 运行时。

### 新增的一条验收阶段：`stage_bundled_node`

光看文件在不在，证明不了"用户点得到连接器"。这一步做四件事：

1. `~/.octop/portable/node/node.exe` 与 `npm.cmd` 必须存在；
2. 用**装好的那份**真跑 `node -v` / `npm -v`（v22.20.0 / 10.9.3）；
3. `VERSION.txt` 必须有 `node=` 行，`start.bat` 必须把 `%ROOT%\node` 前置进 PATH 并设
   `OCTOP_BUNDLED_NODE`——否则用户机器上有 node 也没用，服务进程看不见；
4. 用**装好的 runtime 与 packages** 跑产品自己的检测代码
   （`cli_install.ensure_cli_path()` + `shutil.which("npm")`），必须解析到包内那份 npm。

第 4 步一开始是失败的，而且**是工具的错不是产物的错**：我用 `sys.path.insert` 加载 packages，
便携包里的 pywin32 靠 `packages/` 下的 `.pth` 生效，`insert` 不处理 `.pth`，
于是 `ModuleNotFoundError: No module named 'pywintypes'`——这正是 `launch.py` 存在的理由
（`site.addsitedir`）。改成 `site.addsitedir` 后通过。

### 独立的一次真装：报错里那个包

用内置 npm 真的执行了用户看到的命令（装进临时前缀，不碰系统）：

```
npm install -g --prefix .zc-verify/npm-scope-z10 @tencent-qqmail/agently-cli@1.0.18
  added 2 packages in 12s
cli_install_status('agently-cli') -> {"installed": true, "version": "1.0.18",
  "binary_path": "...\\npm-scope-z10\\agently-cli.CMD"}
```

对照：把 PATH 里所有含 node 的条目过滤掉之后 `which("npm")` 是 `None`——正是 z09 及之前
用户撞到的状态。中途踩了一次本机老坑：给 PATH 塞 Git Bash 风格路径（`/d/otp/...`）时
`shutil.which` 找不到任何东西，必须用 Windows 路径。

### 这一轮没做完的一项（以及为什么）

**界面上点「连接器 → 安装」那一步没有跑。** 登录态的四个阶段（embedding API、登录页、
知识库对话框、图标）都需要这台机器上 zcagent 管理员账号的口令，我没有，也不会去重置你的账号
（`~/octop-login.txt` 是首启向导口令，不是登录口令）。
`--stage verify` 复用已装好的实例，设上 `ZC_VERIFY_PASSWORD` 就能补齐。
后端接口已经用上面两条证明过，所以缺的是"按钮点下去的观感"，不是能力。

### 顺带修掉的两个工具自身问题

- **验收器一失败就把整份报告丢掉**：`_bail()` 现在会把已经通过的阶段写进
  `reports/<version>.json` 再返回非零码——transcript 是要贴进本文件的，
  为一个 401 赔掉前面全部证据不合理。
- **`_auth_token()` 抛裸 401 traceback**：改成明确说明"缺 ZC_VERIFY_PASSWORD，
  前面的阶段已通过并写进报告"。

### 装机后端口归属变化（需要知道）

验收过程会停掉占用 8088 的进程再装。跑完之后 **8088 上是安装版 z10**
（`C:\Program Files\zcagent\zcagent.exe`），不是开发实例；数据没动
（`/api/health` 报 `users_loaded: 2, agents_running: 3`）。
要把 8088 交还开发实例，照 z06 那次的做法处理即可。

---

## 1.0.2b6+z09 · 2026-10-11（主题：镜像下载的向量模型其实加载不了）

修复的来龙去脉与"同一个 exe、同一批文件"的对照实验写在上面 z08 一节的最后，
根因分析在 `CHANGELOG.md` 的 z09 一节。本节只记发版后的产物验收。

| 项 | 结果 |
|---|---|
| 存量缓存修复 | `normalize_mirror_layout(~/.octop/embedding_models)` 返回 2（两个旧布局都改好），改完**不用重新下载** |
| 装机版加载校验（修复数据后、z08 的 exe） | `{'ok': true, 'latency_ms': 219, 'dim': 512}` |
| 新增验收断言 | 默认列表里每个标着"已下载"的模型都必须 `ok=true`，否则装机验收直接失败 |

### 装机验收（发版后，一条命令）

```
resolved zcagent-desktop-windows-amd64-1.0.2b6+z09.exe: 192,200,150 bytes, sha256 4ae768bf…03c825
  attempt 1: 63,601,970/192,200,150 (github, 900s 超时后断点续传)
  attempt 2: 125,943,081/192,200,150 (api)
  attempt 3: 186,967,081/192,200,150 (github)
  attempt 4: 192,200,150/192,200,150 (api)
download verified: 192,200,150 bytes, hash matches the release digest
stopped the running client first: pid 13800
installing silently into C:\Program Files\zcagent ...
installed: C:\Program Files\zcagent\zcagent.exe (208,151,040 bytes), registry 1.0.2b6+z09
server answering on 8088
unpacked runtime: 1.0.2b6+z08 -> 1.0.2b6+z09
  1.0.2b6+z03 carries 'function resolveInitia': /assets/index.CTp--4pI.js
  1.0.2b6+z06 carries 'local-recovery':        /assets/index.CTp--4pI.js
  1.0.2b6+z08 carries 'prefetch_enabled':      /assets/index.BeMijJdR.js
  1.0.2b6+z08 carries '智策科技公司制度知识库':  /assets/zh.BiN4yfW1.js
  default list: 3 models -> [BAAI/bge-small-zh-v1.5, jinaai/jina-embeddings-v2-base-zh,
                             sentence-transformers/paraphrase-multilingual-mpnet-base-v2]
  expanded list: 13 models
  local load probe BAAI/bge-small-zh-v1.5: {'ok': True, 'latency_ms': 378.6, 'dim': 512}
  stored_locale: None
  login_is_chinese: True / login_has_english_signin: False
  account_hint: 这台机器上已有智策数据，登录账号是 admin。
  recovery_form: True / modal_shows_cli_command: False
  kb_default_name: 智策科技公司制度知识库
  kb_default_description: 智策科技公司制度汇总，方便 AI 对请假、报销等事项进行判断。
  version_badge_under_logo: 1
  installed icon: .zc-verify/reports/icon-1.0.2b6+z09.png sha256 62a05850012c9506…
ALL ASSERTIONS HELD -- report at .zc-verify/reports/1.0.2b6+z09.json
```

四条都是这一轮新加/新修的东西第一次真的在装机产物上跑通：

- **`local load probe … ok=True`**：z08 那一版这里是 `ok=False, 'Could not load model …'`。
  同一条断言在两个版本上给出相反结论，正是它值钱的地方。
- **`unpacked runtime: +z08 -> +z09`**：升级链又一次在真机上被验证（z08 那次 before/after 相同，
  证据来自更早的 z05 一节；这次是真实的替换）。
- **知识库弹窗两字段拿到了**：`kb_default_name` / `kb_default_description` 是 z08 需求的中文默认值，
  这次这台机器的知识库开关是**开着**的，所以断言真的在浏览器里点开弹窗读到了值
  （z08 那轮它是关着的，工具按规则记录"没打开"而不是去改用户设置）。
- 图标摘要 `62a05850…` 与 z07/z08 一致：仍是那只边牧，没有被 CI 的构建顺序换掉。


### 空闲预下载两趟对照（z09 产物上重跑）

```
proving idle prefetch for BAAI/bge-small-zh-v1.5 on installed 1.0.2b6+z09 python=3.12.12
  booting with prefetch on port 8099
  result: downloaded=True bytes=94,781,076 settings={'knowledge_onnx_prefetch': 'done', 'knowledge_onnx_prefetch_attempts': '1'}
  booting without prefetch on port 8099
  result: downloaded=False bytes=0 settings={}
OK idle prefetch downloaded 94,781,076 bytes 125.1s after boot and recorded knowledge_onnx_prefetch=done
OK OCTOP_KNOWLEDGE_MODEL_PREFETCH=0 downloaded nothing and wrote no state
report: .zc-verify/prefetch-z09/prefetch-report.json
```

| 趟 | 开关 | 实测 |
|---|---|---|
| 1 | 默认（不设） | 首批 ONNX 字节出现在启动后 **125.1 秒**（>90 秒空闲闸 + 三源探测），130 秒时 **94,781,076 字节**齐、单调增长；`knowledge_onnx_prefetch=done`、`attempts=1` 都写进了那份临时 `OCTOP_HOME` 的 settings 表 |
| 2 | `OCTOP_KNOWLEDGE_MODEL_PREFETCH=0` | 观察 135 秒（超过空闲闸）：**0 字节、0 行状态**，而控制面库确实建起来了（`booted=true`） |

z08 那一轮这一趟只能证到"字节落盘 + attempts 递增"，`done` 拿不到——原因就是 §缓存寻址 那节：
下载完成后 `_download_sync` 里那次 fastembed 校验加载起不来，整个下载被判为失败。
现在同一个工具在 z09 上拿到 `done`，说明**空闲预下载这条链第一次端到端闭合**。

## 1.0.2b6+z08 · 2026-10-11（主题：新手第一分钟；方案见 `docs/PLAN-z08.md`）

```
resolved zcagent-desktop-windows-amd64-1.0.2b6+z08.exe: 192,197,498 bytes,
  sha256 ac66083ef7c54973…44056b
download verified: 192,197,498 bytes, hash matches the release digest
reusing the existing install at C:\Program Files\zcagent
stopped the client that was answering on 8088: pid 15348
server answering on 8088
unpacked runtime: 1.0.2b6+z08 -> 1.0.2b6+z08
  1.0.2b6+z03 carries 'function resolveInitialLocale{…': /assets/index.CTp--4pI.js
  1.0.2b6+z06 carries 'local-recovery':                  /assets/index.CTp--4pI.js
  1.0.2b6+z08 carries 'prefetch_enabled':                /assets/index.BeMijJdR.js
  1.0.2b6+z08 carries '智策科技公司制度知识库':            /assets/zh.BiN4yfW1.js
  default list: 3 models -> [BAAI/bge-small-zh-v1.5, jinaai/jina-embeddings-v2-base-zh,
                             sentence-transformers/paraphrase-multilingual-mpnet-base-v2]
  expanded list: 13 models        all_notated: True
  stored_locale: None
  login_is_chinese: True
  login_has_english_signin: False
  account_hint: 这台机器上已有智策数据，登录账号是 admin。
  recovery_form: True
  modal_shows_cli_command: False
  knowledge bases are off here -- create dialog not opened
  version_badge_under_logo: 1
  installed icon: .zc-verify/reports/icon-1.0.2b6+z08.png sha256 62a05850012c9506…
ALL ASSERTIONS HELD -- report at .zc-verify/reports/1.0.2b6+z08.json
```

本轮 `runtime_before` 与 `runtime_after` 都是 `+z08`：替换发生在前面那次**失败**的尝试里（见下文
"三个工具自身缺陷"）。"新版客户端会替换旧运行时"这条本身的证据在 z05 一节（`+z02 → +z05`）。

### 接口层实测（对着装好的客户端问接口，不是看代码）

`GET /api/knowledge-bases/embedding-options` 的默认列表就是**3 条，全是中文可用**，
每条带一句话优缺点；`?all_onnx=true` 展开是 **13 条而不是 41 条**，其中没有 CLIP 塔，
`intfloat/multilingual-e5-large` 已从推荐位降级到展开项。断言写在
`scripts/verify/client_release.py::stage_embedding_api`：默认 ≤4、展开 ≤20、无 clip、条条有注释。

### 登录后那两面

装机版是**真的能走通登录**的：用户名/密码 + 滑块验证码（`slide-captcha` 拖满，完成信号是轨道的
`aria-valuenow=100`）→ 进入 `/chat`，侧边栏 logo 下方出现短版本号 `v1.0.2b6+z08`（z07 的需求）。

新建知识库弹窗这一段**在这台机器上没有断言**，原因是它现在处于「未启用知识库」状态——页面上只有引导卡，
没有「创建知识库」按钮。为了跑断言而 `PUT /feature` 会把用户的设置改掉，所以工具如实记录"没打开弹窗"，
把默认值改到真正装载它的地方证明：服务出来的 `zh` 语言分片里确实带着「智策科技公司制度知识库」
（见上面的 bundle 输出），表单默认值本身由 `dashboard` 的组件测试覆盖。
首启行事历"老用户不该出现"同理：该不该出现取决于这台机器走到第几步，判据是纯函数，留在单元测试里。

### 空闲预下载：两趟对照

`scripts/verify/prefetch_watch.py`。**不碰共享的 `~/.octop`**：那台机器上默认模型早就下载好了，
此时正确行为是"什么都不做"，而"功能坏了"看起来一模一样——所以工具用装好的运行时刻配一个
临时 `OCTOP_HOME` 与备用端口启动，空缓存里落下的任何字节都只能是这一次运行干的。

| 趟 | 观察 | 结果 |
|---|---|---|
| 开关打开（默认） | 首批字节出现在启动后 **130.1 秒**（>90 秒空闲闸）；ONNX 权重 **94,781,076 字节**、单调增长；`knowledge_onnx_prefetch_attempts=1` | 下载确实由空闲预下载触发 |
| `OCTOP_KNOWLEDGE_MODEL_PREFETCH=0` | 观察 135 秒：0 字节、0 行状态；控制面库确实建起来了（`booted=true`） | 开关真的关得掉 |

同一次运行还多问了一句"这个模型现在能用吗"（`POST /knowledge-bases/onnx-test`），
答案是 `{'ok': false, 'error': 'Could not load model …'}` —— 于是查出下一节那个更严重的缺陷：
**`done` 之所以没写，是因为下载完的加载校验起不来**，不是预下载没跑。

写这个工具时抓到一个会**假绿**的结构：全新目录没有控制面库时，`start()` 会把控制面推迟到
首启向导选完后端，而预下载任务是在 `_boot_runtime` 里创建的——第一次跑"开关关掉"那一趟
确实什么都没下载，但那是"服务还没走到那一步"，不是开关生效。工具因此显式给
`OCTOP_DATABASE_SQLITE_PATH`，并把"控制面库是否建起来"当成所有断言的前置。
副产品是一条真实产品事实：**全新安装的 90 秒计时从走完向导那一刻开始**，不是进程启动，
已写进 `prefetch.py` 的模块说明。

### 这一轮装机验收连续拦下的三个工具自身缺陷

产物都是对的，失败全在验收工具里——但每一条如果留着，下一次真坏掉时它就看不见：

| 现象 | 真相 |
|---|---|
| `PermissionError: C:\Program Files\zcagent\zcagent.exe` | 上一版客户端还在运行，句柄没放；安装阶段必须先按 PID 停掉自己的客户端。而原来"先删掉 exe 再装"的判断方式本身也是错的：NSIS 在 `/S` 下遇到占用不弹窗，只是原地留着旧构建 |
| "installer never produced a fresh zcagent.exe" | 装好了。注册表 `DisplayVersion` 已是 `1.0.2b6+z08`，可 NSIS 把**打包时存的时间戳**原样盖在释放出来的文件上，按"mtime 晚于本次安装"判断必然失败。判断依据改成读安装器自己写的注册表版本 |
| "served chunk 缺 prefetch_enabled" | 标记确实在产物里，只是不在入口 chunk：Vite 把路由级改动切进按需加载的 `index.BeMijJdR.js`，而入口是 `index.CTp--4pI.js`。断言改成顺着入口里的动态 import 字面量爬分片图（实测 13 个 chunk、0.2 秒），并报告每条标记落在哪个文件 |
| 登录段点不到「登录」按钮 | AntD 把两个汉字排成「登 录」，而且滑块验证码没过时按钮是 disabled。改成用 `slide-captcha` 的 `data-testid` 拖满，完成信号读轨道的 `aria-valuenow=100`（验证通过后滑块元素**不会**消失，别按"消失了"判） |
| 找不到「创建知识库」按钮 | 这台机器的知识库开关本来是关的，页面上只有「未启用知识库」引导卡。为了跑断言去 `PUT /feature` 会把用户设置改掉，所以改成如实记录"没打开弹窗"；表单默认值改由服务出来的 `zh` 语言分片证明 |

### 但这一轮也查出产物自己的一处真缺陷

上面四条是工具的错，下面这条是**产品的**：装好的 z08 客户端对已下载的
`BAAI/bge-small-zh-v1.5` 调 `POST /api/knowledge-bases/onnx-test` 回
`{'ok': false, 'error': 'Could not load model BAAI/bge-small-zh-v1.5 from any source'}`，
而磁盘上 `model_optimized.onnx` 有 94,781,076 字节、文件齐全。

对照实验（**同一个 exe、同一批文件**，只改缓存目录的写法）：

| 缓存写法 | 接口回答 |
|---|---|
| `snapshots/cos-mirror` + `refs/main = "cos-mirror\n"` | `ok=false`，"Could not load model …" |
| `snapshots/<40 位哈希>` + `refs/main` = 那个哈希、**不带换行** | `{'ok': true, 'latency_ms': 219, 'dim': 512}` |

根因与修法见 `CHANGELOG.md` 的 z09 一节：`huggingface_hub` 只认 40 位提交哈希那种寻址，
且 1.33 读 `refs/main` 时不会 strip 换行——两条都错了，所以"镜像下载成功"之后加载仍然
要连 huggingface.co。连得上的机器等于下载两遍，连不上的机器知识库永远起不来。
z09 修下载写法，并加 `normalize_mirror_layout()` 在加载前就地修好存量缓存。

### 门禁（z09 这一轮）

- `ruff check` / `ruff format`：改动文件全绿（上游 `bridge.py`、`update.py` 按既定原则不动）。
- `scripts/rebrand.py --check`：**3274 文件扫过，无旧品牌残留**。
- `pytest tests/unit/agents tests/unit/knowledge`：**811 passed / 3 skipped**，其中
  `tests/unit/agents/test_onnx_cache_layout.py` 8 条是这次新增的。
- 前端本轮没有改动，z08 发版时的门禁数字（`tsc -b` 通过、后端 533 passed、
  受影响文件 vitest 44 passed、全量 vitest 与干净树对照无回归）仍然成立。

### 一条必须说的安全事实

`CHANGELOG.md` 的 z04 一节曾写有验收用的管理员口令明文，公开仓库的历史不可撤销，
现在那一行只描述账号、不写口令。装机后请用 z06 的本地重置流程换成用户自己的口令；
后续任何文档与提交都不再写出口令明文（验收工具改成从 `ZC_VERIFY_PASSWORD` 读）。

## 1.0.2b6+z07 · 2026-10-11（首次用 `scripts/verify/client_release.py` 一条命令跑完）

```
resolved zcagent-desktop-windows-amd64-1.0.2b6+z07.exe: 192,187,491 bytes, sha256 b1b5effeda882464...
download verified: 192,187,491 bytes, hash matches the release digest
reusing the existing install at C:\Program Files\zcagent
unpacked runtime: 1.0.2b6+z05 -> 1.0.2b6+z07
  bundle carries the 1.0.2b6+z03 change: True
  bundle carries the 1.0.2b6+z06 change: True
  stored_locale: None
  login_is_chinese: True
  login_has_english_signin: False
  account_hint: 这台机器上已有智策数据，登录账号是 admin。
  recovery_form: True
  modal_shows_cli_command: False
  installed icon: .zc-verify/reports/icon-1.0.2b6+z07.png sha256 62a05850012c9506...
ALL ASSERTIONS HELD
```

要点：**升级链在真机上恢复了**——这台机器停在 `+z05` 的解压运行时，装上 z07 后被替换成 `+z07`。
图标从**装好的 exe** 里抠出来确认是边牧（z02 那台是上游红章鱼）。登录页点名账号、
「忘记密码」是表单且不含 `octop user passwd`。

### 过程中被工具拦住的一次假验收

第一次跑链条时，负责"释放 8088"的 PowerShell 里 `$_` 被 bash 展开掉了，开发实例没被杀，
`8088` 仍在应答。工具的启动前置检查直接拒绝：

> `8088 already answers -- an older client or the dev server is running, and every check below
> would read its bundle instead of the new one`

没有这条断言，那一轮会**全绿**——因为读的是旧服务的 chunk。这正是当初 z03 修复"在产物里却看不见"
的同型问题，工具把它变成了硬失败。

### 仍未自动验证的一项（已于 z07 人工确认）

WebView2 里右键菜单**实际弹出来的样子**没有自动化验证（原生窗口截图在这台机器拿不到有效画面）。
`context_menu.go` 的内容、"不许出现 save/print/另存/打印"、以及两个窗口都关掉内建菜单，
都由 Go 测试锁住。装机后人工右键看过：**只剩「上一页 / 重新加载系统」两项**，与断言一致。
这条靠眼睛而不是自动化，所以以后动右键菜单仍需人工看一眼。

## 1.0.2b6+z05 · 2026-10-11（装机全流程，含"新客户端能否替换旧运行时"的验收）

这一节验的是 z04 那个比较器修复：**保留一台机器上第一次解压出来的旧运行时，再装新版，看它会不会换掉。**

| 项 | 结果 |
|---|---|
| 下载完整性 | `zcagent-desktop-windows-amd64-1.0.2b6+z05.exe` = **192,372,790 字节**，本机重算 SHA256 = `d0a36437f25259e8…`，与 Release API 的 `digest` 一致（`gh release download` 曾在本项目对残缺文件返回 0，所以用 curl 续传 + 字节数核对） |
| 起始状态 | `~\.octop\portable\VERSION.txt` = `octop_version=1.0.2b6+z02`（就是复现 bug 的那个状态）；`8088` 服务的是 z02 的 `index.XAfRwQg_.js` |
| 静默安装 | NSIS **忽略**了正斜杠形式的 `/D=D:/otp/...`，装到默认位置 `C:\Program Files\zcagent`（注册表 `DisplayVersion=1.0.2b6+z05`）。要装到别处必须用反斜杠 |
| 替换旧运行时 | 启动 `C:\Program Files\zcagent\zcagent.exe` 后 `VERSION.txt` 变成 **`octop_version=1.0.2b6+z05`** —— z02 之后一直卡住的升级链恢复 |
| 产物内容 | `8088` 的入口 chunk 变为 `index.Scx49Zw2.js`，其中 `resolveInitialLocale(){return readStoredUiLocale()??"zh"}` 确认在包内 |
| 界面语言 | 用强制 `navigator.language=en-US`、localStorage 为空的浏览器上下文渲染（模拟 WebView2 在中文 Windows 上的表现）：登录页中文、无 "Sign in"、"忘记密码"弹窗中文 |
| 图标 | 从 exe 里抠出内嵌图标：z05/z03 = 边牧犬（钢蓝）；对照 z02 的 `C:\Program Files\zcagent` 旧产物 = 上游红色 Octop 图标 |

### 一个必须写进交付话术的事实

判断"要不要替换运行时"的比较器在 **exe 里**，不在解压出来的运行时里。所以**装了 z02/z03 的机器不会
被自己的更新检查修好**，必须重新下载并运行一次新安装程序。

### 顺带修掉的第二个英文来源

`desktop/src/settings.go` 的 `defaultSettings()` 把外壳语言钉在 `LocaleEN`，于是托盘菜单与
"First launch: unpacking the bundled runtime…"在仪表盘已经中文的情况下仍然英文。
z05 起默认中文，用户在设置窗里选的语言（`desktop-settings.json`）优先。
曾考虑按系统显示语言取默认值，实测本机 `GetUserDefaultUILanguage` 返回 `en-US`（中文 Windows
装了英文显示语言），照它走反而会造成"网页中文、外壳英文"的分裂，所以放弃。

## 1.0.2b6+z02 · 2026-10-10

| 项 | 结果 |
|---|---|
| 下载完整性 | `zcagent-desktop-windows-amd64-1.0.2b6+z02.exe` 本机重算 SHA256 = `434c71d9…80332f`，与 GitHub Release 的 `digest` 一致 |
| 内嵌元数据 | `ProductName=zcagent`、`CompanyName=zcagent`、`FileVersion=ProductVersion=1.0.2b6+z02`、`FileDescription=zcagent Installer`（PowerShell `VersionInfo` 读回） |
| 静默安装 | `installer.exe /S /D=D:\otp\deliver\installed` → 得到 `zcagent.exe` + `uninstall.exe`，共 199 MB，不需要管理员权限 |
| 启动 | WebView2 环境创建成功；应用把绿色包解到 `%USERPROFILE%\.octop\portable\`，再以 `portable\runtime\python.exe portable\launch.py run --host 127.0.0.1 --port 8088` 起服务；`GET /` 200，`GET /api/branding` 正常应答 |
| 卸载 | `uninstall.exe /S` 后安装目录清空、控制面板无残留条目 |
| **残留** | `~\.octop\portable\` **712 MB 不会被卸载删掉**（它在数据目录里，卸载器按设计不动数据目录）。交付话术里要说清楚，或给实施人员一条清理命令 |

### 开发版才有的一个坑（不是产物问题）

源码 editable 安装时，「应用更新」页显示的 `current_version` 取自 **已安装的发行版元数据**
（`importlib.metadata`），不是 `src/octop/__init__.py`。所以改完版本号没重新 `uv pip install -e .`
之前，页面会一直显示旧版本（实测显示 `1.0.2b6+z1` 而源码已是 `+z02`）。装好的 wheel / 便携包没有
这个问题——实测安装版显示的就是 `1.0.2b6+z02`。

## 1.0.2b6+z01 · 便携包（已被 z02 取代，记录保留）

解压 658 MB → `start.bat --port 8090` → 内嵌 CPython 3.12.12 起服务 → 首启向导全流程走通
（口令 → SQLite → 建管理员 → 模型可跳过）→ 登录进 `/chat`；主色 `#3d5a80`、标题「智策 …」、
可见文案无 "Octop"。当时读回的下载地址是 `https://octop.cloud/`，且包内 `README.txt` 仍写着
"Octop green portable package" —— 两处都在 z02 修掉。
