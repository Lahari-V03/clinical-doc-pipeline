"""
policy_compare.py — LLM-powered clinical policy document comparison.

Pulls two versions from the version store and uses OpenAI to generate a plain-language summary of what changed and the operational impact.

Usage:
    # Compare last two versions automatically
    python analysis/policy_compare.py --policy cms_ncd

    # Compare specific versions
    python analysis/policy_compare.py --policy cms_ncd --v1 v1 --v2 v2

    # List all versions for a policy
    python analysis/policy_compare.py --policy cms_ncd --list
"""

import argparse
import os
import sys
from datetime import datetime

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis.version_store import VersionStore

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SAMPLES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "samples", "policy"
)
REPORTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "qa", "reports"
)

MAX_CHARS = 6000


def read_text(path):
    """Read extracted text from a .txt file."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def truncate(text, max_chars=MAX_CHARS):
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[... document truncated for token limit ...]"


def compare_with_llm(text_v1, text_v2, label_v1, label_v2, date_v1, date_v2):
    """Send both policy texts to OpenAI and return comparison summary."""
    client = OpenAI(api_key=OPENAI_API_KEY)

    prompt = f"""
You are a healthcare policy analyst working for a payment integrity company like Cotiviti.

You have two versions of a Medicare/healthcare policy document:
- {label_v1} (dated {date_v1})
- {label_v2} (dated {date_v2})

---
{label_v1} ({date_v1}):
{truncate(text_v1)}

---
{label_v2} ({date_v2}):
{truncate(text_v2)}

---

Provide a structured comparison:

1. WHAT CHANGED
   - Key policy changes between the two versions
   - New procedures, determinations, or requirements added
   - Items removed or discontinued
   - Changes to timelines, thresholds, or metrics

2. OPERATIONAL IMPACT
   - What these changes mean for a payment integrity or claims processing team
   - Specific actions that should be taken

3. FLAGS FOR HUMAN REVIEW
   - Changes that are ambiguous or require expert interpretation
   - Confidence level: HIGH / MEDIUM / LOW

Keep it concise and actionable.
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a senior healthcare policy analyst specializing in "
                    "Medicare coverage determinations and payment integrity. "
                    "You produce clear, accurate, and actionable policy change summaries."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=1000,
    )

    return response.choices[0].message.content


def save_report(summary, label_v1, label_v2, policy_name):
    """Save comparison report to qa/reports/."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(
        REPORTS_DIR, f"{policy_name}_{label_v1}_vs_{label_v2}_{timestamp}.txt"
    )

    divider = "═" * 60
    report = f"""
{divider}
  CLINICAL POLICY COMPARISON REPORT
  Cotiviti — Clinical NLT Pipeline POC
  Generated : {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
  Policy    : {policy_name}
  Comparing : {label_v1} → {label_v2}
{divider}

{summary}

{divider}
  ⚠️  AI-generated. Requires human review before use in
  payment integrity or claims processing decisions.
{divider}
"""
    print(report)

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"  Report saved → {report_path}")
    return report_path


def run(policy_name, label_v1=None, label_v2=None, list_only=False):
    """
    Main entry point for policy comparison.

    Args:
        policy_name: Policy group folder name e.g. 'cms_ncd'
        label_v1:    Version label for older version e.g. 'v1'
        label_v2:    Version label for newer version e.g. 'v2'
        list_only:   If True, just list versions and exit
    """
    policy_dir = os.path.join(SAMPLES_DIR, policy_name)
    store = VersionStore(policy_dir)

    if list_only:
        store.list_versions()
        return

    # Get versions to compare
    if label_v1 and label_v2:
        v1, v2 = store.get_by_labels(label_v1, label_v2)
    else:
        print("  No labels specified — comparing last two versions automatically.")
        v1, v2 = store.get_last_two()

    print(f"\n  Comparing:")
    print(f"    {v1['label']} → {v1['file']} ({v1['date']})")
    print(f"    {v2['label']} → {v2['file']} ({v2['date']})")

    text_v1 = read_text(v1["path"])
    text_v2 = read_text(v2["path"])

    print(f"\n  Sending to OpenAI for analysis...")
    summary = compare_with_llm(
        text_v1, text_v2,
        v1["label"], v2["label"],
        v1["date"], v2["date"]
    )

    save_report(summary, v1["label"], v2["label"], policy_name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare two clinical policy versions using LLM")
    parser.add_argument("--policy", type=str, required=True, help="Policy group name e.g. cms_ncd")
    parser.add_argument("--v1",     type=str, default=None,  help="Older version label e.g. v1")
    parser.add_argument("--v2",     type=str, default=None,  help="Newer version label e.g. v2")
    parser.add_argument("--list",   action="store_true",     help="List all versions for this policy")
    args = parser.parse_args()
    run(policy_name=args.policy, label_v1=args.v1, label_v2=args.v2, list_only=args.list)