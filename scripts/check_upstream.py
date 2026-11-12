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
import tempfile
import time
import urllib.error
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


def retry(fn, attempts: int = 3, delay: float = 2.0):
    """网络操作重试几次。每天只跑一次的任务，一次 SSL 抖动就等于当天什么都没查。"""
    for i in range(attempts):
        try:
            return fn()
        except (subprocess.CalledProcessError, OSError, urllib.error.URLError) as exc:
            if i + 1 == attempts:
                raise
            print(f"  ...失败（{exc}），{delay * (i + 1):.0f}s 后重试", file=sys.stderr)
            time.sleep(delay * (i + 1))
    raise AssertionError("unreachable")


def latest_tag(repo: str) -> str:
    out = retry(lambda: run(["git", "ls-remote", "--tags", "--refs", f"https://github.com/{repo}.git"]))
    tags = [line.rsplit("refs/tags/", 1)[-1].strip() for line in out.splitlines() if "refs/tags/" in line]
    tags = [t for t in tags if TAG_RE.match(t)]
    if not tags:
        raise SystemExit(f"[{repo}] 没有找到形如 1.2.3 的标签")
    return max(tags, key=version_key)


def fetch_tarball(repo: str, tag: str) -> bytes:
    url = f"https://codeload.github.com/{repo}/tar.gz/{tag}"
    req = urllib.request.Request(url, headers={"User-Agent": "openwrt-airplay2-updater"})

    def download() -> bytes:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.read()

    return retry(download)


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


