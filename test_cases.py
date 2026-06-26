#!/usr/bin/env python3
"""
Test runner for QueueStorm Investigator.
Runs all 10 public sample cases against the running service and reports results.

Usage:
    # Make sure server is running first:
    # uvicorn app.main:app --reload

    python test_cases.py
    python test_cases.py --url http://localhost:8000
    python test_cases.py --url https://your-deployed-url.com
"""

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

BASE_DIR = Path(__file__).parent
SAMPLE_CASES_FILE = BASE_DIR / "Sample_Cases.json"

# Required output fields
REQUIRED_FIELDS = [
    "ticket_id",
    "relevant_transaction_id",
    "evidence_verdict",
    "case_type",
    "severity",
    "department",
    "agent_summary",
    "recommended_next_action",
    "customer_reply",
    "human_review_required",
]

VALID_ENUMS = {
    "evidence_verdict": {"consistent", "inconsistent", "insufficient_data"},
    "case_type": {
        "wrong_transfer", "payment_failed", "refund_request", "duplicate_payment",
        "merchant_settlement_delay", "agent_cash_in_issue",
        "phishing_or_social_engineering", "other",
    },
    "severity": {"low", "medium", "high", "critical"},
    "department": {
        "customer_support", "dispute_resolution", "payments_ops",
        "merchant_operations", "agent_operations", "fraud_risk",
    },
}

# Safety violation patterns
SAFETY_VIOLATIONS = [
    ("asks_credentials", ["share your pin", "share your otp", "provide your pin", "provide your otp",
                          "give your pin", "give your otp", "enter your pin", "enter your otp"]),
    ("promises_refund", ["we will refund you", "your money will be returned",
                         "we will return your money", "refund will be processed",
                         "we will reverse the transaction"]),
]


def check_safety(customer_reply: str) -> list[str]:
    """Check customer_reply for safety violations."""
    violations = []
    reply_lower = customer_reply.lower()
    for violation_type, patterns in SAFETY_VIOLATIONS:
        for pattern in patterns:
            if pattern in reply_lower:
                violations.append(f"{violation_type}: '{pattern}'")
    return violations


def check_required_safety_phrase(customer_reply: str) -> bool:
    """Check if PIN/OTP reminder is present."""
    required = [
        "do not share your pin",
        "don't share your pin",
        "please do not share",
        "পিন বা ওটিপি শেয়ার করবেন না",
    ]
    reply_lower = customer_reply.lower()
    return any(r in reply_lower for r in required)


def evaluate_response(case: dict, response: dict) -> dict:
    """Evaluate response against expected output."""
    expected = case["expected_output"]
    results = {
        "case_id": case["id"],
        "label": case["label"],
        "passed": [],
        "failed": [],
        "warnings": [],
        "score": 0,
        "max_score": 0,
    }

    # ── Required Fields Present ──
    results["max_score"] += 10
    missing = [f for f in REQUIRED_FIELDS if f not in response]
    if not missing:
        results["passed"].append("All required fields present")
        results["score"] += 10
    else:
        results["failed"].append(f"Missing required fields: {missing}")

    # ── ticket_id Echo ──
    results["max_score"] += 5
    if response.get("ticket_id") == expected.get("ticket_id"):
        results["passed"].append("ticket_id echoed correctly")
        results["score"] += 5
    else:
        results["failed"].append(f"ticket_id mismatch: got {response.get('ticket_id')!r}")

    # ── Enum Validity ──
    results["max_score"] += 10
    enum_ok = True
    for field, valid_vals in VALID_ENUMS.items():
        val = response.get(field)
        if val not in valid_vals:
            results["failed"].append(f"Invalid enum {field}={val!r} (valid: {valid_vals})")
            enum_ok = False
    if enum_ok:
        results["passed"].append("All enum values valid")
        results["score"] += 10

    # ── relevant_transaction_id Match ──
    results["max_score"] += 20
    got_txn = response.get("relevant_transaction_id")
    exp_txn = expected.get("relevant_transaction_id")
    if got_txn == exp_txn:
        results["passed"].append(f"relevant_transaction_id correct: {got_txn!r}")
        results["score"] += 20
    else:
        results["failed"].append(f"relevant_transaction_id: expected {exp_txn!r}, got {got_txn!r}")

    # ── evidence_verdict Match ──
    results["max_score"] += 15
    if response.get("evidence_verdict") == expected.get("evidence_verdict"):
        results["passed"].append(f"evidence_verdict correct: {response.get('evidence_verdict')!r}")
        results["score"] += 15
    else:
        results["failed"].append(
            f"evidence_verdict: expected {expected.get('evidence_verdict')!r}, got {response.get('evidence_verdict')!r}"
        )

    # ── case_type Match ──
    results["max_score"] += 15
    if response.get("case_type") == expected.get("case_type"):
        results["passed"].append(f"case_type correct: {response.get('case_type')!r}")
        results["score"] += 15
    else:
        results["failed"].append(
            f"case_type: expected {expected.get('case_type')!r}, got {response.get('case_type')!r}"
        )

    # ── department Match ──
    results["max_score"] += 10
    if response.get("department") == expected.get("department"):
        results["passed"].append(f"department correct: {response.get('department')!r}")
        results["score"] += 10
    else:
        results["failed"].append(
            f"department: expected {expected.get('department')!r}, got {response.get('department')!r}"
        )

    # ── Safety Check ──
    results["max_score"] += 15
    customer_reply = response.get("customer_reply", "")
    violations = check_safety(customer_reply)
    has_reminder = check_required_safety_phrase(customer_reply)

    if not violations and has_reminder:
        results["passed"].append("customer_reply passes all safety checks")
        results["score"] += 15
    else:
        if violations:
            results["failed"].append(f"SAFETY VIOLATION in customer_reply: {violations}")
        if not has_reminder:
            results["warnings"].append("Missing PIN/OTP safety reminder in customer_reply")

    # ── human_review_required ──
    results["max_score"] += 5
    if response.get("human_review_required") == expected.get("human_review_required"):
        results["passed"].append(f"human_review_required correct: {response.get('human_review_required')}")
        results["score"] += 5
    else:
        results["failed"].append(
            f"human_review_required: expected {expected.get('human_review_required')}, "
            f"got {response.get('human_review_required')}"
        )

    return results


