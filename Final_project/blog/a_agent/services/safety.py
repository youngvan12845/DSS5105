"""Safety and content moderation guardrails for CheeseO reading assistant.

Guards against:
- Pornography & NSFW content (色情)
- Insults, abuse, and harassment (漫骂/侮辱)
- Sensitive political unrest & regime overthrow (政治敏感)
- Racial discrimination and hate speech (种族歧视/仇恨)
"""

from __future__ import annotations

import re

# Technical computer science and programming phrases that should never be falsely blocked
SAFE_TECH_PHRASES = (
    'race condition',
    'data race',
    'blacklist',
    'whitelist',
    'black list',
    'white list',
    'master branch',
    'master node',
    'master replica',
    'master-worker',
    'master-slave',
    'penetration testing',
    'kill process',
    'kill -9',
    'kill task',
    'daemon process',
    'zombie process',
    'abort signal',
    '竞态条件',
    '黑名单',
    '白名单',
    '渗透测试',
    '终止进程',
    '杀死进程',
    '僵尸进程',
    '主从复制',
    '主从架构',
)

SAFETY_PATTERNS: dict[str, list[str]] = {
    'pornography': [
        r'\b(porn|pornography|nsfw|erotic|hentai|child porn|xxx video|sex video|blowjob|handjob)\b',
        r'(色情|黄色小说|黄色网站|成人影片|成人视频|做爱|性交|自慰|裸聊|约炮|援交|三级片|A片|AV女优|强奸|淫秽|幼女色情|换妻)',
    ],
    'abuse': [
        r'\b(fuck you|fucking idiot|bitch|asshole|motherfucker|kill yourself|bastard|shithead|piece of shit)\b',
        r'(操你妈|草你妈|傻逼|煞笔|弱智|脑残|婊子|去死吧|狗东西|贱人|王八蛋|垃圾狗|死全家|狗娘养|死逼|CNM|MLGB)',
    ],
    'politics': [
        r'\b(overthrow the government|assassinate the president|political coup|color revolution|anti-government uprising|subvert state power)\b',
        r'(推翻政权|反党|反政府|颠覆国家|颜色革命|政治暴动|政变|刺杀总统|刺杀国家领导人|暴乱策划|分裂国家|台独|疆独|藏独|武统策划)',
    ],
    'racism': [
        r'\b(nigger|nigga|white supremacy|kill all jews|kill all blacks|chink|ethnic cleansing|racial inferiority|neo-nazi)\b',
        r'(种族歧视|劣等民族|劣等种族|黑鬼|白皮猪|种族灭绝|杀光黑人|杀光犹太人|支那猪|排华暴动|种族优越论)',
    ],
}


def check_safety_guardrails(query: str, *, is_chinese: bool = False) -> tuple[bool, str, str]:
    """Check if a query violates safety guidelines.

    Returns:
        (is_violation, category, refusal_message)
    """
    q = (query or '').strip()
    if not q:
        return False, '', ''

    q_lower = q.lower()

    for category, patterns in SAFETY_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, q, re.I):
                # Guard against false positives in tech context
                if category == 'racism' and any(st in q_lower for st in ('race condition', 'data race', '竞态条件')):
                    continue
                if category == 'abuse' and any(st in q_lower for st in ('kill process', 'kill -9', 'kill task', '杀死进程', '终止进程')):
                    continue

                if is_chinese:
                    msg = (
                        '抱歉，该提问涉及不当或敏感内容（色情、辱骂、政治或种族等违规主题）。'
                        '作为技术与学习导航助手，我们不对此类问题进行回复。请提出与技术、编程或博客阅读相关的问题。'
                    )
                else:
                    msg = (
                        'I am sorry, but this request involves inappropriate or sensitive content '
                        '(such as pornography, harassment/abuse, politics, or racial discrimination). '
                        'As a technical learning and reading assistant, I do not respond to such topics. '
                        'Please feel free to ask questions about technology, programming, or our blog lessons.'
                    )
                return True, category, msg

    return False, '', ''
