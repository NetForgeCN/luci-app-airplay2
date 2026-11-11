# luci-app-airplay2 (shairport-sync)

OpenWrt 上的 AirPlay / AirPlay 2 音频接收器，带 LuCI 界面。

- 上游：<https://github.com/mikebrady/shairport-sync>
- 当前版本：**shairport-sync 5.6.3 + nqptp 1.2.9**（OpenSSL 构建，含 AirPlay 2）
- 支持：OpenWrt master / snapshot（apk）与 24.10 / 23.05（opkg）
- 现成安装包：<https://github.com/NetForgeCN/luci-app-airplay2/releases>
  - `v5.1.0`：master / snapshot 的 `.apk`
  - `v5.0.0`：24.10 / 23.05 的 `.ipk`

## 本仓库提供的包

| 包 | 说明 |
| --- | --- |
| `airplay2` | shairport-sync 5.6.2，装为 `/usr/bin/airplay2`，OpenSSL + AirPlay 2 |
| `nqptp` | AirPlay 2 时间同步伴侣（1.2.9，smi11） |
| `luci-app-airplay2` | LuCI 界面（含中文翻译） |

## 分支

| 分支 | 用途 |
| --- | --- |
| `main` | 主线，同一份 Makefile 自适应 master 与 24.10/23.05 |
| `openwrt-24.10` | 24.10 旧版快照（硬编码 `@AUDIO_SUPPORT`），仅用于锁定旧行为 |

## 为什么需要单独的 feed

官方 feed 里没有能直接用的组合：

1. master 的 packages feed 已不含 shairport-sync；自带的 nqptp 是 1.2.4（smi10），与 5.x 要求的 smi11 不兼容，装了也出不了声。
2. 音频门控换过三代：24.10 是 kconfig 符号 `AUDIO_SUPPORT`，过渡期两者都没有，现在 master 是 `audio-support` / `video-support` 真实包。Makefile 检测代际后自适应，检测不到就不加门控——门控解析失败会让 OpenWrt **静默丢弃整个包**，menuconfig 里连报错都没有。
3. master 用 apk（`.apk`），24.10 用 opkg（`.ipk`）。

## 安装

### 方式一：作为 feed 编译（推荐）

```sh
cd <openwrt 源码树>

# feeds.conf 只能追加，不要覆盖（覆盖掉官方 feed 会导致依赖全部解析不到）
[ -f feeds.conf ] || cp feeds.conf.default feeds.conf
grep -q 'src-git airplay2' feeds.conf || \
  echo 'src-git airplay2 https://github.com/NetForgeCN/luci-app-airplay2.git;main' >> feeds.conf

./scripts/feeds update -a
./scripts/feeds install -a
./scripts/feeds uninstall nqptp                      # 清掉官方那份 1.2.4
./scripts/feeds install -p airplay2 airplay2 nqptp luci-app-airplay2

make menuconfig
#   Sound                    -> <*> airplay2
#   LuCI -> 3. Applications  -> <*> luci-app-airplay2
make -j$(nproc)
```

产物：master 在 `bin/packages/<架构>/airplay2/*.apk`，24.10 是 `*.ipk`。

> master 上如果按 `/` 能搜到 `airplay2`、菜单里却看不见，先补 `CONFIG_PACKAGE_video-support=y` 再进 menuconfig，见「排障 · menuconfig」。

### 方式二：直接放进 package/

```sh
cd package/
git clone https://github.com/NetForgeCN/luci-app-airplay2.git
cd ..
make menuconfig && make -j$(nproc)
```

`package/` 下的包属于 core 级别，天然优先于所有 feed；但若之前 `feeds install` 过官方 nqptp，先 `./scripts/feeds uninstall nqptp` 清掉同名的那份。

### 方式三：用 CI / SDK 编译

`.github/workflows/build-packages.yml` 直接在 `ghcr.io/openwrt/sdk:<arch>-SNAPSHOT` 容器里构建：

