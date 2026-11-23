"""注册唯一性预检接口测试。

对应注册 PRD §4 #1/#2 的「失焦异步校验」，接口文档 2.4。
"""

import pytest

from helpers import create_user


def _check(client, field, value):
    return client.get(f"/api/auth/check?field={field}&value={value}")


def test_username_available(client, db):
    body = _check(client, "username", "newuser").json()

    assert body["code"] == 0
    assert body["data"]["exists"] is False
    assert body["data"]["message"] == ""


def test_username_taken(client, db):
    create_user(db, username="tester01")

    body = _check(client, "username", "tester01").json()

    assert body["code"] == 0
    assert body["data"]["exists"] is True
    assert body["data"]["message"] == "用户名已存在"


def test_username_check_case_insensitive(client, db):
    create_user(db, username="tester01")

    assert _check(client, "username", "TESTER01").json()["data"]["exists"] is True


@pytest.mark.parametrize("reserved", ["admin", "ADMIN", "root", "administrator"])
def test_username_reserved(client, db, reserved):
    body = _check(client, "username", reserved).json()

    assert body["code"] == 0
    assert body["data"]["exists"] is True
    assert body["data"]["message"] == "该用户名为系统保留，请更换"


@pytest.mark.parametrize("value", ["ab", "a" * 21, "bad-name", "中文名"])
def test_username_invalid_format(client, db, value):
    body = _check(client, "username", value).json()

    assert body["code"] == 400
    assert body["message"] == "用户名需为 3-20 位字母、数字或下划线"


def test_email_available(client, db):
    body = _check(client, "email", "new@example.com").json()

    assert body["code"] == 0
    assert body["data"]["exists"] is False


def test_email_taken(client, db):
    create_user(db, email="tester01@example.com")

    body = _check(client, "email", "tester01@example.com").json()

    assert body["code"] == 0
    assert body["data"]["exists"] is True
    assert body["data"]["message"] == "邮箱已被注册"


def test_email_check_case_insensitive(client, db):
    create_user(db, email="tester01@example.com")

    assert _check(client, "email", "TESTER01@EXAMPLE.COM").json()["data"]["exists"] is True


def test_email_invalid_format(client, db):
    body = _check(client, "email", "bad-email").json()

    assert body["code"] == 400
    assert body["message"] == "请输入正确的邮箱格式"


def test_invalid_field(client, db):
    body = _check(client, "nickname", "x").json()

    assert body["code"] == 400
    assert body["message"] == "参数错误"


def test_empty_value(client, db):
    body = _check(client, "username", "").json()

    assert body["code"] == 400
    assert body["message"] == "请输入内容"


def test_check_is_public(client, db):
    """未登录也应可调用（注册页尚未登录）。"""
    resp = client.get("/api/auth/check?field=username&value=someone")

    assert resp.status_code == 200
    assert resp.json()["code"] == 0
