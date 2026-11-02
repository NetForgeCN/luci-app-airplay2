# luci-app-airplay2 (shairport-sync)

AirPlay 2 is a simple and easy-to-use AirPlay audio player.

Upstream: <https://github.com/mikebrady/shairport-sync>

## Packages in this feed

| Package | Description |
| --- | --- |
| `airplay2` | shairport-sync 5.6.2（OpenSSL / AirPlay 2），installed as `/usr/bin/airplay2` |
| `luci-app-airplay2` | LuCI 界面 |
| `nqptp` | AirPlay 2 时间同步伴侣程序（1.2.9，smi11） |

## 只有 openssl（AirPlay 2）一种构建

shairport-sync 5.x 在 mbedtls 下**无法**编译 `--with-airplay-2`（CI 实测确认会直接
构建失败），而 5.x 时代 mbedtls/mini 变体只剩 AirPlay 1 一条路，对本仓库没有意义。
因此本仓库直接砍掉 `airplay2-mbedtls` 和 `airplay2-mini`，只保留** openssl 单一
构建**（含 AirPlay 2），这也是上游 OpenWrt packages feed 的做法（AirPlay 2 仅限
openssl 变体）。

`opkg install airplay2` 装到的就是带 AirPlay 2 的版本，`luci-app-airplay2` 的依赖
同样指向它。如果你设备上之前装过 `airplay2-mbedtls` / `airplay2-mini`，升级前请先
`opkg remove` 掉它们再装 `airplay2`。

## 重要：nqptp 必须 >= 1.2.9

shairport-sync 5.6.x 使用共享内存接口版本 **smi11**（`NQPTP_SHM_STRUCTURES_VERSION 11`），
只有 **nqptp 1.2.9 及以上**提供该版本。OpenWrt packages feed 中的 nqptp 1.2.4 只提供
smi10，与 5.x 不兼容——表现是 AirPlay 2 无法建立同步、没有声音。

因此本仓库自带一份 nqptp 1.2.9。安装时请同时安装本仓库构建的 `nqptp` ipk，
并确认设备上的版本：

```sh
nqptp -V
# Version: 1.2.9. Shared Memory Interface Version: smi11.
```

不要只升级 airplay2 而保留旧的 nqptp。

## 构建

AirPlay 2 的代码生成步骤需要把 `plists/get_info_response.xml` 转成二进制 plist 再写成
C 数组，上游用的是主机上的 `plistutil` 和 `xxd`。这两个程序在交叉编译环境（以及
OpenWrt feed 的 libplist——它没有 host 构建）中都没有，因此本仓库打了补丁
（`airplay2/patches/100-plist-codegen-without-host-tools.patch`），改用构建主机上的
**python3** 生成；如果主机同时装了 plistutil 和 xxd，仍然会走上游原始流程。

## 从 4.3.x 升级的注意点

- shairport-sync 5.0 起配置文件格式有较大变化（多声道、`alac_decoder` 默认改为 ffmpeg、
  `pw`/`pa` 段分别改名为 `pipewire`/`pulseaudio` 等），详见上游
  [CONFIGURATIONFILECHANGES5.md](https://github.com/mikebrady/shairport-sync/blob/5.6.2/CONFIGURATIONFILECHANGES5.md)。
- LuCI 现有的 UCI 选项在 5.6.2 下已核对过，仍然全部有效（`diagnostics.log_output_to`
  已被上游标记为废弃，只会打印一条警告，不影响启动）。