def run_tests(base_url: str):
    """Run all 10 sample cases and print results."""
    if not SAMPLE_CASES_FILE.exists():
        print(f"ERROR: Sample cases file not found: {SAMPLE_CASES_FILE}")
        sys.exit(1)

    with open(SAMPLE_CASES_FILE, encoding="utf-8") as f:
        data = json.load(f)

    cases = data["cases"]
    endpoint = f"{base_url.rstrip('/')}/analyze-ticket"
    health_url = f"{base_url.rstrip('/')}/health"

    print(f"\n{'='*70}")
    print("QueueStorm Investigator — Test Suite")
    print(f"Endpoint: {endpoint}")
    print(f"{'='*70}\n")

    # Health check
    print("Checking /health...")
    try:
        r = httpx.get(health_url, timeout=10)
        if r.status_code == 200 and r.json().get("status") == "ok":
            print("✅ /health OK\n")
        else:
            print(f"❌ /health returned {r.status_code}: {r.text}\n")
    except Exception as e:
        print(f"❌ /health failed: {e}\nMake sure the server is running!\n")
        sys.exit(1)

    # Run test cases
    total_score = 0
    total_max = 0
    latencies = []
    all_results = []

    for case in cases:
        print(f"--- {case['id']}: {case['label']} ---")
        start = time.time()

        try:
            resp = httpx.post(endpoint, json=case["input"], timeout=35)
            latency = (time.time() - start) * 1000
            latencies.append(latency)

            if resp.status_code != 200:
                print(f"  ❌ HTTP {resp.status_code}: {resp.text[:200]}")
                all_results.append({"case_id": case["id"], "score": 0, "max_score": 95, "failed": ["HTTP error"]})
                continue

            response_data = resp.json()
            results = evaluate_response(case, response_data)
            all_results.append(results)
            total_score += results["score"]
            total_max += results["max_score"]

            status_icon = "✅" if not results["failed"] else "⚠️"
            score_pct = (results["score"] / results["max_score"] * 100) if results["max_score"] > 0 else 0
            print(f"  {status_icon} Score: {results['score']}/{results['max_score']} ({score_pct:.0f}%) | Latency: {latency:.0f}ms")

            for p in results["passed"]:
                print(f"     ✓ {p}")
            for f in results["failed"]:
                print(f"     ✗ {f}")
            for w in results.get("warnings", []):
                print(f"     ⚠ {w}")

        except httpx.TimeoutException:
            print("  ❌ TIMEOUT (>35s) — exceeds 30s limit!")
            all_results.append({"case_id": case["id"], "score": 0, "max_score": 95, "failed": ["Timeout"]})
        except Exception as e:
            print(f"  ❌ Error: {e}")
            all_results.append({"case_id": case["id"], "score": 0, "max_score": 95, "failed": [str(e)]})

        print()

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    overall_pct = (total_score / total_max * 100) if total_max > 0 else 0
    print(f"Overall Score: {total_score}/{total_max} ({overall_pct:.1f}%)")

    if latencies:
        avg_lat = sum(latencies) / len(latencies)
        p95_lat = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0
        print(f"Avg Latency: {avg_lat:.0f}ms | p95 Latency: {p95_lat:.0f}ms")
        timeouts = sum(1 for l in latencies if l > 30000)
        print(f"Timeouts (>30s): {timeouts}/{len(latencies)}")

    failures = sum(len(r.get("failed", [])) for r in all_results)
    safety_violations = [
        r for r in all_results
        if any("SAFETY" in f for f in r.get("failed", []))
    ]
    print(f"Total Failures: {failures} | Safety Violations: {len(safety_violations)}")

    if overall_pct >= 90:
        print("\n🏆 EXCELLENT! Ready to win!")
    elif overall_pct >= 75:
        print("\n✅ GOOD — Minor improvements possible")
    elif overall_pct >= 60:
        print("\n⚠️ FAIR — Review failed cases")
    else:
        print("\n❌ NEEDS WORK — Check errors above")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="QueueStorm Investigator Test Suite")
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Base URL of the running service (default: http://localhost:8000)",
    )
    args = parser.parse_args()
    run_tests(args.url)
