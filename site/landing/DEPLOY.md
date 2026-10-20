# Cloudflare Pages 部署

官网（`site/landing/`）的部署记录。**这份文件是为了下次部署时不用再翻聊天记录**：
账号、项目名、域名、命令、出错时怎么办，都在这里。

## 目标

| 项 | 值 |
|---|---|
| Cloudflare 账号 ID | `b945f659e7168126d8c819670695bd9f` |
| Pages 项目名 | `zcagent` |
| 自定义域名 | `zcagent.jiuyeke.cn` |
| 源码仓库 | `openclawzhangchong/zcagent`（**公开仓库**），分支 `product/main` |
| 构建命令 | `python site/landing/build.py` |
| 输出目录 | `site/landing/dist` |

## 令牌不在这个仓库里

**本仓库是公开的。** API 令牌绝不能提交进来——那等于把 Cloudflare 账号的写权限
公开给所有人。本文件只记账号 ID、项目名、域名与流程；令牌放在**本地**被 git 忽略的文件里：

```
site/landing/.cloudflare.env      # .gitignore 已覆盖
```

```dotenv
CLOUDFLARE_ACCOUNT_ID=b945f659e7168126d8c819670695bd9f
CLOUDFLARE_API_TOKEN=<在这里放令牌>
```

换机器或换人接手时，令牌需要重新签发，不在版本历史里。

## 本地部署（wrangler 直传）

```powershell
# 1. 读入本地令牌
Get-Content site/landing\.cloudflare.env | ForEach-Object {
  $n, $v = $_ -split '=', 2
  if ($n) { Set-Item -Path "env:$n" -Value $v }
}

# 2. 构建
.venv\Scripts\python.exe site\landing\build.py

# 3. 上传
npx wrangler@4 pages deploy site\landing\dist --project-name zcagent --branch main
```

## 首次配置（已经做过，换账号时才需要重跑）

```powershell
npx wrangler@4 pages project create zcagent
npx wrangler@4 pages project list
```

## 绑定自定义域名

Pages 控制台里 **Workers 和 Pages → zcagent → Custom domains → Add**，填
`zcagent.jiuyeke.cn`。域名在同一个 Cloudflare 账号下时，CNAME 会自动建。

也可以走 API：

```powershell
$h = @{ Authorization = "Bearer $env:CLOUDFLARE_API_TOKEN" }
Invoke-RestMethod -Method Post `
  -Uri "https://api.cloudflare.com/client/v4/accounts/b945f659e7168126d8c819670695bd9f/pages/projects/zcagent/domains" `
  -Headers $h -Body (@{ name = "zcagent.jiuyeke.cn" } | ConvertTo-Json)
```

## Cloudflare Pages 的 Git 集成（可选）

不想每次手动传，就在控制台 **Pages → Create → Connect to Git → 选
`openclawzhangchong/zcagent`**，然后：

- Production branch：`product/main`
- Build command：`python site/landing/build.py`
- Build output directory：`site/landing/dist`

环境变量不用加任何密钥——`build.py` 只读仓库里已有的 `release.json` 与 `brand.yaml`。
`Pillow` 是可选的，缺了只跳过 `assets/og-cover.png`。

## 发版后怎么更新官网

官网的版本号、字节数、SHA256、下载地址都来自 `site/download/release.json`。
发新 tag 时改那份 JSON，然后：

```powershell
# 从 Release API 取权威数字，再一起构建
$env:GH_TOKEN = gh auth token
.venv\Scripts\python.exe site\landing\build.py --from-github
```

`--from-github` 按 JSON 里钉住的 tag 取那一版发布，不猜"最新"；拿不到 `digest` 就失败退出。
**没有校验值的下载页不如没有**，所以这里不允许静默降级。

## 出错了怎么办

| 现象 | 原因 / 处理 |
|---|---|
| `build.py` 报 `template uses tokens that no data source provides` | 模板里写了数据源给不出的 `{{TOKEN}}`。补进 `build_tokens()` 或改掉模板——不要留空位 |
| `build.py --check` 报 `stale:` | `dist/` 与模板不一致，重跑一次 `build.py` |
| wrangler 报 10000 / 认证失败 | `CLOUDFLARE_API_TOKEN` 没生效，确认 `.cloudflare.env` 里有值且 `$env:` 已设置 |
| wrangler 报 10090 / 项目不存在 | 先 `pages project create zcagent` |
| 域名绑定后打不开 | 看 Pages 的 **Custom domains** 状态是否变成 Active；未 Active 时检查 DNS 里有没有同名冲突记录 |
| 页面内容更新了但线上还是旧的 | 直传时要带 `--branch main` 才进 production；不带只会得到一个 preview 别名，线上看不出任何变化 |
| 想比"线上和本地 dist 是不是同一份"，字节数对不上 | **别用字节数或 sha 比**。Pages 会压缩 HTML（实测本地 `index.html` 36,145 字节 → 线上 16,867 字节）。比结构标记：`<title>`、版本号、产物摘要串 |
| 刚部署完 curl 还是旧内容 | 生效有几十秒延迟。轮询到出现新标记为止，不要 sleep 一次就下结论 |
| `npx wrangler` 报找不到 node / 命令无输出 | 本机 `which node` 是空的，但 `C:\Program Files\nodejs\node.exe` 存在（v24.20.0）。每条命令显式前置：`PATH="/c/Program Files/nodejs:$PATH" npx --yes wrangler@4 …` |

