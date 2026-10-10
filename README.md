# 智策 / zcagent

基于 **[TencentCloud/Octop](https://github.com/TencentCloud/Octop)**（MIT License）做自有品牌的 AI 助手产品。
上游原文档保留在 [`README.upstream.md`](./README.upstream.md)，逐版本改动见 [`CHANGELOG.md`](./CHANGELOG.md)，
接手前先读 [`docs/HANDOVER.md`](./docs/HANDOVER.md)（状态快照、踩过的坑、验证基线、待办），
在此仓库写代码前读 [`docs/CONVENTIONS.md`](./docs/CONVENTIONS.md)（只读区、硬红线、冲突面积纪律、追版 SOP）。

- 上游基线：`v1.0.2b6` / commit `0c5a46a`
- 许可证：上游 MIT，本 fork 同样以 MIT 发布（`LICENSE` 保留上游版权声明）

## 分支与同步模型

| 分支 | 作用 |
|---|---|
| `upstream-main` | 上游 `main` 的零改动镜像，只在追版时快进 |
| `product/main` | 产品分支，所有自有改动都在这里 |

```bash
git remote add upstream https://github.com/TencentCloud/Octop.git   # 已配置
git fetch upstream --tags
git checkout product/main && git merge upstream/v1.0.2b6            # 只 merge stable tag
```

**只 merge stable tag**（`v1.0.1`、`v1.0.2` 这种三段号）。上游 beta（`v1.0.2b1…b6`）约 2–5 天一个，追 beta 会天天解冲突。

上游的 7 条 tag 触发流水线（PyPI / docker / desktop / fnos / auto-tag / sync / anti-spam）在本仓库的 Actions 设置里**已禁用**，只保留 CI 与 CodeQL，避免我们打 tag 去触发腾讯的发布链。

## 本地跑起来

前置：Python 3.12+、Node 18+、[uv](https://docs.astral.sh/uv/)。

```bash
# 国内直连 PyPI 只有 ~75 KB/s，243 个包要半小时以上；用镜像约 4 分钟
UV_DEFAULT_INDEX=https://mirrors.cloud.tencent.com/pypi/simple uv sync

cd dashboard && npm ci && npm run build && cd ..   # 产物落到 src/octop/dashboard/（已 gitignore）

.venv/bin/octop init --admin-username admin --admin-password '<≥8位含字母和数字>'
.venv/bin/octop run                                # http://127.0.0.1:8088
```

改完前端要重新 `npm run build`；改后端字符串要重启进程才生效。

## OEM 换品牌（给别人部署时）

单一真源是 [`brand/brand.yaml`](./brand/brand.yaml)，工具是 `scripts/rebrand.py`：

```bash
python scripts/rebrand.py --apply    # 改名 / 换色 / 从主图标生成全套产物与字标
python scripts/rebrand.py --check    # 断言没有旧品牌残留，并报告"未被覆盖"的文件
python scripts/rebrand.py --revert   # 还原本工具改过的一切
python scripts/rebrand.py --status   # 看 diff 面积
```

换一家客户 = 改 `brand.yaml` 的 `name.en` / `name.zh` / `colors.brand` / `identity.*`，换一张 `brand/assets/icon-1024.png`，然后 `--apply`。
字标（牧羊犬 + 中文名 + 英文名）由 PIL 用系统 CJK 字体排版生成，**不是** AI 生成文字，所以改名字自动重出、不会糊。

### 绝对不要改的标识符

这些改了会破坏数据兼容或对外协议，`rebrand.py` 已把它们排除在外：

| 保留项 | 原因 |
|---|---|
| Python 包名 `octop` / `src/octop/` | 依赖名 `octop-harness` 等是上游 PyPI 真名 |
| `OCTOP_HOME`、`~/.octop`、`octop.db` | 已在磁盘上的用户数据；且在 Go 桌面壳与 4 种启动脚本里各写一遍 |
| 专家工作区 `.octop/` | 路径已持久化进 DB 行，改了会孤儿化所有已有专家 |
| `X-Octop-*` 请求头 | 前后端两份常量；改名直接断云端协同（对端是别的实例） |
| AntD `prefixCls="octop"` | 所有 `.octop-*` 覆盖样式依赖它 |
| `octop:*` localStorage key | 25+ 处散落，改了丢用户偏好 |
| 侧边栏 19 个 nav key | 与后端 `infra/users/preferences.py` 交叉校验，改 key 会让已存配置失效 |
| `infra/db/migrations/00N_*` 编号 | 自加编号会在追版时硬冲突；私有数据放独立库 |
| i18n 的 **key**（如 `askOctopHint`） | 只改 value；改 key 会破前后端 key 奇偶校验测试 |

## 更新源

`/admin/advanced?tab=updates` 检查的是一个 PyPI JSON API。企业内网部署时把索引指到自己托管的包：

```bash
OCTOP_UPDATE_INDEX_URL=https://devpi.internal.example.com   # 默认 https://pypi.org
```

**自建 devpi 需要多给两个变量**（实测：devpi 的 `/pypi/<name>/json` 只服务 `root/pypi` 镜像，私有 index 的形状是 `/{user}/{index}/{name}/`，响应键为 `{"result": {版本号: …}}`）：

```bash
OCTOP_UPDATE_JSON_URL=http://devpi.internal:3111/zcagent/prod/{name}/     # 查版本
OCTOP_UPDATE_SIMPLE_URL=http://devpi.internal:3111/zcagent/prod/+simple/  # 装包
```

配了自有索引后，安装候选只包含该索引，不会回落公共镜像或 pypi.org。更新检查默认**关闭**：`OCTOP_UPDATE_CHECK=1` 显式打开，或配置上述任一变量时自动打开。

> 私有 index 要 `bases=root/pypi` 建，否则一键升级解析不到依赖。实测到的部分：`probe_index` 在我们的 `root/dev/+simple/` 上返回 `has_version`，`rank_install_indexes` 只返回这一个候选；**没有**实测真正的"点一下装完"（本机 devpi 的 `root/pypi` 镜像取不到外网包，`+simple/waitress/` 返回"project does not exist"）。

版本号规则是 `<上游基线>+z<两位序号>`（例：`1.0.2b6+z01`）。**序号必须零填充**：PEP 440 对字母数字 local 段按字符串比较，`+z10` 会排在 `+z9` 下面，不填充就等于给 pip 一个降级包。

分发名仍是 `octop`（它同时是 pip 升级目标和已安装发行版查询名），所以本仓库目前**不发布** PyPI 包；PEP 440 local version 本来也上不了 PyPI，内网索引正合适。

## 已知平台限制

- **`工作台 / 终端` 在 Windows 上不支持**：`src/octop/api/routers/terminal.py` 依赖 `pty`/`fcntl`，代码里显式给出 "not supported on Windows"。要在 Windows 用这块得走 Linux/macOS 或容器。
- **浏览器 AI+ 需要 Chromium**：`playwright install chromium`。注意 npmmirror 没有托管新版 Chrome-for-Testing 构建（404），无头截图可直接用系统 Edge：`p.chromium.launch(channel="msedge")`。

## 质量门禁

上游 `make all` = Ruff + `mypy --strict src/octop` + pytest；前端另有 `tsc -b`、ESLint、Prettier 和 **218 个 vitest 文件**。
注意上游 `ci.yml` **没有 Node job**、`Makefile` 也不跑 vitest，所以前端这 218 个文件在上游 CI 里从不执行——本仓库的自检要自己盯：

```bash
.venv/bin/python -m pytest -m "not live" -q          # 全量很慢，改品牌时用 --status 找受影响文件
cd dashboard && npx vitest run
```

本仓库的 `Frontend` workflow（PR 与 `product/main` push）执行 `npm ci` → `npm run lint` → `npm run format:check` → `npm run build`（含 `tsc -b`）→ vitest 汇总（vitest 暂不阻塞，先建立基线）。

两条与门禁相关的约定：

- **格式化属于 `--apply`**：替换品牌词会改变字符串长度，prettier 于是要求重新换行；`scripts/rebrand.py` 在重写完之后对本工具刚碰过的 dashboard 文件跑 prettier。别把它当成"记得手工 `npm run format`"——第一次追版之后就会静默变红。
- **换行由 `.gitattributes` 固定为 LF**：仓库里所有文本 blob 都是 LF，但 Windows 检出配合 `core.autocrlf=true` 会给出 CRLF 工作树，`format:check` 便把上千个干净文件报成脏。遇到这种情况先信 CI，别急着 `prettier --write .`。
