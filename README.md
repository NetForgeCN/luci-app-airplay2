# luci-app-airplay2 (shairport-sync)

OpenWrt 上的 AirPlay / AirPlay 2 音频接收器（播放端），带 LuCI 管理界面。

- 上游：<https://github.com/mikebrady/shairport-sync>
- 当前版本：**shairport-sync 5.6.2 + nqptp 1.2.9**（OpenSSL 构建，含 AirPlay 2）
- 目标版本：**OpenWrt master（snapshot）** 与 **24.10 / 23.05**
- 现成安装包：<https://github.com/NetForgeCN/luci-app-airplay2/releases>
  - `v5.1.0`：master / snapshot 的 **.apk**
  - `v5.0.0`：24.10 / 23.05 的 **.ipk**

## 分支说明

| 分支 | 用途 |
| --- | --- |
| `main` | 主线。同一份 Makefile 自适应 master 与 24.10/23.05 |
| `openwrt-24.10` | 24.10 专用的旧版快照（硬编码 `@AUDIO_SUPPORT`），仅在需要锁定旧行为时使用 |

## 本仓库提供的包

| 包 | 说明 |
| --- | --- |
| `airplay2` | shairport-sync 5.6.2，装为 `/usr/bin/airplay2`，OpenSSL + AirPlay 2 |
| `nqptp` | AirPlay 2 时间同步伴侣守护进程（1.2.9，smi11） |
| `luci-app-airplay2` | LuCI 界面（含中文翻译） |

## 为什么需要本仓库（master 上的现状）

1. **master 的官方 packages feed 已不再提供 shairport-sync**，只有 `nqptp` 1.2.4（smi10，与本版本不兼容）。想要 5.x 只能靠这里。
2. **音频功能门控经历了三代变化**，写死任何一种都会让包在另一类树上“消失”：
   | 树 | 门控形式 |
   | --- | --- |
   | 24.10 及更早 | kconfig 符号 `AUDIO_SUPPORT` |
   | 部分 snapshot | 二者都没有（过渡期） |
   | 当前 master | 真实包 `audio-support` / `video-support` |
   Makefile 用 `sound.mk` 是否引用 `AUDIO_SUPPORT` 判断代际，**检测不到就不加门控**——门控解析失败会让 OpenWrt 直接把包从元数据里丢掉，menuconfig 里连报错都没有。
3. **ffmpeg 重构**：master 的 `libffmpeg-full` 已改名为 `libffmpeg`，靠 `PROVIDES:=libffmpeg-full` 保持旧名兼容，因此依赖写法不用改。
4. **`FFMPEG_LIBDRM` 默认开启**：其依赖链 `libffmpeg → libdrm → video-support` 会给 airplay2 附加条件 `(!FFMPEG_LIBDRM || PACKAGE_video-support)`，条件不满足时条目被隐藏。树里存在 `hardware-support` 包时自动 `+video-support` 抵消。
5. **包格式变了**：master 用 **apk**（产物 `.apk`），24.10 用 **opkg**（产物 `.ipk`）。

## 方式一：作为 feed 编译（推荐）

```sh
cd <openwrt 源码树>

# 1. 准备 feeds.conf：已有就跳过；追加，不要覆盖
[ -f feeds.conf ] || cp feeds.conf.default feeds.conf
grep -q 'src-git airplay2' feeds.conf || \
  echo 'src-git airplay2 https://github.com/NetForgeCN/luci-app-airplay2.git;main' >> feeds.conf
cat feeds.conf      # 应为 5 行：4 个官方 feed + airplay2

# 2. 拉取并安装（-p 指定从本 feed 取 nqptp，避免与官方 1.2.4 混淆）
./scripts/feeds update -a
./scripts/feeds install -a
./scripts/feeds uninstall nqptp
./scripts/feeds install -p airplay2 airplay2 nqptp luci-app-airplay2

# 3. 关键前置：关掉 ffmpeg 的 DRM（详见「常见问题 3」，不做这一步菜单里根本没有 airplay2）
sed -i '/^CONFIG_FFMPEG_LIBDRM/d' .config
echo '# CONFIG_FFMPEG_LIBDRM is not set' >> .config
make defconfig

# 4. 选包并编译
make menuconfig
#   Sound                    -> <*> airplay2
#   LuCI -> 3. Applications  -> <*> luci-app-airplay2   （显示的是标题，字母序在 L 区）
make -j$(nproc)
```

