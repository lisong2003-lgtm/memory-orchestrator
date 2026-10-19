#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""memory-orchestrator 自检：结构、铁律、config、ctxcompress、cp-memory 初始化与写读回清理、state、recovery index、export_ctx。"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:
    pass


def _load_toml(path):
    if sys.version_info >= (3, 11):
        with open(path, "rb") as f:
            return tomllib.load(f)
    # Python 3.9 降级：只解析本项目自检需要的顶层标量
    import re
    with open(path, encoding="utf-8") as f:
        txt = f.read()
    out = {"mcp_servers": {}}
    m = re.search(r"(?m)^model_context_window\s*=\s*(\d+)\s*$", txt)
    if m:
        out["model_context_window"] = int(m.group(1))
    m = re.search(r"(?m)^model_auto_compact_token_limit\s*=\s*(\d+)\s*$", txt)
    if m:
        out["model_auto_compact_token_limit"] = int(m.group(1))
    m = re.search(r"(?ms)\[mcp_servers\.cp-memory\](.*?)(?=^\[|\Z)", txt)
    if m:
        body = m.group(1)
        for line in body.splitlines():
            line=line.strip()
            if line.startswith("command") and "=" in line:
                val=line.split("=",1)[1].strip().strip('"').strip("'")
                if val:
                    out["mcp_servers"]["cp-memory"] = {"command": val}
                break
    return out

SKILL_DIR = Path(__file__).resolve().parents[1]
SKILL = SKILL_DIR / "SKILL.md"
TPL = SKILL_DIR / "references" / "templates.md"
SCRIPTS = SKILL_DIR / "scripts"
HOT = Path.home() / ".codex/memory/hot.md"
AGENTS = Path.home() / ".codex/AGENTS.md"
CONFIG = Path.home() / ".codex/config.toml"
CTX = Path.home() / ".codex/tools/agent-ctx-compress/bin/ctxcompress"
CPM = Path.home() / ".codex/tools/cp-memory/bin/cp-memory-mcp"
PY = sys.executable

failures = []
checks_done = 0

def check(name, fn):
    global checks_done
    try:
        fn()
        checks_done += 1
        print(f"PASS  {name}")
    except Exception as e:
        failures.append(name)
        print(f"FAIL  {name}: {e}")

def p_skill_structure():
    txt = SKILL.read_text(encoding="utf-8")
    assert re.match(r"^---\nname:\s*memory-orchestrator\n(?:slug|displayName|description|version):", txt), "frontmatter 不完整"
    assert re.search(r"(?m)^description:\s*[^\n]*对话", txt), "frontmatter 缺 description 且与技能用途不符"
    for sec in ["## 会话状态", "## cp-memory 工具调用清单", "## Checkpoint", "## 压缩", "## 恢复包", "## 归档", "## 记忆规则", "## 禁忌"]:
        assert sec in txt, f"缺少 {sec}"

def p_template():
    t = TPL.read_text(encoding="utf-8")
    for k in ["recovery-package.md", "ctxcompress", "hot.md", "export_ctx.py"]:
        assert k in t, f"templates 缺少 {k}"

def p_hot():
    assert HOT.exists()
    assert "下一步" in HOT.read_text(encoding="utf-8")

def p_agents():
    a = AGENTS.read_text(encoding="utf-8")
    for k in ["上下文健康铁律", "12 轮", "memory-orchestrator", "cp-memory", "160000", "hot.md", "agent-ctx-compress/bin/ctxcompress"]:
        assert k in a, f"AGENTS 缺少 {k}"

def p_config():
    c = _load_toml(CONFIG)
    assert c.get("model_context_window") == 200000, c.get("model_context_window")
    assert c.get("model_auto_compact_token_limit") == 160000, c.get("model_auto_compact_token_limit")
    srv = c.get("mcp_servers", {}).get("cp-memory")
    assert srv and str(CPM) in srv.get("command", ""), srv

def p_protect_align():
    script = Path.home() / ".codex/scripts/protect-codex-config.py"
    t = script.read_text(encoding="utf-8")
    assert "ark-code-latest" in t and "200000" in t