- snapshot 镜像**不自带 SDK**，需要先跑镜像里的 `setup.sh` 下载解压
- `feeds install` 不会改 `.config`，必须显式写入 `CONFIG_PACKAGE_airplay2=y` 等，否则 `make package/xxx/compile` 会静默跳过却报成功
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

- 依赖（libffmpeg、libavahi、libsodium 等）会自动从官方源安装，flash 紧张的小内存设备注意容量（约 3-5 MB）
- 不要只升 airplay2 而保留旧的 nqptp：smi 版本不匹配时 AirPlay 2 连得上但没声音

## 配置要点（LuCI → 服务 → Airplay 2）

| 项 | 建议 |
| --- | --- |
| ALSA 输出设备 | 选具体的 `hw:N`，**不要用「默认」**（它指向 card 0，在有板载声卡的机器上往往不是你要的那块） |
| ALSA 混音器控制名称 | 先看 `amixer -c N scontrols`，能列出来才填 `PCM`/`Speaker`；没有硬件混音器的 DAC（如 UAC1 的 SA9023）**必须留空**，填了会打开失败、整条链路无声 |
| 端口 | AirPlay 2 用 **7000**（AirPlay 1 才是 5000）。改完 `restart`，用 `netstat -lntp \| grep 7000` 确认真的换了 |
| 名称 | 支持 `%v`（版本）、`%h`（主机名），`AirPlay2-%v-%h` 即可 |

## 排障

顺序永远是：**有声卡 → 能出声 → 能投射**。跳步只会分不清问题在哪一层。

### 1. 没有声卡（`--- no soundcards ---`）

```sh
cat /proc/asound/cards
aplay -l
```

先分清“驱动没装”还是“设备没枚举”：

```sh
find /lib/modules -name 'snd-usb-audio*'
lsmod | grep snd
ls /sys/bus/usb/devices/
```

| 看到什么 | 判断 |
| --- | --- |
| 只有 `usb1`、`usb2`、`2-1`、`2-1:1.0` 这种节点 | 没有外部 USB 设备枚举成功，**不是驱动问题** |
| `2-1` 且 `idVendor=8087`、`idProduct=8000` | 这是主板内置的 Intel Rate Matching Hub（dmesg 里有 `hub 2-1:1.0: 8 ports detected`），**不是你的音箱**；真实设备是 `2-1.2`、`1-1` 这种带点的子节点 |
| 驱动在、设备也在，但还是没有卡 | `modprobe snd-usb-audio`，再看 `dmesg \| tail` |

音箱没枚举时先换口（后置直连主板，别用前置面板/延长线）、换**数据线**——大量“USB 音箱”配的是纯供电线（只有 VBUS/GND），插上永远不枚举。插个 U 盘到同一口可立刻区分是口坏了还是线的问题。若音箱另有 3.5mm 或蓝牙，它的 USB 很可能只供电。

x86 想用机箱后的 3.5mm，还需要 HDA（`kmod-usb-audio` 只管 USB 声卡）：

```
CONFIG_PACKAGE_kmod-snd-hda-intel=y
CONFIG_PACKAGE_kmod-snd-hda-codec-realtek=y
CONFIG_PACKAGE_kmod-snd-hda-codec-hdmi=y
```

### 2. 有声卡但放不出声

```sh
cat /proc/asound/cards                      # 记下编号
amixer -c 0 scontrols                       # 混音器真实名字
amixer -c 0 sset Master 80% unmute
head -c 1000000 /dev/urandom | aplay -D plughw:0 -t raw -f S16_LE -r 48000 -c 2
```

`aplay` 打白噪声不需要任何音频文件（OpenWrt 的 `alsa-utils` 不一定带 `speaker-test`）。能听到“沙沙”声，才说明硬件链路通了，这时再去调 airplay2。

### 3. 手机连上但声音还在手机里 / 电脑点一下灰掉再恢复

这就是 airplay2 最后写 ALSA 失败：设备名不对或打不开。

