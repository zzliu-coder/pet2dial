# Pet2Dial

把 Codex Desktop 的宠物刷到 M5Stack Dial 或 LilyGO T-Encoder Pro 上，让它变成一个桌面外置宠物和旋钮式任务遥控器。

Pet2Dial 是一个 Codex skill、圆屏设备固件和 macOS BLE bridge 组成的开源项目。它读取你在 Codex 中当前选中的 custom pet，把官方 `spritesheet.webp` 动画图集转换成设备固件资源，再通过 Bluetooth Low Energy 持续同步 Codex 的宠物状态、任务卡片和状态计数。

![Pet2Dial running on M5Stack Dial](docs/images/pet2dial-on-m5stack-dial.jpg)

## 核心亮点

- **外置 Codex pet**：Dial 显示的是你 Codex 当前选中的 custom pet，来源是本机 `~/.codex/pets` 和 Codex 配置。
- **沿用官方动画体系**：保留 Codex pet 的 9 行动画语义：`idle`、`running-right`、`running-left`、`waving`、`jumping`、`failed`、`waiting`、`running`、`review`。
- **状态名不分叉**：Dial payload 只使用 Codex pet 状态名，长期优先级是 `waiting > failed > review > running > idle`。
- **多任务状态并存**：宠物动画显示最高优先级状态，同时用两排计数显示 `W# F#` / `V# R#`，适合多个 Codex 线程同时运行。
- **四态任务卡片**：旋转 Dial 浏览 `WAITING`、`FAILED`、`REVIEW`、`RUNNING` 卡片，点击卡片打开对应的 `codex://threads/<thread_id>`。
- **review 不被历史污染**：首次启动会把历史完成任务设为 baseline，之后只显示新的完成 turn；同一会话后续完成新 turn 会再次出现 review。
- **双硬件目标**：默认支持 M5Stack Dial，也支持 LilyGO T-Encoder Pro；两者共享同一个 BLE 协议、bridge 和 Codex 状态模型。
- **USB 只负责刷机**：固件刷入后，日常状态同步走 BLE，Mac 不需要一直插着 USB。
- **macOS 后台服务**：可安装 LaunchAgent，并通过生成的 `CodexDialBridge.app` 处理蓝牙权限，后台运行时不占 Dock。
- **Codex 升级可检查**：`codex-compat` 会生成本机兼容性快照，帮助判断 Codex 升级后 pet atlas、session 事件或 app bundle 是否发生漂移。
- **开源友好边界**：项目不提交用户本地宠物图片、Codex 会话日志、seen 状态、compat 快照或私有配置。

## 它解决什么问题

Codex Desktop 已经有宠物模式，但它仍然属于屏幕里的 UI。Pet2Dial 把这个状态面板移到桌面硬件上，让 AI coding workspace 多一个常亮、可触摸、可旋转的物理入口。

典型使用场景：

- 同时跑多个 Codex 任务时，一眼看到当前是否 `running`、`waiting`、`failed` 或有待 `review` 输出。
- 用旋钮切换任务卡片，减少在桌面窗口之间来回找会话。
- 点击 Dial 直接回到对应 Codex 线程。
- 保留 Codex 原生宠物的视觉语言，让硬件端看起来像 Codex pet 的外置镜像。

## 支持范围

当前成功路径以 macOS 为基准：

- macOS
- Codex Desktop
- M5Stack Dial（M5StampS3）或 LilyGO T-Encoder Pro
- Python 3.10+
- PlatformIO
- USB-C 线，用于首次刷固件
- Bluetooth Low Energy，用于日常同步

Windows 和 Linux 目前没有适配和验证。要支持 Windows，至少需要重新处理：

- Codex home 路径发现，macOS 默认是 `~/.codex`
- BLE bridge 权限和后台运行方式
- 串口发现逻辑，macOS 默认看 `/dev/cu.usbmodem*`
- `codex://threads/<thread_id>` 的打开方式
- 后台服务机制，macOS 当前使用 LaunchAgent
- Codex Desktop 安装路径和 app bundle 检查方式

