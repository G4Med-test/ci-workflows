from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import check_protection
import tests_list

PROTECTED = [
    {"type": "deletion", "ruleset_id": 1},
    {"type": "non_fast_forward", "ruleset_id": 1},
    {"type": "pull_request", "ruleset_id": 1, "parameters": {"required_approving_review_count": 1}},
    {"type": "required_status_checks", "ruleset_id": 1, "parameters": {}},
]


class ProblemsTests(unittest.TestCase):
    def test_ruleset_of_protect_repos_passes(self):
        self.assertEqual(check_protection.problems(PROTECTED), [])

    def test_unprotected_branch_lists_every_problem(self):
        self.assertEqual(check_protection.problems([]), [
            "deletion is allowed", "force pushes are allowed",
            "direct pushes are allowed (no pull request rule)"])

    def test_pull_requests_without_approval_fail(self):
        rules = PROTECTED[:2] + [{"type": "pull_request",
                                  "parameters": {"required_approving_review_count": 0}}]
        self.assertEqual(check_protection.problems(rules), ["pull requests need no approval"])

    def test_strictest_of_several_rulesets_counts(self):
        rules = PROTECTED + [{"type": "pull_request", "ruleset_id": 2,
                              "parameters": {"required_approving_review_count": 0}}]
        self.assertEqual(check_protection.problems(rules), [])


class MainTests(unittest.TestCase):
    def run_main(self, *args, rules=(), default_branch="main"):
        calls = []

        def get(path):
            calls.append(path)
            return {"default_branch": default_branch} if path.count("/") == 3 else list(rules)

        with mock.patch.object(check_protection, "get", get), \
                mock.patch("builtins.print") as printed:
            status = check_protection.main(list(args))
        return status, calls, "\n".join(str(c.args[0]) for c in printed.call_args_list)

    def test_protected_repository_passes(self):
        status, calls, out = self.run_main("G4Med-test/A", rules=PROTECTED, default_branch="master")
        self.assertEqual(status, 0)
        self.assertEqual(calls, ["/repos/G4Med-test/A", "/repos/G4Med-test/A/rules/branches/master"])
        self.assertEqual(out, "G4Med-test/A: master protected")

    def test_unprotected_repository_fails_with_the_fix(self):
        status, calls, out = self.run_main("--branch", "main", "G4Med-test/A")
        self.assertEqual(status, 1)
        self.assertEqual(calls, ["/repos/G4Med-test/A/rules/branches/main"])
        self.assertIn("::error::G4Med-test/A: main is not protected", out)
        self.assertIn("protect-repos.sh G4Med-test/A", out)

    def test_default_repositories_are_the_trusted_ones_and_the_tests(self):
        repos = check_protection.default_repositories()
        self.assertEqual(repos[:6], check_protection.ORGANIZATION)
        self.assertEqual(repos[6:], [test["repo"] for test in tests_list.load()])


if __name__ == "__main__":
    unittest.main()
