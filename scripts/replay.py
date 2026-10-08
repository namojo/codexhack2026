#!/usr/bin/env python3
"""Replay synthetic rescue cases; never sends emergency messages."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_cases(case_id: str | None = None) -> list[dict]:
    cases = []
    for path in sorted((ROOT / "scenarios").glob("*.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(case.get("id"), str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", case["id"]):
            raise ValueError(f"잘못된 시나리오 ID: {path.name}")
        if case_id and case.get("id") != case_id:
            continue
        if case.get("synthetic") is not True:
            raise ValueError(f"합성 데이터 표시가 없습니다: {path.name}")
        case["_input_path"] = str(path.relative_to(ROOT))
        case["_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        cases.append(case)
    if not cases:
        raise ValueError(f"사례를 찾지 못했습니다: {case_id or 'scenarios/'}")
    ids = [c["id"] for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("중복된 시나리오 ID가 있습니다")
    return cases


def live_analyses(case: dict, command: str, timeout: int) -> tuple[dict, list[dict]]:
    """Only raw event and prior state enter the analyzer; no answer keys."""
    from rescue.engine import replay
    argv = shlex.split(command)
    if not argv:
        raise ValueError("분석 명령이 비어 있습니다")
    analyses, failures = {}, []
    for index, event in enumerate(case["events"]):
        if event["channel"] == "operator":
            continue
        prefix = {k: v for k, v in case.items()
                  if k not in {"fixture_analysis", "expectations", "demo_notes"}}
        prefix["events"] = case["events"][:index]
        prefix["expectations"] = []
        prior = replay(prefix, mode="live", analyses=analyses)["final"]
        # Do not send prior checks, scenario expectations, or future messages.
        packet = {"protocol_version": 1, "synthetic": True,
                  "event": event, "prior_state": prior,
                  "allowed_kinds": ["request", "location_update", "count_correction",
                                    "rescue_report", "safe_report", "duplicate_candidate",
                                    "unreadable_media", "location_conflict", "no_response",
                                    "delivery_failure"]}
        try:
            process = subprocess.run(argv, input=json.dumps(packet, ensure_ascii=False),
                                     capture_output=True, text=True, timeout=timeout,
                                     cwd=ROOT, check=False)
            if process.returncode:
                # Provider stderr may contain sensitive data; record exit code only.
                raise RuntimeError(f"분석 명령 exit={process.returncode}")
            analyses[event["id"]] = json.loads(process.stdout)
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
            failures.append({"event_id": event["id"], "error_type": type(exc).__name__,
                             "message": "분석 출력 없음; 원문 보존 및 분석 거절로 처리"})
    return analyses, failures


def run_cases(cases: list[dict], mode: str = "fixture", *, analyzer_command: str | None = None,
              analysis_dir: Path | None = None, timeout: int = 45) -> dict:
    from rescue.engine import replay
    results = []
    for case in cases:
        start = time.perf_counter()
        analyses, failures = None, []
        if mode == "live":
            if analyzer_command:
                analyses, failures = live_analyses(case, analyzer_command, timeout)
            elif analysis_dir:
                path = analysis_dir / f"{case['id']}.json"
                analyses = json.loads(path.read_text()) if path.exists() else {}
                if not path.exists():
                    failures = [{"error_type": "MissingAnalysisFile",
                                 "message": "모델 출력 파일 없음; fixture 대체 금지"}]
            else:
                raise ValueError("live에는 --analyzer-command 또는 --analysis-dir이 필요합니다")
        result = replay(case, mode=mode, analyses=analyses)
        result.update({"title": case["title"], "description": case["description"],
                       "channels": case["channels"], "events": case["events"],
                       "demo_notes": case.get("demo_notes", ""),
                       "input_path": case["_input_path"], "input_sha256": case["_sha256"],
                       "analyzer_failures": failures,
                       "replay_seconds": round(time.perf_counter() - start, 6)})
        results.append(result)
    checks = [check for r in results for check in r["checks"]]
    code_paths = sorted(list((ROOT / "rescue").glob("*.py")) + list((ROOT / "scripts").glob("*.py"))
                        + list((ROOT / "web").glob("*")))
    return {"schema_version": 1, "project": "아직 여기", "synthetic": True,
            "mode": mode, "analysis_source": "수작업 분석 픽스처" if mode == "fixture" else
            ("외부 분석 명령" if analyzer_command else "외부 제공 분석 파일 (출처 별도 확인)"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "python_version": sys.version.split()[0],
            "code_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in code_paths if p.is_file()},
            "passed": all(r["passed"] for r in results), "case_count": len(results),
            "passed_cases": sum(r["passed"] for r in results),
            "checks_count": len(checks), "passed_checks": sum(c["passed"] for c in checks),
            "analyzer_failure_count": sum(len(r["analyzer_failures"]) for r in results),
            "limitations": ["공식 119 시스템 연동 없음", "실제 OCR·ASR 미실행",
                            "운영자 시간 절감·생존율 미측정",
                            "픽스처 통과는 모델 정확도 검증이 아님"],
            "results": results}


def markdown_report(report: dict) -> str:
    lines = ["# 아직 여기 — 재생 결과", "",
             f"- 모드: {report['mode']} / {report['analysis_source']}",
             "- 데이터: 합성", f"- 사례: {report['passed_cases']}/{report['case_count']}",
             f"- 기대값 검사: {report['passed_checks']}/{report['checks_count']}",
             f"- 분석 실행 오류: {report['analyzer_failure_count']}", "",
             "| 사례 | 결과 | 검사 |", "|---|---|---|"]
    for result in report["results"]:
        checks = result["checks"]
        lines.append(f"| {result['scenario_id']} — {result['title']} | "
                     f"{'PASS' if result['passed'] else 'FAIL'} | "
                     f"{sum(c['passed'] for c in checks)}/{len(checks)} |")
    failures = [(r, c) for r in report["results"] for c in r["checks"] if not c["passed"]]
    if failures:
        lines += ["", "## 실패 근거", ""]
        for result, check in failures:
            lines.append(f"- {result['scenario_id']} / {check['label']}: "
                         f"expected={check['expected']!r}, actual={check['actual']!r}")
    lines += ["", "## 검증 범위", ""] + [f"- {item}" for item in report["limitations"]]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--all", action="store_true")
    selector.add_argument("--case", help="시나리오 ID")
    parser.add_argument("--mode", choices=["fixture", "live"], default="fixture")
    analyzers = parser.add_mutually_exclusive_group()
    analyzers.add_argument("--analyzer-command", help="STDIN 패킷 → STDOUT JSON 분석 명령")
    analyzers.add_argument("--analysis-dir", type=Path)
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--include-output-faults", action="store_true",
                        help="live 평가에 수작업 모델 출력 오류주입 사례도 포함")
    parser.add_argument("--output", type=Path, help="새 출력 디렉터리; 기존 경로 덮어쓰기 금지")
    args = parser.parse_args()
    if args.timeout < 1 or args.timeout > 60:
        parser.error("timeout은 1~60초입니다")
    if args.mode == "fixture" and (args.analyzer_command or args.analysis_dir):
        parser.error("분석 명령·분석 파일은 --mode live와 함께 사용하세요")
    try:
        output = args.output or ROOT / "artifacts" / (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + f"-{time.time_ns() % 1000000000:09d}-{args.mode}")
        if output.exists():
            raise ValueError(f"기존 결과를 덮어쓰지 않습니다: {output}")
        cases = load_cases(args.case)
        excluded = []
        if args.mode == "live" and not args.include_output_faults:
            excluded = [c["id"] for c in cases if c.get("test_kind") == "output_fault"]
            cases = [c for c in cases if c.get("test_kind") != "output_fault"]
            if not cases:
                raise ValueError("선택 사례는 분석기 오류주입용입니다. --include-output-faults로 명시적으로 실행하세요")
        report = run_cases(cases, args.mode, analyzer_command=args.analyzer_command,
                           analysis_dir=args.analysis_dir, timeout=args.timeout)
        output.mkdir(parents=True, exist_ok=False)
        report["command"] = [sys.executable] + sys.argv
        report["excluded_output_fault_cases"] = excluded
        report["output_dir"] = str(output.resolve())
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
        (output / "report.md").write_text(markdown_report(report))
        print(f"{'PASS' if report['passed'] else 'FAIL'} {report['passed_cases']}/{report['case_count']} 사례, "
              f"{report['passed_checks']}/{report['checks_count']} 검사; mode={args.mode}")
        print(output.resolve())
        return 0 if report["passed"] else 1
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"FAIL {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
