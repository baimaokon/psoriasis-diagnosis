"""
response.py — 统一 API 响应格式
────────────────────────────────
所有路由端点均通过 success()/error() 返回一致 JSON：
  success → {"code": 0, "message": "操作成功", "data": {...}}
  error   → {"code": 1, "message": "错误信息", "data": null}
前端 request.js 拦截器依赖 code 字段做统一错误处理。
"""
def success(data=None, message="操作成功"):
    return {"code": 0, "message": message, "data": data}


def error(message="操作失败", code=1):
    return {"code": code, "message": message, "data": None}