我没有 Windows 环境，所以这个仓库当前不承诺 Windows 可用。欢迎基于同一 wire contract 做 Windows bridge 适配。

## 快速开始：M5Stack Dial

克隆仓库后，在仓库根目录运行：

```bash
python3 skill/pet2dial/scripts/pet2dial.py doctor
python3 skill/pet2dial/scripts/pet2dial.py init --force
python3 skill/pet2dial/scripts/pet2dial.py setup-env
python3 skill/pet2dial/scripts/pet2dial.py convert
python3 skill/pet2dial/scripts/pet2dial.py build
python3 skill/pet2dial/scripts/pet2dial.py upload
python3 skill/pet2dial/scripts/pet2dial.py run-bridge
```

如果 Dial 已经通过 USB 接上 Mac，可以直接跑完整成功路径：

```bash
python3 skill/pet2dial/scripts/pet2dial.py success-path --upload
```

日常使用建议安装后台服务：

```bash
python3 skill/pet2dial/scripts/pet2dial.py install-autostart
python3 skill/pet2dial/scripts/pet2dial.py status
python3 skill/pet2dial/scripts/pet2dial.py logs
```

默认生成的工作项目位置：

```text
~/CodexDialPet
```

## 快速开始：LilyGO T-Encoder Pro

LilyGO T-Encoder Pro 使用同一套 Codex pet 转换、BLE bridge、LaunchAgent 和任务卡片协议。差异在固件层：CO5300 390x390 圆屏、CST816 touch、物理编码器、U8g2 CJK 字体和 LilyGO board support。

推荐生成项目位置：

```text
~/CodexTEncoderPet
```

首次安装：

```bash
python3 skill/pet2dial/scripts/pet2dial.py --target t-encoder-pro --project ~/CodexTEncoderPet init --force
python3 skill/pet2dial/scripts/pet2dial.py --target t-encoder-pro --project ~/CodexTEncoderPet setup-env
python3 skill/pet2dial/scripts/pet2dial.py --target t-encoder-pro --project ~/CodexTEncoderPet setup-board
python3 skill/pet2dial/scripts/pet2dial.py --target t-encoder-pro --project ~/CodexTEncoderPet convert
python3 skill/pet2dial/scripts/pet2dial.py --target t-encoder-pro --project ~/CodexTEncoderPet build
python3 skill/pet2dial/scripts/pet2dial.py --target t-encoder-pro --project ~/CodexTEncoderPet upload
python3 skill/pet2dial/scripts/pet2dial.py --target t-encoder-pro --project ~/CodexTEncoderPet install-autostart
```

如果 LilyGO T-Encoder Pro 已经通过 USB 接上 Mac，可以直接跑完整成功路径：

```bash
python3 skill/pet2dial/scripts/pet2dial.py --target t-encoder-pro --project ~/CodexTEncoderPet success-path --upload
```

`setup-board` 会把 LilyGO 的 T-Encoder Pro vendor 支持包拉到生成项目里：

```text
~/CodexTEncoderPet/vendor/T-Encoder-Pro
```

这个 vendor 目录很大，仓库只记录来源和锁定 commit：

```text
https://github.com/Xinyuan-LilyGO/T-Encoder-Pro.git
5f5c3bf6a714991001d385ca8c13ca75a41c5a98
```

LilyGO T-Encoder Pro 详细说明见：

```text
docs/boards/t-encoder-pro.md
```

`run-bridge` 和 `install-autostart` 会自动修复生成工程、虚拟环境和缺失 Python 依赖。macOS 上 bridge 会通过生成的 `CodexDialBridge.app` 启动，让系统用标准隐私模型授予蓝牙权限。

## 作为 Codex Skill 使用

把 skill 安装到：

```text
~/.codex/skills/pet2dial
```

或者把本仓库里的 skill 目录作为源：

```text
skill/pet2dial
```

然后在 Codex 里说：

```text
Use pet2dial to put my current Codex pet on my M5Stack Dial.
```

Skill 会检查环境、创建干净项目、安装依赖、转换宠物图集、构建固件、上传到 Dial，并启动 BLE bridge。

