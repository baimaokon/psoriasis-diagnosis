def success(data=None, message="操作成功"):
    return {"code": 0, "message": message, "data": data}


def error(message="操作失败", code=1):
    return {"code": code, "message": message, "data": None}

