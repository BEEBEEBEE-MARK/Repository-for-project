"""健康检查与全局路由行为测试。"""


def test_health(client):
    resp = client.get("/api/health")

    assert resp.status_code == 200
    assert resp.json() == {"code": 0, "message": "ok", "data": {"status": "healthy"}}


def test_unknown_api_path_returns_json(client):
    """未定义的 /api 路径应返回统一 JSON，而不是被前端静态文件挂载吞掉。"""
    resp = client.get("/api/not-exists")

    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json()["code"] == 404


def test_method_not_allowed_returns_json(client):
    """已存在的路径用错方法，也应返回统一 JSON。"""
    resp = client.put("/api/health")

    assert resp.status_code == 405
    assert resp.headers["content-type"].startswith("application/json")