## 官方宠物状态模型

Pet2Dial 的目标是做 Codex pet 的外置镜像。设备端只接受 Codex pet 状态名：

```text
0 idle           空闲
1 running-right 旋钮向前切换任务卡片时的临时动画
2 running-left  旋钮向后切换任务卡片时的临时动画
3 waving        BLE 连接或唤醒类本地事件后的临时动画
4 jumping       点击宠物大图时的临时互动
5 failed        Codex turn_aborted / task_failed / task_cancelled
6 waiting       等待审批、权限、用户输入，或 BLE 断开时的设备等待态
7 running       Codex 正在运行
8 review        新完成、尚未在 Dial 上读过的 Codex turn
```

长期状态优先级：

```text
waiting > failed > review > running > idle
```

当前开源版本默认使用保守的 rollout fallback：读取本机 Codex session JSONL，只输出官方状态名。`task_complete` 映射到 `review`，结构化等待事件如 `approval_request`、`request_user_input` 映射到 `waiting`。如果 Codex 后续提供稳定外部状态 API，新的状态源可以接入同一套 wire contract。

## UI 与交互

宠物大图视图保持宠物可见，顶部显示两排紧凑状态计数：

```text
W#  F#
V#  R#
```

计数含义：

- `W` = waiting
- `F` = failed
- `V` = review
- `R` = running

宠物本体播放最高优先级的长期状态动画。没有单独的主文字标签。

交互规则：

- 点击宠物大图：宠物 `jumping`，随后回到长期状态。
- 旋钮向前切卡：`running-right`，短暂播放后回到长期状态。
- 旋钮向后切卡：`running-left`，短暂播放后回到长期状态。
- 卡片视图点击屏幕：打开当前 Codex 会话。
- BLE 连接或唤醒类本地事件：短暂 `waving`。

旋转 Dial 会进入任务卡片视图。宠物缩小，卡片展示当前选中的 Codex 会话。卡片标签使用完整状态名：`WAITING`、`FAILED`、`REVIEW`、`RUNNING`。

BLE 事件协议很小：

```text
CLICK|<thread_id>  打开 Codex 会话
LEAVE|<thread_id>  把已打开的 review turn 标记为 seen
```

## 任务卡片与 review 语义

Dial 卡片会显示四类任务：

- `waiting`：等待审批、权限、用户输入或计划确认
- `failed`：失败、取消、异常中断
- `review`：新完成、尚未在 Dial 上读过的 turn
- `running`：正在运行的 Codex 会话

历史完成任务的处理规则：

- 首次启动或从旧 seen 状态升级时，当前历史 `task_complete` 会进入 baseline。
- baseline 内的旧完成任务不会挤满 Dial。
- 新出现的 completed turn 会显示为 `review`。
- 同一个 thread 后续完成新 turn，会再次显示为新的 review。
- 点击 review 卡片只表示“打开”；离开卡片后才标记为 seen。

手动清空当前 review backlog：

```bash
python3 skill/pet2dial/scripts/pet2dial.py clear-review-backlog
```

## 宠物图集转换

Pet2Dial 使用 Codex compatible custom pet：

```text
~/.codex/pets/<pet-id>/pet.json
~/.codex/pets/<pet-id>/spritesheet.webp
```

`--pet` 省略时，`auto` 会优先读取 Codex 当前选中的 custom pet：

```text
selected-avatar-id = "custom:<pet-id>"
```

旧的 first-awake UI 历史只作为 fallback。

Codex pet atlas 输入规格：

```text
1536x1872 atlas
192x208 cells
8 columns
9 animation rows
```

Dial 固件资源规格：

```text
single pet
96x96 frames
8 frames per row
9 rows
RGB565
```

## Codex 兼容性检查

Codex 升级后，pet atlas、session 事件、app bundle 或 URL handler 都可能变化。运行：

```bash
python3 skill/pet2dial/scripts/pet2dial.py codex-compat
```

它会检查：

