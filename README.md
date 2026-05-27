# Pet2Dial

把 Codex Desktop 的宠物搬到 M5Stack Dial 上，让它变成一个桌面外置宠物和旋钮式任务遥控器。

Pet2Dial 是一个 Codex skill、M5Stack Dial 固件和 macOS BLE bridge 组成的开源项目。它读取你在 Codex 中当前选中的 custom pet，把官方 `spritesheet.webp` 动画图集转换成 Dial 固件资源，再通过 Bluetooth Low Energy 持续同步 Codex 的宠物状态、运行中任务和待 review 任务。

![Pet2Dial running on M5Stack Dial](docs/images/pet2dial-on-m5stack-dial.jpg)

## 核心亮点

- **外置 Codex pet**：Dial 显示的是你 Codex 当前选中的 custom pet，来源是本机 `~/.codex/pets` 和 Codex 配置。
- **沿用官方动画体系**：保留 Codex pet 的 9 行动画语义：`idle`、`running-right`、`running-left`、`waving`、`jumping`、`failed`、`waiting`、`running`、`review`。
- **状态名不分叉**：Dial payload 只使用官方宠物状态名，长期优先级沿用 `waiting > failed > running > review > idle`。
- **旋钮任务卡片**：旋转 Dial 浏览 Codex 会话卡片，点击屏幕打开对应的 `codex://threads/<thread_id>`。
- **review 不被历史污染**：首次启动会把历史完成任务设为 baseline，之后只显示新的完成 turn；同一会话后续完成新 turn 会再次出现 review。
- **USB 只负责刷机**：固件刷入后，日常状态同步走 BLE，Mac 不需要一直插着 USB。
- **macOS 后台服务**：可安装 LaunchAgent，并通过生成的 `CodexDialBridge.app` 处理蓝牙权限，后台运行时不占 Dock。
- **开源友好边界**：项目不提交用户本地宠物图片、Codex 会话日志、seen 状态或私有配置。

## 它解决什么问题

Codex Desktop 已经有宠物模式，但它仍然属于屏幕里的 UI。Pet2Dial 把这个状态面板移到桌面硬件上，让 AI coding workspace 多一个常亮、可触摸、可旋转的物理入口。

典型使用场景：

- 同时跑多个 Codex 任务时，一眼看到当前是否 `running`、`waiting`、`failed` 或有待 `review` 输出。
- 用旋钮切换任务卡片，减少在桌面窗口之间来回找会话。
- 点击 Dial 直接回到对应 Codex 线程。
- 保留 Codex 原生宠物的视觉语言，让硬件端看起来像 Codex pet 的外置镜像。

## 硬件与软件要求

- M5Stack Dial（M5StampS3）
- macOS
- Codex Desktop
- Python 3.10+
- PlatformIO
- USB-C 线，用于首次刷固件
- Bluetooth Low Energy，用于日常同步

M5Stack Dial 负责显示圆形 UI、读取旋钮和触摸输入，并作为 BLE peripheral 接收 Mac bridge 推送的状态。

## 快速开始

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

Pet2Dial 的目标是做 Codex pet 的外置镜像。设备端只接受官方状态名：

```text
0 idle           空闲
1 running-right 旋钮向前切换任务卡片时的临时动画
2 running-left  旋钮向后切换任务卡片时的临时动画
3 waving        BLE 连接或点击打开会话后的临时动画
4 jumping       新任务卡片出现时的临时动画
5 failed        Codex turn_aborted / task_failed / task_cancelled
6 waiting       等待审批、权限、用户输入，或 BLE 断开时的设备等待态
7 running       Codex 正在运行
8 review        新完成、尚未在 Dial 上读过的 Codex turn
```

长期状态优先级：

```text
waiting > failed > running > review > idle
```

当前开源版本默认使用保守的 rollout fallback：读取本机 Codex session JSONL，只输出官方状态名。`task_complete` 映射到 `review`，结构化等待事件如 `approval_request`、`request_user_input` 映射到 `waiting`。如果 Codex 后续提供稳定外部状态 API，新的状态源可以接入同一套 wire contract。

## 任务卡片与 review 语义

Dial 的默认视图保持宠物可见，并显示 running/review 计数。

旋转 Dial 会进入任务卡片视图。宠物缩小，卡片展示当前选中的 Codex 会话。点击屏幕会打开对应 Codex 会话。对于 review 卡片，点击只表示“打开”，离开卡片后才标记为 seen。

BLE 事件协议很小：

```text
CLICK|<thread_id>  打开 Codex 会话
LEAVE|<thread_id>  把已打开的 review turn 标记为 seen
```

历史完成任务的处理规则：

- 首次启动或从旧 seen 状态升级时，当前历史 `task_complete` 会进入 baseline。
- baseline 内的旧完成任务不会挤满 Dial。
- 新出现的 completed turn 会显示为 `review`。
- 同一个 thread 后续完成新 turn，会再次显示为新的 review。

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

## 项目结构

```text
SKILL.md                                      Codex skill 入口
skill/pet2dial/scripts/pet2dial.py           一站式 setup/build/upload/bridge 命令
skill/pet2dial/templates/project/firmware    M5Stack Dial PlatformIO 固件
skill/pet2dial/templates/project/codex_dial_bridge
                                             Mac 端 BLE bridge
skill/pet2dial/templates/project/tools       Codex pet atlas 转换工具
skill/pet2dial/references/success-contract.md
                                             成功路径和固定默认值
docs/hackster                                Hackster 发布文案
```

## 诊断命令

查看环境：

```bash
python3 skill/pet2dial/scripts/pet2dial.py doctor
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
pet2dial.py init
pet2dial.py setup-env
pet2dial.py convert
PlatformIO firmware build
```

观察到的固件占用：

```text
RAM:   15.4%
Flash: 78.9%
```

## 当前边界

- 主要支持 macOS + Codex Desktop + M5Stack Dial。
- 默认状态源是本地 rollout fallback，能够复刻官方状态名和优先级，但 waiting/review 精度受 Codex 外部可读状态限制。
- 固件首次上传需要 USB。
- 仓库不包含用户自己的 pet 图片、Codex 会话日志、seen 状态文件或本机配置。

## English Summary

Pet2Dial turns the selected Codex Desktop custom pet into a tiny external hardware companion on an M5Stack Dial. It converts the official Codex pet atlas into firmware assets, flashes the Dial, and keeps pet/task state synchronized over Bluetooth Low Energy.

The Dial shows the official Codex pet animation states, running tasks, and unseen review turns. Rotate to browse task cards, tap to open the matching `codex://threads/<thread_id>` conversation, and run the bridge as a macOS background service for daily use.

## Contest Note

This project was built for the M5Stack Global Innovation Contest 2026. It uses an M5Stack controller product, was first prepared for Hackster publication in 2026, and includes both hardware and software documentation.

## License

MIT.