产物：master 在 `bin/packages/<架构>/airplay2/*.apk`，24.10 在 `.../*.ipk`。

## 方式二：直接放进 package/

```sh
cd package/
git clone https://github.com/NetForgeCN/luci-app-airplay2.git
cd ..
make menuconfig && make -j$(nproc)
```

`package/` 下的包属于 core 级别，天然优先于所有 feed；但若之前 `feeds install` 过官方 nqptp，先 `./scripts/feeds uninstall nqptp` 清掉同名的那份。

## 方式三：用 CI / SDK 编译

CI（`.github/workflows/build-packages.yml`）直接在 `ghcr.io/openwrt/sdk:<arch>-SNAPSHOT` 容器里构建：

- snapshot 镜像**不自带 SDK**，需要先跑镜像里的 `setup.sh` 下载解压
- `feeds install` 不会改 `.config`，必须显式写入 `CONFIG_PACKAGE_airplay2=y` 等，否则 `make package/xxx/compile` 会静默跳过
- 产物是 `.apk`，上传时按目录取，不要写 `*.ipk`

## 在已装好的设备上安装

### master（apk）

Releases 里的文件名带架构后缀（`x86_64` / `aarch64_generic`）：

```sh
# 电脑上
scp nqptp-1.2.9-r1_<arch>.apk airplay2-5.6.2-r1_<arch>.apk \
    luci-app-airplay2-1.0.0-r1.apk luci-i18n-airplay2-zh-cn.apk root@<IP>:/tmp/

# 路由器上
apk update
cd /tmp
apk add --allow-untrusted ./nqptp-1.2.9-r1_<arch>.apk ./airplay2-5.6.2-r1_<arch>.apk \
    ./luci-app-airplay2-1.0.0-r1.apk ./luci-i18n-airplay2-zh-cn.apk
```

自己编译的包没有签名，必须加 `--allow-untrusted`。

### 24.10 / 23.05（opkg）

```sh
opkg update
cd /tmp
opkg install nqptp_1.2.9-r1_<架构>.ipk airplay2_5.6.2-r1_<架构>.ipk luci-app-airplay2_1.0.0-r1_all.ipk
```

### 两者共通

```sh
nqptp -V                     # 必须显示 smi11
/etc/init.d/nqptp enable && /etc/init.d/nqptp start
/etc/init.d/airplay2 enable && /etc/init.d/airplay2 start
```

然后 LuCI → 服务 → Airplay 2 里配置输出设备与名称。

提示：

- 依赖（libffmpeg、libavahi、libsodium 等）会自动从官方源安装，flash 紧张的小内存设备注意容量（约 3-5 MB）
- 不要只升 airplay2 而保留旧的 nqptp：smi 版本不匹配时 AirPlay 2 无声

## 常见问题：menuconfig 里看不到 / 选不上 airplay2

按顺序排查。

### 1. 门控解析失败（最常见）

airplay2 的 `DEPENDS` 里若带了一个该树无法解析的门控（`@AUDIO_SUPPORT` 或 `audio-support` 包），OpenWrt 会**直接把包从元数据中丢弃**，menuconfig 里既不显示也不报错。本仓库已做代际检测，正常情况下不会踩到；若你改过 Makefile，检查：

```sh
grep -c 'PACKAGE_airplay2$' tmp/.config-package.in   # 为 0 就是被丢弃了
```

### 2. `feeds.conf` 缺官方 feed 或被覆盖

`feeds.conf.default` 原样是 4 行官方 feed，airplay2 只能 `>>` 追加。只剩一行 airplay2 时，`libffmpeg`、`alsa-lib`、`luci-base` 全部解析不到。修复：

```sh
git checkout feeds.conf.default
cp feeds.conf.default feeds.conf
```

