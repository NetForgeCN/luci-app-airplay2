# luci-app-airplay2 (shairport-sync)

OpenWrt 上的 AirPlay / AirPlay 2 音频接收器（播放端），带 LuCI 管理界面。

- 上游：<https://github.com/mikebrady/shairport-sync>
- 当前版本：**shairport-sync 5.6.2 + nqptp 1.2.9**（OpenSSL 构建，含 AirPlay 2）
- 编译验证：OpenWrt 24.10 SDK（aarch64_generic、x86_64）
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

在 OpenWrt 源码树根目录执行：

```sh
# 1. 添加本仓库为 feed（建议放在 packages 一行的上面，保证 nqptp 用本仓库这份）
echo 'src-git airplay2 https://github.com/NetForgeCN/luci-app-airplay2.git;main' >> feeds.conf
# 若还没有 feeds.conf：cp feeds.conf.default feeds.conf 后再执行上面的 echo

# 2. 拉取并安装到编译树（-p 明确指定从本 feed 取，避免 nqptp 与 packages feed 的 1.2.4 混淆）
./scripts/feeds update airplay2
./scripts/feeds install -p airplay2 airplay2 nqptp
./scripts/feeds install -p airplay2 luci-app-airplay2   # 需要 LuCI 界面时

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