## Git Bash 版（本仓库日常实际用的那条路）

PowerShell 那套在前一节；下面这条是这台机器上真正跑通的序列，
令牌仍然只在 `site/landing/.cloudflare.env`（被 git 忽略，**永远不要写进任何 .md 或提交**）：

```bash
cd /d/otp/Octop
PATH="/c/Program Files/nodejs:$PATH" .venv/Scripts/python.exe site/landing/build.py
set -a && . site/landing/.cloudflare.env && set +a
PATH="/c/Program Files/nodejs:$PATH" npx --yes wrangler@4 pages deploy site/landing/dist \
  --project-name zcagent --branch main

# 部署后核验：读 API + 读线上，不信上传回显
curl -sS -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CLOUDFLARE_ACCOUNT_ID/pages/projects/zcagent" \
  | .venv/Scripts/python.exe -c "import json,sys; r=json.load(sys.stdin)['result']; print(r['production_branch'], r['domains'])"
curl -sSL "https://zcagent.jiuyeke.cn/?v=$(date +%s)" | grep -o "1\.0\.2b6+z[0-9][0-9]" | sort | uniq -c
```

实测一次的成本：构建 29 个文件、上传 1.3 秒（26 个文件命中缓存），
线上约 40 秒后切过去。

两条后来补上的事实：

- **目录页不需要写重定向规则。** `/guide` 不带斜杠时 Pages 自己就 301 到 `/guide/`
  （实测 `status=301 redirect=…/guide/`），所以 `_redirects` 里那条是多余的，已删。
- **构建与部署之间必须用 `&&`。** `build.py` 开头会 `rmtree(dist)`，所以它一旦失败，
  `dist/` 就是残缺的；这时若用 `;` 接 wrangler，会把半份站点推上线而 wrangler 照样回
  "Deployment complete"。命令里再加一道存在性检查（`test -f dist/index.html` 与
  `test -f dist/guide/index.html`）才部署。
- 多页之后 `dist/` 的文件数会随页面数变化（单页 32、干净检出 26，差别在并行改动里
  未跟踪的那几张屏），**别把文件数当正确性判据**，用 `build.py --check`。
| 页面白屏、控制台报 CSP | `_headers` 里的 `Content-Security-Policy` 只允许同源资源；新加外链资源时要一起放开 |

## z11 这一版**没有**部署 landing：HEAD 自身构建不出来

发 z11 时下载页（Qoder Sites）已核对上线为 z11，官网停在 z10。原因不是忘了，是
`python site/landing/build.py` 在**干净检出**上跑不通，两条都是 `bb409021`（改首屏那枚 pill）留下的：

1. 那次把线上版本的模板抄进了仓库，模板因此开始用 `{{CHANGELOG_URL}}`、`{{DOC_URL}}`、
   `{{INSTALL_URL}}`、`{{INSTALL_PS1_URL}}`、`{{ISSUES_URL}}` 这五个 token，而**已提交的
   `build.py` 一个都不提供** → 构建直接以
   `template uses tokens that no data source provides` 失败。这五个 token 与
   `src/_redirects` 目前只存在于未提交的工作区。
2. 就算补上 1，模板还引用 `./assets/screens/{tasks,expert-market,skill-market,connectors}.png`
   四张图，同样只在未提交的工作区里（由 `screens/*.html` + `shot_screens.py` 生成）
   → 死链门禁报 4 个 dead link 后退出。

线上那五枚短链是好的（`/repo`、`/issues`、`/changelog`、`/docs`、`/install` 逐个实测 302，
目标与 `_redirects` 一致），所以**访问者没有坏链**，只是版本号落后一版。

**怎么解**：把在做的这套 landing 改动（`build.py` 的 token、`src/_redirects`、
`screens/*`、`shot_screens.py`、重拍的四张 PNG）作为一个整体提交，然后在干净检出上跑
`build.py`，让门禁自己判定它是否完整——不要从工作区直接部署。
提交后重新 `build.py` 一次即可拿到 z11，因为版本号全部来自 `site/download/release.json`，
而那份已经是 z11。

> 教训：**模板、builder、资源必须同一次提交落地。** 只把"线上看起来对的那一版"抄进
> 模板，等于让仓库落后于线上 yet 又领先于自己——两边都对不上，而且 `git diff` 看不出来。
