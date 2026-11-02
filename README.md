# luci-app-airplay2 (shairport-sync)

OpenWrt 上的 AirPlay / AirPlay 2 音频接收器（播放端），带 LuCI 管理界面。

- 上游：<https://github.com/mikebrady/shairport-sync>
- 当前版本：**shairport-sync 5.6.2 + nqptp 1.2.9**（OpenSSL 构建，含 AirPlay 2）
- 编译验证：OpenWrt **24.10** SDK（aarch64_generic、x86_64）
- 分支要求：只能用 **`openwrt-24.10` / `openwrt-23.05` 稳定分支**，不要用 `master`（原因见「常见问题」第 1 条）
- 现成安装包：<https://github.com/NetForgeCN/luci-app-airplay2/releases>

## 本仓库提供的包

| 包 | 说明 |
| --- | --- |
| `airplay2` | shairport-sync 5.6.2，装为 `/usr/bin/airplay2`，OpenSSL + AirPlay 2 |
| `nqptp` | AirPlay 2 时间同步伴侣守护进程（1.2.9，smi11） |
| `luci-app-airplay2` | LuCI 界面（含中文翻译） |

## v5.6.2 相对旧版（4.3.7）的改动点

1. **shairport-sync 4.3.7 → 5.6.2**
2. **只保留 OpenSSL 单一构建**（含 AirPlay 2）。旧版的 `airplay2-mbedtls` / `airplay2-mini` 变体已删除：shairport-sync 5.x 无法在 mbedtls 下编译 `--with-airplay-2`，而 5.x 时代不带 AirPlay 2 的变体没有意义。这也与 OpenWrt 官方 packages feed 的做法一致（AirPlay 2 仅限 openssl 变体）
3. **新增 nqptp 1.2.9 包**。5.6.x 要求共享内存接口 smi11，只有 nqptp ≥ 1.2.9 提供；官方 packages feed 里的 nqptp 1.2.4（smi10）不兼容
4. **构建补丁**：AirPlay 2 的 plist 代码生成改用构建主机上的 python3，不再需要 `plistutil` / `xxd`（交叉编译环境里没有，OpenWrt feed 的 libplist 也没有 host 构建）
5. **CI**：tag `v*` 触发构建并发布 Release；`pull_request` / `workflow_dispatch` 只编译验证不发版

## 方式一：在 OpenWrt 编译阶段加入（推荐：feeds）

> **前置检查**：`feeds.conf` 里必须有官方四个 feed（packages / luci / routing / telephony）。本仓库只是**追加**一行，**绝不能把 `feeds.conf.default` 覆盖成只剩 airplay2**——那样 packages/luci feed 全部消失，airplay2 的依赖（libffmpeg-full、alsa-lib、luci-base…）一处都解析不到，menuconfig 里什么都不会出现。

在 OpenWrt 源码树根目录执行：

```sh
# 0. 准备 feeds.conf：已有就跳过；没有就从 default 复制（复制，不是覆盖）
[ -f feeds.conf ] || cp feeds.conf.default feeds.conf
grep -q '^src-git packages' feeds.conf || echo "!! feeds.conf 缺官方 feed，请重新 cp feeds.conf.default feeds.conf"

# 1. 追加本仓库为 feed —— 必须用 >> 追加，不要用 > 覆盖
grep -q 'src-git airplay2' feeds.conf || \
  echo 'src-git airplay2 https://github.com/NetForgeCN/luci-app-airplay2.git;main' >> feeds.conf
cat feeds.conf      # 应看到 5 行：4 个官方 feed + 1 个 airplay2

# 2. 拉取并安装到编译树（-p 明确指定从本 feed 取 nqptp，避免 nqptp 与 packages feed 的 1.2.4 混淆）
./scripts/feeds update -a
./scripts/feeds install -a
./scripts/feeds uninstall nqptp                                  # install -a 会先装官方 1.2.4，先摘掉
./scripts/feeds install -p airplay2 nqptp                         # 换成我们的 1.2.9（smi11）

# 3. 选包并编译
make menuconfig
#   Sound  ---> <*> airplay2
#   LuCI   ---> Applications  ---> <*> luci-app-airplay2
#   nqptp 会被 airplay2 自动作为依赖选中
make -j$(nproc)
# 产物在 bin/packages/<架构>/airplay2/*.ipk，或直接刷含这些包的固件
```

**关于 nqptp 的重要说明**：官方 packages feed 里也有一个 nqptp（1.2.4，smi10），与 5.6.x 不兼容。两个规避办法（任选其一，上面步骤已含其一）：

