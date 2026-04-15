"""Test script for Code Review Agent with sample code."""

import asyncio
import os
import sys
import json

# Add src to path - use absolute path
src_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "src")
sys.path.insert(0, src_path)
sys.path.insert(0, os.path.join(src_path, "..", "simple-agent", "src"))

from code_review_agent.agent import CodeReviewAgent
from code_review_agent.core.scope_detector import ReviewScopeDetector
from code_review_agent.core.diff_fetcher import DiffFetcher
from code_review_agent.core.context_reader import ContextReader
from code_review_agent.core.analyzer import ReviewAnalyzer
from code_review_agent.tools import git as git_tools


async def test_scope_detector_fixed():
    """Test scope detector with fixed unstaged bug."""
    print("=" * 50)
    print("Testing Scope Detector (Fixed)")
    print("=" * 50)

    detector = ReviewScopeDetector()

    # Test unstaged specifically
    user_input = "review unstaged changes"
    scope = await detector.detect(user_input)
    print(f"Input: {user_input}")
    print(f"  Type: {scope.type}, Value: {scope.value}, Base: {scope.base_branch}")
    print(f"  Description: {scope.description}")

    if scope.type != "unstaged":
        print("  ERROR: Should be 'unstaged'!")
    else:
        print("  OK: Correctly identified as 'unstaged'")

    return scope.type == "unstaged"


async def test_code_analysis():
    """Test code analysis with sample file."""
    print("=" * 50)
    print("Testing Code Analysis")
    print("=" * 50)

    # Get staged diff
    diff = await git_tools.get_staged_diff()
    print(f"Staged diff: {len(diff)} chars")

    if not diff:
        print("No staged changes found!")
        return False

    # Get file contents
    fetcher = DiffFetcher()
    files = fetcher.extract_files_from_diff(diff)
    print(f"Files: {files}")

    reader = ContextReader()
    file_contents = await reader.read_changed_files(diff)

    # Analyze
    from code_review_agent.types import ReviewScope, DiffMetadata
    scope = ReviewScope(type="staged", description="Staged changes")
    metadata = fetcher._parse_diff_metadata(diff)

    analyzer = ReviewAnalyzer()
    report = await analyzer.analyze(diff, file_contents, scope, metadata)

    print(f"\nIssues found: {len(report.issues)}")
    for issue in report.issues:
        print(f"  - [{issue.severity}] {issue.type}: {issue.file}:{issue.line}")
        print(f"    {issue.description}")

    print(f"\nSummary: {report.summary}")
    print(f"Metadata: {report.metadata}")

    return len(report.issues) > 0


async def test_full_review_with_llm():
    """Test full agent review with LLM."""
    print("=" * 50)
    print("Testing Full Review with LLM")
    print("=" * 50)

    agent = CodeReviewAgent()

    # Ask to review staged changes
    print("\nRunning review with LLM...")
    result = await agent.review("Please review my staged changes and identify any bugs, security issues, or code quality problems")

    print(f"\n--- Review Result ---")
    print(result[:2000])

    return True


async def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("CODE REVIEW AGENT TESTS - ENHANCED")
    print("=" * 60)

    # Test 1: Scope detector fix
    test1 = await test_scope_detector_fixed()

    # Test 2: Code analysis
    test2 = await test_code_analysis()

    # Test 3: Full review with LLM
    print("\n" + "=" * 60)
    try:
        test3 = await test_full_review_with_llm()
    except Exception as e:
        print(f"LLM Test Error: {e}")
        test3 = False

    print("\n" + "=" * 60)
    print("TEST RESULTS")
    print("=" * 60)
    print(f"Scope Detector Fix: {'PASS' if test1 else 'FAIL'}")
    print(f"Code Analysis: {'PASS' if test2 else 'FAIL'}")
    print(f"Full LLM Review: {'PASS' if test3 else 'FAIL'}")


if __name__ == "__main__":
    asyncio.run(main())
