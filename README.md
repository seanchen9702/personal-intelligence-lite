# Personal Intelligence Lite

低成本个人 AI 情报系统的最小可运行版本。

## 这个 V0.1 目前只做什么

1. 从 Simon Willison 的公开 Atom Feed 获取最新长文。
2. 每次最多处理 5 条尚未分析的内容。
3. 使用 `gpt-5.6-luna` 按你的个人内容筛选规则进行 PIS 评分。
4. 输出中文标题、摘要、价值判断、信息性质和建议动作。
5. 将结果保存到 `data/items.json`，并由 GitHub Actions 自动提交回仓库。

暂时**不做** YouTube、X、邮件、Weekly、数据库。先证明端到端链路可用。

## 第一次运行

### 1. 创建一个 GitHub 私有仓库

建议名称：

`personal-intelligence-lite`

### 2. 上传这个项目的全部文件

注意 `.github/workflows/manual-test.yml` 也必须上传。

### 3. 创建 OpenAI API Key

在 OpenAI API 平台创建 API Key。不要把 Key 写进代码或上传到仓库。

### 4. 将 API Key 添加为 GitHub Secret

进入仓库：

`Settings → Secrets and variables → Actions → New repository secret`

Name：

`OPENAI_API_KEY`

Secret：

粘贴你的 API Key。

### 5. 手动运行

进入：

`Actions → Personal Intelligence - Manual Test → Run workflow`

### 6. 判断是否成功

成功后应看到：

- Actions 运行变为绿色；
- `data/items.json` 出现实际记录；
- 每条记录含 `pis`、`title_zh`、`summary_zh`、`why_it_matters` 等字段；
- 仓库新增一个由 `personal-intelligence-bot` 产生的 commit。

## 当前信息源

Simon Willison 的长文 Atom Feed：

`https://simonwillison.net/atom/entries/`

选择长文 Feed，而不是所有短链接/动态，目的是先降低噪音。

## 成本控制

- 每次最多分析 5 条；
- 使用低成本 `gpt-5.6-luna`；
- Feed 获取免费；
- GitHub Actions 初步测试通常可用免费额度；
- 初版不获取视频字幕、不调用 X API。

## 下一阶段

第一条链路成功后，再依次增加：

1. 每日自动调度；
2. 5-10 个 RSS / Newsletter 来源；
3. YouTube Data API；
4. 候选视频 transcript；
5. Daily Brief；
6. 邮件推送；
7. X Bookmarks。
