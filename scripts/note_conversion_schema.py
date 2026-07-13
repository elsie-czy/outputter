CONVERSION_REVIEW_SCHEMA = {
    "comment_score": "0-20",
    "follow_score": "0-20",
    "first_comment_score": "0-15",
    "reply_score": "0-15",
    "total": "0-70",
    "grade": "good|review|retry",
    "comment_hook": "string",
    "comment_hook_type": "报书名|求同款|雷点投票|二选一|求投喂|无",
    "follow_reason": "string",
    "first_comment": "string",
    "reply_prompts": ["string"],
    "suggestions": [
        {
            "dimension": "评论钩子|关注理由|首评|回复话术",
            "problem": "发现的问题",
            "action": "具体修改动作",
            "reason": "判断依据",
        }
    ],
}


CONVERSION_DIMENSIONS = {
    "comment_score": 20,
    "follow_score": 20,
    "first_comment_score": 15,
    "reply_score": 15,
}
