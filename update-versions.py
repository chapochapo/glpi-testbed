#!/usr/bin/env python3
"""Fetch latest GLPI Docker images and update generate-compose.py, docker-compose.yml, and README.md.

Run locally:  python3 update-versions.py
"""
import ast
import json
import re
import subprocess
import sys
import urllib.request

HUB_REPO  = "glpi/glpi"
GENERATOR = "generate-compose.py"
COMPOSE   = "docker-compose.yml"
README    = "README.md"


def fetch_tags(repo: str) -> list[str]:
    tags: list[str] = []
    url: str | None = (
        f"https://hub.docker.com/v2/repositories/{repo}/tags/"
        "?page_size=100&ordering=last_updated"
    )
    while url:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read())
        tags.extend(t["name"] for t in data["results"])
        url = data.get("next")
    return tags


def parse_versions(tags: list[str]) -> tuple[list[int], list[int]]:
    v10: list[int] = []
    v11: list[int] = []
    for tag in tags:
        m = re.fullmatch(r"(10|11)\.0\.(\d+)", tag)
        if m:
            (v10 if m.group(1) == "10" else v11).append(int(m.group(2)))
    return sorted(v10), sorted(v11)


def read_current(path: str) -> tuple[list[int], list[int], str]:
    content = open(path).read()
    m10 = re.search(r"^VERSIONS_10X\s*=\s*(\[.*?\])", content, re.MULTILINE)
    m11 = re.search(r"^VERSIONS_11X\s*=\s*(\[.*?\])", content, re.MULTILINE)
    if not m10 or not m11:
        sys.exit(f"Could not parse version lists in {path}")
    return ast.literal_eval(m10.group(1)), ast.literal_eval(m11.group(1)), content


def apply_update(content: str, v10: list[int], v11: list[int]) -> str:
    content = re.sub(
        r"^(VERSIONS_10X\s*=\s*)\[.*?\]",
        lambda m: m.group(1) + repr(v10),
        content, flags=re.MULTILINE,
    )
    content = re.sub(
        r"^(VERSIONS_11X\s*=\s*)\[.*?\]",
        lambda m: m.group(1) + repr(v11),
        content, flags=re.MULTILINE,
    )
    return content


def instance_table(v10: list[int], v11: list[int]) -> str:
    rows = [
        "| GLPI version | URL | Credentials |",
        "|---|---|---|",
    ]
    for p in v10:
        rows.append(f"| 10.0.{p:<2} | http://localhost:{10000 + p} | glpi / glpi |")
    for p in v11:
        rows.append(f"| 11.0.{p:<2} | http://localhost:{11000 + p} | glpi / glpi |")
    return "\n".join(rows)


