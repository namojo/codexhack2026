"""개인 smoke와 합성 사례 재생 근거를 JSON으로 출력한다.

실행: python3 -B -m rescue.verify > rescue/verification-rescue-v1.json
이 확인은 독립 QA와 실제 모델 평가를 대체하지 않는다.
"""

from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest

from rescue.engine import replay
from rescue.smoke import EngineSmoke


def main():
    root = Path(__file__).resolve().parents[1]
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(EngineSmoke)
    tests = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    cases = []
    for path in sorted((root / "scenarios").glob("*.json")):
        item = {"path": str(path.relative_to(root)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        try:
            result = replay(json.loads(path.read_text(encoding="utf-8")))
            item.update(passed=result["passed"], metrics=result["metrics"], checks=result["checks"])
        except (ValueError, TypeError, KeyError) as exc:
            item.update(passed=False, error=f"{type(exc).__name__}: {exc}")
        cases.append(item)
    passed = tests.wasSuccessful() and bool(cases) and all(case["passed"] for case in cases)
    fingerprints = {}
    for name in ["docs/contract.md", "rescue/engine.py", "rescue/smoke.py", "rescue/verify.py"]:
        fingerprints[name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
    evidence = {
        "schema_version": 1, "synthetic": True, "mode": "fixture",
        "created_at": datetime.now(timezone.utc).isoformat(), "cwd": str(root),
        "command": "python3 -B -m rescue.verify", "exit_code": 0 if passed else 1,
        "input_sha256": fingerprints, "passed": passed,
        "smoke": {"tests": tests.testsRun, "failures": len(tests.failures), "errors": len(tests.errors),
                  "passed": tests.wasSuccessful(), "output": stream.getvalue()},
        "case_count": len(cases), "passed_cases": sum(case["passed"] for case in cases),
        "events": sum(case.get("metrics", {}).get("events", 0) for case in cases),
        "assertions": sum(len(case.get("checks", [])) for case in cases), "cases": cases,
        "not_run": ["독립 QA", "실제 LLM", "실제 OCR", "실제 ASR", "실제 브라우저"],
    }
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return evidence["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
