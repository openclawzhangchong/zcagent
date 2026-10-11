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
| 页面白屏、控制台报 CSP | `_headers` 里的 `Content-Security-Policy` 只允许同源资源；新加外链资源时要一起放开 |