# LeetCode 每日一题提醒插件

定时获取 LeetCode 每日一题并推送到订阅的群组

## 来源与致敬

本项目移植自 [nonebot-plugin-leetcode](https://github.com/zxz0415/leetcode)，感谢原作者的出色工作！

## 安装

1. 在 AstrBot 插件管理面板中添加仓库地址：
   ```
   https://github.com/NumInvis/astrbot_plugin_leetcode
   ```

2. 点击安装即可

## 配置

在 AstrBot 插件配置面板中设置：
- `check_interval_seconds`: 检查间隔（秒），默认 3600
- `inform_hour`: 提醒时间（小时，24小时制），默认 9
- `inform_minute`: 提醒时间（分钟），默认 0
- `admin_users`: 管理员用户列表

## 使用

### 基本命令

- `/lc菜单` - 查看主菜单
- `/lc帮助` - 查看详细帮助
- `/lc今日` - 立即获取今日题目
- `/lc列表` - 查看当前群订阅状态

### 管理命令

- `/lc订阅` - 在当前群订阅每日一题
- `/lc退订` - 在当前群取消订阅
- `/lc全部订阅` - 查看所有群的订阅（仅管理员）

### 示例

订阅每日一题：
```
/lc订阅
```

立即查看今日题目：
```
/lc今日
```

## 功能特性

- 📅 每日定时推送 LeetCode 每日一题
- 🔢 显示题目难度（简单/中等/困难）
- 📊 显示题目通过率
- 🏷️ 显示题目标签
- 🔗 提供题目链接
- ⏰ 可自定义推送时间
- 📋 支持多群订阅
- 💾 本地缓存今日题目

## 数据来源

题目数据来自 [LeetCode 中文站](https://leetcode.cn/)

## 致谢

- 原项目：[nonebot-plugin-leetcode](https://github.com/zxz0415/leetcode)
- 数据来源：[LeetCode](https://leetcode.cn/)

## License

MIT License
