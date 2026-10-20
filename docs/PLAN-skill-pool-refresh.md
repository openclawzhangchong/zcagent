# 已安装的技能，对话里的模型看不见 —— 根因与修法

报告现象：从内置插件市场装了 `beatra`，界面「技能」里它是开着的，对话里也用 `/beatra`
点名了，但模型「感觉不到」——它只列出 `/daily-hot-news`，当没有 `beatra` 这个技能。

结论先说：这不是市场安装的 bug，是**技能池在每个会话里被永久冻结**；顺带发现
**禁用技能同样到不了提示词**。两处都是上游包（`deepagents` / `octop-harness`）的行为，
不指望追版能修好，所以我们自己在回合开始前把真相写回状态。

## 1. 事实（全部实测，不是读代码推的）

### 1.1 现网数据

装机实例（`1.0.2b6+z13`）里 `GET /api/agents/G20BE4/skills` 返回 27 条，`beatra`
是 `enabled: true`；但直接解出该 agent 的 LangGraph checkpoint：

| 会话 | 最新 checkpoint 时间 | `skills_metadata` | 有 beatra |
|---|---|---|---|
| `thr_01M5CSX2…` | 22:06（比安装晚 3 分钟） | 26 条 | 否 |
| `thr_01M4PZM1…` | 21:58 | 26 条 | 否 |
| 其余两条 | — | 26 条 | 否 |

四条会话共用同一个内容寻址 blob（`hm_checkpoint_blobs` 里只有一份 26 条的
`skills_metadata`）。也就是说：**回合一直在跑，技能池一个字节都没变过。**

### 1.2 文件本身没问题

用真正的解析器（`deepagents.middleware.skills._parse_skill_metadata`）直接跑这两个
`SKILL.md`：`beatra` 22,418 B、LF、无 BOM、`name` 与目录名一致、description 386 字，
解析通过。`Skipping …: no valid YAML frontmatter` 之类的静默丢弃可以排除。

### 1.3 冻结机制，最小复现

`SkillsMiddleware.before_agent` 开头就是：

```python
if "skills_metadata" in state:
    return None
```

通道已存在就什么都不做，而这个通道会被 checkpoint 持久化（`octop_memory` 还专门把它
列为「稳定通道」外置存储）。控制实验：

```
turn 1 skills: ['alpha']
（在对话开着的时候装上 beta）
turn 2 returned: None (re-scan skipped)
turn 2 skills: ['alpha']          -> beta visible to the model: False
new-thread skills: ['alpha','beta'] -> 新会话能看见
```

所以「新开一个对话」当时是唯一的绕法——这是个可用的产品答案吗？不是。

### 1.4 附带发现：禁用也到不了提示词

`SkillFilterMiddleware` 的文档说自己「把被禁用的技能从 `skills_metadata` 里去掉，
因此不会出现在系统提示词中」。按真实中间件顺序合成一遍再打印系统消息：

```
pool: ['alpha', 'beta']
skills the model was actually shown:
    - **alpha**: skill alpha
    - **beta**: skill beta
=> disabling a skill is INVISIBLE to the prompt
```

原因：`create_deep_agent` 把 `SkillsMiddleware` 放在栈底第一位，而
`factory._chain_model_call_handlers` 明确「first in list becomes outermost」，
所以技能段落早在 filter 覆盖 state 之前就已经渲染完了。它的
`wrap_tool_call`（拦住对 `skills/<slug>` 的文件与命令访问）是生效的——只有提示词这一路没用。

## 2. 修法

上游两个包我们都不拥有，能动的只有宿主侧。既然**提示词只认通道里的内容**，那正确
的位置就是把「当前应当展示的技能列表」写回通道：

`src/octop/infra/skills/thread_state.py`

1. 用 agent 自己的 `backend` + `workspace.skill_paths(extra=config.skills_dir)`
   构造一次 `SkillsMiddleware`，拿空 state 调 `abefore_agent`——空 state 是唯一会
   触发真扫描的输入，产出的形状与路径拼法因此和新建会话时**完全一致**；
2. 按 `config.skills_disabled` 过滤掉禁用项（用上游自己的 `skill_identity_keys`）；
3. 对结果取签名（name/description/path + 加载错误，排序后哈希），与该会话上次写入
   的签名比较；
4. 不一致才 `graph.aupdate_state({"configurable": {"thread_id": …}}, {...})`。

调用点在 `AgentManager.stream()` 里，紧贴既有的
`_apply_pending_bootstrap_graph_refresh`，并且在**会话执行锁内**——那个锁的存在理由
就是「同一线程并发会交错写 checkpoint」，我们的写入必须遵守。失败只降级为「本轮不够
新」，绝不让对话报错。

两个设计上的巧合值得记下来：

- **冻结反过来帮我们**：写完通道后 `before_agent` 会跳过，所以不会有一轮中途再扫描
  把我们写的覆盖掉；
- **禁用与启用因此一起好了**：签名算的是过滤后的列表，所以 toggle 也算变更。若哪天
  上游修了中间件顺序，我们这份过滤变成「对子集再减一次」，幂等，不怕合并。

代价：每回合多一次全量扫描。27 个技能实测 **32.7 ms**（`download_files` + YAML 解析），
相对一次模型调用可以忽略；checkpoint 只在签名变化时多写一行。

## 3. 验收

`scripts/verify/skill_turn_probe.py` —— 自带 scratch 控制面（独立 `OCTOP_HOME`、 spare 端口），
真模型跑两回合：

* 前门口令 `PROMPT-<rand>` 只写在 frontmatter `description` 里，那才是系统提示词携带的部分；
* 后门口令 `BODY-<rand>` 只写在正文里，模型要读文件才能得到。

于是「它是不是靠提示词答的」不会和「它自己翻文件翻了」混为一谈。

| | 修复前（`--expect broken`） | 修复后（`--expect fixed`） |
|---|---|---|
| 模型回答 | 「没有」 | 「存在。口令：PROMPT-73211F」 |
| 通道内技能数 | 25 → 25（纹丝不动） | 25 → 26 |
| 结论 | verdict: OK | verdict: OK |

单测 12 条在 `tests/unit/skills/test_thread_state.py`，含「禁用项不进池」「toggle 触发重写」
「无 thread_id / 无可写 graph 时不写」「签名不看顺序只看内容」「memo 有界」。

## 4. 还没做的

* **改名/删除技能后旧条目**：删除会让它从扫描结果消失，因此会被重写掉；但如果某个
  技能是被别的包挂载的，`skills_dir` 变化不在本模块的签名里——目前由 `skill_paths()`
  覆盖，够用，不再额外设计。
* **一次写一次读之外没有做 TTL**，靠进程内 memo；重启后每条会话首轮各重写一次，是
  故意的自愈（上一次进程里留下的陈旧会话因此也会被治好）。
* 上游缺陷（1.3 / 1.4）没有向他们提 issue；我们的修法不依赖上游改动。