- 安装时始终用 `-p airplay2` 指定来源（脚本会优先用指定 feed）；
- 或者把本仓库的 feed 行写在 feeds.conf 里 packages 那行的**前面**（不指定 `-p` 时，排在前面的 feed 优先）。

如果之前已经装过 packages feed 的 nqptp，先 `./scripts/feeds uninstall nqptp` 再按上面重装。

## 方式二：直接 clone 到 package/ 目录

```sh
cd package/
git clone https://github.com/NetForgeCN/luci-app-airplay2.git
cd ..
make menuconfig && make -j$(nproc)
```

注意：这种方式下如果执行过 `./scripts/feeds install -a`（或显式安装过 packages feed 的 nqptp），`package/` 里的本仓库与 `package/feeds/packages/nqptp` 会同名冲突。先 `./scripts/feeds uninstall nqptp` 清掉 feed 那份，再继续编译。

nqptp 不需要单独处理：它就在本仓库里（`nqptp/` 目录），跟 airplay2 一起被加入编译树。

## 常见问题：menuconfig 里看不到 / 选不上 airplay2

按顺序排查，绝大多数是第 1、2 条。

### 1. 用了 `master` 开发分支（本项目不支持）

本项目只支持 **`openwrt-24.10` / `openwrt-23.05`** 稳定分支（CI 用 24.10 SDK 验证）。`master` 上音频/视频的功能门控已从 kconfig 符号改成真实包，有两处硬性不兼容：

| 本项目写法 | 24.10 / 23.05 | master |
| --- | --- | --- |
| `DEPENDS:=@AUDIO_SUPPORT` | `AUDIO_SUPPORT` 符号存在 | 符号已删除，改为 `audio-support` 包 → 条件永假 |
| `+libffmpeg-full` | 包存在 | ffmpeg 已重构为单一 `libffmpeg`，包名不存在 |

任意一条不满足，airplay2 的 kconfig 条目就**根本不会被生成**——Sound 里没有，按 `/` 搜 `airplay2` 也搜不到。换稳定分支即可：

```sh
git clone -b openwrt-24.10 --depth 1 https://github.com/openwrt/openwrt.git openwrt
```

### 2. `feeds.conf` 缺 feed 或被覆盖

现象与第 1 条相同（条目根本不生成）。检查：

```sh
cat feeds.conf                                  # 应有 packages/luci/routing/telephony + airplay2 共 5 行
ls -d package/feeds/airplay2/*                  # 应有 airplay2 nqptp luci-app-airplay2
grep -c PACKAGE_airplay2 tmp/.config-package.in # 应为非 0
```

`feeds.conf.default` 原样是 4 行官方 feed，airplay2 只能用 `>>` **追加**。若 `feeds.conf.default` 已被覆盖成只剩 airplay2：`git checkout feeds.conf.default`，再按「方式一」重做。

### 3. ffmpeg 带 `FFMPEG_LIBDRM` 时的额外条件（仅未来/开发分支）

24.10 的 ffmpeg 没有这个选项，正常用不到。只有当 ffmpeg 版本含 `FFMPEG_LIBDRM`（默认 y）时，airplay2 → libffmpeg → libdrm → `video-support` 这条链会带来条件依赖 `(!FFMPEG_LIBDRM || PACKAGE_video-support)`，条件不满足时条目被隐藏。判定：menuconfig 里按 `/` 搜 `FFMPEG_LIBDRM`，搜不到就与本条无关。

需要处理时（二选一，改完 `make defconfig`）：

**方案 A（推荐，纯音频用不到 DRM，零副作用）**

```sh
sed -i '/^CONFIG_FFMPEG_LIBDRM/d' .config
echo '# CONFIG_FFMPEG_LIBDRM is not set' >> .config
make defconfig
```

**方案 B（保留 ffmpeg 的 DRM 支持）**——选上 `video-support`（Hardware support → video-support，会引入 libdrm 等）

```sh
sed -i '/^CONFIG_PACKAGE_video-support/d' .config
echo 'CONFIG_PACKAGE_video-support=y' >> .config
make defconfig
```

### 4. 哪些依赖会自动带出

选上 `airplay2` 后自动带出：`nqptp`、`libffmpeg-full`、`alsa-lib`、`libopenssl`、`libavahi-client`、`libsoxr`、`libplist`、`libsodium`、`libgcrypt`、`libmosquitto`、`libconfig`、`libpopt`、`libuuid`。