def check_patches(tarball: bytes, patch_dir: pathlib.Path) -> tuple[int, list[tuple[str, str]]]:
    """把包里的补丁在解压出来的源码树上逐个 --dry-run 一遍。

    返回 (补丁总数, [(补丁名, 失败原因)])。上游一搬动源文件，我们的补丁就最先失效，
    而它在编译日志里表现为“找不到某个 .c”，跟升级本身看不出关系，所以先查出来。
    """
    patches = sorted(patch_dir.glob("*.patch"))
    if not patches:
        return 0, []

    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:gz") as tar:
            try:
                tar.extractall(tmp, filter="data")
            except TypeError:  # python < 3.11.4 没有 filter 参数
                tar.extractall(tmp)
        roots = [p for p in pathlib.Path(tmp).iterdir() if p.is_dir()]
        if not roots:
            return len(patches), [(p.name, "源码包里没有目录") for p in patches]

        # OpenWrt 以 -p1 打补丁；补丁里的路径是 a/ b/，正好对上解压出来的唯一顶层目录。
        # --batch 必须加：文件被上游挪走时 patch 会问 "File to patch:" 并一直等输入，
        # 在 CI 里就是挂到超时。
        source = roots[0]
        failures = []
        for p in patches:
            try:
                res = subprocess.run(
                    ["patch", "-p1", "--batch", "--dry-run", "-s", "-i", str(p.resolve())],
                    cwd=source,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            except subprocess.TimeoutExpired:
                failures.append((p.name, "patch 超过 120 秒没有返回"))
                continue
            if res.returncode != 0:
                detail = (res.stdout + res.stderr).strip().splitlines()
                failures.append((p.name, detail[-1] if detail else f"patch 退出码 {res.returncode}"))
        return len(patches), failures


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
    """把 README 里所有写着版本号的地方一起改掉。

    versions 传的是“全部包的最终版本”，不只是这次变动的包，因为正文里有一行
    把 shairport-sync 与 nqptp 写在同一句里。
    每条替换都只在匹配到旧写法时生效，改不到就原样保留，所以某天重写段落时
    这里停在旧正则上也不会把文件改坏——只是需要顺手补一条。
    """
    if not readme.exists():
        return False
    text = original = readme.read_text()

    ap2 = versions.get("airplay2")
    nqptp = versions.get("nqptp")

    # 顶部那行「当前版本：shairport-sync x + nqptp y」
    if ap2 and nqptp:
        text = re.sub(
            r"shairport-sync \d+(?:\.\d+)+ \+ nqptp \d+(?:\.\d+)+",
            f"shairport-sync {ap2} + nqptp {nqptp}",
            text,
            count=1,
        )

    if ap2:
        # 包表格：「| `airplay2` | shairport-sync 5.6.3，装为 ...」
        text = re.sub(r"shairport-sync \d+(?:\.\d+)+\uFF0c", f"shairport-sync {ap2}\uFF0c", text)
        # 安装命令里的产物名：apk 用连字符，ipk 用下划线，PKG_RELEASE 已被重置为 1。
        # 前面必须不能是字母数字或连字符，否则会把 luci-app-airplay2-1.0.0-r1 一起改掉
        # ——它是另一个包的版本号，跟 shairport-sync 无关。
        text = re.sub(r"(?<![\w-])airplay2-\d+(?:\.\d+)+-r\d+", f"airplay2-{ap2}-r1", text)
        text = re.sub(r"(?<![\w-])airplay2_\d+(?:\.\d+)+-r\d+", f"airplay2_{ap2}-r1", text)
        # 指向上游某个 tag 的文档链接
        text = re.sub(r"blob/\d+(?:\.\d+)+/", f"blob/{ap2}/", text)
        # 「在 5.6.3 下仍全部有效」
        text = re.sub(r"在 \d+(?:\.\d+)+ 下", f"在 {ap2} 下", text)

    if nqptp:
        text = re.sub(r"nqptp-\d+(?:\.\d+)+-r\d+", f"nqptp-{nqptp}-r1", text)
        text = re.sub(r"nqptp_\d+(?:\.\d+)+-r\d+", f"nqptp_{nqptp}-r1", text)

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
    lines.append("- 同步 README 里所有写着版本号的地方：顶部版本行、安装命令里的产物名、指向上游 tag 的文档链接")
    lines.append("- 这条 PR 上会跑 `Build packages`，编译过了才算数")
    lines.append("")

    # 无论哪个包有更新，都用“更新之后”的版本重新核对一次 SMI
    def tarball_of(name: str) -> bytes:
        meta = PACKAGES[name]
        pinned = current_version(ROOT / meta["dir"] / "Makefile")
        if args.dry_run:
            pinned = next((r["new"] for r in changed if r["pkg"] == name), pinned)
        key = (name, pinned)
        if key not in tarballs:
            tarballs[key] = fetch_tarball(meta["repo"], pinned)
        return tarballs[key]

    def smi_of(name: str) -> int | None:
        return nqptp_shm_version(tarball_of(name))

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

    # 补丁是升级时最先坏、也最难从编译日志里认出来的部分，单独一段报出来
    patched = [
        (name, *check_patches(tarball_of(name), ROOT / PACKAGES[name]["dir"] / "patches"))
        for name in PACKAGES
        if (ROOT / PACKAGES[name]["dir"] / "patches").is_dir()
    ]
    patched = [row for row in patched if row[1]]
    if patched:
        lines.append("## 补丁检查")
        lines.append("")
        for name, total, failures in patched:
            if failures:
                lines.append(f"⚠️ **`{name}`：{len(failures)}/{total} 个补丁打不上了，必须先在本地 rebase 再合并**")
                lines.append("")
                for patch, why in failures:
                    lines.append(f"- `{patch}` → {why}")
            else:
                lines.append(f"`{name}`：{total} 个补丁在新源码上仍能干净 apply。")
            lines.append("")

    lines.append("## 合并前确认")
    lines.append("")
    lines.append("- [ ] 上游 `RELEASENOTES` / `CONFIGURATIONFILECHANGES5.md` 有无新增、改名的配置项需要补进 UCI / init")
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
    # 分支名带上版本号：同一版本重复检查只会命中同一个分支（CI 里会跳过推送），
    # 新版本则落在新分支上，不会把已经开着的 PR 分支 force-push 掉，从而不会丢掉
    # 别人在那条分支上补的提交。
    _set_output("branch", "chore/" + "-".join(f"{r['pkg']}-{r['new']}" for r in changed))
    return 0


def _set_output(key: str, value: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{key}={value}\n")


if __name__ == "__main__":
    sys.exit(main())
