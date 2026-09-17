import os
import tempfile
import unittest
from pathlib import Path

import build_readme


def release(repo, tag, published, draft=False, prerelease=False):
    return {
        "tagName": tag,
        "url": f"https://github.com/aliradid/{repo}/releases/tag/{tag}",
        "publishedAt": None if draft else published,
        "isDraft": draft,
        "isPrerelease": prerelease,
    }


def repo(name, releases, archived=False):
    return {
        "name": name,
        "url": f"https://github.com/aliradid/{name}",
        "isArchived": archived,
        "releases": {"nodes": releases},
    }


README = (
    "intro\n"
    "<!-- releases:start -->\n"
    "- old line\n"
    "<!-- releases:end -->\n"
    "outro\n"
)

CITATION_NEEDED_LINE = (
    "- 2026-09-16: [citation-needed v1.0.0]"
    "(https://github.com/aliradid/citation-needed/releases/tag/v1.0.0)"
)


class ReplaceBlockTest(unittest.TestCase):
    def test_only_the_text_between_markers_changes(self):
        self.assertEqual(
            build_readme.replace_block(README, "- new line"),
            "intro\n<!-- releases:start -->\n- new line\n<!-- releases:end -->\noutro\n",
        )

    def test_missing_or_misordered_markers_raise(self):
        for text in (
            "no markers at all\n",
            "intro\n<!-- releases:start -->\n",
            "intro\n<!-- releases:end -->\n",
            "<!-- releases:end -->\n<!-- releases:start -->\n",
        ):
            with self.subTest(text=text), self.assertRaises(ValueError):
                build_readme.replace_block(text, "- new line")


class PickReleasesTest(unittest.TestCase):
    def test_newest_published_stable_release_is_used(self):
        repos = [
            repo("when-in-rome", [
                release("when-in-rome", "v2.0.0", None, draft=True),
                release("when-in-rome", "v2.0.0-rc1", "2026-09-20T10:00:00Z", prerelease=True),
                release("when-in-rome", "v1.1.1", "2026-09-16T09:30:00Z"),
                release("when-in-rome", "v1.1.0", "2026-09-16T08:00:00Z"),
            ])
        ]
        self.assertEqual(build_readme.pick_releases(repos), [{
            "repo": "when-in-rome",
            "tag": "v1.1.1",
            "url": "https://github.com/aliradid/when-in-rome/releases/tag/v1.1.1",
            "date": "2026-09-16",
        }])

    def test_repos_without_a_stable_release_are_left_out(self):
        repos = [
            repo("siem-ai", []),
            repo("proctoring-privacy", [
                release("proctoring-privacy", "v0.1.0-beta", "2026-09-01T00:00:00Z", prerelease=True),
            ]),
        ]
        self.assertEqual(build_readme.pick_releases(repos), [])

    def test_profile_repo_and_archived_repos_are_left_out(self):
        repos = [
            repo("aliradid", [release("aliradid", "v1.0.0", "2026-09-10T00:00:00Z")]),
            repo("old-tool", [release("old-tool", "v3.0.0", "2026-09-11T00:00:00Z")], archived=True),
            repo("citation-needed", [release("citation-needed", "v1.0.0", "2026-09-12T00:00:00Z")]),
        ]
        self.assertEqual(
            [r["repo"] for r in build_readme.pick_releases(repos)],
            ["citation-needed"],
        )

    def test_newest_first_and_at_most_five(self):
        repos = [
            repo(f"tool-{day}", [release(f"tool-{day}", "v1.0.0", f"2026-09-0{day}T12:00:00Z")])
            for day in (3, 7, 1, 6, 2, 5, 4)
        ]
        self.assertEqual(
            [r["repo"] for r in build_readme.pick_releases(repos)],
            ["tool-7", "tool-6", "tool-5", "tool-4", "tool-3"],
        )


class RenderTest(unittest.TestCase):
    def test_each_release_is_a_linked_line_with_its_date(self):
        releases = [
            {
                "repo": "when-in-rome",
                "tag": "v1.1.1",
                "url": "https://github.com/aliradid/when-in-rome/releases/tag/v1.1.1",
                "date": "2026-09-16",
            },
            {
                "repo": "citation-needed",
                "tag": "v1.0.0",
                "url": "https://github.com/aliradid/citation-needed/releases/tag/v1.0.0",
                "date": "2026-09-16",
            },
        ]
        self.assertEqual(
            build_readme.render(releases),
            "- 2026-09-16: [when-in-rome v1.1.1]"
            "(https://github.com/aliradid/when-in-rome/releases/tag/v1.1.1)\n"
            + CITATION_NEEDED_LINE,
        )

    def test_no_releases_still_renders_a_list_item(self):
        self.assertRegex(build_readme.render([]), r"^- \S")


class ResponseTest(unittest.TestCase):
    def test_repository_nodes_are_returned(self):
        node = repo("citation-needed", [])
        payload = {"data": {"user": {"repositories": {"nodes": [node]}}}}
        self.assertEqual(build_readme.repos_from_response(payload), [node])

    def test_api_errors_raise_instead_of_returning_no_repos(self):
        for payload in (
            {"data": None, "errors": [{"message": "API rate limit exceeded"}]},
            {"data": {"user": None}},
        ):
            with self.subTest(payload=payload), self.assertRaises(RuntimeError):
                build_readme.repos_from_response(payload)


class UpdateReadmeTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "README.md"
        self.repos = [
            repo("citation-needed", [release("citation-needed", "v1.0.0", "2026-09-16T08:00:00Z")]),
        ]

    def test_file_is_not_touched_when_the_block_is_current(self):
        current = (
            "intro\n<!-- releases:start -->\n"
            + CITATION_NEEDED_LINE
            + "\n<!-- releases:end -->\noutro\n"
        )
        self.path.write_text(current, encoding="utf-8")
        os.utime(self.path, (1_000_000_000, 1_000_000_000))

        changed = build_readme.update_readme(self.path, self.repos)

        self.assertFalse(changed)
        self.assertEqual(self.path.read_text(encoding="utf-8"), current)
        self.assertEqual(self.path.stat().st_mtime, 1_000_000_000)

    def test_file_is_rewritten_when_a_new_release_appears(self):
        self.path.write_text(README, encoding="utf-8")

        changed = build_readme.update_readme(self.path, self.repos)

        self.assertTrue(changed)
        self.assertEqual(
            self.path.read_text(encoding="utf-8"),
            "intro\n<!-- releases:start -->\n"
            + CITATION_NEEDED_LINE
            + "\n<!-- releases:end -->\noutro\n",
        )


if __name__ == "__main__":
    unittest.main()
