#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""项目步骤自动编排（memory-orchestrator 正式版，纯 stdlib、不上网）。

把一个大项目拆成有序步骤，维护 plan JSON；每完成一步自动推进到下一步。
支持幂等初始化、断点恢复、默认免逐步确认（auto）、完成时写审计日志。

命令：
  step_orchestrator.py plan   <plan.json> [--project 项目] [--agent 名称]
  step_orchestrator.py render [--project 项目] [--json]
  step_orchestrator.py complete [--project 项目] [--note 说明] [--thread-id 对话框ID]
  step_orchestrator.py status [--project 项目]

环境变量：
  CODEX_MEMORY_STATE_FALLBACK  覆盖 plan 文件根目录（默认 $CODEX_HOME/memory/plans）
  AUTO=1 / APPROVAL_MODE=auto  免进度确认（legacy 显式开启，已默认）
  AUTO=0 / APPROVAL_MODE=manual 关闭免确认，回到逐次确认模式
  MEMORY_AGENT                 默认 agent 名（默认 codex）
"""
import argparse
import json
import os
import time
from pathlib import Path


def default_base() -> Path:
    env = os.environ.get("CODEX_MEMORY_STATE_FALLBACK") or os.environ.get("CODEX_MEMORY_PLANS")
    if env:
        return Path(env)
    return Path.home() / ".codex" / "memory" / "plans"


def audit_path() -> Path:
    return Path.home() / ".codex" / "audit.log"


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def plan_file(project: str) -> Path:
    return default_base() / f"{project}.plan.json"


def load_plan(project: str):
    p = plan_file(project)
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    data.setdefault("agent", os.environ.get("MEMORY_AGENT", "codex"))
    data.setdefault("current", 0)
    return data


def save_plan(project: str, data) -> None:
    default_base().mkdir(parents=True, exist_ok=True)
    plan_file(project).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def init_plan(planfile, project, agent):
    src = json.loads(Path(planfile).read_text(encoding="utf-8"))
    steps = src.get("steps")
    if not isinstance(steps, list) or not steps:
        raise SystemExit("plan 文件缺少非空 steps 数组")
    existing = load_plan(project)
    if existing is not None:
        print(f"⚠️ 已存在计划「{project}」，未变更（幂等，不重复 init）。")
        return None
    step_list = []
    for i, s in enumerate(steps):
        sid = str(s.get("id")) if s.get("id") is not None else f"s{i+1}"
        step_list.append({
            "id": sid,
            "title": str(s.get("title") or f"步骤{i+1}"),
            "prompt": str(s.get("prompt") or ""),
            "verify": str(s.get("verify") or ""),
            "done": False,
            "note": "",
            "started_at": now() if i == 0 else "",
            "finished_at": "",
        })
    data = {
        "project": project,
        "agent": agent,
        "current": 0,
        "steps": step_list,
        "created_at": now(),
    }
    save_plan(project, data)
    return data


# 默认每步自动放行（用户预授权全部步骤的本地操作，红色清单仍不豁免）
PREAPPROVAL = ('默认免逐步确认（供开新对话直接执行）：本步已获用户预授权，直接执行、不弹授权；仅红线（公司数据上云/Git远端、删除原始资料、未授权系统配置改动）需先询问。')

RED_LINES = ("红线（auto 也不豁免）：不把公司数据发云端/Git 远端、不删除原始资料、不擅自改系统配置；"
             "破坏性变更先写审计日志并保持可回滚。")


def render(project, as_json=False):
    if not as_json:
        print("▶ 默认免逐步确认（auto）：新对话框按本开工提示词直接执行，不逐次弹授权；红线（公司数据上云/Git远端、删除原始资料、未授权系统配置改动）仍先询。设 AUTO=0 可关闭。")
    data = load_plan(project)
    if data is None:
        raise SystemExit("未找到计划，请先运行 plan")
    idx = data["current"]
    total = len(data["steps"])
    if idx >= total:
        print("🎉 项目全部步骤已完成。共", total, "步。")
        return None
    s = data["steps"][idx]
    prevs = [x for x in data["steps"][:idx] if x.get("done")]
    prev_txt = "\n".join(f"- {p['id']}（{p['title']}）" + (f"：{p['note']}" if p.get("note") else "")
                         for p in prevs) or "（无，这是第 1 步）"
    nxt = data["steps"][idx + 1] if idx + 1 < total else None
    if as_json:
        print(json.dumps({
            "step": idx + 1, "total": total,
            "id": s["id"], "title": s["title"],
            "prompt": s["prompt"], "verify": s["verify"],
            "previous": prev_txt,
            "next": nxt["title"] if nxt else None,
            "preapproval": PREAPPROVAL,
            "red_lines": RED_LINES,
        }, ensure_ascii=False, indent=2))
        return None
    lines = [
        f"【Step {idx+1}/{total}】{s['title']}",
        "已完成的步骤：",
        prev_txt,
        "",
        "本步骤开工提示词：",
        s["prompt"],
        "",
        "本步骤验证方式：",
        s["verify"] or "（按 AGENTS 完成验证并附证据）",
        "",
        "下一步预告：",
        nxt["title"] if nxt else "（无，这是最后一步）",
        "",
        PREAPPROVAL,
        RED_LINES,
    ]
    print("\n".join(lines))
    return None


def complete(project, note="", thread_id=""):
    data = load_plan(project)
    if data is None:
        raise SystemExit("未找到计划")
    idx = data["current"]
    total = len(data["steps"])
    if idx >= total:
        print("🎉 已全部完成，无需推进。")
        return None
    s = data["steps"][idx]
    if not s.get("started_at"):
        s["started_at"] = now()
    s["done"] = True
    s["note"] = note or s.get("note") or ""
    s["finished_at"] = now()
    audit_line = f"{now()} memory-orchestrator step {s['id']} done project={data['project']} title={s['title']}"
    if thread_id:
        audit_line += f" thread_id={thread_id}"
    try:
        audit_path().parent.mkdir(parents=True, exist_ok=True)
        with audit_path().open("a", encoding="utf-8") as fh:
            fh.write(audit_line + "\n")
    except OSError:
        print("⚠️ 审计日志写入失败（不影响计划推进）：", audit_path())
    if not all(x.get("done") for x in data["steps"]):
        data["current"] = idx + 1
        ns = data["steps"][data["current"]]
        if not ns.get("started_at"):
            ns["started_at"] = now()
    save_plan(project, data)
    if idx + 1 < total:
        print(f"✅ 已标记完成步骤[{idx+1}/{total}]：{s['title']}（当前推进至 step {data['current']+1}/{total}）")
        auto = not (os.environ.get("AUTO") == "0" or os.environ.get("APPROVAL_MODE", "").lower() == "manual")
        if auto:
            print("\n=== 免确认自动进入下一步：===\n")
            render(project)
        else:
            print("\n下一步需确认时才推进；确认后运行 render 查看下一份开工提示词。")
    else:
        print(f"🎉 计划「{data['project']}」全部完成。共 {total} 步。")
    return None


def status(project):
    data = load_plan(project)
    if data is None:
        raise SystemExit("未找到计划")
    total = len(data["steps"])
    done = sum(1 for s in data["steps"] if s.get("done"))
    print(f"项目={data['project']} agent={data['agent']} 进度 {done}/{total}")
    for i, s in enumerate(data["steps"]):
        if s.get("done"):
            mark = "✅"
        elif i == data.get("current", 0):
            mark = "▶️ 当前"
        else:
            mark = "⏳"
        print(f"  {mark} [{s['id']}] {s['title']}" + (f"（{s['note']}）" if s.get("note") else ""))


def main():
    ap = argparse.ArgumentParser(description="项目步骤自动编排（memory-orchestrator）")
    ap.add_argument("action", choices=["plan", "render", "complete", "status"])
    ap.add_argument("planfile", nargs="?", help="plan JSON（仅 plan 动作必填）")
    ap.add_argument("--project", default=None, help="项目名；缺省用 plan 文件里的 project")
    ap.add_argument("--agent", default=os.environ.get("MEMORY_AGENT", "codex"))
    ap.add_argument("--note", default="")
    ap.add_argument("--thread-id", default="")
    ap.add_argument("--json", action="store_true", help="render 输出 JSON（供开新对话框接力使用）")
    args = ap.parse_args()

    if args.action == "plan":
        if not args.planfile:
            ap.error("plan 需要 planfile")
        src = json.loads(Path(args.planfile).read_text(encoding="utf-8"))
        project = args.project or src.get("project") or ""
        if not project:
            ap.error("缺少项目名：请在 plan 文件中写 project 或传 --project")
        d = init_plan(args.planfile, project, args.agent)
        if d:
            print(f"已初始化计划「{project}」共 {len(d['steps'])} 步（重复运行将幂等跳过）。")
    elif args.action == "render":
        if not args.project:
            ap.error("--project 必填")
        render(args.project, as_json=args.json)
    elif args.action == "complete":
        if not args.project:
            ap.error("--project 必填")
        complete(args.project, note=args.note, thread_id=args.thread_id)
    elif args.action == "status":
        if not args.project:
            ap.error("--project 必填")
        status(args.project)


if __name__ == "__main__":
    main()
