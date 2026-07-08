from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_portal_html_uses_dist_bundle_only():
    content = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    assert '<script type="module" src="/static/dist/portal-main.js"></script>' in content
    assert '/static/src/portal-main.js' not in content


def test_workspace_html_uses_dist_bundle_only():
    for name in ("admin.html", "user.html"):
        content = (ROOT / "static" / name).read_text(encoding="utf-8")
        assert '<script type="module" src="/static/dist/workspace-main.js"></script>' in content
        assert '/static/src/workspace-main.js' not in content


def test_production_build_disables_sourcemaps():
    content = (ROOT / "package.json").read_text(encoding="utf-8")
    assert '"build": "esbuild static/src/portal-main.js static/src/workspace-main.js --bundle --outdir=static/dist --minify --format=esm --target=es2020 --entry-names=[name]"' in content


def test_watch_build_keeps_sourcemaps():
    content = (ROOT / "package.json").read_text(encoding="utf-8")
    assert '"build:watch": "esbuild static/src/portal-main.js static/src/workspace-main.js --bundle --outdir=static/dist --sourcemap --format=esm --target=es2020 --entry-names=[name] --watch"' in content


def test_runtime_dockerfile_copies_only_runtime_static_assets():
    content = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert 'COPY static/*.html static/' in content
    assert 'COPY static/style.css static/' in content
    assert 'COPY static/ static/' not in content


def test_chat_view_does_not_offer_local_only_conversation_actions():
    content = (ROOT / "static" / "src" / "views" / "chat.js").read_text(encoding="utf-8")
    assert 'data-action="rename-conversation"' not in content
    assert 'data-action="remove-conversation"' not in content


def test_workspace_html_exposes_load_more_conversations_control():
    for name in ("admin.html", "user.html"):
        content = (ROOT / "static" / name).read_text(encoding="utf-8")
        assert 'id="loadMoreConversationsBtn"' in content
