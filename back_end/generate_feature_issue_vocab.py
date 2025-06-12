#!/usr/bin/env python3
"""Utility to extract a master list of main_characteristics and visible_issues
from all stored Gemini raw JSON analyses.

Run:
    python generate_feature_issue_vocab.py

It connects to the local SQLite DB (path defined below), scans the
`analysis_results.raw_gemini_response` column, parses the JSON and
collects unique strings. Results are written to
`gemini_feature_issue_vocab.json` in the same directory.
"""
import json
import os
import sqlite3
from typing import Set, Dict

DB_PATH = os.path.join(os.path.dirname(__file__), "real_estate_analysis.db")
OUTPUT_JSON = os.path.join(os.path.dirname(__file__), "gemini_feature_issue_vocab.json")


def _extract_from_analysis(analysis: Dict, characteristics: Set[str], issues: Set[str]):
    """Extract feature/issue strings from a single image analysis dict."""
    # main_characteristics: list[str]
    for feat in analysis.get("main_characteristics", []):
        if isinstance(feat, str):
            characteristics.add(feat.strip().lower())

    # visible_issues: list[{issue:str, severity:str}]
    for iss in analysis.get("visible_issues", []):
        if isinstance(iss, dict):
            val = iss.get("issue")
            if val:
                issues.add(val.strip().lower())


def collect_vocab():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT raw_gemini_response FROM analysis_results WHERE raw_gemini_response IS NOT NULL")

    characteristics: Set[str] = set()
    issues: Set[str] = set()

    rows = cursor.fetchall()
    for (raw_json_str,) in rows:
        try:
            data = json.loads(raw_json_str)
        except json.JSONDecodeError:
            # Skip malformed rows
            continue

        # data can be list / dict with 'image_analyses' / single dict
        analyses = []
        if isinstance(data, dict):
            if "image_analyses" in data and isinstance(data["image_analyses"], list):
                analyses = data["image_analyses"]
            else:
                analyses = [data]
        elif isinstance(data, list):
            analyses = data

        for analysis in analyses:
            if isinstance(analysis, dict):
                _extract_from_analysis(analysis, characteristics, issues)

    conn.close()

    vocab = {
        "characteristics": sorted(characteristics),
        "visible_issues": sorted(issues),
    }

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(vocab, f, indent=2, ensure_ascii=False)
    print(f"✅ Vocabulary generated. Characteristics: {len(characteristics)}, Issues: {len(issues)}")


if __name__ == "__main__":
    collect_vocab()
