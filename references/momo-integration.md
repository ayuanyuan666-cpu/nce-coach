# 墨墨背单词集成

> 使用时的入口：用户选②、说"背完单词了"、或批改完成后推进到墨墨环节时 Read 本文件。

## API 配置

- Base URL: `https://open.maimemo.com/open`
- 所有请求带 `Authorization: Bearer {token}`
- Token 从 `user/learner-state.json` 的 `momo_token` 字段读取

## 拉取今日数据

```
POST /api/v1/study/get_today_items  → 今日背了哪些词、是否新词、完成状态
POST /api/v1/study/get_study_progress → 今日进度
POST /api/v1/study/query_study_records → 弱词(VAGUE/FORGET)、顽固词(STICKING)
```

## 巩固流程

拉取墨墨词汇后，先展示词汇列表，然后让用户选择巩固形式：

```
今天墨墨的词汇有：<列出词汇>
你想怎么巩固？
① 来点阅读材料 —— 用这些词生成故事、对话、日记什么的，我来读
② 我来造句 —— 针对薄弱词做四句型转换，你造我批改
③ 随便 —— 你帮我挑一个
```

用户选择后直接执行，不再次弹出菜单。子菜单仅在进入墨墨模块时展示一次。

## 造句规则（②）

针对墨墨薄弱词汇（VAGUE/FORGET）：
- 先讲词：中文解释意思、常见用法、给一个例句
- 再让用户做四句型转换
- **一句一句出**，不是五句全出完再等用户。每句给出后等用户回答、批改，再给下一句
- 五句写完后统一小结

## 阅读材料规则（①）

- 每次生成一篇后，必须问用户"还要再来一篇吗？"或提示切换形式/主题
- 用户不主动说停就不退出墨墨巩固环节，持续循环输出
- 形式+主题从 `references/content-pools.md`（Read 该文件获取完整池）中选取
- 生成前查看 `content_preferences`，生成后**立即**记录反馈
- 故事规则：短小精悍、当前语法水平为基准可略超一点点（i+1 原则）

## 顽固词攻坚

当 query_study_records 返回 STICKING 或 last_response=FARGET/VAGUE 的词：
1. 结合 NCE 课文语境，为这些词生成个性化助记 + 例句
2. 通过以下 API 写回墨墨：
```
POST /api/v1/notes  → 助记 (note_type可用: 谐音/联想/拆分/场景)
POST /api/v1/phrases → 例句 (含翻译)
```
3. 告知用户"已写入，明天打开墨墨就能看到"

## 边缘情况

- API 返回空数据 → 提示"墨墨那边还没数据，今天打开 App 同步一下？"
- Token 未配置时 → 引导用户去墨墨 App→设置→开放 API 申请 token
