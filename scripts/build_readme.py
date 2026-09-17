#!/usr/bin/env python3
"""Rewrite the Latest releases block in README.md from aliradid's public repos."""

import json
import os
import sys
import urllib.request
from pathlib import Path

USER = "aliradid"
README = Path(__file__).resolve().parent.parent / "README.md"
START = "<!-- releases:start -->"
END = "<!-- releases:end -->"

QUERY = """
query($login: String!) {
  user(login: $login) {
    repositories(first: 100, privacy: PUBLIC, isFork: false, ownerAffiliations: [OWNER]) {
      nodes {
        name
        url
        isArchived
        releases(first: 10, orderBy: {field: CREATED_AT, direction: DESC}) {
          nodes { tagName url publishedAt isDraft isPrerelease }
        }
      }
    }
  }
}
"""


def replace_block(text, body):
    start = text.find(START)
    end = text.find(END)
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"README.md needs {START} followed by {END}")
    return text[: start + len(START)] + "\n" + body + "\n" + text[end:]


def pick_releases(repos, limit=5):
    latest = []
    for repo in repos:
        if repo["name"] == USER or repo["isArchived"]:
            continue
        stable = [
            release
            for release in repo["releases"]["nodes"]
            if release["publishedAt"] and not release["isDraft"] and not release["isPrerelease"]
        ]
        if stable:
            newest = max(stable, key=lambda release: release["publishedAt"])
            latest.append((newest["publishedAt"], repo["name"], newest))

    latest.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [
        {"repo": name, "tag": release["tagName"], "url": release["url"], "date": published[:10]}
        for published, name, release in latest[:limit]
    ]


def render(releases):
    if not releases:
        return "- No releases yet."
    return "\n".join(
        f"- {release['date']}: [{release['repo']} {release['tag']}]({release['url']})"
        for release in releases
    )


def repos_from_response(payload):
    if payload.get("errors"):
        raise RuntimeError(f"GitHub API error: {payload['errors']}")
    user = (payload.get("data") or {}).get("user")
    if not user:
        raise RuntimeError(f"GitHub user {USER!r} not found")
    return user["repositories"]["nodes"]


def update_readme(path, repos):
    path = Path(path)
    old = path.read_text(encoding="utf-8")
    new = replace_block(old, render(pick_releases(repos)))
    if new == old:
        return False
    path.write_text(new, encoding="utf-8")
    return True


def fetch_repos(token):
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": USER}}).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return repos_from_response(json.load(response))


def main():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        sys.exit("set GITHUB_TOKEN so the script can read releases from the GitHub API")
    changed = update_readme(README, fetch_repos(token))
    print("README.md updated" if changed else "README.md already up to date")


if __name__ == "__main__":
    main()
