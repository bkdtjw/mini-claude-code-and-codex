# 推特大模型LLMAgent热门消息

基于推特（X）上关于「大模型」「LLM」「agent」的热门推文（Top tweets），我为你整理了一份最新中文摘要：

---

## 📊 推特 AI 热门讨论摘要

### 一、关键观点

**1. 头部模型陷入「能力焦虑」与「降智」争议**
- **Claude Opus 4.6 口碑下滑**：多位高互动推文指出 Opus 4.6「非常拉」「基本不带思考」，猜测「降智是各大模型的必然结果」（@python_xxt）。
- **Anthropic 新动向**：传闻将推出新模型 **Mythos**（@Balder13946731），同时推出 **advisor tool**，让 Sonnet/Haiku 等小模型在执行任务时可调用 Opus 进行指导，以控制算力成本（@claudeai、@op7418）。
- **ChatGPT 6 传闻**：有消息称将于 4 月 14 日发布，号称性能提升 40%，尤其在代码和 Agent 能力上（@Balder13946731）。

**2. Agent 基础设施进入「托管化」竞争**
- **Claude Managed Agents 公开 Beta**：Anthropic 开始提供生产级 Agent 托管服务，Notion、Asana 等已接入，宣称「原型到上线只要几天」（@servasyy_ai）。
- **Hermes Agent 崛起**：被社区视为 **OpenClaw（龙虾）以来第一个真正的竞争对手**，Nous Research 开源，GitHub 星标近两月接近 3 万（@dotey）。
- **工程方法论之争**：@lidangzzz 反复强调 **goal-driven（目标驱动）** 是唯一正确路径——必须以 goal 为对齐目标、以大量 test 为评判标准、用 master agent 监督 subagent。

**3. 端侧 AI 与本地部署成新热点**
- **Google Gemma-4 跑上 iPhone**：通过 Google AI Edge Gallery 本地运行（约 3G），支持中文且数据可离线使用，被视为端侧大模型的重要里程碑（@joshesye）。

**4. 国产模型商业化与中美差距**
- **涨价风波**：GLM 顶配套餐被指从 600 美元涨至 1500 美元，引发「国产大模型乘 Opus 限制龙虾之机疯狂捞钱」的批评（@0xVeryBigOrange）。
- **差距评估**：智谱 CEO 张鹏表示，中美大模型差距仍在 **6–12 个月**（@jike_collection）。
- **地缘政治**：美国三大 AI 公司被指要联手反击中国模型「抄袭和蒸馏」（@baoshu88）。

**5. 个人知识管理与长期记忆**
- **Karpathy 的 LLM Wiki 方案刷屏**：Andrej Karpathy 提出的个人 LLM Wiki 理念获超 2500 万曝光，被评价为「比 Auto Research 更有创意」，多位博主已落地改造自己的笔记系统（@karpathy、@dotey、@fankaishuoai）。
- **MemOS 等记忆方案受关注**：将 Memory 从 Prompt 中抽离，解决长 Session 的 Context 与 Token 膨胀问题（@HiTw93）。

---

### 二、热门账号

| 账号 | 领域 | 特点 |
|------|------|------|
| **@lidangzzz（立党）** | LLM/Agent 工程方法论 | 中文推圈最具代表性的「硬核派」，高频输出关于 goal-driven、benchmark、multi-agent 的犀利观点 |
| **@dotey（宝玉）** | 产品评测与技术解读 | 关注 Hermes Agent、Agent Loop、Karpathy 方案等前沿落地 |
| **@HiTw93（Tw93）** | 技术实践 | 深耕大模型训练、Agent 长期记忆、英文 prompt 优化 |
| **@Balder13946731** | AI 传闻/八卦 | 高互动爆料账号，ChatGPT 6、Mythos 等消息源 |
| **@karpathy** | 顶级 AI 研究员 | LLM Wiki 理念发起人，单条推文曝光超 600 万 |
| **@python_xxt** | 开发者吐槽 | 对 Claude「降智」的批评引发广泛共鸣 |

---

### 三、讨论趋势

1. **从「拼模型智商」转向「拼 Agent 工程化」**：社区关注点明显从单纯的 benchmark 分数，转向如何搭建 goal-driven、可托管、带长期记忆的 Agent 系统。
2. **端侧化与离线化兴起**：Gemma-4 上手机代表「大模型不离云」的叙事正在被打破，本地隐私与成本优势受到追捧。
3. **订阅风险与工具迁移**：Claude 对「openclaw/龙虾」的封杀导致大量用户被迫迁移至 GPT 或国产模型，引发对「包年订阅大模型风险」的反思（@hexiecs）。
4. **Token 消耗观的颠覆**：头部 KOL 开始普及「未来每人每小时消耗 5000 万–1 亿 token」的观念，multi-agent 的「费 token」不再被视为缺点，而是生产力价值本身。

---

> **总结**：当前推特中文 AI 圈的核心情绪是**焦虑与兴奋并存**——既担心头部模型「降智」和地缘政治带来的工具割裂，又对 Agent 托管、端侧部署、个人 LLM Wiki 等新范式充满期待。