```sh
cat /proc/asound/cards
uci set airplay2.@airplay2[0].alsa_output_device='hw:0'
uci set airplay2.@airplay2[0].alsa_mixer_control_name=''
uci commit airplay2 && /etc/init.d/airplay2 restart
logread -f | grep -iE 'airplay2|shairport|nqptp|alsa'
```

排完设备仍无声，再依次确认：

- `nqptp -V` 必须是 `smi11`（1.2.4 的 smi10 不行）
- `airplay2 -h | head -6` 不能出现 `IMPORTANT NOTE`（出现即缺 fltp AAC，AirPlay 2 不可用）
- 端口 7000 在 `LISTEN`，且与界面里填的一致
- 隔离定位：`airplay2 -c /var/etc/airplay2-airplay2.conf --service-type=classic -v`，AirPlay 1 有声、AirPlay 2 没声就集中查前两条

### 4. menuconfig 里搜得到、菜单里看不到

master 上 `FFMPEG_LIBDRM` 默认 y，而 `libdrm` 依赖 `video-support`，这条条件会传播给所有 libffmpeg 使用者（包括 `luci-app-airplay2`）：条件不满足时条目存在但被隐藏。`make menuconfig` **之前**补一行即可：

```sh
sed -i '/^CONFIG_PACKAGE_video-support[= ]/d' .config
echo 'CONFIG_PACKAGE_video-support=y' >> .config
make defconfig
```

一定要连 `video-support` 一起处理：只关 `FFMPEG_LIBDRM` 会被 `FFMPEG_V4L2_REQUEST`（`default y` 且 `select` 它）在 defconfig 时弹回 y。`make defconfig` 打印 qt5 / fwknop / squeezelite 的 `recursive dependency` 是这些 feed 自身的既有问题，与本包无关。

## 上游更新（自动）

`.github/workflows/upstream-check.yml` 每天检查一次 shairport-sync 与 nqptp 的新 tag：

- 有更新 → 改写 `PKG_VERSION` / `PKG_HASH` / `PKG_RELEASE`，同步本文件顶部的版本号，推 `chore/upstream-bump` 分支并开 PR，再派发一次 `Build packages` 做编译验证
- 没有更新 → 什么都不做，不产生空提交
- PR 正文会列出两个包的 SMI 版本；不一致时显著提示——这是最容易漏、又必然导致“连得上但没声音”的地方

逻辑在 `scripts/check_upstream.py`，本地也能跑：

```sh
python3 scripts/check_upstream.py --dry-run     # 只看结果，不改文件
python3 scripts/check_upstream.py               # 直接改 Makefile
python3 scripts/check_upstream.py nqptp         # 只查某个包
```

## 从 4.3.x 升级

- shairport-sync 5.0 起配置文件格式有较大变化（多声道、`alac_decoder` 默认改为 ffmpeg 等），见上游 [CONFIGURATIONFILECHANGES5.md](https://github.com/mikebrady/shairport-sync/blob/5.6.2/CONFIGURATIONFILECHANGES5.md)
- LuCI 的 UCI 选项已逐项核对，在 5.6.2 下仍全部有效
- 装过旧版 `airplay2-mbedtls` / `airplay2-mini` 的，先卸载再装 `airplay2`

## 构建细节（维护者参考）

- plist 代码生成补丁：`airplay2/patches/100-plist-codegen-without-host-tools.patch`，用构建主机的 python3 生成 AirPlay 2 的二进制 plist，不需要 `plistutil` / `xxd`
- 上游 `plists/get_info_response.xml` 自带一个多余的 `</dict>`，补丁已做兼容
- `PKG_BUILD_DIR` 需手设为 `$(BUILD_DIR)/shairport-sync-$(PKG_VERSION)`（源码包解压目录名与 `PKG_NAME` 不一致）
- nqptp 的 init 为 `START=98`（先于 airplay2 的 99）并带 respawn
- shairport-sync 5.x 无法在 mbed TLS 下构建 `--with-airplay-2`，因此只保留 OpenSSL 单一构建
