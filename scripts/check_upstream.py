#!/usr/bin/env python3
"""检查 shairport-sync / nqptp 的上游新版本，有更新就直接改写对应包的 Makefile。

    scripts/check_upstream.py            # 检查全部
    scripts/check_upstream.py nqptp      # 只检查某一个
    scripts/check_upstream.py --dry-run  # 只看结果，不落盘

有更新时：改写 PKG_VERSION / PKG_HASH / PKG_RELEASE，同步 README 里的版本号，
并生成 upstream-report.md（供 CI 当作 PR 正文）。

只用 git ls-remote 取标签、codeload 下 tarball，不碰 GitHub API，避免限流。
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import pathlib
import re
import subprocess
import sys
import tarfile
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPORT = ROOT / "upstream-report.md"

# 想再纳管别的上游包，加一行即可
PACKAGES = {
    "airplay2": {"repo": "mikebrady/shairport-sync", "dir": "airplay2"},
    "nqptp": {"repo": "mikebrady/nqptp", "dir": "nqptp"},
}

TAG_RE = re.compile(r"^\d+(?:\.\d+)+$")
SMI_RE = re.compile(r"#define\s+NQPTP_SHM_STRUCTURES_VERSION\s+(\d+)")


def run(cmd: list[str]) -> str:
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def version_key(tag: str) -> tuple[int, ...]:
    return tuple(int(p) for p in tag.split("."))


def latest_tag(repo: str) -> str:
    out = run(["git", "ls-remote", "--tags", "--refs", f"https://github.com/{repo}.git"])
    tags = [line.rsplit("refs/tags/", 1)[-1].strip() for line in out.splitlines() if "refs/tags/" in line]
    tags = [t for t in tags if TAG_RE.match(t)]
    if not tags:
        raise SystemExit(f"[{repo}] 没有找到形如 1.2.3 的标签")
    return max(tags, key=version_key)


def fetch_tarball(repo: str, tag: str) -> bytes:
    url = f"https://codeload.github.com/{repo}/tar.gz/{tag}"
    req = urllib.request.Request(url, headers={"User-Agent": "openwrt-airplay2-updater"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def nqptp_shm_version(tarball: bytes) -> int | None:
    """从源码包里读出 NQPTP_SHM_STRUCTURES_VERSION，也就是 smiNN 的 NN。"""
    try:
        with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:gz") as tar:
            for member in tar.getmembers():
                if member.name.endswith("nqptp-shm-structures.h"):
                    fh = tar.extractfile(member)
                    if fh:
                        m = SMI_RE.search(fh.read().decode("utf-8", "replace"))
                        if m:
                            return int(m.group(1))
    except (tarfile.TarError, OSError):
        return None
    return None


def current_version(makefile: pathlib.Path) -> str:
    m = re.search(r"^PKG_VERSION:=(.+)$", makefile.read_text(), re.M)
    if not m:
        raise SystemExit(f"{makefile} 里没有 PKG_VERSION")
    return m.group(1).strip()


def rewrite_makefile(text: str, version: str, digest: str) -> str:
    text = re.sub(r"^PKG_VERSION:=.*$", f"PKG_VERSION:={version}", text, count=1, flags=re.M)
    text = re.sub(r"^PKG_HASH:=.*$", f"PKG_HASH:={digest}", text, count=1, flags=re.M)
    text = re.sub(r"^PKG_RELEASE:=.*$", "PKG_RELEASE:=1", text, count=1, flags=re.M)
    return text


def sync_readme(readme: pathlib.Path, versions: dict[str, str]) -> bool:
    if not readme.exists():
        return False
    text = original = readme.read_text()
    if "airplay2" in versions and "nqptp" in versions:
        text = re.sub(
            r"shairport-sync \d+(?:\.\d+)+ \+ nqptp \d+(?:\.\d+)+",
            f"shairport-sync {versions['airplay2']} + nqptp {versions['nqptp']}",
            text,
            count=1,
        )
    if text != original:
        readme.write_text(text)
        return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("targets", nargs="*", help="要检查的包名，留空表示全部")
    ap.add_argument("--dry-run", action="store_true", help="只报告，不修改文件")
    args = ap.parse_args()

    names = args.targets or list(PACKAGES)
    unknown = [n for n in names if n not in PACKAGES]
    if unknown:
        raise SystemExit(f"未知的包：{', '.join(unknown)}")

    changed: list[dict] = []
    overview: list[dict] = []
    tarballs: dict[tuple[str, str], bytes] = {}

    for name in names:
        meta = PACKAGES[name]
        makefile = ROOT / meta["dir"] / "Makefile"
        old = current_version(makefile)
        new = latest_tag(meta["repo"])

        row = {"pkg": name, "repo": meta["repo"], "old": old, "new": new, "smi": "—"}
        if version_key(new) <= version_key(old):
            overview.append(row)
            print(f"[{name}] {old} 已是最新（上游 {new}）")
            continue

        tarball = fetch_tarball(meta["repo"], new)
        tarballs[(name, new)] = tarball
        digest = sha256(tarball)
        row["hash"] = digest
        smi = nqptp_shm_version(tarball)
        if smi is not None:
            row["smi"] = f"smi{smi}"
        overview.append(row)
        changed.append(row)
        print(f"[{name}] {old} -> {new}  sha256={digest}  smi={row['smi']}")

        if not args.dry_run:
            text = makefile.read_text()
            makefile.write_text(rewrite_makefile(text, new, digest))

    if not changed:
        REPORT.unlink(missing_ok=True)
        print("no updates")
        _set_output("changed", "false")
        return 0

    if not args.dry_run:
        versions = {r["pkg"]: r["new"] for r in changed}
        known = {p: current_version(ROOT / PACKAGES[p]["dir"] / "Makefile") for p in PACKAGES}
        known.update(versions)
        sync_readme(ROOT / "README.md", known)

    title = "上游更新：" + "，".join(f"{r['pkg']} {r['old']} → {r['new']}" for r in changed)
    lines = [f"# {title}", ""]
    lines.append("由 `.github/workflows/upstream-check.yml` 自动生成，合并前请人工过一遍下面的清单。")
    lines.append("")
    lines.append("## 版本")
    lines.append("")
    lines.append("| 包 | 上游仓库 | 旧 | 新 | SMI |")
    lines.append("| --- | --- | --- | --- | --- |")
    for r in overview:
        lines.append(f"| `{r['pkg']}` | {r['repo']} | {r['old']} | {r['new']} | {r['smi']} |")
    lines.append("")
    lines.append("## 已自动完成")
    lines.append("")
    lines.append("- 改写 `PKG_VERSION` / `PKG_HASH` / `PKG_RELEASE`（hash 取自 codeload tarball 的 sha256）")
    lines.append("- 同步 README 顶部的版本号")
    lines.append("- 这条 PR 上会跑 `Build packages`，编译过了才算数")
    lines.append("")

    # 无论哪个包有更新，都用“更新之后”的版本重新核对一次 SMI
    def smi_of(name: str) -> int | None:
        meta = PACKAGES[name]
        pinned = current_version(ROOT / meta["dir"] / "Makefile")
        if args.dry_run:
            pinned = next((r["new"] for r in changed if r["pkg"] == name), pinned)
        key = (name, pinned)
        if key not in tarballs:
            tarballs[key] = fetch_tarball(meta["repo"], pinned)
        return nqptp_shm_version(tarballs[key])

    smi_needed = smi_of("airplay2")
    smi_provided = smi_of("nqptp")

    lines.append("## 兼容性（SMI）")
    lines.append("")

    if smi_needed is not None and smi_provided is not None and smi_needed != smi_provided:
        lines.append("⚠️ **SMI 不匹配**")
        lines.append("")
        lines.append(
            f"新版 shairport-sync 需要 **smi{smi_needed}**，本仓库的 nqptp 提供 **smi{smi_provided}**。"
            "两者不一致时 AirPlay 2 会连得上但完全没声音，必须先确认 nqptp 有对应版本再合并。"
        )
        lines.append("")
    elif smi_needed is not None and smi_provided is not None:
        lines.append(f"SMI 版本一致（两边都是 smi{smi_needed}），无需额外处理。")
        lines.append("")
    else:
        lines.append("SMI 版本未能自动解析，请手工 `nqptp -V` 核对。")
        lines.append("")

    lines.append("## 合并前确认")
    lines.append("")
    lines.append("- [ ] 上游 `CONFIGURATIONFILECHANGES5.md` 有无影响 LuCI 已有的 UCI 选项")
    lines.append("- [ ] `DEPENDS` 是否需要补新依赖（看 configure.ac 里新加的 `--with-*`）")
    lines.append("- [ ] 编译产物 `libffmpeg-full` 等运行时依赖仍然满足")
    lines.append("")

    if args.dry_run:
        print("\n".join(lines))
    else:
        REPORT.write_text("\n".join(lines) + "\n")
        print(f"wrote {REPORT}")

    _set_output("changed", "true")
    _set_output("title", title)
    return 0


def _set_output(key: str, value: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{key}={value}\n")


if __name__ == "__main__":
    sys.exit(main())