def update_readme(v10: list[int], v11: list[int]) -> bool:
    content = open(README).read()
    orig = content
    n = len(v10) + len(v11)      # total GLPI versions
    n_ctr = n * 2                 # total containers (GLPI + MySQL pairs)
    latest_11 = v11[-1]

    # RAM: GLPI ~84 MB/instance, MySQL ~539 MB/instance
    glpi_ram   = round(84  * n / 1000, 1)
    mysql_ram  = round(539 * n / 1000, 1)
    total_ram  = round(623 * n / 1000, 1)
    used_ram   = round(total_ram)
    rec_ram    = used_ram + 2
    disk_gb    = round(n * 1.0 + 0.82)   # N GLPI images ~1 GB + shared MySQL ~820 MB

    subs = [
        # Intro: instance count and version range
        (r"runs \d+ GLPI versions simultaneously",
         f"runs {n} GLPI versions simultaneously"),
        (r"Covers GLPI 10\.0\.\d+–10\.0\.\d+ and 11\.0\.0–11\.0\.\d+",
         f"Covers GLPI 10.0.{v10[0]}–10.0.{v10[-1]} and 11.0.0–11.0.{v11[-1]}"),
        # Hardware: "All N containers" heading
        (r"All \d+ containers running simultaneously",
         f"All {n_ctr} containers running simultaneously"),
        # Hardware table
        (r"\| \| Per container \| \d+ containers \|",
         f"| | Per container | {n} containers |"),
        (r"(\| GLPI \(Apache \+ PHP\) \| ~84 MB RAM \| ~)[\d.]+( GB RAM \|)",
         rf"\g<1>{glpi_ram}\g<2>"),
        (r"(\| MySQL 8\.0 \| ~539 MB RAM \| ~)[\d.]+( GB RAM \|)",
         rf"\g<1>{mysql_ram}\g<2>"),
        # RAM and disk requirements
        (r"\*\*RAM:\*\* \d+ GB free recommended \(\d+ GB used by containers, 2 GB headroom for the OS\)",
         f"**RAM:** {rec_ram} GB free recommended ({used_ram} GB used by containers, 2 GB headroom for the OS)"),
        (r"\*\*Disk:\*\* ~\d+ GB for container images \(\d+ GLPI images",
         f"**Disk:** ~{disk_gb} GB for container images ({n} GLPI images"),
        # Subset example (always show the latest 11.x instance)
        (r"podman compose up -d glpi_11_0_\d+ mysql_11_0_\d+  # start only GLPI 11\.0\.\d+ and its database",
         f"podman compose up -d glpi_11_0_{latest_11} mysql_11_0_{latest_11}  # start only GLPI 11.0.{latest_11} and its database"),
        # Usage comments
        (r"# Pull all images \(one-time, ~\d+ GB\)",
         f"# Pull all images (one-time, ~{disk_gb} GB)"),
        (r"# Start all \d+ containers\b",
         f"# Start all {n_ctr} containers"),
        (r"# recreate all \d+ containers",
         f"# recreate all {n_ctr} containers"),
        # docker-compose.yml description
        (r"Defines all \d+ services \(\d+ GLPI \+ \d+ MySQL\), \d+ named volumes, and \d+ isolated bridge networks",
         f"Defines all {n_ctr} services ({n} GLPI + {n} MySQL), {n_ctr} named volumes, and {n} isolated bridge networks"),
        # Architecture diagram footer
        (r"           × \d+ versions",
         f"           × {n} versions"),
        # Port formula example (last 11.x)
        (r"11\.0\.\d+ → 11\d+\.",
         f"11.0.{latest_11} → {11000 + latest_11}."),
    ]

    for pattern, replacement in subs:
        content = re.sub(pattern, replacement, content)

    # Instance table (replaces the whole table block)
    table = instance_table(v10, v11)
    content = re.sub(
        r"\| GLPI version \| URL \| Credentials \|.*?(?=\n\nPort formula:)",
        table,
        content,
        flags=re.DOTALL,
    )

    if content == orig:
        return False
    with open(README, "w") as f:
        f.write(content)
    return True


def main() -> None:
    print("Fetching tags from Docker Hub ...")
    tags = fetch_tags(HUB_REPO)
    new_10, new_11 = parse_versions(tags)
    print(f"  Docker Hub  10.0.x patches: {new_10}")
    print(f"  Docker Hub  11.0.x patches: {new_11}")

    cur_10, cur_11, content = read_current(GENERATOR)
    print(f"  Current     10.0.x patches: {cur_10}")
    print(f"  Current     11.0.x patches: {cur_11}")

    if cur_10 == new_10 and cur_11 == new_11:
        print("Already up to date — nothing to do.")
        return

    updated = apply_update(content, new_10, new_11)
    with open(GENERATOR, "w") as f:
        f.write(updated)
    print(f"Updated {GENERATOR}")

    with open(COMPOSE, "w") as f:
        subprocess.run(["python3", GENERATOR], stdout=f, check=True)
    print(f"Regenerated {COMPOSE}")

    if update_readme(new_10, new_11):
        print(f"Updated {README}")

    added_10 = sorted(set(new_10) - set(cur_10))
    added_11 = sorted(set(new_11) - set(cur_11))
    removed_10 = sorted(set(cur_10) - set(new_10))
    removed_11 = sorted(set(cur_11) - set(new_11))
    if added_10:
        print(f"  Added   10.0.x: {added_10}")
    if added_11:
        print(f"  Added   11.0.x: {added_11}")
    if removed_10:
        print(f"  Removed 10.0.x: {removed_10}")
    if removed_11:
        print(f"  Removed 11.0.x: {removed_11}")


if __name__ == "__main__":
    main()