`luci-app-airplay2` 需要另行手选：`LuCI → 3. Applications → Luci for Apple Airplay2 Receiver`（菜单显示的是 TITLE，字母序在 **L** 区，不在 A 区）。

搜索结果里若出现 `DEFAULT_luci-i18n-airplay2-zh-cn` 这类 `Type: unknown` 的符号，是 kconfig 中被引用但未定义的残留符号，无实际作用，忽略即可；真正的中文包是 `LuCI → Applications → luci-i18n-airplay2-zh-cn`（前提 `luci-app-airplay2` 已选中）。

另外：menuconfig 搜索结果里若出现 `DEFAULT_luci-i18n-airplay2-zh-cn` 这类 "Type: unknown" 的符号，是 kconfig 中被引用但未定义的残留符号，没有实际作用，忽略即可；真正要选的中文界面包是 `LuCI → Applications → luci-i18n-airplay2-zh-cn`（前提是 `luci-app-airplay2` 已选中）。

## 在已装好的 OpenWrt 上安装（免编译）

从 [Releases](https://github.com/NetForgeCN/luci-app-airplay2/releases) 下载对应架构的 ipk：

1. 先确认路由器架构：SSH 进路由器执行 `opkg print-architecture`（或在 LuCI 概览页看「架构」）。一般 ARM64 设备（MT7986 等）用 `aarch64_generic`，x86 用 `x86_64`
2. 下载 4 个文件：`nqptp_1.2.9-r1_<架构>.ipk`、`airplay2_5.6.2-r1_<架构>.ipk`、`luci-app-airplay2_1.0.0-r1_all.ipk`、`luci-i18n-airplay2-zh-cn_..._all.ipk`（中文界面，可选）
3. 传到路由器并安装：

```sh
# 电脑上
scp nqptp_*_<架构>.ipk airplay2_*_<架构>.ipk luci-app-airplay2_*_all.ipk luci-i18n-*_all.ipk root@<路由器IP>:/tmp/

# 路由器上
opkg update    # 必须先更新，libffmpeg-full 等依赖要从在线源拉
opkg remove airplay2-mbedtls airplay2-mini 2>/dev/null   # 旧变体（如有装过）
cd /tmp
opkg install nqptp_1.2.9-r1_<架构>.ipk airplay2_5.6.2-r1_<架构>.ipk \
             luci-app-airplay2_1.0.0-r1_all.ipk luci-i18n-airplay2-zh-cn_*_all.ipk

# 验证 nqptp 版本（必须显示 smi11）
nqptp -V
# Version: 1.2.9. Shared Memory Interface Version: smi11.

/etc/init.d/nqptp enable && /etc/init.d/nqptp start
/etc/init.d/airplay2 enable && /etc/init.d/airplay2 start
```

4. LuCI → 服务 → Airplay 2 里开启并配置（输出设备、名称等），iPhone 就能发现了

提示：

- 依赖（libffmpeg-full、libavahi、libsodium 等）会自动从官方源安装，**flash 空间紧张的小内存设备注意容量**（合计约 3-5 MB）
- 不要只升 airplay2 而保留旧的 nqptp：smi 版本不匹配时 AirPlay 2 无法同步、没有声音

## 从 4.3.x 升级的注意点

- shairport-sync 5.0 起配置文件格式有较大变化（多声道、`alac_decoder` 默认改为 ffmpeg、`pw`/`pa` 段改名为 `pipewire`/`pulseaudio` 等），详见上游 [CONFIGURATIONFILECHANGES5.md](https://github.com/mikebrady/shairport-sync/blob/5.6.2/CONFIGURATIONFILECHANGES5.md)
- 本仓库 LuCI 的 UCI 选项已逐项核对，在 5.6.2 下仍然全部有效（`diagnostics.log_output_to` 被上游标记为废弃，仅打印一条警告，不影响运行）
- 装过旧版 `airplay2-mbedtls` / `airplay2-mini` 的，先 `opkg remove` 再装 `airplay2`

## 构建细节（维护者参考）

- plist 代码生成补丁：`airplay2/patches/100-plist-codegen-without-host-tools.patch`
- 上游 `plists/get_info_response.xml` 自带一个多余的 `</dict>`（严格解析器会报错、libplist 能容忍），补丁已做兼容处理
- `PKG_BUILD_DIR` 需手设为 `$(BUILD_DIR)/shairport-sync-$(PKG_VERSION)`：源码包解压目录名与 `PKG_NAME` 不一致
- nqptp 的 init 为 `START=98`（先于 airplay2 的 99）并带 respawn
