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

def check(name, fn):
    try:
        fn()
        print(f"PASS  {name}")
    except Exception as e:
        failures.append(name)
        print(f"FAIL  {name}: {e}")

def p_skill_structure():
    txt = SKILL.read_text(encoding="utf-8")
    assert re.match(r"^---\nname:\s*memory-orchestrator\ndescription:", txt), "frontmatter 不完整"
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

def _mcp_lines(payloads):
    p = subprocess.Popen([str(CPM)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0)
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

def p_cpmemory_init():
    res = _mcp_lines([{"method": "initialize",
                       "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                  "clientInfo": {"name": "selftest", "version": "1"}}}])
    if not res:
        raise RuntimeError("empty response")
    if '"cp-memory"' not in json.dumps(res[0].get("result")):
        raise RuntimeError(str(res[0])[:400])

def p_cpmemory_roundtrip():
    entity = f"selftest_{int(time.time())}"
    r = _mcp_lines([
        {"method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                            "clientInfo": {"name": "selftest", "version": "1"}}},
        {"method": "tools/call", "params": {"name": "memory_add",
                                            "arguments": {"entity": entity, "property": "roundtrip",
                                                          "value": "ok", "category": "fact", "tags": "selftest"}}},
        {"method": "tools/call", "params": {"name": "memory_probe", "arguments": {"entity": entity}}},
    ])
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
    ])
    if not cl or "result" not in cl[1]:
        raise RuntimeError("cleanup=" + str(cl)[:300])
    assert '"ok": true' in cl[1]["result"]["content"][0]["text"], "清理失败"

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
        subprocess.run([PY, str(SCRIPTS / "state.py"), "set", "active_project=t", "turn_count=1"], check=True,
                       capture_output=True, env=env)
        subprocess.run([PY, str(SCRIPTS / "state.py"), "bump", "active_project=t"], check=True, capture_output=True, env=env)
        r = subprocess.run([PY, str(SCRIPTS / "state.py"), "get"], check=True, capture_output=True, env=env)
        d = json.loads(r.stdout)
        assert d["active_project"] == "t" and d["turn_count"] == 2, d
    finally:
        try: os.unlink(td)
        except Exception: pass

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
check("state.py 轮次计数", p_state)
check("recovery.py 索引登记", p_recovery_index)

if failures:
    print("FAILURES:", failures)
    sys.exit(1)
print(f"\nALL PASS ({12}/12)")