### 3. 菜单里看不到，但搜索能搜到（`FFMPEG_LIBDRM`）

**这是 master 上最常见的现象**：按 `/` 能搜到 `luci-app-airplay2`，回到菜单里却怎么都找不到。

原因：`PACKAGE_luci-app-airplay2` 的 kconfig 里带了一条条件

```
Depends on: (!FFMPEG_LIBDRM [=y] || PACKAGE_video-support [=y]) && ...
```

来源是 `airplay2 → libffmpeg-full → libdrm`，而 `libdrm` 写的是 `DEPENDS:=video-support`；OpenWrt 会把这条条件传播给所有 `libffmpeg` 使用者。master 上 `FFMPEG_LIBDRM` **默认 y**，`video-support` 默认 n，条件不成立 → **条目存在但被隐藏**（搜索仍能搜到，因为符号确实生成了）。菜单里选不上，也就没法通过选它来自救——这是条件依赖的“鸡生蛋”问题，必须先改 `.config`。

判定（看当前取值，一条命令）：

```sh
grep -E '^(# )?CONFIG_(FFMPEG_LIBDRM|PACKAGE_video-support)' .config
# 出现 CONFIG_FFMPEG_LIBDRM=y 且没有 CONFIG_PACKAGE_video-support=y，就是本条
# （kconfig 文本里那句 depends on 是常驻的，要看取值而不是看有没有那行）
```

修复（`make menuconfig` **之前**做，二选一）：

```sh
# A. 纯音频设备用不到 DRM，关掉最干净（推荐）
sed -i '/^CONFIG_FFMPEG_LIBDRM/d' .config
echo '# CONFIG_FFMPEG_LIBDRM is not set' >> .config
make defconfig
```

```sh
# B. 固件里其它组件需要 DRM：保留 ffmpeg 的 DRM，改选 video-support
sed -i '/^CONFIG_PACKAGE_video-support[= ]/d' .config
echo 'CONFIG_PACKAGE_video-support=y' >> .config
make defconfig
```

改完再进 `make menuconfig`，`Sound` 和 `LuCI → 3. Applications` 里都能看到了。本仓库的 `airplay2` 在树里有 `hardware-support` 包时会自动 `+video-support`，所以非交互构建（直接写 `.config` + `make`）不受影响，只有手工 menuconfig 需要这一步。

### 4. 依赖会自动带出吗

`airplay2` 选中后自动带出 `nqptp`、`libffmpeg-full`、`alsa-lib`、`libopenssl`、`libavahi-client`、`libsoxr`、`libplist`、`libsodium`、`libgcrypt`、`libmosquitto`、`libconfig`、`libpopt`、`libuuid`。`luci-app-airplay2` 是独立应用包，需要手选（`LuCI → 3. Applications`）。

## 从 4.3.x 升级的注意点

- shairport-sync 5.0 起配置文件格式有较大变化（多声道、`alac_decoder` 默认改为 ffmpeg 等），见上游 [CONFIGURATIONFILECHANGES5.md](https://github.com/mikebrady/shairport-sync/blob/5.6.2/CONFIGURATIONFILECHANGES5.md)
- LuCI 的 UCI 选项已逐项核对，在 5.6.2 下仍全部有效
- 装过旧版 `airplay2-mbedtls` / `airplay2-mini` 的，先卸载再装 `airplay2`

## 构建细节（维护者参考）

- plist 代码生成补丁：`airplay2/patches/100-plist-codegen-without-host-tools.patch`，用构建主机的 python3 生成 AirPlay 2 的二进制 plist，不需要 `plistutil` / `xxd`
- 上游 `plists/get_info_response.xml` 自带一个多余的 `</dict>`，补丁已做兼容
- `PKG_BUILD_DIR` 需手设为 `$(BUILD_DIR)/shairport-sync-$(PKG_VERSION)`（源码包解压目录名与 `PKG_NAME` 不一致）
- nqptp 的 init 为 `START=98`（先于 airplay2 的 99）并带 respawn
- shairport-sync 5.x 无法在 mbed TLS 下构建 `--with-airplay-2`，因此只保留 OpenSSL 单一构建