def p_ctxcompress():
    r = subprocess.run([str(CTX), "--version"], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "0.1.0" in (r.stdout + r.stderr)

def p_monitor_dialogs():
    r = subprocess.run([PY, str(SCRIPTS / "monitor_dialogs.py"), "--days", "14", "--json"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-800:]
    data = json.loads(r.stdout)
    assert "scanned" in data and "over_sessions" in data and "warn_sessions" in data


def _fake_rollout(dirpath, uid, n):
    path = Path(dirpath) / f"rollout-2026-10-19T000000_{uid}.jsonl"
    lines = [json.dumps({"type": "session_meta", "payload": {"session_id": uid}})]
    for i in range(n):
        lines.append(json.dumps({"payload": {"type": "item_completed",
                                              "turn_id": f"{uid}-{i}",
                                              "item": {"type": "UserMessage"}}}))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def p_monitor_all_conflict():
    r = subprocess.run([PY, str(SCRIPTS / "monitor_dialogs.py"), "--all", "--days", "1"],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode != 0, "monitor_dialogs.py --all 与 --days 应互斥"


def p_monitor_all_dedup():
    with tempfile.TemporaryDirectory() as d:
        sessions = Path(d) / "sessions"
        sessions.mkdir()
        _fake_rollout(sessions, "00000000-0000-0000-0000-000000000001", 9)  # over
        _fake_rollout(sessions, "00000000-0000-0000-0000-000000000002", 6)  # warn? 6<7, none
        tmp_state = Path(d) / "state.json"
        env = dict(os.environ, CODEX_MEMORY_STATE=str(tmp_state))
        r1 = subprocess.run([PY, str(SCRIPTS / "monitor_dialogs.py"), "--all",
                             "--sessions-dir", str(sessions), "--write-state", "--json"],
                            capture_output=True, text=True, env=env, timeout=60)
        assert r1.returncode == 0, r1.stderr[-800:]
        d1 = json.loads(r1.stdout)
        assert d1["full_scan"] is True, d1
        assert len(d1["over_sessions"]) >= 1 and d1["new_reminders"] >= 1, d1
        r2 = subprocess.run([PY, str(SCRIPTS / "monitor_dialogs.py"), "--all",
                             "--sessions-dir", str(sessions), "--write-state", "--json"],
                            capture_output=True, text=True, env=env, timeout=60)
        assert r2.returncode == 0, r2.stderr[-800:]
        d2 = json.loads(r2.stdout)
        assert d2["new_reminders"] == 0, d2  # 已 over_warned 去重，不得重复刷屏
        st = json.loads(tmp_state.read_text(encoding="utf-8"))
        assert st["index"]["last_full_scan"], st["index"]
        assert len(st["index"]["over_warned_ids"]) >= 1, st["index"]


def p_state_r2_registry():
    fd, td = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        env = dict(os.environ, CODEX_MEMORY_STATE=td)
        for _ in range(7):
            _run_state(env, "bump", "active_project=pp", "thread_id=ta", "agent=claude")
        for _ in range(7):
            _run_state(env, "bump", "active_project=pp", "thread_id=tb")
        r = _run_state(env, "cross-check", "agent=claude", "--json")
        data = json.loads(r.stdout)
        assert any(o["agent"] == "codex" and o["status"] == "warn" for o in data["others"]), data
        # claude 未 touch 存活标记 → 建议在 codex 侧提示安装（先手动把 alive 置假造场景）
        _run_state(env, "touch", "agent=codex")
        full = json.loads(_run_state(env, "get").stdout)
        full["agents"]["claude"] = {"agent_alive": False}
        Path(td).write_text(json.dumps(full, ensure_ascii=False), encoding="utf-8")
        data2 = json.loads(_run_state(env, "cross-check", "agent=codex", "--json").stdout)
        assert any(s["agent"] == "claude" and s["suggest_install"] for s in data2["suggest_install"]), data2
        get = json.loads(_run_state(env, "get").stdout)
        assert any("@claude" in k for k in (get.get("dialogs") or {})), "非 codex Agent 应有 @ 命名空间键"
    finally:
        try:
            os.unlink(td)
        except Exception:
            pass


def p_handoff_gateway():
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, CODEX_MEMORY_STATE=str(Path(d) / "state.json"))
        # 手动 Agent：manual 能力 + dry-run
        r = subprocess.run([PY, str(SCRIPTS / "handoff_gateway.py"), "--agent", "cursor",
                            "--project", "demo", "--out-dir", str(Path(d) / "out"),
                            "--dry-run", "--json"], capture_output=True, text=True, env=env, timeout=60)
        assert r.returncode == 0, r.stderr[-800:]
        out = json.loads(r.stdout)
        assert out["capability"] == "manual", out
        assert out["recovery_path"].endswith(".md"), out
        assert out["open_command"], out
        # Codex：full_auto，不打开外部应用
        r2 = subprocess.run([PY, str(SCRIPTS / "handoff_gateway.py"), "--agent", "codex",
                             "--project", "demo", "--out-dir", str(Path(d) / "out2"),
                             "--dry-run", "--json"], capture_output=True, text=True, env=env, timeout=60)
        assert r2.returncode == 0, r2.stderr[-800:]
        out2 = json.loads(r2.stdout)
        assert out2["capability"] == "full_auto", out2
        assert out2["open_command"] is None, out2

def _mcp_lines(payloads, env=None):
    p = subprocess.Popen([str(CPM)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0, env=env)
    out = []
    initialized = False
    for i, obj in enumerate(payloads, start=1):
        msg = dict({"jsonrpc": "2.0", "id": i}, **obj)
        try:
            p.stdin.write((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
            p.stdin.flush()
        except BrokenPipeError:
            break
        while True:
            line = p.stdout.readline()
            if not line:
                break
            line = line.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except Exception:
                continue
            if obj.get("method") == "initialize" and not initialized:
                try:
                    p.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}\n')
                    p.stdin.flush()
                except BrokenPipeError:
                    pass
                initialized = True
                time.sleep(0.5)
            if parsed.get("id") == i:
                out.append(parsed)
                break
        else:
            break
    try:
        p.stdin.close()
    except Exception:
        pass
    try:
        p.kill()
    except Exception:
        pass
    return out

def _cp_env():
    # 沙箱友好：cp-memory 数据库放到临时可写路径，避免依赖 $CODEX_HOME 写权限
    fd, cpdb = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    env = dict(os.environ, CP_MEMORY_DB_PATH=cpdb)
    return env, cpdb

def p_cpmemory_init():
    env, cpdb = _cp_env()
    try:
        res = _mcp_lines([{"method": "initialize",
                       "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                  "clientInfo": {"name": "selftest", "version": "1"}}}], env=env)
        if not res:
            raise RuntimeError("empty response")
        if '"cp-memory"' not in json.dumps(res[0].get("result")):
            raise RuntimeError(str(res[0])[:400])
    finally:
        try: os.unlink(cpdb)
        except Exception: pass

def p_cpmemory_roundtrip():
    env, cpdb = _cp_env()
    entity = f"selftest_{int(time.time())}"
    try:
        r = _mcp_lines([
            {"method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                                "clientInfo": {"name": "selftest", "version": "1"}}},
            {"method": "tools/call", "params": {"name": "memory_add",
                                                "arguments": {"entity": entity, "property": "roundtrip",
                                                              "value": "ok", "category": "fact", "tags": "selftest"}}},
            {"method": "tools/call", "params": {"name": "memory_probe", "arguments": {"entity": entity}}},
        ], env=env)
        if len(r) < 3:
            raise RuntimeError("r-len=" + str(len(r)) + " " + json.dumps(r, ensure_ascii=False)[:700])
        if "result" not in r[1]:
            raise RuntimeError("add r1=" + str(r[1])[:500])
        if "result" not in r[2]:
            raise RuntimeError("probe r2=" + str(r[2])[:500])
        add = r[1]["result"]
        text = add["content"][0]["text"]
        ident = json.loads(text).get("id")
        assert ident, "memory_add 未返回 id"
        probe_txt = r[2]["result"]["content"][0]["text"]
        assert entity in probe_txt and "roundtrip" in probe_txt, "memory_probe 未读到写入"
        # 清理
        cl = _mcp_lines([
            {"method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                                "clientInfo": {"name": "selftest", "version": "1"}}},
            {"method": "tools/call", "params": {"name": "memory_remove", "arguments": {"id": ident}}},
        ], env=env)
        if not cl or "result" not in cl[1]:
            raise RuntimeError("cleanup=" + str(cl)[:300])
        assert '"ok": true' in cl[1]["result"]["content"][0]["text"], "清理失败"
    finally:
        try:
            os.unlink(cpdb)
        except Exception:
            pass


def _run_state(env, *args):
    return subprocess.run([PY, str(SCRIPTS / "state.py"), *args], check=True, capture_output=True, env=env, text=True)

def p_export_ctx():
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "r.jsonl"
        src.write_text(json.dumps({"response_item": {"type": "message", "role": "user",
                                                     "content": [{"type": "text", "text": "你好"}]}}), encoding="utf-8")
        out = Path(d) / "chat.json"
        subprocess.run([PY, str(SCRIPTS / "export_ctx.py"), "-i", str(src), "-o", str(out)], check=True, capture_output=True)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data and data[0]["role"] == "user" and data[0]["content"] == "你好"

def p_state():
    fd, td = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        env = dict(os.environ, CODEX_MEMORY_STATE=td)
        _run_state(env, "set", "active_project=t", "turn_count=1")
        _run_state(env, "bump", "active_project=t")
        d = json.loads(_run_state(env, "get").stdout)
        assert d["active_project"] == "t" and d["turn_count"] == 2, d
        for _ in range(6):
            out = _run_state(env, "bump", "active_project=p", "thread_id=ta")
            r = json.loads(out.stdout)
            assert r["warned"] is False and r["message"] == ""
        out = _run_state(env, "bump", "active_project=p", "thread_id=ta")
        r = json.loads(out.stdout)
        assert r["turn_count"] == 7 and r["warned"] is True and "请准备开新对话" in r["message"], r
        out = _run_state(env, "bump", "active_project=p", "thread_id=ta")
        r = json.loads(out.stdout)
        assert r["turn_count"] == 8 and r["forced"] is True and "恢复包" in r["message"], r
        out = _run_state(env, "bump", "active_project=p", "thread_id=ta")
        r = json.loads(out.stdout)
        assert r["message"] == "", r  # 已提醒过，不得重复刷屏
        out = _run_state(env, "bump", "active_project=p", "thread_id=tb")
        r = json.loads(out.stdout)
        assert r["turn_count"] == 1 and r["warned"] is False, r
        full = json.loads(_run_state(env, "get").stdout)
        blob = json.dumps(full, ensure_ascii=False)
        assert "内容" not in blob, "state 记录了不应存在的内容字段"
        assert full["turn_count"] == 1
    finally:
        try: os.unlink(td)
        except Exception: pass

def p_agent_hook():
    fd, td = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        env = dict(os.environ, CODEX_MEMORY_STATE=td, PYTHON=PY)
        r = subprocess.run(["bash", str(SCRIPTS / "agent_hook.sh"), "active_project=hk", "thread_id=d1"],
                           check=True, capture_output=True, text=True, env=env)
        out = json.loads(r.stdout)
        assert out["turn_count"] == 1 and out["active_project"] == "hk" and out["thread_id"] == "d1", out
    finally:
        try: os.unlink(td)
        except Exception: pass

def p_no_network():
    allowed_scans = ["state.py", "monitor_dialogs.py", "export_ctx.py", "recovery.py", "agent_hook.sh", "handoff_gateway.py"]
    banned = ("socket", "requests", "urllib", "aiohttp", "httpx", "http://", "https://")
    for name in allowed_scans:
        txt = (SCRIPTS / name).read_text(encoding="utf-8")
        low = txt.lower()
        found = [b for b in banned if b in low]
        assert not found, f"{name} 含网络关键词: {found}"


def p_recovery_index():
    fd, tf = tempfile.mkstemp(suffix=".md")
    os.close(fd)
    try:
        env = dict(os.environ, RECOVERY_INDEX=tf)
        subprocess.run([PY, str(SCRIPTS / "recovery.py"), "--add", "demo", "/tmp/demo.md"], check=True,
                       capture_output=True, env=env)
        text = Path(tf).read_text(encoding="utf-8")
        assert "demo" in text and "/tmp/demo.md" in text
    finally:
        try: os.unlink(tf)
        except Exception: pass

check("SKILL.md 结构与 frontmatter", p_skill_structure)
check("references/templates.md 模板完整", p_template)
check("hot.md 降级线存在", p_hot)
check("AGENTS.md 铁律注入", p_agents)
check("config.toml 数值与 MCP 配置", p_config)
check("protect 脚本与 200K 对齐", p_protect_align)
check("ctxcompress CLI 真实运行", p_ctxcompress)
check("monitor_dialogs.py 跨对话框监测", p_monitor_dialogs)
check("cp-memory initialize 真实运行", p_cpmemory_init)
check("cp-memory 写-读-清 闭环", p_cpmemory_roundtrip)
check("export_ctx.py 转换 JSONL", p_export_ctx)
check("state.py 轮次/隔离/提前提醒/隐私", p_state)
check("agent_hook.sh 实时钩子", p_agent_hook)
check("脚本无网络调用", p_no_network)
check("recovery.py 索引登记", p_recovery_index)
check("monitor --all 与 --days 互斥", p_monitor_all_conflict)
check("monitor --all 存量全量 + over_warned 去重", p_monitor_all_dedup)
check("state.py 多 Agent 注册表/cross-check/@命名空间", p_state_r2_registry)
check("handoff_gateway.py 能力矩阵降级", p_handoff_gateway)


if failures:
    print("FAILURES:", failures)
    sys.exit(1)
print(f"\nALL PASS ({checks_done} 项)")
