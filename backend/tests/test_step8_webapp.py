"""M6：後端提供電腦版網頁（/app）"""

import app.main as main


def test_webapp_serving(client, tmp_path, monkeypatch):
    monkeypatch.setattr(main, "WEBAPP_DIR", tmp_path / "missing")
    assert client.get("/", follow_redirects=False).headers["location"] == "/docs"
    assert client.get("/app/").status_code == 404

    (tmp_path / "web" / "_expo").mkdir(parents=True)
    (tmp_path / "web" / "index.html").write_text("<html>APP</html>")
    (tmp_path / "web" / "_expo" / "app.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("secret")
    monkeypatch.setattr(main, "WEBAPP_DIR", tmp_path / "web")

    assert client.get("/", follow_redirects=False).headers["location"] == "/app/"
    assert client.get("/app/_expo/app.js").text == "console.log(1)"
    assert client.get("/app/inspections").text == "<html>APP</html>"  # APP 內頁面回 index.html
    assert "secret" not in client.get("/app/../secret.txt").text  # 不能讀到 webapp 以外的檔案
    assert "secret" not in client.get("/app/%2e%2e/secret.txt").text
