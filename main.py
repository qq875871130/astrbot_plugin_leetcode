"""
LeetCode 每日一题提醒插件
移植自 nonebot-plugin-leetcode
版本: 1.0.0
"""

import asyncio
import json
import os
import re
from datetime import datetime
from typing import Dict, Optional

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register, StarTools

from ._version import __version__, __plugin_name__, __author__, __plugin_desc__


def clean_html(html_content: str) -> str:
    """清理HTML标签，提取纯文本"""
    if not html_content:
        return ""
    # 移除HTML标签
    text = re.sub(r'<[^>]+>', '', html_content)
    # 解码HTML实体
    text = text.replace('&quot;', '"').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&nbsp;', ' ').replace('&#39;', "'")
    # 移除多余空白
    text = re.sub(r'\n\s*\n', '\n\n', text)
    text = text.strip()
    return text


# ============ 配置常量 ============
ADMIN_USERS: list = []


@register(__plugin_name__, __author__, __plugin_desc__, __version__)
class LeetCodePlugin(Star):
    """LeetCode 每日一题提醒插件主类"""

    def __init__(self, context: Context):
        super().__init__(context)
        self.context = context

        # 数据目录
        self.data_dir = str(StarTools.get_data_dir("astrbot_plugin_leetcode"))
        os.makedirs(self.data_dir, exist_ok=True)

        # 配置文件路径
        self.config_file = os.path.join(self.data_dir, "config.json")
        self.subscription_file = os.path.join(self.data_dir, "subscription.json")
        self.personal_subscription_file = os.path.join(self.data_dir, "personal_subscription.json")

        # 保存群的 unified_msg_origin
        self.group_origins: Dict[str, str] = {}

        # 个人订阅相关数据结构
        self.user_origins: Dict[str, str] = {}  # 保存用户的 unified_msg_origin
        self.subscribed_users: list = []   # 订阅用户ID列表
        self.user_language_prefs: Dict[str, str] = {}  # 用户语言偏好设置

        # 加载配置
        self._load_config()

        # 今日题目缓存
        self.today_question: Optional[Dict] = None
        self.today_date: str = ""

        # HTTP 会话
        self._session = None

        # 全局管理员列表
        global ADMIN_USERS
        ADMIN_USERS = self.admin_users.copy()

        # 文件写入锁
        self._file_lock = asyncio.Lock()

        # 异步任务
        self._monitor_task: Optional[asyncio.Task] = None

        logger.info(f"LeetCode 每日一题提醒插件已加载")

    def _load_config(self):
        """加载配置文件"""
        # 默认配置
        default_config = {
            "check_interval_seconds": 3600,
            "inform_hour": 9,
            "inform_minute": 0,
            "admin_users": [],
            "group_origins": {},
            "subscribed_groups": []
        }

        # 从文件加载配置
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    default_config.update(loaded_config)
            except json.JSONDecodeError as e:
                logger.error(f"配置文件JSON格式错误: {e}")
            except Exception as e:
                logger.error(f"加载配置文件失败: {e}")

        # 从 AstrBot 配置加载（优先级更高）
        try:
            # 在 AstrBot v4 中，通过 context 获取配置
            astrbot_config = getattr(self.context, 'config', None)
            if astrbot_config:
                default_config["check_interval_seconds"] = astrbot_config.get(
                    "leetcode_check_interval_seconds", default_config["check_interval_seconds"]
                )
                default_config["inform_hour"] = astrbot_config.get(
                    "leetcode_inform_hour", default_config["inform_hour"]
                )
                default_config["inform_minute"] = astrbot_config.get(
                    "leetcode_inform_minute", default_config["inform_minute"]
                )

                # 加载管理员列表
                admin_from_config = astrbot_config.get("leetcode_admin_users", [])
                if admin_from_config:
                    default_config["admin_users"] = [str(u) for u in admin_from_config]

                # 加载多语言和个人订阅配置
                default_config["default_language"] = astrbot_config.get(
                    "leetcode_default_language", default_config.get("default_language", "zh")
                )
                default_config["enable_personal_subscribe"] = astrbot_config.get(
                    "leetcode_enable_personal_subscribe", default_config.get("enable_personal_subscribe", True)
                )
                default_config["personal_inform_hour"] = astrbot_config.get(
                    "leetcode_personal_inform_hour", default_config.get("personal_inform_hour", 9)
                )
                default_config["personal_inform_minute"] = astrbot_config.get(
                    "leetcode_personal_inform_minute", default_config.get("personal_inform_minute", 30)
                )
        except Exception as e:
            logger.warning(f"从 AstrBot 配置加载失败，使用默认配置: {e}")

        # 加载订阅配置（动态修改的）
        if os.path.exists(self.subscription_file):
            try:
                with open(self.subscription_file, 'r', encoding='utf-8') as f:
                    sub_data = json.load(f)
                    if "subscribed_groups" in sub_data:
                        default_config["subscribed_groups"] = sub_data["subscribed_groups"]
                    if "group_origins" in sub_data:
                        self.group_origins = sub_data["group_origins"]
            except json.JSONDecodeError as e:
                logger.error(f"订阅配置JSON格式错误: {e}")
            except Exception as e:
                logger.error(f"加载订阅配置失败: {e}")

        self.check_interval_seconds = default_config["check_interval_seconds"]
        self.inform_hour = default_config["inform_hour"]
        self.inform_minute = default_config["inform_minute"]
        self.admin_users = default_config["admin_users"]
        self.subscribed_groups = default_config["subscribed_groups"]

        # 多语言和个人订阅配置
        self.default_language = default_config.get("default_language", "zh")
        self.enable_personal_subscribe = default_config.get("enable_personal_subscribe", True)
        self.personal_inform_hour = default_config.get("personal_inform_hour", 9)
        self.personal_inform_minute = default_config.get("personal_inform_minute", 30)

        # 加载个人订阅配置
        self._load_personal_subscription()

    def _get_group_id(self, event: AstrMessageEvent) -> Optional[str]:
        """获取群组ID"""
        group_id = event.get_group_id()
        if group_id:
            return str(group_id)
        return None

    def _save_group_origin(self, event: AstrMessageEvent):
        """保存群的统一会话标识"""
        group_id = self._get_group_id(event)
        if group_id and hasattr(event, 'unified_msg_origin'):
            self.group_origins[group_id] = event.unified_msg_origin

    def _get_session_for_group(self, group_id: str) -> str:
        """获取群的会话标识"""
        if group_id in self.group_origins:
            return self.group_origins[group_id]
        return group_id

    def _is_admin(self, event: AstrMessageEvent) -> bool:
        """检查用户是否为管理员"""
        if event.is_admin():
            return True
        sender_id = str(event.get_sender_id())
        return sender_id in ADMIN_USERS

    def _load_personal_subscription(self):
        """加载个人订阅配置"""
        if os.path.exists(self.personal_subscription_file):
            try:
                with open(self.personal_subscription_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.subscribed_users = data.get("subscribed_users", [])
                    self.user_origins = data.get("user_origins", {})
                    self.user_language_prefs = data.get("user_language_prefs", {})
            except json.JSONDecodeError as e:
                logger.error(f"个人订阅配置JSON格式错误: {e}")
            except Exception as e:
                logger.error(f"加载个人订阅配置失败: {e}")

    async def _save_personal_subscription(self):
        """保存个人订阅配置"""
        async with self._file_lock:
            try:
                data = {
                    "subscribed_users": self.subscribed_users,
                    "user_origins": self.user_origins,
                    "user_language_prefs": self.user_language_prefs
                }
                with open(self.personal_subscription_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"保存个人订阅配置失败: {e}")

    def _get_user_id(self, event: AstrMessageEvent) -> str:
        """获取用户ID"""
        return str(event.get_sender_id())

    def _save_user_origin(self, event: AstrMessageEvent):
        """保存用户的统一会话标识"""
        user_id = self._get_user_id(event)
        if hasattr(event, 'unified_msg_origin'):
            self.user_origins[user_id] = event.unified_msg_origin

    def _get_session_for_user(self, user_id: str) -> str:
        """获取用户的会话标识"""
        if user_id in self.user_origins:
            return self.user_origins[user_id]
        return user_id

    def _get_user_language(self, user_id: str) -> str:
        """获取用户的语言偏好，如果没有设置则使用默认语言"""
        return self.user_language_prefs.get(user_id, self.default_language)

    async def _save_subscription(self):
        """保存订阅配置"""
        async with self._file_lock:
            try:
                data = {
                    "subscribed_groups": self.subscribed_groups,
                    "group_origins": self.group_origins
                }
                with open(self.subscription_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"保存订阅配置失败: {e}")

    async def initialize(self):
        """插件初始化时执行"""
        self._monitor_task = asyncio.create_task(self._async_monitor())

    async def terminate(self):
        """插件卸载时清理资源"""
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

    async def _async_monitor(self):
        """异步监控任务"""
        logger.info("LeetCode 每日一题监控任务已启动")
        last_inform_date = ""      # 群组推送日期记录
        last_personal_inform_date = ""  # 个人推送日期记录

        try:
            while True:
                try:
                    now = datetime.now()
                    today_date = now.strftime("%Y-%m-%d")

                    # 检查群组订阅推送时间
                    if (now.hour == self.inform_hour and
                        now.minute == self.inform_minute and
                        today_date != last_inform_date):

                        logger.info(f"开始获取 LeetCode 每日一题(群组): {today_date}")
                        question = await self._fetch_daily_question()
                        if question:
                            self.today_question = question
                            self.today_date = today_date
                            await self._send_question_to_subscribers(question)
                            last_inform_date = today_date
                            logger.info(f"LeetCode 每日一题已推送到群组: {question.get('title', '未知')}")

                    # 检查个人订阅推送时间（可以设置不同时间）
                    if (self.enable_personal_subscribe and
                        now.hour == self.personal_inform_hour and
                        now.minute == self.personal_inform_minute and
                        today_date != last_personal_inform_date):

                        logger.info(f"开始获取 LeetCode 每日一题(个人): {today_date}")
                        question = await self._fetch_daily_question()
                        if question:
                            self.today_question = question
                            self.today_date = today_date
                            await self._send_question_to_personal_subscribers(question)
                            last_personal_inform_date = today_date
                            logger.info(f"LeetCode 每日一题已推送到个人: {question.get('title', '未知')}")

                except Exception as e:
                    logger.error(f"LeetCode 监控任务出错: {e}")

                await asyncio.sleep(30)

        except asyncio.CancelledError:
            logger.info("LeetCode 每日一题监控任务已停止")

    async def _fetch_daily_question(self) -> Optional[Dict]:
        """获取 LeetCode 每日一题 - 使用内置的 urllib"""
        try:
            import urllib.request
            import ssl

            url = "https://leetcode-api-pied.vercel.app/daily"
            logger.info(f"[每日一题] 开始获取，URL: {url}")

            # 创建SSL上下文，忽略证书验证
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            # 使用线程池执行同步请求
            loop = asyncio.get_event_loop()

            def fetch():
                req = urllib.request.Request(
                    url,
                    headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                )
                with urllib.request.urlopen(req, context=ssl_context, timeout=30) as response:
                    return response.read().decode('utf-8')

            response_text = await loop.run_in_executor(None, fetch)
            logger.info(f"[每日一题] API 原始响应: {response_text[:500]}...")

            data = json.loads(response_text)
            question = data.get("question", {})
            link = data.get("link", "")
            title_slug = question.get("titleSlug")

            logger.info(f"[每日一题] 解析数据 - titleSlug: {title_slug}, link: {link}")
            logger.info(f"[每日一题] question 对象 keys: {list(question.keys())}")

            # 获取标题（优先使用中文标题，如果没有则使用英文）
            title = question.get("title", "")
            title_cn = question.get("translatedTitle")
            logger.info(f"[每日一题] 标题 - title: {title}, translatedTitle: {title_cn}")
            if not title_cn:
                title_cn = title

            # 获取题目内容（HTML格式，需要清理）
            content_html = question.get("content", "")
            logger.info(f"[每日一题] 英文内容长度: {len(content_html) if content_html else 0}")

            # 尝试获取中文内容
            content_cn = ""
            content_cn_failed = False
            logger.info(f"[每日一题] 准备获取中文内容，title_slug: {title_slug}")
            if title_slug:
                try:
                    content_cn = await self._fetch_chinese_content(title_slug)
                    if content_cn:
                        logger.info(f"[每日一题] 中文内容获取成功，长度: {len(content_cn)}")
                    else:
                        logger.warning(f"[每日一题] 中文内容为空")
                        content_cn_failed = True
                except Exception as e:
                    logger.warning(f"[每日一题] 获取中文内容失败: {e}")
                    content_cn_failed = True
            else:
                logger.warning(f"[每日一题] 没有 title_slug，跳过中文内容获取")

            result = {
                "date": data.get("date"),
                "title": title,
                "titleCn": title_cn,
                "titleSlug": title_slug,
                "frontendQuestionId": question.get("questionFrontendId"),
                "difficulty": question.get("difficulty"),
                "acRate": question.get("acRate", 0) / 100.0 if question.get("acRate") else 0,
                "link": f"https://leetcode.com{link}" if link.startswith("/") else link,
                "topicTags": question.get("topicTags", []),
                "content": content_html,
                "contentCn": content_cn,
                "contentCnFailed": content_cn_failed
            }

            logger.info(f"[每日一题] 最终结果 - 标题: {title_cn or title}, content长度: {len(content_html) if content_html else 0}, contentCn长度: {len(content_cn) if content_cn else 0}, 失败: {content_cn_failed}")
            return result
        except Exception as e:
            logger.error(f"[每日一题] 获取 LeetCode 每日一题失败: {e}", exc_info=True)

        return None

    async def _fetch_chinese_content(self, title_slug: str) -> str:
        """从 LeetCode 中国站获取中文题目内容"""
        try:
            import urllib.request
            import urllib.error
            import ssl

            # LeetCode 中国站 GraphQL API
            url = "https://leetcode.cn/graphql"
            logger.info(f"[中文内容] 开始获取，title_slug: {title_slug}, URL: {url}")

            # GraphQL 查询
            query = {
                "operationName": "questionData",
                "variables": {"titleSlug": title_slug},
                "query": """query questionData($titleSlug: String!) {
                    question(titleSlug: $titleSlug) {
                        translatedContent
                    }
                }"""
            }

            # 使用紧凑的 JSON 格式，避免换行符问题
            query_str = json.dumps(query, separators=(',', ':'))
            data = query_str.encode('utf-8')
            logger.info(f"[中文内容] 请求体: {query_str}")
            logger.info(f"[中文内容] 请求体 bytes: {data}")

            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            loop = asyncio.get_event_loop()

            def fetch():
                req = urllib.request.Request(
                    url,
                    data=data,
                    headers={
                        'Content-Type': 'application/json',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                        'Connection': 'close',
                    },
                    method='POST'
                )
                logger.info(f"[中文内容] 请求头: {dict(req.headers)}")
                try:
                    with urllib.request.urlopen(req, context=ssl_context, timeout=5) as response:
                        logger.info(f"[中文内容] 响应状态: {response.status}")
                        return response.read().decode('utf-8')
                except urllib.error.HTTPError as e:
                    logger.error(f"[中文内容] HTTP Error: {e.code} - {e.reason}")
                    try:
                        error_body = e.read().decode('utf-8')
                        logger.error(f"[中文内容] 错误响应体: {error_body[:500]}")
                    except:
                        pass
                    raise

            response_text = await loop.run_in_executor(None, fetch)
            logger.info(f"[中文内容] API 原始响应: {response_text[:500]}...")

            response_data = json.loads(response_text)
            logger.info(f"[中文内容] 解析后数据: {response_data}")

            question_data = response_data.get("data", {}).get("question", {})
            logger.info(f"[中文内容] question_data: {question_data}")

            translated_content = question_data.get("translatedContent", "")
            logger.info(f"[中文内容] translatedContent 长度: {len(translated_content) if translated_content else 0}")

            return translated_content
        except Exception as e:
            logger.warning(f"[中文内容] 获取失败: {e}")
            return ""

    async def _fetch_question_by_id(self, question_id: str) -> Optional[Dict]:
        """根据题目号获取 LeetCode 题目详情"""
        try:
            import urllib.request
            import ssl

            # 使用 lcid.cc API 获取题目信息
            url = f"https://lcid.cc/info/{question_id}"
            logger.info(f"正在获取题目 {question_id}: {url}")

            # 创建SSL上下文，忽略证书验证
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            # 使用线程池执行同步请求
            loop = asyncio.get_event_loop()

            def fetch():
                req = urllib.request.Request(
                    url,
                    headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                )
                with urllib.request.urlopen(req, context=ssl_context, timeout=30) as response:
                    return response.read().decode('utf-8')

            response_text = await loop.run_in_executor(None, fetch)
            logger.info(f"题目 {question_id} 响应: {response_text[:200]}")

            data = json.loads(response_text)

            # 获取标题（优先使用中文标题）
            title = data.get("title", "")
            title_cn = data.get("title_cn", "")
            slug = data.get("slug", "")
            if not title_cn:
                title_cn = title

            # 获取英文内容
            content_en = data.get("content", "")

            # 尝试获取中文内容
            content_cn = ""
            content_cn_failed = False
            if slug:
                try:
                    content_cn = await self._fetch_chinese_content(slug)
                except Exception as e:
                    logger.warning(f"获取中文内容失败: {e}")
                    content_cn_failed = True

            # 构建结果
            result = {
                "date": "",
                "title": title,
                "titleCn": title_cn,
                "titleSlug": slug,
                "frontendQuestionId": str(data.get("id", question_id)),
                "difficulty": data.get("difficulty", ""),
                "acRate": 0,
                "link": f"https://leetcode.com/problems/{slug}/",
                "topicTags": [],
                "content": content_en,
                "contentCn": content_cn,
                "contentCnFailed": content_cn_failed
            }

            logger.info(f"成功获取题目 {question_id}: {title_cn or title}")
            return result
        except Exception as e:
            logger.error(f"获取题目 {question_id} 失败: {e}", exc_info=True)

        return None

    def _build_question_message(self, question: Dict, language: str = "zh") -> str:
        """构建题目消息，支持多语言显示
        
        Args:
            question: 题目数据字典
            language: 语言选项 - "zh"(中文), "en"(英文), "both"(双语)
        """
        logger.info(f"[构建消息] 开始构建，language: {language}, question.keys: {list(question.keys())}")

        result_text = f"📅 {question.get('date', '')}\n"

        difficulty_emoji = {
            "Easy": "🟢",
            "Medium": "🟡",
            "Hard": "🔴"
        }

        difficulty_cn = {
            "Easy": "简单",
            "Medium": "中等",
            "Hard": "困难"
        }

        emoji = difficulty_emoji.get(question.get("difficulty", ""), "⚪")
        title_cn = question.get("titleCn") or question.get("title", "未知题目")
        title = question.get("title", "未知题目")
        qid = question.get("frontendQuestionId", "")
        difficulty = question.get("difficulty", "")
        difficulty_cn_text = difficulty_cn.get(difficulty, difficulty)
        ac_rate = question.get("acRate", 0)
        link = question.get("link", "")
        
        tags = []
        for tag in question.get("topicTags", []):
            if isinstance(tag, dict):
                tag_name = tag.get("nameTranslated") or tag.get("name", "")
                if tag_name:
                    tags.append(tag_name)
            else:
                tags.append(str(tag))

        # 根据语言设置构建标题
        if language == "zh":
            # 仅中文
            result_text += f"{emoji} 【{qid}. {title_cn}】\n"
        elif language == "en":
            # 仅英文
            result_text += f"{emoji} 【{qid}. {title}】\n"
        else:
            # 双语模式
            result_text += f"{emoji} 【{qid}. {title_cn}】\n"
            if title_cn != title:
                result_text += f"English: {title}\n"

        result_text += f"难度: {difficulty_cn_text}\n"
        if ac_rate:
            result_text += f"通过率: {ac_rate * 100:.1f}%\n"
        if tags:
            result_text += f"标签: {', '.join(tags)}\n"
        result_text += f"🔗 链接: {link}\n"

        # 添加完整题目内容
        content = question.get("content", "")
        content_cn = question.get("contentCn", "")  # 中文内容
        content_cn_failed = question.get("contentCnFailed", False)  # 中文内容获取是否失败

        logger.info(f"[构建消息] 内容处理 - content长度: {len(content) if content else 0}, contentCn长度: {len(content_cn) if content_cn else 0}, 失败: {content_cn_failed}, language: {language}")

        if content or content_cn:
            clean_content_en = clean_html(content) if content else ""
            clean_content_cn = clean_html(content_cn) if content_cn else ""
            
            # 根据语言设置显示内容
            if language == "zh":
                logger.info(f"[构建消息] 语言=zh，clean_content_cn长度: {len(clean_content_cn)}, clean_content_en长度: {len(clean_content_en)}")
                if clean_content_cn:
                    # 仅中文
                    logger.info("[构建消息] 使用中文内容")
                    result_text += f"\n📝 题目描述:\n"
                    display_content = clean_content_cn
                    # 分段发送，避免消息过长
                    max_length = 3000
                    if len(display_content) > max_length:
                        result_text += display_content[:max_length] + "\n\n... (内容已截断，请访问链接查看完整题目)"
                    else:
                        result_text += display_content
                elif clean_content_en:
                    # 中文内容获取失败，显示提示和英文内容
                    logger.info("[构建消息] 中文内容为空，使用英文内容")
                    if content_cn_failed:
                        result_text += f"\n⚠️ 中文内容获取失败，已切换为英文显示\n"
                    result_text += f"\n📝 Description:\n"
                    display_content = clean_content_en
                    max_length = 3000
                    if len(display_content) > max_length:
                        result_text += display_content[:max_length] + "\n\n... (内容已截断，请访问链接查看完整题目)"
                    else:
                        result_text += display_content
                    
            elif language == "en" and clean_content_en:
                # 仅英文
                result_text += f"\n📝 题目描述:\n"
                display_content = clean_content_en
                max_length = 3000
                if len(display_content) > max_length:
                    result_text += display_content[:max_length] + "\n\n... (内容已截断，请访问链接查看完整题目)"
                else:
                    result_text += display_content
                    
            elif language == "both":
                # 双语模式 - 同时显示中英文
                # 中文部分
                if clean_content_cn:
                    result_text += f"\n📝 题目描述 (中文):\n"
                    max_length = 1500
                    if len(clean_content_cn) > max_length:
                        result_text += clean_content_cn[:max_length] + "\n\n... (内容已截断)"
                    else:
                        result_text += clean_content_cn
                elif content_cn_failed:
                    # 中文内容获取失败提示
                    result_text += f"\n⚠️ 中文内容获取失败\n"
                
                # 英文部分
                if clean_content_en:
                    result_text += f"\n\n📝 Description (English):\n"
                    max_length = 1500
                    if len(clean_content_en) > max_length:
                        result_text += clean_content_en[:max_length] + "\n\n... (content truncated)"
                    else:
                        result_text += clean_content_en
            else:
                # 默认显示可用内容
                result_text += f"\n📝 题目描述:\n"
                display_content = clean_content_cn or clean_content_en
                max_length = 3000
                if len(display_content) > max_length:
                    result_text += display_content[:max_length] + "\n\n... (内容已截断，请访问链接查看完整题目)"
                else:
                    result_text += display_content

        return result_text

    async def _send_question_to_subscribers(self, question: Dict):
        """发送题目到所有群组订阅者"""
        text = self._build_question_message(question, self.default_language)

        for group_id in self.subscribed_groups:
            try:
                await self.context.send_message(
                    self._get_session_for_group(group_id),
                    text
                )
                logger.info(f"LeetCode 每日一题已发送到群 {group_id}")
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"发送题目到群 {group_id} 失败: {e}")

    async def _send_question_to_personal_subscribers(self, question: Dict):
        """发送题目到所有个人订阅者"""
        for user_id in self.subscribed_users:
            try:
                # 获取用户的语言偏好
                user_lang = self._get_user_language(user_id)
                text = self._build_question_message(question, user_lang)
                
                await self.context.send_message(
                    self._get_session_for_user(user_id),
                    text
                )
                logger.info(f"LeetCode 每日一题已发送到用户 {user_id}")
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"发送题目到用户 {user_id} 失败: {e}")

    async def _send_plain_text(self, group_id: str, text: str):
        """发送纯文本消息"""
        try:
            await self.context.send_message(self._get_session_for_group(group_id), text)
        except Exception as e:
            logger.error(f"发送消息到群 {group_id} 失败: {e}")

    # ========== 命令处理 ==========

    @filter.command("lc菜单")
    async def cmd_menu(self, event: AstrMessageEvent):
        """显示主菜单"""
        self._save_group_origin(event)

        # 判断当前是群聊还是私聊
        group_id = self._get_group_id(event)
        
        if group_id:
            # 群聊环境 - 需要管理员权限
            if not self._is_admin(event):
                yield event.plain_result("⚠️ 只有管理员可以使用此命令")
                return

            msg = """🤖 LeetCode 每日一题 - 主菜单

【查询命令】
📋 /lc今日 - 立即获取今日题目（含完整描述）
🔍 /lc题目 [题号] - 查询指定题目（如: /lc题目 1）
🤖 /lc解题 [题号] - 使用AI分析并解答题目（如: /lc解题 1）
📋 /lc列表 - 查看当前群订阅状态

【管理命令】
➕ /lc订阅 - 在当前群订阅每日一题
➖ /lc退订 - 在当前群取消订阅
📋 /lc全部订阅 - 查看所有群的订阅
📖 /lc帮助 - 查看详细帮助"""
        else:
            # 私聊环境 - 个人订阅功能
            msg = """🤖 LeetCode 每日一题 - 个人菜单

【查询命令】
📋 /lc今日 - 立即获取今日题目（含完整描述）
🔍 /lc题目 [题号] - 查询指定题目（如: /lc题目 1）
🤖 /lc解题 [题号] - 使用AI分析并解答题目（如: /lc解题 1）

【个人订阅】
➕ /lc订阅我 - 订阅每日一题私信推送
➖ /lc退订我 - 取消个人订阅
📋 /lc我的状态 - 查看个人订阅状态

【语言设置】
🌐 /lc语言 [zh/en/both] - 设置题目显示语言
   示例: /lc语言 zh (仅中文)
   示例: /lc语言 en (仅英文)
   示例: /lc语言 both (双语显示)

📖 /lc帮助 - 查看详细帮助"""

        yield event.plain_result(msg)

    @filter.command("lc帮助")
    async def cmd_help(self, event: AstrMessageEvent):
        """显示详细帮助"""
        group_id = self._get_group_id(event)

        # 群聊需要管理员权限，私聊无需权限
        if group_id and not self._is_admin(event):
            yield event.plain_result("⚠️ 只有管理员可以使用此命令")
            return

        # 保存会话标识
        if group_id:
            self._save_group_origin(event)
        else:
            self._save_user_origin(event)

        if group_id:
            # 群聊帮助
            msg = """📖 LeetCode 每日一题 - 群组使用说明

【查询命令】
1️⃣ /lc今日 - 立即获取并显示今日题目（含完整描述）
2️⃣ /lc题目 [题号] - 查询指定题号的题目
   示例: /lc题目 1 (查询两数之和)
   示例: /lc题目  (不传参数则获取今日题目)
3️⃣ /lc解题 [题号] - 使用AI分析题目并提供解题思路、代码和关键点
   示例: /lc解题 1 (AI解答两数之和)
   示例: /lc解题  (不传参数则解答今日题目)
4️⃣ /lc列表 - 查看当前群是否已订阅

【管理命令】
5️⃣ /lc订阅 - 在当前群订阅每日一题推送
6️⃣ /lc退订 - 在当前群取消每日一题推送
7️⃣ /lc全部订阅 - 查看所有群的订阅情况（超级管理员）

【AI解题说明】
/lc解题命令需要AstrBot已配置LLM提供商（如OpenAI、Claude等）
AI会提供：题目理解、解题思路、算法步骤、参考代码、关键点

【个人订阅】
私聊我还可以使用个人订阅功能:
• /lc订阅我 - 私信接收每日题目
• /lc语言 - 设置题目显示语言

【配置】
- 默认每日 09:00 推送
- 可在插件配置中修改推送时间

【提示】
- 只有管理员可以使用管理命令
- 每日一题数据来自 LeetCode 中文站"""
        else:
            # 私聊帮助
            msg = """📖 LeetCode 每日一题 - 个人使用说明

【查询命令】
1️⃣ /lc今日 - 立即获取并显示今日题目
2️⃣ /lc题目 [题号] - 查询指定题号的题目
   示例: /lc题目 1 (查询两数之和)
3️⃣ /lc解题 [题号] - 使用AI分析题目并提供解题思路
   示例: /lc解题 1 (AI解答两数之和)

【个人订阅命令】
4️⃣ /lc订阅我 - 订阅每日一题私信推送
   每天会自动收到题目推送
5️⃣ /lc退订我 - 取消个人订阅
6️⃣ /lc我的状态 - 查看订阅状态和语言设置

【语言设置】
7️⃣ /lc语言 [zh/en/both] - 设置题目显示语言
   • zh   - 仅中文
   • en   - 仅英文
   • both - 双语显示
   示例: /lc语言 zh

【AI解题说明】
/lc解题命令需要AstrBot已配置LLM提供商
AI会提供：题目理解、解题思路、算法步骤、参考代码、关键点

【提示】
- 个人订阅推送时间可在插件配置中修改
- 语言偏好仅影响个人收到的题目显示
- 每日一题数据来自 LeetCode 中文站"""

        yield event.plain_result(msg)

    @filter.command("lc订阅")
    async def cmd_subscribe(self, event: AstrMessageEvent):
        """订阅每日一题"""
        self._save_group_origin(event)
        if not self._is_admin(event):
            yield event.plain_result("⚠️ 只有管理员可以使用此命令")
            return

        group_id = self._get_group_id(event)
        if not group_id:
            yield event.plain_result("❌ 此命令只能在群聊中使用")
            return

        if group_id in self.subscribed_groups:
            yield event.plain_result("❌ 本群已经订阅了 LeetCode 每日一题")
            return

        self.subscribed_groups.append(group_id)
        await self._save_subscription()

        yield event.plain_result(f"✅ 本群已成功订阅 LeetCode 每日一题\n每日 {self.inform_hour:02d}:{self.inform_minute:02d} 推送")

    @filter.command("lc退订")
    async def cmd_unsubscribe(self, event: AstrMessageEvent):
        """取消订阅"""
        self._save_group_origin(event)
        if not self._is_admin(event):
            yield event.plain_result("⚠️ 只有管理员可以使用此命令")
            return

        group_id = self._get_group_id(event)
        if not group_id:
            yield event.plain_result("❌ 此命令只能在群聊中使用")
            return

        if group_id not in self.subscribed_groups:
            yield event.plain_result("❌ 本群没有订阅 LeetCode 每日一题")
            return

        self.subscribed_groups.remove(group_id)
        await self._save_subscription()

        yield event.plain_result("✅ 本群已取消订阅 LeetCode 每日一题")

    @filter.command("lc今日")
    async def cmd_today(self, event: AstrMessageEvent):
        """获取今日题目"""
        group_id = self._get_group_id(event)
        user_id = self._get_user_id(event)

        # 群聊需要管理员权限，私聊无需权限
        if group_id and not self._is_admin(event):
            yield event.plain_result("⚠️ 只有管理员可以使用此命令")
            return

        # 保存会话标识
        if group_id:
            self._save_group_origin(event)
        else:
            self._save_user_origin(event)

        today_date = datetime.now().strftime("%Y-%m-%d")

        # 检查缓存
        if self.today_question and self.today_date == today_date:
            question = self.today_question
        else:
            yield event.plain_result("⏳ 正在获取今日题目...")
            question = await self._fetch_daily_question()
            if question:
                self.today_question = question
                self.today_date = today_date

        if not question:
            yield event.plain_result("❌ 获取今日题目失败，请稍后再试")
            return

        # 根据用户或群组设置选择语言
        if group_id:
            language = self.default_language
        else:
            language = self._get_user_language(user_id)

        text = self._build_question_message(question, language)
        yield event.plain_result(text)

    @filter.command("lc列表")
    async def cmd_list(self, event: AstrMessageEvent):
        """查看当前群订阅状态"""
        self._save_group_origin(event)
        if not self._is_admin(event):
            yield event.plain_result("⚠️ 只有管理员可以使用此命令")
            return

        group_id = self._get_group_id(event)
        if not group_id:
            yield event.plain_result("❌ 此命令只能在群聊中使用")
            return

        if group_id in self.subscribed_groups:
            yield event.plain_result(f"✅ 本群已订阅 LeetCode 每日一题\n每日 {self.inform_hour:02d}:{self.inform_minute:02d} 推送")
        else:
            yield event.plain_result("❌ 本群未订阅 LeetCode 每日一题")

    @filter.command("lc全部订阅")
    async def cmd_all_subscriptions(self, event: AstrMessageEvent):
        """查看所有群的订阅"""
        self._save_group_origin(event)
        if not self._is_admin(event):
            yield event.plain_result("⚠️ 只有管理员可以使用此命令")
            return

        if not self.subscribed_groups:
            yield event.plain_result("📋 暂无群订阅 LeetCode 每日一题")
            return

        lines = ["📋 已订阅 LeetCode 每日一题的群:"]
        lines.append("=" * 30)
        for i, group_id in enumerate(self.subscribed_groups, 1):
            lines.append(f"{i}. {group_id}")

        yield event.plain_result("\n".join(lines))

    # ========== 多语言配置命令 ==========

    @filter.command("lc语言")
    async def cmd_set_language(self, event: AstrMessageEvent, language: str = ""):
        """设置题目显示语言: /lc语言 [zh/en/both]"""
        self._save_user_origin(event)
        user_id = self._get_user_id(event)

        if not language:
            # 显示当前语言设置
            current_lang = self._get_user_language(user_id)
            lang_desc = {"zh": "中文", "en": "英文", "both": "双语"}
            yield event.plain_result(
                f"🌐 您当前的语言设置: {lang_desc.get(current_lang, current_lang)} ({current_lang})\n\n"
                f"可用选项:\n"
                f"• zh - 仅中文\n"
                f"• en - 仅英文\n"
                f"• both - 双语显示\n\n"
                f"用法: /lc语言 [zh/en/both]"
            )
            return

        language = language.lower().strip()
        if language not in ["zh", "en", "both"]:
            yield event.plain_result(
                "❌ 无效的语言选项\n\n"
                "可用选项:\n"
                "• zh - 仅中文\n"
                "• en - 仅英文\n"
                "• both - 双语显示"
            )
            return

        # 保存用户语言偏好
        self.user_language_prefs[user_id] = language
        await self._save_personal_subscription()

        lang_desc = {"zh": "中文", "en": "英文", "both": "双语"}
        yield event.plain_result(
            f"✅ 语言设置已更新为: {lang_desc.get(language, language)}\n"
            f"后续收到的题目将以所选语言显示。"
        )

    # ========== 个人订阅管理命令 ==========

    @filter.command("lc订阅我")
    async def cmd_subscribe_me(self, event: AstrMessageEvent):
        """个人订阅每日一题"""
        if not self.enable_personal_subscribe:
            yield event.plain_result("❌ 个人订阅功能已禁用")
            return

        self._save_user_origin(event)
        user_id = self._get_user_id(event)

        # 检查是否在群聊中使用
        if self._get_group_id(event):
            yield event.plain_result("❌ 此命令只能在私聊中使用\n请直接私信我发送 /lc订阅我")
            return

        if user_id in self.subscribed_users:
            yield event.plain_result(
                "❌ 您已经订阅了 LeetCode 每日一题\n\n"
                f"每日 {self.personal_inform_hour:02d}:{self.personal_inform_minute:02d} 会推送题目到您的私信"
            )
            return

        self.subscribed_users.append(user_id)
        await self._save_personal_subscription()

        yield event.plain_result(
            f"✅ 订阅成功！\n\n"
            f"您已成功订阅 LeetCode 每日一题\n"
            f"每日 {self.personal_inform_hour:02d}:{self.personal_inform_minute:02d} 会推送题目到您的私信\n\n"
            f"其他命令:\n"
            f"• /lc语言 - 设置题目显示语言\n"
            f"• /lc退订我 - 取消订阅\n"
            f"• /lc今日 - 立即获取今日题目"
        )

    @filter.command("lc退订我")
    async def cmd_unsubscribe_me(self, event: AstrMessageEvent):
        """取消个人订阅"""
        self._save_user_origin(event)
        user_id = self._get_user_id(event)

        # 检查是否在群聊中使用
        if self._get_group_id(event):
            yield event.plain_result("❌ 此命令只能在私聊中使用\n请直接私信我发送 /lc退订我")
            return

        if user_id not in self.subscribed_users:
            yield event.plain_result("❌ 您没有订阅 LeetCode 每日一题")
            return

        self.subscribed_users.remove(user_id)
        await self._save_personal_subscription()

        yield event.plain_result("✅ 已取消订阅 LeetCode 每日一题\n期待您再次使用！")

    @filter.command("lc我的状态")
    async def cmd_my_status(self, event: AstrMessageEvent):
        """查看个人订阅状态"""
        self._save_user_origin(event)
        user_id = self._get_user_id(event)

        # 检查是否在群聊中使用
        if self._get_group_id(event):
            yield event.plain_result("❌ 此命令只能在私聊中使用\n请直接私信我发送 /lc我的状态")
            return

        # 获取用户语言偏好
        current_lang = self._get_user_language(user_id)
        lang_desc = {"zh": "中文", "en": "英文", "both": "双语"}

        lines = ["📊 您的个人订阅状态"]
        lines.append("=" * 30)

        # 订阅状态
        if user_id in self.subscribed_users:
            lines.append("✅ 订阅状态: 已订阅")
            lines.append(f"📅 推送时间: 每日 {self.personal_inform_hour:02d}:{self.personal_inform_minute:02d}")
        else:
            lines.append("❌ 订阅状态: 未订阅")
            lines.append("💡 使用 /lc订阅我 可以订阅每日推送")

        lines.append(f"🌐 语言偏好: {lang_desc.get(current_lang, current_lang)}")
        lines.append("")
        lines.append("可用命令:")
        lines.append("• /lc订阅我 - 订阅推送")
        lines.append("• /lc退订我 - 取消订阅")
        lines.append("• /lc语言 [zh/en/both] - 设置语言")
        lines.append("• /lc今日 - 获取今日题目")

        yield event.plain_result("\n".join(lines))

    @filter.command("lc全部个人订阅")
    async def cmd_all_personal_subscriptions(self, event: AstrMessageEvent):
        """查看所有个人订阅（管理员命令）"""
        if not self._is_admin(event):
            yield event.plain_result("⚠️ 只有管理员可以使用此命令")
            return

        if not self.subscribed_users:
            yield event.plain_result("📋 暂无个人订阅 LeetCode 每日一题")
            return

        lines = ["📋 已订阅 LeetCode 每日一题的用户:"]
        lines.append("=" * 30)
        for i, user_id in enumerate(self.subscribed_users, 1):
            lang = self._get_user_language(user_id)
            lines.append(f"{i}. {user_id} (语言: {lang})")

        lines.append("")
        lines.append(f"总计: {len(self.subscribed_users)} 人")

        yield event.plain_result("\n".join(lines))

    @filter.command("lc题目")
    async def cmd_question(self, event: AstrMessageEvent, question_id: str = ""):
        """根据题目号查询题目，不传参数则获取今日题目"""
        group_id = self._get_group_id(event)
        user_id = self._get_user_id(event)

        # 群聊需要管理员权限，私聊无需权限
        if group_id and not self._is_admin(event):
            yield event.plain_result("⚠️ 只有管理员可以使用此命令")
            return

        # 保存会话标识
        if group_id:
            self._save_group_origin(event)
        else:
            self._save_user_origin(event)

        # 获取语言设置
        language = self.default_language if group_id else self._get_user_language(user_id)

        if not question_id:
            # 没有提供题目号，获取今日题目
            today_date = datetime.now().strftime("%Y-%m-%d")

            # 检查缓存
            if self.today_question and self.today_date == today_date:
                question = self.today_question
            else:
                yield event.plain_result("⏳ 正在获取今日题目...")
                question = await self._fetch_daily_question()
                if question:
                    self.today_question = question
                    self.today_date = today_date

            if not question:
                yield event.plain_result("❌ 获取今日题目失败，请稍后再试")
                return

            text = self._build_question_message(question, language)
            yield event.plain_result(text)
        else:
            # 提供了题目号，查询指定题目
            yield event.plain_result(f"⏳ 正在查询题目 {question_id}...")

            question = await self._fetch_question_by_id(question_id)

            if not question:
                yield event.plain_result(f"❌ 未找到题目 {question_id}，请检查题号是否正确")
                return

            text = self._build_question_message(question, language)
            yield event.plain_result(text)

    @filter.command("lc解题")
    async def cmd_solve(self, event: AstrMessageEvent, question_id: str = ""):
        """使用AI分析并解答题目，不传参数则解答今日题目"""
        group_id = self._get_group_id(event)
        user_id = self._get_user_id(event)

        # 群聊需要管理员权限，私聊无需权限
        if group_id and not self._is_admin(event):
            yield event.plain_result("⚠️ 只有管理员可以使用此命令")
            return

        # 保存会话标识
        if group_id:
            self._save_group_origin(event)
        else:
            self._save_user_origin(event)

        # 获取语言设置
        language = self.default_language if group_id else self._get_user_language(user_id)

        if not question_id:
            # 没有提供题目号，获取今日题目
            today_date = datetime.now().strftime("%Y-%m-%d")

            # 检查缓存
            if self.today_question and self.today_date == today_date:
                question = self.today_question
            else:
                yield event.plain_result("⏳ 正在获取今日题目...")
                question = await self._fetch_daily_question()
                if question:
                    self.today_question = question
                    self.today_date = today_date

            if not question:
                yield event.plain_result("❌ 获取今日题目失败，请稍后再试")
                return
        else:
            # 提供了题目号，查询指定题目
            yield event.plain_result(f"⏳ 正在查询题目 {question_id}...")

            question = await self._fetch_question_by_id(question_id)

            if not question:
                yield event.plain_result(f"❌ 未找到题目 {question_id}，请检查题号是否正确")
                return

        content = question.get("content", "")
        if not content:
            yield event.plain_result("❌ 暂无题目内容")
            return

        title_cn = question.get("titleCn") or question.get("title", "未知题目")
        qid = question.get("frontendQuestionId", "")
        difficulty = question.get("difficulty", "")
        tags = []
        for tag in question.get("topicTags", []):
            if isinstance(tag, dict):
                tag_name = tag.get("nameTranslated") or tag.get("name", "")
                if tag_name:
                    tags.append(tag_name)

        clean_content = clean_html(content)

        yield event.plain_result("🤖 正在使用AI分析题目，请稍候...")

        try:
            # 根据语言设置调整回答语言
            lang_instruction = {
                "zh": "请用中文回答。",
                "en": "Please answer in English.",
                "both": "请用中文回答，并在关键术语后附上英文对照。"
            }.get(language, "请用中文回答。")

            # 构建提示词
            prompt = f"""请作为算法专家，分析并解答以下LeetCode题目：

题目编号: {qid}
题目名称: {title_cn}
难度: {difficulty}
标签: {', '.join(tags)}

题目描述:
{clean_content[:6000]}

请提供：
1. 题目理解：简要说明题目要求
2. 解题思路：分析解题方法，包括时间复杂度和空间复杂度
3. 算法步骤：详细说明解题步骤
4. 参考代码：提供Python实现（包含注释）
5. 关键点：总结解题的关键要点

{lang_instruction}"""

            # 调用LLM
            umo = event.unified_msg_origin
            provider_id = await self.context.get_current_chat_provider_id(umo=umo)

            llm_resp = await self.context.llm_generate(
                chat_provider_id=provider_id,
                prompt=prompt,
            )

            answer = llm_resp.completion_text

            msg = f"🤖 【{qid}. {title_cn}】AI解题分析\n"
            msg += "=" * 40 + "\n\n"
            msg += answer

            yield event.plain_result(msg)

        except Exception as e:
            logger.error(f"AI解题失败: {e}", exc_info=True)
            yield event.plain_result(f"❌ AI解题失败: {e}\n请检查是否已配置LLM提供商")
