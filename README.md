# LeetCode 每日一题插件

🎯 功能强大的 LeetCode 每日一题插件，支持题目查询、AI解题分析、定时推送等功能。

## ✨ 功能特性

- 📅 **每日一题推送** - 定时推送 LeetCode 每日一题到订阅群组
- 🔍 **题目查询** - 支持按题号查询任意 LeetCode 题目
- 📝 **完整题目内容** - 显示题目描述、难度、通过率、标签等详细信息
- 🤖 **AI解题分析** - 接入 AstrBot LLM，提供智能解题思路和参考代码
- 🔗 **题目链接** - 一键跳转到 LeetCode 原题页面
- 👑 **权限管理** - 所有命令均需管理员权限，安全可靠
- 💾 **本地缓存** - 缓存今日题目，避免重复请求

## 🚀 安装

### 方式一：通过 AstrBot 插件市场安装

1. 打开 AstrBot 管理面板
2. 进入「插件」→「插件市场」
3. 搜索 `LeetCode` 并安装

### 方式二：手动安装

1. 克隆仓库到插件目录：
   ```bash
   cd /path/to/astrbot/data/plugins
   git clone https://github.com/NumInvis/astrbot_plugin_leetcode.git
   ```

2. 重启 AstrBot

## ⚙️ 配置

在 AstrBot 插件配置面板中设置：

| 配置项 | 类型 | 说明 | 默认值 |
|--------|------|------|--------|
| `admin_users` | 列表 | 管理员用户ID列表 | `[]` |

### 配置管理员

在 AstrBot 配置文件中添加管理员用户ID：

```json
{
  "admin_users": ["123456789", "987654321"]
}
```

## 📖 使用指南

### 命令列表

所有命令均需管理员权限才能使用。

#### 📋 查询命令

| 命令 | 说明 | 示例 |
|------|------|------|
| `/lc菜单` | 显示主菜单 | `/lc菜单` |
| `/lc帮助` | 显示详细帮助 | `/lc帮助` |
| `/lc今日` | 获取今日题目（含完整描述） | `/lc今日` |
| `/lc题目 [题号]` | 查询指定题号的题目 | `/lc题目 1` |
| `/lc解题 [题号]` | 使用AI分析并解答题目 | `/lc解题 1` |
| `/lc列表` | 查看当前群订阅状态 | `/lc列表` |

#### 🔧 管理命令

| 命令 | 说明 |
|------|------|
| `/lc订阅` | 在当前群订阅每日一题推送 |
| `/lc退订` | 在当前群取消订阅 |
| `/lc全部订阅` | 查看所有群的订阅情况 |

### 使用示例

#### 1️⃣ 获取今日题目
```
/lc今日
```
输出示例：
```
📅 2026-03-14
🟡 【3296. Minimum Number of Seconds to Make Mountain Height Zero】
难度: 中等
通过率: 56.6%
标签: Array, Math, Binary Search, Greedy, Heap (Priority Queue)
🔗 链接: https://leetcode.com/problems/...

📝 题目描述:
You are given an integer mountainHeight denoting the height of a mountain...
```

#### 2️⃣ 查询指定题目
```
/lc题目 1
```
查询第1题「两数之和」的详细信息。

#### 3️⃣ AI解题分析
```
/lc解题 1
```
AI将提供：
- 📖 题目理解
- 💡 解题思路（含时间/空间复杂度分析）
- 📝 算法步骤
- 💻 参考代码（Python）
- 🔑 关键点总结

#### 4️⃣ 订阅每日推送
```
/lc订阅
```
订阅后，每天会自动推送当日题目到群内。

## 🔌 AI解题前置要求

使用 `/lc解题` 命令需要：

1. AstrBot 已配置 LLM 提供商（如 OpenAI、Claude、Gemini 等）
2. 在 AstrBot 管理面板中配置好相应的 API Key

支持的大模型：
- OpenAI (GPT-3.5/GPT-4)
- Anthropic (Claude)
- Google (Gemini)
- 以及其他 AstrBot 支持的 LLM 提供商

## 🌐 数据来源

- **每日一题数据**: [LeetCode API](https://leetcode.com/)
- **题目详情数据**: [lcid.cc](https://lcid.cc/)

## 📝 更新日志

### v1.1.0
- ✨ 新增 AI 解题功能 (`/lc解题`)
- ✨ 新增按题号查询题目功能 (`/lc题目`)
- ✨ 新增完整题目内容显示
- 🔒 所有命令增加管理员权限检查
- 📈 内容显示上限提升至 6000 字符
- 🔧 简化配置，只保留管理员配置

### v1.0.0
- 🎉 初始版本发布
- 📅 每日一题定时推送
- 📋 题目信息展示（难度、通过率、标签）
- 💾 本地缓存功能

## 🤝 致谢

- 原项目灵感：[nonebot-plugin-leetcode](https://github.com/zxz0415/leetcode)
- 框架支持：[AstrBot](https://github.com/Soulter/AstrBot)
- 数据来源：[LeetCode](https://leetcode.com/)

## 📄 License

MIT License

---

<p align="center">
  Made with ❤️ for LeetCode learners
</p>