- macOS baseline
- Codex home 和 sessions 是否存在
- 当前 selected custom pet
- pet package 和 atlas 几何
- Codex.app 版本与 `app.asar` hash
- 近期 rollout JSONL 里的事件类型
- 与上一次本机兼容性快照的差异

本地快照写入：

```text
~/CodexDialPet/state/codex_compat_snapshot.json
```

这个文件是本机诊断状态，不应该提交到仓库。公开契约见：

```text
skill/pet2dial/references/codex-compatibility.md
```

## 项目结构

```text
SKILL.md                                      Codex skill 入口
skill/pet2dial/scripts/pet2dial.py           一站式 setup/build/upload/bridge 命令
skill/pet2dial/templates/project/firmware    M5Stack Dial PlatformIO 固件
skill/pet2dial/templates/t-encoder-pro       T-Encoder Pro PlatformIO 固件 overlay
skill/pet2dial/templates/project/codex_dial_bridge
                                             Mac 端 BLE bridge
skill/pet2dial/templates/project/tools       Codex pet atlas 转换工具
skill/pet2dial/references/success-contract.md
                                             成功路径和固定默认值
skill/pet2dial/references/codex-compatibility.md
                                             Codex 兼容性契约与升级检查说明
docs/hackster                                Hackster 发布文案
docs/boards                                  硬件目标说明
```

## 诊断命令

查看环境：

```bash
python3 skill/pet2dial/scripts/pet2dial.py doctor
```

检查 Codex 兼容性：

```bash
python3 skill/pet2dial/scripts/pet2dial.py codex-compat
```

查看后台服务：

```bash
python3 skill/pet2dial/scripts/pet2dial.py status
```

查看 bridge 日志：

```bash
python3 skill/pet2dial/scripts/pet2dial.py logs
```

常见日志含义：

- `Could not find BLE device named 'CodexDial'`：Mac 暂时没有扫描到 Dial，bridge 会自动重试。
- `Service Discovery has not been performed yet`：BLE 连接刚建立或设备短暂重连时，GATT 服务尚未准备好，bridge 会断开并重连。
- `Sync pet=... mode=...`：Mac 已经把 Codex pet 和任务状态同步到 Dial。
- `Opened Codex URL codex://threads/...`：点击 Dial 卡片后，Codex URL handler 已被调用。

## 验证记录

当前版本验证过：

```text
quick_validate.py skill/pet2dial
python3 -m unittest discover -s skill/pet2dial/templates/project/tests
pet2dial.py codex-compat
pet2dial.py init
pet2dial.py setup-env
pet2dial.py convert
PlatformIO firmware build
T-Encoder Pro firmware build and USB upload
```

观察到的固件占用：

```text
RAM:   15.4%
Flash: 79.0%
```

## 当前边界

- 主要支持 macOS + Codex Desktop + M5Stack Dial / LilyGO T-Encoder Pro。
- 默认状态源是本地 rollout fallback，能够复刻官方状态名和优先级，但 waiting/review 精度受 Codex 外部可读状态限制。
- 固件首次上传需要 USB。
- 仓库不包含用户自己的 pet 图片、Codex 会话日志、seen 状态文件、本机 compat 快照、本机配置、PlatformIO 构建缓存或 T-Encoder vendor checkout。
- Windows/Linux 需要单独适配路径、BLE、后台服务、串口和 URL 打开机制。

## English Summary

Pet2Dial turns the selected Codex Desktop custom pet into a tiny external hardware companion on an M5Stack Dial or LilyGO T-Encoder Pro. It converts the official Codex pet atlas into firmware assets, flashes the device, and keeps pet/task state synchronized over Bluetooth Low Energy.

The current supported path is macOS-first: Codex Desktop, `~/.codex`, M5Stack Dial, a macOS BLE bridge, LaunchAgent background service, and `codex://threads/<thread_id>` navigation. Windows and Linux are not currently supported, but the BLE wire contract and Codex compatibility document are intended to make future ports possible.

## Contest Note

This project was built for the M5Stack Global Innovation Contest 2026. It uses an M5Stack controller product, was first prepared for Hackster publication in 2026, and includes both hardware and software documentation.

## License

MIT.
