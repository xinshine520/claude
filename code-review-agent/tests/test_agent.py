"""Test script for Code Review Agent."""

import asyncio
import os
import sys

# Add src to path - use absolute path
src_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "src")
sys.path.insert(0, src_path)
sys.path.insert(0, os.path.join(src_path, "..", "simple-agent", "src"))

from code_review_agent.agent import CodeReviewAgent
from code_review_agent.core.scope_detector import ReviewScopeDetector
from code_review_agent.core.diff_fetcher import DiffFetcher
from code_review_agent.tools import git as git_tools


async def test_git_tools():
    """Test git tools."""
    print("=" * 50)
    print("Testing Git Tools")
    print("=" * 50)

    # Test get current branch
    branch = await git_tools.get_current_branch()
    print(f"Current branch: {branch}")

    # Test get diff
    diff = await git_tools.get_diff("main")
    print(f"Diff against main: {len(diff)} chars")

    return True


async def test_scope_detector():
    """Test scope detector."""
    print("=" * 50)
    print("Testing Scope Detector")
    print("=" * 50)

    detector = ReviewScopeDetector()

    # Test various inputs
    test_cases = [
        "review current branch",
        "review commit abc123",
        "review staged changes",
        "review unstaged changes",
        "review PR",
    ]

    for user_input in test_cases:
        scope = await detector.detect(user_input)
        print(f"Input: {user_input}")
        print(f"  Type: {scope.type}, Value: {scope.value}, Base: {scope.base_branch}")
        print(f"  Description: {scope.description}")

    return True


async def test_diff_fetcher():
    """Test diff fetcher."""
    print("=" * 50)
    print("Testing Diff Fetcher")
    print("=" * 50)

    fetcher = DiffFetcher()

    # Test staged changes
    from code_review_agent.types import ReviewScope
    scope = ReviewScope(type="staged")
    diff, metadata = await fetcher.get_diff(scope)
    print(f"Staged diff: {len(diff)} chars")
    print(f"  Files changed: {metadata.files_changed}")
    print(f"  Lines added: {metadata.lines_added}")
    print(f"  Lines removed: {metadata.lines_removed}")

    return True


async def test_agent():
    """Test the full agent."""
    print("=" * 50)
    print("Testing Code Review Agent")
    print("=" * 50)

    agent = CodeReviewAgent()

    # Test review with report
    print("\nTesting review_with_report...")
    try:
        report = await agent.review_with_report("review staged changes")
        print(f"Scope: {report.scope}")
        print(f"Summary: {report.summary}")
        print(f"Issues found: {len(report.issues)}")
        if report.metadata:
            print(f"Metadata: {report.metadata}")
    except Exception as e:
        print(f"Error: {e}")

    return True


async def test_review():
    """Test the agent review with LLM."""
    print("=" * 50)
    print("Testing Agent Review (with LLM)")
    print("=" * 50)

    agent = CodeReviewAgent()

    # Test a simple review request
    print("\nRunning review with LLM...")
    result = await agent.review("Please get the current branch name and show the diff against main")
    print(f"Result: {result[:500]}...")

    return True


async def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("CODE REVIEW AGENT TESTS")
    print("=" * 60)

    # Test basic components
    await test_git_tools()
    await test_scope_detector()
    await test_diff_fetcher()
    await test_agent()

    # Test with LLM
    print("\n" + "=" * 60)
    print("LLM TESTS (may require API)")
    print("=" * 60)
    try:
        await test_review()
    except Exception as e:
        print(f"LLM test error: {e}")

    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
