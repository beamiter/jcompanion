# Eva Companion 落地与验收进度

## 本轮收尾与待办（2026-10-31）

按用户要求先收尾、暂停推进。可用代码停在
[`delayed-receipts-8819d34`](../../eva-companion-acceptance/2026-10-31/delayed-receipts-8819d34/validation.json)
已验证检查点：四端显式保存对话、共享语音／工具结果账本、原操作延迟回执补录已保留。
当前用户服务和安装程序未替换，完整方案尚未完成。

提交版的精简验收报告见 [`evidence/README.md`](evidence/README.md)。
本页指向 `eva-companion-acceptance` 的完整快照及证据子目录均为本机归档，未随源码发布。

本轮刚开始的历史界面原型已从工作区撤回，完整源码和补丁保存在
[`history-ui-paused`](../../eva-companion-acceptance/2026-10-31/history-ui-paused/status.json)。
该原型只有初步接口和部分 GTK 控件；最终代码未编译，也未做原生界面验收，不能直接安装。
撤回后八个仓库的源码哈希已与上述已验证检查点逐项比较一致。

恢复时按以下顺序继续：

- [ ] **历史查看**：审查封存原型，补齐共享类型导出、分页／过期响应测试、锁屏与跨项目隔离；接完 Forge、Anvil、Ember、Frost 的历史面板，再做四端真实窗口检查。
- [ ] **内容留存**：实现语音正文的显式保存／删除／暂停及来源展示；临时历史、长期记忆和任务结果引用继续分开，不能默认保存录音或转写。
- [ ] **真实链路**：目前延迟回执端到端用例的桌面端为 IPC stand-in；补做真实 JWM 动作、异常／重连和取消竞争验收。连接失效后的未知回执不得借新身份接管或自动重发。
- [ ] **真人语音与模型**：重新约定测试时机，再验证当前 USB 麦克风上的停播、关麦和释放；补官方 API smoke、错误／超时／限流。此前停止真人测试的约束仍有效。
- [x] **打包一致性（推送前收口）**：统一 Rust 格式后重新生成四端 host 包并核验摘要；生成脚本固定既有公开依赖基线，提交源码不会改变依赖版本。
- [ ] **其余原方案门槛**：多窗口／IME／VTE／Wayland、跨前端长期记忆体验、C11 桌面节点与锁屏多屏、P7 性能、可复现安装和版本／schema 回滚。

恢复前先读取本节及最新检查点，不将封存原型、旧模型实测或隔离音频结果视为完整方案通过。

对照用户的《Eva Companion · ASCII organism + 四终端》完整版方案及其工程附录。
本页记录当前源码和实际执行证据；目标仍是完整方案，不因某一测试通过而缩小范围。
更新：2026-10-31。所有共享模式继续显式启用。

上一帧时钟检查点完成 102 项真实终端原生用例、4 项原生适配器用例和并发矩阵；该结果保留原二进制范围。本轮继续语音回合记录，完整 C01–C12／P0–P7 方案仍未完成。

**后端验收范围更正（2026-10-31）**：核对运行截图和当前 CLI 映射后确认，两端普通启动的
`--mode vte` 都会归一化为 Block。以下历史 GTK 条目与原报告中标为 VTE 的运行，实际走的是
Block，不能作为独立 VTE 验收；旧报告按原样保留。这不撤销对应 Block 运行的实际观察，
但撤销“两后端已验收”的结论。本轮改用受支持的 `--safe-mode` 进入真实 VTE，并记录应用
拥有的内核 VTE 回收线程与实际 jsh 可执行文件哈希；修正后的原生验收已通过本轮明确范围，完整方案仍在推进。

## 2026-10-31 原操作的延迟回执补录

Eva 在已落盘的操作意图与实际派发之间登记原始 voice activation、turn、call、plan、
operation ID 和请求摘要。已派发操作的异步收尾，以及每两秒的只读回执查询，只有在
结果成功写入执行账本后才追加逐操作回执；不再用当前对话猜测旧结果的归属。
查询返回的操作 ID 不匹配时维持 Unknown。确定回执不允许反向改写，重复状态不重复写入；
一个操作成功也不代表原计划中未派发的后续步骤完成。

新增引用协议 v2 和历史 schema 2；旧 schema 1 仍可读取，不能把含新记录的文件谎报为
旧格式。升级需配套的 Eva 与协调者。关联只在原进程及连接代际内有效；断线后清除关联，
重启或失联后未确认的回执保持 Unknown，不能借新会话自动接管。现有用户服务未升级。

私有端到端用例执行了真实 Eva 规划与串行执行代码：向 IPC 测试端点只派发一次，
在第二个语音 activation 开始后先返回错误 ID、再返回正确完成回执，旧操作得到补录，
新回合未收到旧结果。只发生两次状态查询，没有第二次派发，也没有补发模型请求。
这是 IPC stand-in 验证，不代表真实桌面或官方 API 通过。

159 项共享工作区、314 项 Eva 包测试、41 项桥接测试、17 项真实 daemon IPC 合同、
10 项观察进程检查及 6 项隔离原生音频检查通过；Noop 和延迟回执两条私有链路均通过。
仍需历史界面、语音正文授权保存、真实设备／模型、真实桌面执行及其余原方案验收。
证据见 [`delayed-receipts-8819d34`](../../eva-companion-acceptance/2026-10-31/delayed-receipts-8819d34/validation.json)。

## 2026-10-31 Eva 工具调用与结果引用进入共享账本

新增显式协商的语音对话引用扩展。Eva 在原有规划、能力查询、执行结果及反馈路径发送
输入 item、response、call、参数摘要、结果摘要、operation ID 和已核验状态；伙伴协调者
按原始 source、语音 activation 和 turn 关联。它不提供新的执行入口，不保存 PCM、
转写正文、模型正文、参数正文或执行许可。回复正文的摘要只有在真实生成后登记；
“已生成”仍不等于前端已展示或用户已听见。

`dialogue-events.json` 单独保存有界引用链，不改变原 `dialogue-index.json` 格式。
未完成响应不能提供工具调用，结果必须引用已记录的 call；Unknown 只允许有依据地补充，
不能改写既有确定结果或转绑到新 activation。迟到结果不会重开音频或获得执行权；
写入失败会关闭新模型准入，但不阻止本地释放。旧 clocked 音频客户端仍可连接，
新的引用客户端要求服务端确认 dialogue version，不能静默降级。

验证：157 项共享工作区测试、302 项 Eva 库测试、40 项桥接测试、16 项实际 daemon IPC
合同和 10 项实际观察进程检查通过。另用真实 Eva 规划／反馈代码、loopback Realtime
服务和私有协调者跑通九条引用的链路；该链路提交的是 Noop，没有执行桌面动作。
同一测试程序在隔离 PipeWire 24/48 kHz 与 PulseAudio 图上完成 6 项原生音频检查。
共享工作区严格 Clippy 通过；Eva 继续沿用四项既有 lint 允许项。
本轮没有调用官方 API、打开实体麦克风或安装到当前服务。

完整历史回看、语音正文的显式保存、后台执行回执自动补录、带真实动作的全链路及
实体设备验收仍未完成；这不等于 C07／完整方案已经通过。
证据见 [`dialogue-events-8ab53f6`](../../eva-companion-acceptance/2026-10-31/dialogue-events-8ab53f6/validation.json)。

## 2026-10-31 本地语音打断的来源时间校验

JWM Eva 的打断检测现在先核验原生音频帧时间：拒绝超过 250 ms、未来、时间未经验证、
格式错误、重复或逆序的帧；输入提交之前的帧不能打断新回合。20 ms 音频序列中断后，
语音累计、回声比较和下一轮回放缓存一起重新开始。提交后等待桌面上下文期间产生的
有效插话仍可识别，不能把整个等待阶段的语音都丢掉。诊断仅新增拒绝帧数和断帧次数。

本轮候选程序通过 311 项普通自动测试，8 项需要显式环境的测试按原设置忽略；
另外实际执行了 PipeWire 24/48 kHz 及 PulseAudio 三个隔离图上的 6 项原生测试。
这些图只含合成音源和静音输出，不能替代 USB 麦克风、扬声器回录和真人关闭监听验收。
Clippy 全目标检查沿用四项既有允许项；未安装候选程序、未改变当前服务或调用真实模型。
增量源码、候选程序及日志见
[`barge-source-time-496cd31`](../../eva-companion-acceptance/2026-10-31/barge-source-time-496cd31/validation.json)。
完整 C01–C12／P0–P7 仍未完成。

## 2026-10-31 四端显式保存本次对话

Forge、Anvil、Ember、Frost 的现有记忆面板增加 `Review saving this exchange`。
它只捕获本次主动输入和同一回合的完整文字回复，不复制选区证据、终端历史或语音。
选择当前任务／项目或显式 Global 后，仍须审阅现有记忆变更并再次确认；收到回复、
点击提出保存都不会直接写入。来源是原 turn ID，不覆盖同名已有条目，超出 8192 字节
明确拒绝而不截断。旧回合、变化后的上下文和无关归档范围不能被误存为当前对话。
保存后的内容沿用现有查看、编辑、删除、清空及暂停入口；保存不等于允许模型读取。

四个实际 Block 前端在隔离 X11 桌面通过了主动输入→离线回复→全局保存预览→确认
写入→原生查看→审阅删除→确认删除。每次确认前后均检查实际 SQLite，保留截图和
原回合来源。原生检查同时发现并修复 GTK 弹出面板过窄和 Frost 长文本挤走删除按钮。
早期失败／未完成的测试运行单独保留，未合并成通过。148 项工作区测试（包含 5 项
新增保存逻辑测试）与严格 workspace Clippy 通过，四端当前源码构建通过。
详见[本轮证据](evidence/dialogue-save-checks-2026-10-31.json)。

本轮验证范围为单窗口 Block、离线路径和 Global 保存流程；任务／项目隔离另有共享
逻辑测试。未宣称本轮重跑完整图形迁移矩阵、VTE、物理音频、实际 provider 或发布。
语音正文、完整工具／结果链、跨前端长期对话体验和其余 C01–C12／P0–P7 仍需推进。

## 2026-10-31 对话元数据持久化与任务结果引用

本机 profile 新增有界 `dialogue-index.json`，记录回合身份、原始来源、生成／显示／播放
观察、结束原因及任务结果引用。文字输入和模型正文只在当前会话内存中保存；选区原文、
终端输出、录音、凭据及执行许可不写入该索引，也不因已有历史而加入下一次模型请求。
文字回合在实际派发请求前提交元数据，只有客户端显示回执才能记录 displayed。

重启会把未结束回合标为 `restarted_unknown`，保留已提交的播放下限，清除当前播放状态。
历史记录不恢复活动回合、音频所有权或执行许可；原驻留／语音日志仍独立决定真实归属。
语音只在回合开始、结束、打断、失联等边界写盘，80ms 活跃进度仍留在内存中。

任务结果只记录已认证宿主上报的 ID、incarnation、项目、revision、状态和观察时间。
项目取自原任务注册关系；切换到另一个 pane／项目后收到的旧任务回执仍绑定原项目。
这些引用不代替原执行器的结果记录，不把模型建议、开始执行或历史状态当成新成功。
索引最多保留 4096 个回合和 4096 条任务引用；只淘汰已结束的旧启动回合，当前回合的
重放墓碑不被容量淘汰。文件采用私有权限、原子替换与同步写入；损坏或写入失败不重置
旧文件，新的模型请求停止派发，已有终端服务和原所有权清理仍可继续。

143 项工作区测试（含 42 项 daemon 测试）、严格 workspace Clippy、14 项实际 IPC
契约及 9 项实际 Eva 通信线程检查通过。实际 worker 的磁盘索引保留打断、失联和释放
三种不同结束原因。本轮未重跑上一轮图形／原生音频矩阵，也没有安装或发布。
源码重建与证据见[本轮检查](evidence/dialogue-journal-checks-2026-10-31.json)。

正文的显式保存／分享界面、完整用户／模型／工具／结果链、真实设备语音及其他原方案
验收仍未完成；本轮不将临时对话改成长久记忆。

## 2026-10-31 语音状态新鲜度与排空收尾

新增独立的 `companion-voice` 源码包，显式协商 `linux_boottime_ns_v1`；Eva 使用有哈希
清单的本地 vendor 副本，既有公开 Git 依赖不变。未协商的旧音频消息不能证明当前正在
听／说。原有终端宿主消息和撤除接口保持原协议范围。

活跃音频观察按 80ms 的有界周期刷新，协调器只使用不超过 250ms 的 Linux boot-time
时间戳。时间来自已验证采集帧或原生播放观察，不能在发送时给旧样本重新打戳。
未来、乱序、过期数据不刷新姿态；进程停顿或 IPC 堆积后要有新的有效观察才恢复。
本地过期样本直接丢弃，不断开健康连接或结束回合。过期也不释放原语音许可、不取消
任务、不重发模型请求。原版对照复现停止上报后一直保持 speaking；新版实际 worker
验证暂停、旧队列、恢复、持续监听，以及过期期间仍拒绝另一条文字回应路线。

私有 PipeWire 检查还发现原生 drained 回执后的正常 disconnect 可抢先写入失败，导致
已经排空的输出被报成失败。现在只抑制原生排空已经确认后的这条误报；排空前错误保留。
旧源码单次对照通过，未把它写成原生失败；本轮失败记录和详细时序保留。

136 项工作区测试、295 项 Eva 库测试、40 项原源桥接 fixture、11 项实际 IPC 契约和
9 项实际 worker 检查通过。两种私有 PipeWire 图速率与私有 PulseAudio 共 6 项原生
音频检查通过，使用合成源与静音 sink，未连接日常音频服务。协调器 workspace Clippy
严格通过；Eva Clippy 保留既有 collapsible_if、needless_borrow、large_enum_variant、
too_many_arguments 类豁免，其中 `run_with_handoff_owned` 未改变。本轮最终协调器的
8 GUI／32 PTY 矩阵也通过。源码重建和精确输入核验另存于[本轮机器证据](evidence/voice-freshness-checks-2026-10-31.json)。

这些检查不等于实体语音、声学打断、完整系统休眠、持续物理唯一性或 P7 性能验收。
完整 C01–C12／P0–P7 目标仍未完成。

## 2026-10-31 语音回合身份与共用记录

协调器把真实 Eva owner 上报接入文字共用的有界内存 ledger。文字和语音的同名 turn
互不覆盖；语音记录绑定原 source、activation lease 和 companion 身份，不推断 pane、
项目或任务。生成样本、当前播放观察、已确认播放下限分别记录：后续时钟未知不能抹去
已有下限，也不能据此继续显示正在讲话。打断、观察丢失、资源释放和下一回合各有独立
结束原因，不把已生成但未播放的内容记成已听到，不代替任何任务执行结果。

旧 source/turn 保留重放墓碑；迟到帧不能改绑到新 lease，停止/错误事件也必须持有当前
语音许可。共享记录满时阻止新激活或新上下文请求，已有许可仍可完成精确清理。
Eva 的激活 ID 另加进程内检查溢出的递增序号，避免 JWM 重启后 generation 重用导致
旧释放和新激活同名。旧版实际 worker 对照复现同名，新版同 generation 两次激活不重用。

129 项工作区测试、37 项原源桥接 fixture、生产 Eva 的 8 项 companion 测试、9 项
真实 IPC 契约和 5 项实际 worker/协调器检查通过；协调器严格 all-target Clippy 通过。
worker 检查使用真实通信线程与原生 Unix socket，音频进度来自测试元数据，不是设备或
声学证明。新协调器与原已验证前端通过 8 GUI／32 PTY 矩阵。生产 Eva 构建通过，尚未安装或做实体音频验收。详见[本轮机器证据](evidence/voice-ledger-checks-2026-10-31.json)。

记录仍是易失元数据。持久内容／结果引用、真实麦克风和扬声器的完整语音打断、实际
provider/API、C11、P7 与发布尚未完成；本轮没有启用用户音频设备或替换日常安装。

## 2026-10-31 原生帧时钟重绑与表面身份

GTK 控件在重映射／重建后可能取得另一帧时钟。旧实现只绑定第一次 map，且把原生
帧号直接用作跨时钟的撤除边界；新时钟从小帧号开始时，边界可能长期无法越过。
旧算法的确定性失败已保留。现在在真实 before-paint 分配本 GUI 的递增序号，再在
同一帧的 after-paint 捕获内容，等待原时钟完整且正值的实际呈现时间。
绑定变化会断开旧信号、作废旧帧，保留序号的单调性；无时钟的首次映射会继续重试。
接口背景见 [GTK 帧时钟说明](https://docs.gtk.org/gtk4/method.Widget.get_frame_clock.html)。

身体出现前记录原生表面与 token，只有实际 RetirementAccepted 才释放这份归属。
新表面的空帧不能替旧表面确认撤除，GDK 对象销毁也不作为可信退休证明。
两前端各自的真实双窗口适配器测试已验证：旧身体完成撤除后重建表面／时钟，
新帧号低于旧帧号时仍能再次完成正常交接；带着未完成旧义务销毁表面时，仍阻止新身体。
这 4 项测试在一个测试进程内运行真实窗口，不能据此宣称完整终端同进程多窗口 UX 已验收。

**176 次针对性测试执行**及两端 all-target Clippy 通过，仍保留三类既有 lint 豁免；
独立帧序号／表面归属辅助测试另有 9 项通过。**102 项真实终端原生用例**包含 84 项
生命周期回归、10 项启动未完成关闭、4 项延迟呈现和 4 项同 XID 重映射。后者同时核对
Block／真实 VTE、原 GUI 和 PTY、真实退休、重映射后的原 shell 输入。
8 GUI／32 PTY 的家族矩阵在额外 GTK 窗口并发时通过。
详见[本轮机器证据](evidence/gtk-clock-checks-2026-10-31.json)。

不同原生表面之间仍严格保留未证明的撤除义务；没有将“重建成功”推广成任意崩溃／销毁的
自动恢复。完整终端多窗口、挂起、远程／脱离会话和观察错误，以及真实 IME、记忆权限、
语音、provider/API、可信 C11、P7 和发布仍需推进。

## 2026-10-31 GTK 延迟帧回执与 Granted 活性

旧适配器在每次 after-paint 时覆盖待确认的身体帧；真实 GDK 时序较晚完成时，
有效的旧帧可能一直被更新帧排除。保留旧算法的确定性测试复现了这条饥饿路径。
原 Anvil 延迟反馈对照最终通过，但在首次确认前确实忽略了 28 份已完成的旧帧，
不能把这份对照称为原生失败。此前“身体可见但停在 Granted”的并发失败仍按原样保留。

两端现在记录原始 FrameClock、帧号、精确 token、连接与 admission 版本以及身体／
清空内容；保留最早的 8 份待确认记录。只有原时钟的完整且正值呈现时间到达，才把
对应身体帧登记并立即提交回执；后续绘制不再覆盖它。HostGate 原有提交与验收方法
逐字节不变。缺少时序只触发实际重绘，不生成确认；旧 token、旧连接和身体内容不能证明清空。

**166 次针对性测试执行**与两端 all-target Clippy 通过，仍保留三类既有 lint 豁免。
独立排序回归另有 5 项通过。两前端 × 真实 Block/VTE 的 4 项私有原生延迟测试完成
12 次可见且 Active 的迁移；含启动／预热共 20 份落后于新绘制的身体帧被正确接收，其中 12 份对应延迟反馈迁移。
同一组二进制通过 84 项生命周期回归、10 项启动未完成关闭回归，合计 **98 项原生用例**。
8 GUI／32 PTY 家族矩阵也在额外真实 GTK 窗口同时运行时通过，保留全部实际输入 PID、
双向／快速迁移和暂停 owner 检查。见[本轮机器证据](evidence/gtk-presentation-checks-2026-10-31.json)。

验收期间 JWM 工作区另有 Eva 密钥设置提交 e3f154d。该提交完整保留；本轮固定 JWM 二进制的 366 个本地源码输入未变。原保存基线与包含新提交的完整差异分别记录，新的 Eva 密钥流程不计入本轮验收。

本轮解决的是所选场景中的功能活性；启动输入检查先完成，再引入并发负载。
私有 compositor 的暂停只用于制造实际反馈延迟，不是性能测量、物理／连续唯一性或可信 C11。
独立时钟重建／remap、完整同进程多窗、挂起、远程／主动脱离与观察错误等剩余场景，
以及真实 IME／记忆／审批／语音／provider/API、P7 和发布仍需推进。

## 2026-10-31 GTK 启动尚未完成时的关闭

Forge／Anvil 在 fork 前登记窗口所属的启动票据；pane／tab 移除后，窗口仍保留该票据。
关闭只记录终止意图，必须等实际启动结果和独占 wait owner 的真实会话清理完成，才允许
窗口退出。应用自己 fork，继续使用公开 VTE PTY child setup 与 VTE I/O；启动观察和可选
用户 scope 放在工作线程。失败／取消也由原来的 owned child 收尾，不把取消请求或 libVTE
错误回调当成已回收证明；pidfd 暂时不可用时保持未回收 PID 的父进程锚点并重试。

退出通知绑定原启动票据和原 child Arc。500ms 启动命令也只允许写入原来的、仍活着且
挂载的 child；关闭、失败重试或复用控件不能把旧输入送入新 PTY。Forge 的控制器接收
已经拥有的句柄，迟到结果不重新打开数字 PID；关闭后的结果和回调重入均抑制 UI admission。
原有 cwd／冻结环境／Flatpak argv 包装继续进入同一启动器，真实无 shebang 文件保持
execvp 的 /bin/sh 回退，其他父进程 FD 在 exec 时关闭。

两端 **158 次针对性测试执行**与 all-target Clippy 已通过，仍保留三类既有 lint 豁免。
真实 GTK／PTY 聚合测试覆盖：未交付启动、pane 移除后的清理、独立进程组后代、真实
EMFILE 恢复、失败后重试、窗口对象隔离、同一控件的新旧启动输入、ENOEXEC、冻结
环境、cwd 和 FD 泄漏；窗口对象隔离仍不等于完整同进程多原生窗口验收。
旧生产二进制在窗口关闭和最后标签关闭的四项对照均于启动结果到达前退出，实际子进程
仍活着；另保留两项最初原型对照。两端 10 项新增原生用例均通过，包含窗口、最后标签、分屏取消、
分屏确认后继续关窗和整标签关闭；实际日志验证已移除 pane 的票据先保留，再等待 owned
启动结果后完成窗口清理。另完成 84 项既有生命周期回归，合计 **94 项当前原生通过用例**。原批次两处输入时序失败在补上真实行编辑器就绪检查后重测通过，原报告保留。完整结果见[机器证据](evidence/gtk-launch-checks-2026-10-31.json)。

当前 8 GUI／32 PTY 家族矩阵单独运行通过，包含 72 份实际输入 PID 标记、双向／快速迁移和暂停 owner。并发运行的矩阵曾在 Anvil 已可见时停留于 Granted；原因尚未确定，该失败仍保留，独立复测不替代并发负载和 P7 验收。共七份诊断均未计为当前通过。

系统调用延迟仅用于私有进程的功能压力，不能用作延迟指标。未向 coordinator 注入宿主、
任务、帧或退休证明。远程／主动脱离会话、同进程多窗、挂起、真实 IME／记忆／审批／
语音／provider/API、可信 C11、P7 性能和发布仍保持未完成；完整 C01–C12／P0–P7 目标继续 active。

## 2026-10-31 GTK 可恢复撤除与无身体窗口的关闭

Forge／Anvil 接入与 Ember／Frost 同源的 WithdrawalResumeV1 宿主 bundle；公开 Git
依赖基线保持原值。GUI 退出许可与旧身体的撤除义务分离：取消继续完成原 token 的真实
GDK 呈现和持久退休，然后在原宿主/窗口恢复；重新关闭有新的 intent。GTK idle 回调、
Anvil 消息和取消后的焦点恢复都绑定关闭版本，旧回调不能重新授权退出；后续关闭会使旧版本的焦点恢复失效。
Anvil 先撤除身体，再清理子进程。Keep window open 和 Escape 恢复原控件；按住取消键
后切换焦点仍保留按键所有权，新输入继续交给原生终端/控件。

已确认的当前进程镜像以打开的文件和 start time 固定，后续同 PID exec 或新 PTY 会话
成员会撤回可恢复关闭许可。此观察不替代原有空提示符/进程确认，VTE 和未验证 Block
提示符继续经过真实确认。无可疑本地身体且控制连接已经断开时，窗口可在原进程保护
通过后退出；Withdraw 仍抑制清理等待期间的重新驻留，不生成假的撤除 ACK。仍有可能
存在的身体时，即使 daemon 丢失也继续等待精确退休和重连后的新原生证明。

本轮最终二进制完成 **84 项原生执行**（21 类 × 两前端 × 两后端）：40 项撤除恢复与
连接丢失、16 项标签/分屏关闭、28 项窗口作业回归。每份当前报告均核对运行后端：
Block 用普通入口，VTE 用受支持的安全模式；私有 PATH 的 sh 指向同一真实 jsh，
实际 `/proc` 可执行文件哈希和应用拥有的 VTE 回收线程一并保留。安全模式忽略自定义
配置，整标签关闭通过原生命令面板触发。旧 CLI 标签重复运行不计为 VTE 覆盖。取消用例另核对真实带保护关闭许可的
启动、取消日志与顺序。
初版确认后取消的 4 项旧二进制对照
复现自动退出；随后补出的 4 项未连接关闭对照复现等待不结束。两组失败均保留，早期
夹具暂停顺序、焦点及磁盘满的诊断不混入最终通过数。详见[本轮机器证据](evidence/gtk-resume-checks-2026-10-31.json)。

**152 次测试执行**含两端 GTK 主循环的清理集合、回调重入/窗口隔离、真实 owned spawn、
当前镜像改变、关闭版本、完整宿主 bundle 36 项和逐字节一致的进程包 7 项。Clippy all
targets 通过，仍明确保留三类历史 Eva 告警豁免。8 GUI／32 PTY 家族矩阵也通过，包含
实际 shell/PID 输入、双向/快速迁移和暂停 owner；矩阵 GTK 路径为 Block，VTE 由独立
原生套件验证。源码校验另外区分完整验证源集合与实际生产 dep-info，避免把工作区测试
源码当作 daemon 的运行依赖。821 项本地生产输入覆盖 daemon 与四前端；未改动的
JWM 和真实 jsh 沿用已保存的二进制哈希，不计入这组 dep-info。

这些是私有 X11、真实原生输入、GDK 完整时序及固定尺寸 Cat 采样。4 项撤除中新作业
用例在作业接管 PTY 后暂停原私有 shell，以隔离该受控 trap 夹具的输入读取竞争；不据此
宣称普通 fg/后台控制的全部 UX。窗口对象隔离单测不等于完整同进程多窗口应用。采样不
证明物理或连续唯一性，NativePresented 不等于受信 C11 证书。

异步启动尚未交付结果时的关闭、原生批量选择交互、完整同进程多窗口、挂起、远程/
detached 与观察错误，及真实 IME/记忆/审批/语音/provider/API、C11、P7 性能和发布仍需
继续完成。完整 C01–C12／P0–P7 目标保持 active；未安装或发布到日常桌面。

## 2026-10-31 最后标签与已移除 pane 的清理所有权

对照原方案的 split/tab、过期回调和保留本地确认要求，补验 GTK 结构移除后的生命周期。
旧二进制的 16 项对照中，8 项通过、8 项失败：Anvil 两个启动标签（实际均为 Block）确认最后标签或含分屏标签关闭后
仍留下作业；两端的分屏关闭只看前台进程，会终止仍附属的后台作业。Forge 的普通最后标签
对照通过，未将它记为失败。

现在每个窗口保留已关闭 pane 的精确 ChildLifecycle 句柄，直到原 wait owner 回收完成。
标签模型变空不会跳过先前的异步清理；重复关闭加入现有等待，不并行运行完成回调。
等待期间再移除的 pane 加入同一集合。集合按窗口隔离、按 Arc 身份去重，不在退出时用
旧数字 PID 重新打开进程。Block、VTE 与兼容回收入口都在移除界面对象前保留句柄。
Anvil 单个/批量标签与 pane 的移除路径也接入同一所有权。

分屏关闭复用整个 PTY 会话的作业/空提示符检查。取消原生确认后，原后台作业和原 shell
输入继续有效；明确确认才进入清理。新增 16 项真实 jsh、原生键盘/对话框检查和原有 28 项
窗口作业回归均通过，详见[本轮机器证据](evidence/gtk-close-checks-2026-10-31.json)。
108 次回归执行含两端真实 GTK 主循环中的空集合、重复请求、后来加入的子进程、回调重入
及另一窗口子进程存活检查；不把这些窗口对象单测说成完整同进程多窗口应用验收。
Clippy 仍明确列出此前 Eva 模块的三类告警豁免。

清理完成不替代呈现撤除：原生检查继续要求完整 GDK 时序、匹配旧 token 的撤除记录和存活
宿主的重新驻留。固定窗口的 Cat 采样不证明物理或连续唯一性。

该历史检查点当时，GTK 的可恢复关闭协商尚未接上 ResumeWithdrawal 状态机；当轮“清理等待期间再移除
pane”不是“撤除等待期间启动新工作并恢复窗口”。异步启动尚未交付子进程时的关闭、真实
批量选择交互、同进程多窗口、挂起及 C11/语音/记忆/审批/真实 API/性能发布仍需继续验收。
完整目标保持 active；没有安装或发布到日常桌面。

## 2026-10-31 GTK 作业保护与退出收尾（历史 CLI 标签范围已更正）

Forge、Anvil 以 Block/VTE CLI 标签运行的四种组合（实际均为 Block）曾通过 **28 项**私有 X11 原生用例：后台、停止作业、
非活动标签、`wait`、`while/read`、父 shell 自然退出，以及明确确认关闭仍有后台作业的窗口。
使用同一最终夹具重跑的 **8 项旧二进制对照均复现失败**。报告保存每次实际进程、原生输入、
宿主 token、GDK 完整帧时序和 PNG；不以进程消失代替撤除凭据。

两端复用 `companion-host` 中已有的 PTY 会话/程序身份观察源码，独立的版本化
`companion-process` 包不修改公开 jterm_core/Git 依赖。生成器和每端 bundle 校验器记录完整
文件哈希；Nix 构建、开发校验及 CI 接入校验。Block 的 fork/exec 握手先完成 `setsid`，
再记录会话身份；读取线程每 200ms 检查父进程，并保留最多 1 MiB 的已可读尾部。
VTE 负责 I/O，正常启动的子进程由应用独占回收；同会话作业清理完成后才释放父 PID、通知退出。
确认关闭整窗时 GTK 主循环继续运行，等待异步清理完成，避免进程先退出而丢掉清理线程。
Anvil 的旧裸 PID SIGHUP 路径已改为持有的生命周期对象。

关闭检查覆盖全部标签和 pane 的同会话后台/停止作业，并要求可验证的空提示符。
VTE 没有足够的语义提示符证据；Block 未建立该证据时也保留确认对话框。
这不将命令结束、前台组等于 shell，或 shell 可执行文件相同单独视为空闲。

本轮另记录两类诊断：早期夹具实际使用 `/bin/sh`，最终统一为私有副本 jsh；
默认 GTK “Completed” 标签与 Cat 的薄荷色重合，不能把第二个颜色分组直接算作第二个身体。
最终固定窗口夹具保留全部颜色分组，检查完整 Cat 尺寸，并继续检测前次身体区域中的残留。
这只是固定尺寸的采样检查，不是 compact/resize、物理扫描输出或连续唯一性的通用判定器。

[机器证据与检查边界](evidence/gtk-jobs-checks-2026-10-31.json)列出实际检查、原二进制及诊断。
既有 Eva 模块的 Clippy 告警单列豁免，不声称全仓零告警。共享观察器测试与各端 PTY、
启动/退出、GDK gate 回归单独记录。旧 Ember/Frost 与全家矩阵证据仍按原二进制保留。

完整方案继续推进：最后标签确认关闭、延迟关闭期间新作业、同进程多窗口及挂起仍需专项验收；
远程/主动 setsid 脱离会话、真实 IME/记忆/审批/语音/API、可信 C11 呈现和 P7 性能/发布尚未完成。
没有安装或发布到日常桌面。

## 2026-10-31 后台作业、wait/loop 与父 shell 退出

本轮原生基线确认三个缺口：Frost 在空提示符处允许关闭整窗，未保护仍附属的后台作业；
Ember、Frost 的父 shell 自然退出后，独立进程组的作业仍可能存活。Ember 的同一后台关闭
基线已经通过，没有将其记为失败。原报告与二进制保留。

新增共享 PTY 会话观察：绑定原父 PID、启动时间和 session，检查同一 session 的其他存活
进程，包含后台和暂停作业；空提示符及前台组相同不再独自授权关闭。
观察有进程数/单条记录上限，缺失或无法核对时保留窗口，既有显式标签结束路径保留。
自然退出使用 WNOWAIT 保留父进程身份，按 pidfd 定向清理同 session 的成员，连续两次为空
后才回收父进程并报告原退出码；异常保留状态等待重试，不以复用的数字 PID 发信号。
这不是对任意同 UID 程序的隔离，也不把主动 setsid 脱离会话的进程算作附属作业。

首个修复候选还暴露出 Frost 读取线程依赖 EOF：子进程保持从端打开时，父退出永远没有进入
清理。最终实现每 200ms 独立观察父进程，先交付最多 1 MiB 的可读尾部，再由原 wait owner
完成会话清理；超过尾部上限会记录警告。真实 PTY 单元用例证明无 EOF 时仍保留尾部和退出码，
旧的暂时 hangup/重开 PTY 用例继续通过。观察到父退出但清理未完成时，Frost 按会话 ID/fd
异步重试，不能提前把标签当作已完成任务。

工作区 **119** 项及严格 Clippy、两端 **111** 项互不重复的窗口/PTY/Eva 检查通过。
旧窗口单元夹具在启动辅助进程尚未结束时伪造提示符，现先等待实际会话空闲；两个误选的
零用例过滤器没有计入检查数。源码包保持公开 Git 基线，新增模块及 libc 依赖后为 18 个文件；
锁文件仅补充 companion-host 的已有 libc 依赖，没有引入或更新其他包。

本轮原生检查及精确二进制记录见
[机器证据](evidence/shell-jobs-checks-2026-10-31.json)。它覆盖两端真实 jsh 的后台/暂停作业、
非活动标签、wait、while/read 与父退出，核对原 shell、同宿主以及下一次主动关闭的真实撤除。
旧的迟到工作夹具预先启动后台进程，会被新保护合理阻止；新夹具由原生命令预先安装 shell
trap，实际清除帧等待 scene 时才用信号启动前台任务，不预置子进程，也不暂停父 shell。
直接在待关闭界面键入命令未启动任务的诊断另存，不能作为迟到工作的通过证据。

先前旧二进制的撤除压缩、输入与其他测试均保留各自范围，不重标为新二进制运行。
本轮仍限私有 Xvfb/home/XDG/DBus；日常安装、真实 provider、音频设备和付费 API 未操作。
完整方案继续：其他前端/后端及远程、setsid/线程/持续 fork 等生命周期边界、同进程多窗、
休眠、真实 IME/记忆/审批/语音/API、可信 C11 fence/锚点和 P7 性能/发布尚未完成。

## 2026-10-31 单 profile 原生撤除缓存压缩与丢失确认恢复

Ember、Frost 各在一个独立私有 profile 中，由三个真实 GUI 完成 **71 次原生交接**。
故障中继逐字转发原始帧，仅丢弃原宿主第一次真实 Retired 对应的精确确认；
原宿主保持无新 grant，另外两个 GUI 交替，使精确缓存保持 **64** 条且原条目已被压缩。
随后实际 SIGKILL 并重启协调器，原 GUI 以新 boot/nonce 重新连接，必须取得新的原生
清除回执、再次提交原 token，才收到新协调器生成的确认；中继不缓存或重放旧回复。

两端均保留原 GUI、窗口、HostID/incarnation/surface 与原 shell 的 PID/启动时间。
旧 token 的重新确认不清除当前较新身体；原窗口随后以更高 epoch 恢复，用真实输入核对
原 shell PID，最后一次健康关闭仍完成当前 token 的真实撤除与另一 GUI 接管。
独立证据审计逐项核对交接、换连接 nonce、重启后的新 native pass、原始日志及 PNG SHA。
两端各 **72** 条清除回执（71 次交接加一次重启后重新证明）和 **206 / 262** 张采样通过审计；
这是本轮具体 profile 的原生压缩验收，不将历史 70 次声明 serial 的 IPC 用例重标为原生证据。

首轮 Frost 夹具错误地把 Iced native pass 与捕获的宿主树帧号当成相同值，失败记录原样保留。
现在 observer 在原捕获快照旁传递对应的真实回执 ID，debug 日志记录编号关联；
旧 API、窗口/registration lease、pending 上限、取消与证明接受条件保留。
真实发布、scene 接受、原 native pass、捕获树帧和 Retired serial 必须逐项关联。
**10** 项原生反馈代码测试、**11** 项 Frost Eva 测试、严格反馈 Clippy、
**4** 项中继字节/丢弃控制检查及 **4** 项 PNG 检查通过；合成检查不提供原生证明。

协调器、Ember 编译输入与二进制逐字匹配前一冻结点，沿用其工作区 115 项、严格 Clippy
及 11 项真实 IPC 结果。本轮 Frost 二进制为 5dacd58；其定向原生回归及四终端矩阵另见
[本轮机器证据](evidence/native-retirement-compaction-checks-2026-10-31.json)。
前一轮 4bc45c5 的 Frost 检查保留为历史证据，不宣称全部 66 项已在新 Frost 二进制重跑。
新增夹具、故障中继和离线审计入口均在 tests/；所有运行仍使用私有 Xvfb/home/XDG/DBus，
日常安装未替换。截图只采样默认 Cat；scene 回执仍为 NativePresented 范围，
不构成连续/物理唯一性或可信 CompositorPresented fence。

完整方案继续推进：更多 builtin/wait/loop、后台作业与父 shell/后代生命周期、
真实 provider/远程、其他编辑器/后端、同进程多窗、休眠、实际 IME/记忆/审批/语音/API、
C11 可信 fence/锚点及 P7 性能/发布尚未完成。源码与原生证据冻结状态以机器证据为准。

## 2026-10-31 shell exec / read 内建命令的关闭保护（前一轮记录）

Ember/Frost 普通关闭现在同时核对交互 shell 的可执行文件、进程启动时间与新鲜、
无已接收输入的语义提示符。PID、PGID、SID 相等不再等于空闲：exec 保留这些 ID，
同可执行文件的 exec -c 和 read 内建命令还会保留程序 inode。
可执行文件以打开的文件固定，路径替换或删除不会重新授权另一程序；
无法核对的活会话保留窗口。普通 sh 缺少命令边界时，需用户退出 shell，或经现有
标签关闭确认明确结束会话；最后一个标签仍完成当前身体的真实撤除。

原生基线的四次误关闭原样保留：两端 exec 工作均收到 SIGHUP，read 也被终止。
当前 **18** 项原生检查覆盖两端实际 jsh 的 exec、同程序 exec -c、read，
各自的前台/非活动标签，以及 Frost 普通 sh 的六种相同情形。每次先拒绝普通关闭，
再以真实输入结束工作，核对原 PID/启动时间/TTY/程序及同一宿主，最后验证精确 token
撤除、真实 scene 回执和另一 GUI 接管；普通 sh 的最后一步单独记录原生标签确认。
这没有把后台标签等同于 shell 内后台作业，也不证明父 shell 退出后后代仍存活的行为。

本轮还保留并修复一次 Frost 过度阻塞：真实 Ctrl+C 结束前台工作后，右侧 4.9s 耗时
被 Agent 的整行输入捕获算作命令文字，导致新的健康关闭无法完成。现在关闭检查使用
独立的干净语义提示符条件；已提交输入、排队输入与备用屏幕继续阻止关闭，
Agent 的严格捕获/命令授权条件未放宽。新增两项回归解析实际右侧装饰控制序列，
并核对待提交与 typeahead；原生 Ctrl+C 场景用最终二进制复测通过。

当前工作区 **115** 项及严格 Clippy、前端 **183 + 6** 项互不重复检查、真实 IPC **11** 项
通过。两端 locked/offline 构建与 **931** 份 Rust/Cargo 编译输入前后核对。
源码包仍保留公开 Git pin，新增本地 shell 观察模块；两端 bundle 校验与真实依赖图检查通过。
额外 **48** 项既有回归通过，共 **66** 项当前二进制原生检查，包含两项预期的崩溃阻塞负例。
其中 **20** 项原 Ember 运行在逐字核对其编译输入/二进制后沿用，**46** 项为本轮最终
二进制的独立运行；所有修改后的 Frost 场景均重新运行。

完整矩阵为 **8 GUI / 32 PTY / 72 原生 PID marker**、24 次快速操作及完整反向，
**70** 张 root 采样与 **25** 条接受的 WGPU scene 回执。
本轮既有回归现使用两端真实 jsh；普通 sh 的六项明确确认场景另列，不能混用为同一关闭策略。
截图分类仍只覆盖默认 Cat；其 4 项测试保留。原生 scene 与精确 token 证据独立于截图，
仍为 NativePresented 范围，不是连续/物理唯一性或 CompositorPresented。

新 jsh 标签首轮没有确认原始输入就绪，诊断命令未执行；另一次夹具在 Frost 已聚焦忙碌
标签后又切换，实际关闭了空闲标签并将 Escape 送给工作。两次报告均未改写。
已核对 raw 就绪、正确标签、原空闲进程仍存活；节奏调整与无额外 Return 暂停的诊断另存，
不作为启动期间输入或吞吐/延迟验收。迟到前台夹具仍会暂停原私有 shell，排除已有阻塞 read。

[本轮机器证据](evidence/shell-lifecycle-checks-2026-10-31.json) 与候选快照保留失败、
诊断、精确二进制、八仓库基线/补丁及完整原方案。107 个私有 runtime 的审计无匹配残留；
离线重建逐字核对 **2,633** 份家族 Rust/Cargo 文件、**931** 份编译输入与 **7** 个二进制，
重建后的工作区 **115** 项与 4 项 PNG 检查通过。这不等于前端位级可复现构建或硬件验收。
所有操作仍限私有 Xvfb/home/XDG/DBus/二进制副本；日常安装未替换。

完整目标继续保留：更多 builtin/wait/loop、shell 后台作业与父进程/后代生命周期、
单 profile 超过 64 次的原生撤除压缩、真实 provider/远程、其他编辑器/后端、同进程多窗、
休眠、真实 IME/记忆/审批/语音/API、C11 可信 fence/锚点及性能/发布尚未完成。
66 项不同 profile 的检查不能替代单 profile 的原生压缩验收；已通过的 70 次 IPC 使用声明 serial。

## 2026-10-31 同宿主取消关闭与重新驻留（前一轮记录）

Ember/Frost 在等待 Eva 撤除时可用 Keep window open 或 Escape 取消整窗关闭。
原 GUI、原生窗口、HostID/incarnation/surface 与 shell 保留；普通取消连 IPC 连接也不变。
取消只改变关闭意图：精确旧 token 的真实清除帧、scene 回执和持久撤除继续完成，
随后收到显式重新准入确认、重发新范围的上下文/几何，才允许同一宿主获得更高 epoch 的身体。
工作接管 PTY 后 Escape 留给工作；独立的 Keep 按钮取消关闭，Frost 隐藏侧栏也有入口。

协议仍为 VERSION=1；通过新的显式 HelloWithFeatures/HostAccepted 协商 withdrawal_resume_v1。
旧 Hello/Accepted 的字段与旧 Recall 语义保留。连接 nonce、单调 intent 和 admission_epoch
分别绑定握手、关闭意图与元数据范围；旧 nonce/范围中的高 revision 在进入缓存前即拒绝。
重新准入清除旧上下文、审批与选择范围，并先发送新上下文再发送任务事实。
新客户端需要支持该能力的协调器，能力缺失时保持无身体；不通过新 HostID 绕过旧撤除。

维护入口提取为 jcompanion/crates/companion-host，两个前端使用仓库内可校验的源码包。
公开 Git 基线仍为 jcompanion 9aa5695 与 jterm_core 974ccad；原 pinned adapter 未改。
来源文件 SHA 已与原提交核对，bundle 字节、Cargo patch 与基线检查已接入两端 CI。

本轮同时修复两处原生竞态：

- [Frost 输入框布局缺陷](evidence/native-withdrawal-focus-before-fix-2026-10-31/withdrawal-resume-report.json)：身体隐藏后移除输入框前的控件，丢失焦点/控件身份，实际 backing 出现草稿前缀进入 shell；慢速变体还会打开错误面板。现在保留未绘制的占位与稳定父控件。当前原生用例在 Eva 输入框完整保留 EVA_CANCEL_FOCUS，并在取消后通过原 shell PID marker；绘制和候选几何仍受安全条件控制。
- [重启期间的重复 Revoke](evidence/native-withdrawal-frost-restart-before-boundary-fix-2026-10-31/withdrawal-resume-report.json)：真实清除 scene 已被接受，但重复通知推进证明边界，Frost 的布尔状态没有重新安排帧。现在同连接的重复通知幂等，新连接要求新的 frame boundary，前端按 token/boundary 安排清除。单元测试覆盖在途旧回执与新连接边界；两端原生重启复测通过。

当前精确二进制的 **19** 项原生取消检查全部通过：

| 场景 | 检查内容 |
|---|---|
| 两端 Escape / Keep 按钮 | 暂停私有协调器，在 Revoke 前取消；原 token 未被伪造撤除，恢复后同窗口/宿主/连接重新呈现，并核对原 shell 输入 |
| 两端待 scene 回执取消 | 暂停私有 JWM，先确认真实清除已发布而 scene 未接受；原生 Escape 后恢复，精确旧撤除与同宿主新身体成立 |
| 两端工作接管后点 Keep | 实际独立 PTY 前台进程存活；Escape 字节由工作收到，点 Keep 后继续运行，结束后原 shell 与身体恢复 |
| 两端长按 Enter / Escape 失焦 | 对话框 Enter 的重复不执行新提示符；真实释放后的新按下可执行。Escape 重复、blur/refocus 和释放不泄入终端或取消新意图 |
| Frost 输入框捕获 Escape | 原生 backing 完整草稿与空 shell 提示符另行人工核对；取消后同连接/宿主和原 shell PID marker 成立 |
| 两端取消期间协调器重启 | 允许真正的新 boot/nonce，保留原 GUI/窗口/宿主；新的真实清除后完成旧 token 撤除并恢复 |
| 两端取消后再次关闭 | 旧取消/Ready 不授权新的关闭意图；原生旧 Force 按住后跨取消/新关闭释放，也不成为新 Force 操作 |

每次恢复后再正常关闭，都按当前 token 检查撤除并确认另一真实 GUI 获得身体。
当前检查为工作区 **112** 项、严格 Clippy、前端 **179** 项、真实 IPC **11** 项及进程故障检查。
锁定离线构建、**928** 份 Rust/Cargo 输入与二进制前后 hash 一致；两端 source bundle 校验通过。
本轮额外 **29** 项既有原生回归全部通过，共 **48** 项当前二进制原生检查。包含两项预期崩溃阻塞负例；完整家族矩阵为 **8 GUI / 32 PTY / 72 PID marker**、24 次快速操作、完整反向、**68** 张 root 采样与 **26** 条 WGPU scene 回执。

撤除记录仍最多 64 个 exact token。新协议的旧证明重确认使用经验证的全局单调撤除记录，
只覆盖已经越过的旧 epoch，不能清除更高的当前身体，也不证明任意 tuple 曾被授予。
**70 次**授予/撤除、压缩、重启与旧证明重放通过真实协调器 IPC；其中 serial 是声明的协议夹具，
没有计为 70 次原生 scene 证明，旧客户端 exact-token 路径保留。

原生回归还保留一次图像检测误报：GuardFailure 的 Dim/Effect 装饰云朵被算作第二个身体。
修正只按图谱颜色关系区分身体与装饰，没有扩大连接距离或降低像素门槛。4 项 PNG 检测测试
包含两个仅相隔 24 像素的身体；修复前 3 项失败、之后全部通过，已接入 CI。
对 **686** 张既有真实截图的 **1,752** 个窗口区域重放，原先观察到的身体窗口均保留，
装饰不再成为另一身体；原场景用相同二进制重新运行并完成真实关闭/接管。
原 19 项取消与先前 9 项通过回归的状态/scene 证据沿用同一二进制原运行，画面重新分类；
没有把图片重放称为新的原生运行，也没有改写原失败报告。

[本轮机器证据](evidence/withdrawal-resume-checks-2026-10-31.json) 区分真实产品失败、夹具错误、初步结果与当前 48 项原生检查。93 个私有 runtime 路径的进程清理审计未发现匹配残留；两个不可读环境属于本任务之前的用户 systemd/sd-pam 会话，未操作。精确二进制、八仓库 Git 基线及源码补丁另存本地快照。 离线重建核对 **2,630** 份家族 Rust/Cargo 文件、**928** 份实际编译输入及 **7** 个精确二进制，重建后的 4 项 PNG 检测也通过；不等于独立可复现的位级构建或硬件验收。
前台接管夹具会暂停原私有 shell，排除它先前已阻塞的 stdin read，工作结束后恢复同一个 shell；
这不等于正常 fg 或 shell 先退出/子进程存活验收。最初长按 Enter 测试错误地等待仍按住时
显示身体，已改为先验证按键归属与真实释放，输入保护没有放宽。外部剪贴板探测未计入验收。

全部原生操作仍在独立 Xvfb/home/XDG/DBus/二进制副本内；scene 与 token 证据独立于 PNG，
保持 NativePresented 范围，未提升为 CompositorPresented 或连续物理唯一性。
真实 provider/远程角色、shell exec/builtin/后代生命周期、原生超过 64 次压缩、
其他端 Vim9、同进程多窗、休眠、真实 IME/审批/记忆/语音/API、C11 可信 fence/锚点、
性能及发布仍未完成。完整 C01–C12/P0–P7 目标继续保留。

## 2026-10-31 显式命令 PTY 角色与关闭确认（前一轮记录）

两端原先都把 foreground PGID == PTY child PID 直接视为空闲；显式 argv 启动的
一次性命令、CLI 本身也可以同时是 PID/PGID/SID/foreground。真实原生基线中，
Frost 普通 WM 关闭结束 GUI，Ember 普通 WM 关闭结束命令；两次首信号均为 SIGHUP。
现 Ember 使用已有 SessionPurpose，Frost 从实际 spawn argv 记录 command_owned：
活的命令根进程继续阻止普通整窗关闭。Frost 标签/批量关闭也使用实时 PTY 与会话角色
进入原有确认流程，进程名缓存仅供显示。退出后的 transcript 和交互 shell 保持单独语义。

| 当前二进制原生场景 | 结果与证据 |
|---|---|
| [Ember 命令根进程](evidence/native-command-role-ember-owned-command-2026-10-31/command-role-report.json) / [Frost](evidence/native-command-role-frost-owned-command-2026-10-31/command-role-report.json) | 由真实 GUI 创建独立 PTY；内核 PID=PGID=SID=foreground，PPID 为源 GUI。普通关闭后命令与 GUI 存活；受控结束后窗口继续保留，新的关闭请求经过新的 scene 回执与精确 token 撤除，另一 GUI 接管 |
| [Ember 后台标签](evidence/native-command-role-ember-owned-command-background-2026-10-31/command-role-report.json) / [Frost](evidence/native-command-role-frost-owned-command-background-2026-10-31/command-role-report.json) | 切回原 shell 后，通过实际原生输入产生其 PID marker，核对该 shell 空闲且命令仍活；整窗保护覆盖非活动命令标签。初测只发切换快捷键的较弱证据另存，最终用例均重跑 |
| [Frost 命令标签确认/取消](evidence/native-command-role-frost-owned-command-tab-2026-10-31/command-role-report.json) | 首次关闭标签保持命令与 GUI；Escape 取消仍存活。再次明确 Enter 确认才结束受控命令，原 shell/窗口继续；最终整窗关闭完成精确撤除 |
| 关闭与窗口回归 | 当前二进制重跑 5 项撤除等待/Vim9/最后窗格、8 项工作/可见缩放、8 项 surface（含两项预期崩溃阻塞）、2 项 authority 丢失/重启，均满足各自检查 |
| [完整家族矩阵](evidence/native-matrix-command-role-final-2026-10-31/matrix-report.json) | 8 GUI / 32 独立 PTY / 72 个真实输入 PID marker / 8 宿主连接；冻结旧 owner、24 次快速操作和完整反向通过；77 张 root PNG 采样最多一个默认 Cat 身体，WGPU 接受 23 条 scene 回执 |

入口均为现有原生 UI：Frost 使用 coding-CLI palette；Ember 使用实际任务 composer、
私有 Git 副本、真实隔离 worktree、持久登记与 Start。私有 PATH 中的 codex/opencode
仅为本地 Python 进程夹具，不调用 provider/模型，不生成伪造 TaskFacts 或呈现证明。
这证明命令 PTY 的关闭语义，不构成真实 Codex/OpenCode/jagent 任务验收。Ember
仅在独立测试配置开启其既有任务启动 gate，日常配置与仓库未改。

本轮实际检查：Ember **6** 项窗口 / **2** 项 Eva，Frost **69** 项关闭 / **11** 项 Eva，
两端 locked/offline 构建、编译输入前后 hash 和修改文件格式通过。Frost Eva adapter
只有 rustfmt 排版变化，其 focused tests 已重跑。精确匹配其余 **8,745** 份既有文件、
协调器二进制及 28 份编译输入后，明确沿用 **77/7** 协调器/IPC、**7/9** receipt harness、
**8** 输入与此前记录的 lint；没有宣称重跑或完整前端 Clippy 全绿，原有依赖警告保留。

[机器证据](evidence/command-role-checks-2026-10-31.json) 区分真实失败、配置夹具失败、
非验收 UI 探索、较弱初测与最终 **29** 项原生检查，保留原始报告、首信号、harness、
最终 residence.json 和 PNG；[画面核对](evidence/command-role-checks-2026-10-31/visual-review.json) 另记范围。
私有 runtime 清理审计、精确二进制及离线源码重建快照另存；
没有替换日常安装，没有提交或发布。

下一步仍需同一宿主的显式取消 withdrawal/重新准入协议；不得丢弃旧 token 证明、
生成新 host ID 绕过等待，或默默改变旧 Recall 的含义。真实 provider/远程会话、shell
builtin/exec 与更多子进程生命周期、其他端 Vim9、同进程多窗、休眠、IME/记忆/审批实际 UI、
语音/API、C11 可信 fence/锚点及性能/发布仍未完成。完整 C01–C12 范围继续保留。

## 2026-10-31 撤除等待期任务保护与嵌入式 Vim9（前一轮记录）

本轮新增真实 PTY 竞态：通过原生终端输入启动后台 Python，暂停私有 JWM，在正常
WM_DELETE_WINDOW 关闭已发布清除帧、但 scene 回执未到时，让该任务取得其实际
PTY 前台进程组。恢复 JWM 后核对新 scene 回执与精确旧 token 撤除；没有注入宿主、
任务或呈现证明。这个受控场景测试真实前台工作与关闭意图，不等于普通 shell fg 操作验收。

修复前，Ember 会在新任务结束后沿用旧意图自动退出；Frost 会在任务仍在运行时退出，
重复实测的首个终止信号为 SIGHUP。现两端保留已经开始的撤除与原始证明，另暂停 GUI
退出；任务出现后再次关闭仍拒绝，结束任务也不构成新的退出授权。Frost 使用当前
kernel PTY 前台组，关闭等待不再依赖标题的进程名缓存；保留窗口时解除关闭遮罩、
恢复终端输入。明确确认关闭最后一个窗格继续走其原有进程确认与持久化退出路径。

| 当前二进制原生场景 | 结果与证据 |
|---|---|
| [Ember 等待期任务](evidence/native-close-intent-ember-late-job-2026-10-31/close-intent-report.json) / [Frost](evidence/native-close-intent-frost-late-job-2026-10-31/close-intent-report.json) | 实际前台任务、原始撤除证明与 GUI 分别核对；新工作存活，重复关闭拒绝；任务结束后仍保留窗口，并执行真实终端输入 marker，重新关闭正常退出，另一 GUI 接管 |
| [Ember 嵌入式 Vim9 保存/整窗关闭](evidence/native-close-intent-ember-embedded-save-2026-10-31/close-intent-report.json) | 自带 bridge 的真实 Vim9、独立 PTY、connected 与 modified=1 来自 Vim 引擎。未保存时 WM 关闭拒绝且文件不变；原生 :w 精确保存而编辑器/GUI 继续存活，之后明确 :q 完成原关闭意图，经过实际新 scene 回执与精确 token 撤除才退出 |
| [Ember 仅退出编辑器](evidence/native-close-intent-ember-embedded-editor-exit-2026-10-31/close-intent-report.json) | 没有整窗关闭意图时，原生保存与 :q 仅退出 Vim9；原 shell/GUI 继续，身体恢复；新的窗口关闭请求才退出。与上一轮外部 alternate-screen Vim 分开验收 |
| [Frost 最后窗格明确确认](evidence/native-close-intent-frost-late-final-tab-2026-10-31/close-intent-report.json) | 已为新前台任务保留窗口后，原生关闭最后窗格先保持任务与 GUI；用户 Enter 明确确认后才终止该工作并正常退出；实际旧 token 撤除继续成立 |
| 原有窗口与 compositor 回归 | 当前两端二进制重跑 8 项工作/可见缩放、8 项 surface（含两项预期崩溃阻塞）、2 项 authority 丢失/重启，均满足各自检查 |
| [完整家族矩阵](evidence/native-matrix-close-intent-final-2026-10-31/matrix-report.json) | 8 GUI / 32 独立 PTY / 72 个真实输入 PID marker / 8 宿主连接；冻结旧 owner、正向、24 次快速操作和完整反向通过；77 张 root PNG 采样最多一个默认 Cat 身体，WGPU 接受 27 条 scene 回执 |

实际重跑：Frost **68** 项关闭相关与 **11** 项 Eva 测试、Ember **5** 项窗口与 **2** 项 Eva
测试，两端 locked/offline 构建及编译输入前后 hash 通过。已匹配精确 coordinator 二进制
与全部编译输入、JWM 源码，以及 receipt/key harness 源码：上一轮 **77/7** 协调器/真实
IPC、**7/9** receipt harness 和 **8** 输入测试及其已记录 lint 结果明确沿用，未宣称本轮重跑。
Frost 两条原有 iced_winit 弃用警告仍保留，没有宣称完整前端 Clippy 全绿。

[机器证据](evidence/close-intent-checks-2026-10-31.json) 留存修复前真实失败、首信号记录、
较弱中间通过、嵌入式 Vim9 初测、最终当前二进制、harness、最终 residence.json 与 PNG。
[人工画面核对](evidence/close-intent-checks-2026-10-31/visual-review.json) 另记具体截图与范围。
私有 Xvfb/home/XDG/DBus 环境清理后 /proc 审计无残留；本地快照保留精确二进制与源码，
日常安装未替换，未提交或发布。

完整范围继续保留：暂停 GUI 关闭并没有撤销已经开始的宿主 withdrawal；取消关闭后重新
允许该窗口驻留身体的协议仍待补齐。直接命令/Agent CLI 型 PTY 与远程会话，需要按
实际子进程角色补充关闭保护，不能仅凭 foreground==child PID 推定交互 shell 空闲。
其他前端嵌入式 Vim9、取消关闭 UI、同进程多窗、实际休眠/恢复、IME/选区/滚动、语音/API、
C11 可信 fence/锚点与性能/发布仍未完成；两条已知 Ember UI 基线失败继续保留。

## 2026-10-31 真实任务关闭保护、准备重试与按键释放（前一轮记录）

本轮原生运行找到并修复三项问题：

- Ember 普通 WM 关闭会让真实前台 Python 任务收到 SIGHUP。现在关闭前检查所有交互窗格的实际 PTY 前台进程组；无法确认空闲也拒绝关闭。首次拒绝后不保留自动关闭意图，任务结束仍须重新关闭。显式进程终止保持原有行为。
- 接收端安全区域在 Prepare/Prepared 之间短暂失效后，协调器会永久停在 preparing。现在仅在同一目标的区域重新有效时重发已持久化 epoch 的 Prepare；旧身体在有效 Prepared 前继续保留，旧 epoch 仍被拒绝。新增两项真实 IPC 回归在修复前稳定失败。
- Ember 输入 `:`、`{`、`}` 时，按下和释放事件的逻辑符号可能不同。真实诊断观察到键已经释放、Vim 已退出，但 egui 的 held-key 集合仍保留这些符号，Eva 持续被输入保护隐藏。现在按已知物理键配对原始逻辑按下/释放与重复，失焦清空映射；当前 Text/剪贴板语义和未知键回退继续保留。

| 当前二进制原生验收 | 结果与证据 |
|---|---|
| [Ember 前台任务](evidence/native-window-use-ember-busy-2026-10-31/window-use-report.json) / [Frost](evidence/native-window-use-frost-busy-2026-10-31/window-use-report.json) | 普通 WM_DELETE_WINDOW 请求后，真实 Python、GUI 和 PTY 身份保持；原生 Ctrl+C 仅结束精确任务，窗口继续保留。重新关闭取得新 native scene 回执和精确 token 撤除，存活 GUI 接管 |
| [Ember 非活动窗格任务](evidence/native-window-use-ember-busy-background-2026-10-31/window-use-report.json) / [Frost](evidence/native-window-use-frost-busy-background-2026-10-31/window-use-report.json) | 实际按键分屏，独立新 PTY 的原生 PID marker 证明当前活动窗格空闲；另一窗格仍运行原任务，整窗关闭保护仍成立，随后回原窗格 Ctrl+C 与全流程关闭通过 |
| [Ember 外部 Vim](evidence/native-window-use-ember-external-vim-2026-10-31/window-use-report.json) / [Frost](evidence/native-window-use-frost-external-vim-2026-10-31/window-use-report.json) | 真实 /usr/bin/vim、原生按键编辑、引擎 &modified=1；拒绝关闭期间文件仍为原值。:wq 后精确保存编辑文本，GUI 未自动关闭，新请求完成撤除。此项与嵌入式 Vim9 IDE 分开 |
| [Ember 已映射缩放](evidence/native-window-use-ember-mapped-resize-2026-10-31/window-use-report.json) / [Frost](evidence/native-window-use-frost-mapped-resize-2026-10-31/window-use-report.json) | 同一可见原生窗口依次 1184×940、1304×1060、1344×1100；核对实际 map state/尺寸、身体收敛、原宿主往返和真实终端输入 |
| 映射/关闭/崩溃与 compositor 回归 | 当前二进制重验 8 项 surface 场景及两端 authority 丢失/重启；两项 SIGKILL 仍保持精确旧 token 与 recovery_blocked，属于预期阻塞负例 |
| [完整家族矩阵](evidence/native-matrix-window-use-final-2026-10-31/matrix-report.json) | 8 GUI / 32 独立 PTY / 72 个实际输入 PID marker / 8 宿主连接；冻结旧 owner、正向、24 次快速操作、完整反向通过；69 张 root PNG 采样最多一个默认 Cat 身体，WGPU 接受 26 条 scene 回执 |

实际重跑协调器 **77** 工作区测试、严格 all-target Clippy/格式、**7** 真实 IPC 与进程故障契约。
Ember egui/winit **8** 项输入测试、严格 all-target Clippy/修改文件格式和 **5** 项窗口测试通过。
两端 locked/offline 构建及 Rust/Cargo 输入前后 hash 一致；receipt harness 的 7/9 结果仅在核对其生产源码、Cargo 和 harness 输入与前一验收快照相同后沿用，未声称本轮重跑。

[机器证据与全部原始日志](evidence/window-use-checks-2026-10-31.json) 区分真实任务丢失、准备停滞、逻辑键卡住与较早的测试假设失败。
PTY 空闲不意味着有安全画布：中断后提示符可能共享一行；Ember 测试先确认任务退出且一秒未自动关闭，再通过实际空回车建立可用提示符。此项没有放宽几何/输入保护；Vim 在新提示符后仍失败的原始记录及 held-key 诊断同样保留。
私有测试使用独立 Xvfb/home/XDG/DBus 和二进制副本，清理后 /proc 审计无残留自建进程。精确二进制与源码补丁存入本地验收快照，未改日常安装。

尚未完成：嵌入式 Vim9 对话框/延迟关闭、关闭等待期新任务进入、同进程多原生窗、实际休眠/恢复、IME/选区/滚动、其他驱动/后端、真实语音/API、C11 可信 fence/锚点、多屏及性能/发布。采样不证明连续物理唯一性；没有提升为 CompositorPresented，已有两条 Ember UI 基线失败仍保留。

## 2026-10-31 窗口代际、正常关闭与崩溃负例（前一轮记录）

同尺寸重映射的初步往返曾通过，但日志显示隐藏前的 counter 仍跨映射被接受。
这只能证明往返，不能证明旧回执隔离。新增精确 counter 断言后，Ember/Frost 均在
真实 GUI 中失败，两个原始 false 报告保留；没有把初步通过当成代际验收。

现接入服务端 MapNotify/UnmapNotify，在 IME 过滤与应用回调前作废 native flight、
部分回执和旧缩放控制值；计数保持单调。隐藏不签发证明、不专门唤醒隐藏绘制；
映射后唤醒一次新绘制。begin/finish 另核对 X11 实际 VIEWABLE，未映射 backing
不能发布证据偶数。交接必须等新一代真实发布和合成回执，旧 counter 不能复活。

| 当前最终二进制场景 | 结果 |
|---|---|
| [Ember 同尺寸重映射](evidence/native-surface-ember-remap-2026-10-31/surface-report.json) / [Frost](evidence/native-surface-frost-remap-2026-10-31/surface-report.json) | 暂停 JWM，真实清除已发布且回执未到；实际 unmap、remap 后保持同一原生窗口、尺寸和 GUI 宿主。旧 counter 始终被拒绝，新帧完成往返与真实输入 |
| [Ember 缩放 ABA](evidence/native-surface-ember-resize-2026-10-31/surface-report.json) / [Frost](evidence/native-surface-frost-resize-2026-10-31/surface-report.json) | 未映射 backing 实际缩小再恢复原尺寸，然后重映射；旧回执拒绝、原宿主往返和真实输入通过。此项不代表全部已映射缩放/多屏场景 |
| [Ember 正常关闭](evidence/native-surface-ember-close-2026-10-31/surface-report.json) / [Frost](evidence/native-surface-frost-close-2026-10-31/surface-report.json) | 普通 WM_DELETE_WINDOW 关闭；新清除帧的 scene 回执和精确 token 撤除成立，源 GUI 正常退出，存活 GUI 获得身体。未使用强制关闭/超时成功 |
| [Ember 崩溃负例](evidence/native-surface-ember-crash-2026-10-31/surface-report.json) / [Frost](evidence/native-surface-frost-crash-2026-10-31/surface-report.json) | 真实 SIGKILL；4 秒观察中保持精确旧 token 与 recovery_blocked，未授权替代。属于预期阻塞负例，**不是崩溃自动恢复通过** |
| [compositor 丢失/重启](evidence/native-surface-ember-authority-2026-10-31/lifecycle-report.json) / [Frost](evidence/native-surface-frost-authority-2026-10-31/lifecycle-report.json) | 新版两端重新通过界面/像素恢复、无伪造 scene 回执及替换 JWM 往返，回归上一轮修复 |
| [完整家族矩阵](evidence/native-matrix-surface-final-2026-10-31/matrix-report.json) | 8 GUI / 32 PTY / 72 个真实输入 marker / 8 宿主连接；冻结旧 owner、完整正向、24 次快速操作、完整反向遍历通过；72 张 root PNG 采样最多一个默认 Cat 身体 |

生产源码 harness：Ember **7/7**、Frost **9/9**，严格 Clippy/格式通过。
两端 locked/offline 构建通过，记录的 Rust/Cargo 输入前后一致。协调器/JWM 本轮未改；
协调器可执行文件与全部已记录编译输入逐一匹配上一轮，故沿用其 77 工作区测试、5 IPC
和进程故障证据，不声称本轮重跑。最终矩阵四份 WGPU 窗口接受 **26** 条 scene 回执。

[本轮机器证据](evidence/surface-lifecycle-checks-2026-10-31.json) 保存 8 项窗口场景、
两项 compositor 回归、完整矩阵、严格失败基线、源码与二进制 hash、harness 和 PNG。
15 个本轮私有 runtime 的 `/proc` 审计没有残留自建进程；精确二进制与源码补丁已做
本地快照。未发布、未替换日常桌面程序。

完整范围仍未完成：已映射缩放、同进程多窗、忙任务/Vim 关闭保护、真实休眠/恢复、
部分/丢失回执、其他后端/驱动/外观、真实 IME/语音/API、可信单节点 fence/锚点、
性能与发布继续保留。崩溃自动恢复需要可信表面销毁证明；窗口消失或经过时间不能替代。

复现命令（私有 Xvfb/DBus/home，浮动规则仅用于保持测试尺寸）：

```sh
env -u SSH_CONNECTION -u SSH_TTY XDG_SESSION_ID=eva-native-test \
  python3 tests/native_surface_lifecycle.py --daemon /absolute/jcompaniond \
  --host ember=/absolute/ember --wm /absolute/jwm --shell /absolute/jsh --case remap
# --case resize / close / crash；Frost 使用 --host frost=/absolute/frost，无需 --shell。
```

## 2026-10-31 compositor 生命周期与迟到呈现修复（前一轮记录）

本轮实际复现并修复两个独立缺陷：

- **所有权丢失后的 UI 停滞**：真实清除帧已发布、JWM 被暂停且合成回执未到时，
  清空私有 X11 compositor selection 后，旧版 Ember 仍不能处理排队输入。
  现接入 XFixes 真实所有权事件及 JWM root marker 变化；作废旧帧与旧缩放控制值，
  保持 counter 单调，并唤醒延后绘制。同编号 owner 被复用也会失效；事件本身不产生证明。
- **快速交接时 daemon 退出**：旧身体的迟到 Presented 可把 preparing 改为 active，
  同时残留目标宿主，随后驻留日志校验失败。现在仅在 Granted/Active 阶段接受 Presented；
  新目标仍须准备完成，旧 token 仍须精确撤除。单元与真实 IPC 新回归均先失败、修复后通过。

| 当前最终二进制复验 | 结果 |
|---|---|
| [Ember 所有权丢失/重启](evidence/native-authority-ember-final-2026-10-31/lifecycle-report.json) | 两个真实 GUI；无后续输入/缩放即恢复排队输入与 native 像素更新；没有新 scene 回执，精确旧 token 仍阻塞；新 JWM 就绪后往返通过 |
| [Frost 所有权丢失/重启](evidence/native-authority-frost-final-2026-10-31/lifecycle-report.json) | 两个真实 GUI；除键盘 marker 外，另核对实际 native 像素和新 Vulkan 完成，避免误判 iced 模型更新为绘制恢复；旧 token 阻塞与往返均通过 |
| [完整八窗口矩阵](evidence/native-matrix-authority-final-2026-10-31/matrix-report.json) | 8 GUI / 32 独立 PTY / 72 个真实输入 PID marker / 8 宿主连接；冻结旧 owner、全部正向访问、24 次快速操作及完整反向遍历通过 |
| 协调器与生产源码检查 | **77** 工作区测试、**5** 真实 IPC 场景、进程故障、严格 all-target Clippy/格式通过；Ember **6/6**、Frost **8/8** receipt harness 及其严格 Clippy/格式通过；三个 locked/offline 构建与 Rust/Cargo 输入 hash 通过 |

两端实际重启均复用了 compositor owner 数字编号；旧回执没有因此复活。
最终矩阵保留 **66** 张 root PNG，采样最多一个默认 Cat 身体；四份 WGPU 窗口共
**24** 条接受的 scene 回执。Native backing PNG 逐张校验解码后像素 hash，
与冻结的 compositor root 分开记录。键盘 marker、像素变化、Vulkan 完成与合成证明
各有独立含义；这些观察不作为性能或物理 scanout 证明。

原始失败未改成通过：[修复前 UI 挂起](evidence/native-authority-loss-before-fix-2026-10-31/lifecycle-report.json)、
[新 WM 初始化焦点尝试](evidence/native-authority-frost-startup-attempt-2026-10-31/lifecycle-report.json)、
[Ember 非证据绘制探针尝试](evidence/native-authority-ember-probe-attempt-2026-10-31/lifecycle-report.json)、
[触发 daemon 日志校验退出的矩阵](evidence/native-matrix-authority-preparing-failure-2026-10-31/matrix-report.json)
及其单元/IPC 修复前日志均保留。最后一组已完成 72 输入检查和正向遍历，快速阶段失败，
没有完整反向结果；不能用最终通过回写该报告。

[本轮机器证据与来源](evidence/authority-lifecycle-checks-2026-10-31.json) 包含准确二进制、
源码 hash、构建和回归日志、全部原生报告与 harness。13 个本轮私有 runtime 的
`/proc` 审计无残留自建进程；本地验收快照保留可执行文件与源码补丁，尚非发布安装。
其他 compositor/后端、关闭/崩溃/重映射/缩放/休眠、IME、语音/API、可信单节点和
性能/发布验收仍未完成；本轮没有提升为 CompositorPresented。

原生生命周期复现命令（私有 Xvfb/DBus/home，两个实际 GUI）：

```sh
env -u SSH_CONNECTION -u SSH_TTY XDG_SESSION_ID=eva-native-test \
  python3 tests/native_lifecycle.py --daemon /absolute/jcompaniond \
  --host ember=/absolute/ember --wm /absolute/jwm --shell /absolute/jsh
# Frost 使用 --host frost=/absolute/frost，无需 --shell。
```

## 2026-10-31 发布帧关联与完整矩阵复验（前一轮记录）

已修复 Ember/Frost 过早把 native queue/present 返回当成撤除回执的路径：
Vulkan 实际呈现附带单调 ID，必须收到该 ID 的 `vkWaitForPresentKHR` 成功，才发布
X11 扩展偶数计数。随后还必须收到当前 compositor 的同计数 Drawn 与非零已知 Timing，
才能把原始 UI pass / 已捕获的树快照交给宿主 gate。旧 grant、旧窗口 registration、
未来/重放计数、零时间与超时均不能升级为成功。此原型只接受 owner 绑定的 JWM marker。

还补齐每窗单帧等待：证据帧等待合成回执时暂停 native redraw，保留排队输入/纹理数据，
避免新计数持续淘汰上一份回执；尺寸变化会作废旧帧。完整未知时间对可以解除节奏、
重试新帧，但不会产生证明。未发生延后绘制时，成功回执本身不启动重绘循环。
该链路仍属于 `NativePresented`；不是物理 scanout 或可信 `CompositorPresented` 证书。

| 实际复验 | 结果 |
|---|---|
| [仅发布、尚未限流的中间版本](evidence/native-matrix-unpaced-publication-2026-10-31/matrix-report.json) | 8 GUI / 32 PTY / 72 输入检查成立；Ember→Ember 等待撤除证明，持续发布的新计数使旧场景回执失效；整组失败，原报告保留 |
| [发布与帧节奏修复后的完整矩阵](evidence/native-matrix-published-paced-2026-10-31/matrix-report.json) | **通过**：8 个真实 GUI、32 个独立 PTY、72 个实际输入 PID marker、8 个独立宿主与连接；冻结旧 owner 4 秒、全部正向访问、24 次快速焦点/分屏操作、完整反向遍历均完成 |
| [最终 Ember↔Forge](evidence/native-published-ember-forge-2026-10-31/report.json) | 同一最终二进制往返、冻结 Ember 4 秒、daemon SIGKILL/重启恢复通过；真实 jsh 任务 marker 核对完成 |
| [最终 Frost↔Forge](evidence/native-published-frost-forge-2026-10-31/report.json) | 同一最终二进制往返、冻结 Frost 4 秒、daemon SIGKILL/重启恢复通过 |
| [不支持的发布驱动负例](evidence/native-unsupported-publisher-2026-10-31/report.json) | 强制软件 Vulkan 驱动后，Ember 实际身体出现，但没有发布/合成证明；切换 Forge 后保留旧 owner、停在 awaiting_removal_proof，没有允许替代身体。原始 `passed=false` 保留，负例预期另行核对通过 |

完整矩阵的 70 张实际 root PNG 均未触发多窗或窗内多身体检测。四份 WGPU 窗口共 27 条
Vulkan 完成、27 条 native 发布和 27 条已接受的 scene 回执相对应；包含此前实际出现
双 Ember 的同一负载、检测规则与窗口/分屏配置。代表性全景已人工查看，仍只支持采样结论。
截图先于 journal 读取，不把二者视为原子证据，也不推算迁移延迟或连续物理唯一性。

直接编译生产 receipt/scope 代码的 harness：Ember **4/4**、Frost **6/6**；两份严格
Clippy 与格式检查通过。Frost Eva 聚焦测试 **11/11**；两端 locked/offline 最终构建通过，
构建前后 Rust/Cargo 输入 hash 一致。删除了只搜索旧“提交后回调”源码字符串的断言，
以真实状态/registration 生命周期测试和原生矩阵替代；没有放宽像素或交接 gate。
新增独立 CI job，尚未声称远端 CI 已运行。

[机器检查与来源](evidence/frame-feedback-checks-2026-10-31.json) 记录准确二进制、源码、
全部原始报告/PNG、72 个输入 marker、数字化 compositor 日志及 harness 快照。
最终测试退出后，按全部八个本轮私有 runtime 目录核对 `/proc`，没有残留自建测试进程。

**整体方案仍未完成**：其他 compositor、Glow/Wayland、真实 IME/选择/滚动、关闭/崩溃/
休眠与 compositor 重启、真实语音/API、记忆/任务 UI、可信单节点 fence/锚点、性能和
发布验收继续保留。Ember 先前独立基线的两条 UI 断言失败也未被改写为通过。

## 2026-10-31 多实例矩阵与新缺陷（历史两轮）

新增 `tests/native_matrix.py`，实际打开四端各两份 GUI，每份四个 split。
已核对 8 个真实 GUI、32 个独立 PTY/session leader，以及 72 次真实 GUI 输入写出的
shell PID。方向键逐个返回预期 shell；jsh 使用内核 raw/no-echo 状态确认编辑器就绪，
不把刚出现的进程或短暂继承同一 PTY 的 fork helper 当成就绪的新 pane。
截图还按默认 Cat 的空间区域分组，以发现同一窗口多个 split 中的独立身体；该分类
已与此前保留的 35 张原生图逐一比对，计数均一致，仍不是任意皮肤/连续物理证明。

发布帧关联修复之前，两次完整尝试均未通过，原结果保留：

| 尝试 | 实际结果 |
|---|---|
| [轮转修复前](evidence/native-matrix-before-fairness-2026-10-31/matrix-report.json) | 8 GUI / 32 PTY 与输入路由通过；冻结旧 Forge 时阻塞替代，但恢复后旧身体仍可见，交接持续 awaiting_removal_proof |
| [轮转修复后](evidence/native-matrix-after-fairness-2026-10-31/matrix-report.json) | 冻结后继续走过 Forge↔Forge、Anvil 和第一份 Ember；进入第二份 Ember 时，[同一张实际合成画面出现两个身体](evidence/native-matrix-after-fairness-2026-10-31/023-waiting-ember-2.png)，整组返回非零；尚未执行 rapid burst 与完整反向遍历 |

本轮 JWM 修复普通窗口纹理刷新的饥饿问题：原有 3ms 预算按固定场景次序服务，
前部持续脏的窗口可能让后台旧身体一直排不到刷新。现在以最后一个实际成功刷新的
普通窗口为游标轮转，焦点和状态栏保持优先，预算/音频节奏/失败导入退避保持原规则。
新增受限预算下的公平服务回归；相关范围 **298 passed**、严格 all-target Clippy、
修改 Rust 文件格式检查和 XCB 编译均通过。

这修复了先前的停滞，但没有解决所有原生撤除证明：WGPU 的 queue/present 提交回调
不能证明旧窗口画面已经从 compositor 的合成结果中清除。双身体是实际 PNG 中的两个
图形，不是仅由非原子的 journal/截图时序推断；随后一张图中旧身体才消失。
这些结果要求把 X11 WGPU/iced 的撤除回执关联到 compositor 实际处理的清除帧。
这两次历史尝试本身不能支持多实例单身体或发布通过；后续修复复验见上节。

[检查与来源](evidence/matrix-checks-2026-10-31.json) 包含准确二进制 SHA、日志与限制；
报告旁保留了运行时的完整 harness 快照、全部 72 个输入 PID marker 和代表性 PNG。
[独立 Ember 四分屏输入诊断](evidence/native-ember-split-diagnostic-2026-10-31/split-diagnostic.json)
与 [两份 Forge/各四分屏冻结恢复诊断](evidence/native-forge-split-freeze-diagnostic-2026-10-31/split-freeze-diagnostic.json)
通过，仅支持各自的窄范围，不替代失败的完整矩阵。

完整矩阵复现命令（使用对应报告的二进制与 harness）：

```sh
env -u SSH_CONNECTION -u SSH_TTY XDG_SESSION_ID=eva-native-test \
  python3 tests/native_matrix.py --daemon target/debug/jcompaniond \
  --host forge=/absolute/forge --host anvil=/absolute/anvil \
  --host ember=/absolute/ember --host frost=/absolute/frost \
  --wm /absolute/jwm --shell /absolute/jsh --desktop-shell
```

这在私有 Xvfb/home/XDG/DBus 中运行；为各测试窗口启用 JWM 现有 shortcut passthrough，
使 Ctrl+Alt 方向键到达前端。此场景还启用了私有 JWM desktop shell 负载；默认独立
测试会显式禁用可选 shell 配置。它不证明正常桌面快捷键冲突已经解决，也未测试
真实中文 IME、音频采集/播放、模型 API 或性能预算。

## 本轮已落地

协调器从已发布 `9aa569540091524d637a7115b64c587b9177a55b` 恢复到独立工作树。
真实 IPC 集成测试首先复现了任务串台：A 任务失败后切到 B pane，身体仍显示 A 的
`guard_failure`。现在任务事实按任务 ID 保存；行为调度仅取当前上下文匹配的事实。
迟到的后台回执不会替换前台任务，旧 revision 的拒绝也不会因观察了其他任务而失效。
缓存达到明确上限时返回错误，不静默丢弃旧回执。

- `cargo test --workspace --locked --offline`：76 passed，0 failed，0 ignored。
- `cargo clippy --workspace --all-targets --locked --offline -- -D warnings`：通过。
- `tests/fault_processes.py`：真实 daemon、Unix socket、profile 独占、宿主 SIGSTOP/
  SIGCONT、daemon SIGKILL/重启、精确旧 token 撤除、伪造证明拒绝、断连阻塞均通过。
- `tests/ipc_contracts.py`：4 项真实 IPC 集成场景通过，已加入 CI。覆盖当前任务隔离与
  每任务 revision、选区原文/单次授权、记忆审阅/作用域/归档管理/持久删除、语音租约
  排他/重启保留/精确 owner 释放。均使用新建的离线 profile，无模型或音频设备调用。

上一轮协调器与 Anvil/Forge/Ember/Frost 的初始源码构建均通过，二进制 SHA 与来源见
[`source-builds-2026-10-30.json`](evidence/source-builds-2026-10-30.json)。
Frost 构建保留两条既有 iced_winit 弃用警告，未宣称四端严格 Clippy 通过。
本轮 [工作区检查](evidence/local-checks-2026-10-30.json)、
[真实 IPC 结果](evidence/ipc-contracts-2026-10-30.json)、
[进程故障记录](evidence/process-faults-2026-10-30.txt) 与
[修正配置后的 Forge/Anvil 原生报告](evidence/native-forge-anvil-final-2026-10-30/report.json)
分别留档。早期沙箱拒绝和无效测试配置的记录仍保留，并与最终验证区分。

## 本轮原生交接已落地

JWM 新增显式 `JWM_X11_FRAME_SYNC=1` 的 X11 扩展帧回执。独立线程观察真实 XSync
计数器，按窗口 generation/原生 counter resource 关联成功的 scene swap；真实
compositor selection 失效、旧 generation/未来/重放帧、已移除窗口或失败导入都不会被当作成功。
渲染线程只读取不可变快照，以非阻塞队列投递 swap 结果；没有用超时或预估时间制造非零呈现值。

这里使用的是协议允许的实际邻近 swap 时间。它是 NativePresented 提交级证据，
不等于物理 scanout/GPU fence，也没有把 JWM 单节点的退休能力从 None 提升为
CompositorPresented。实现与限制见 sibling `jwm/docs/x11-frame-feedback.md`。

原生验收同时找到并修复 Ember 的尺寸错误：既有结构空白被限制为 88px 高，而
共享 atlas 的 22 行需要约 242px。现在优先使用真实既有 padding，不加正文行，
保留输入/IME/选区/滚动保护和空间不足的 Compact/Hidden。加强后的回归先失败、
修复后通过；6 项相关几何/保护测试通过。

| 当前源码原生场景 | 结果与证据 |
|---|---|
| Forge↔Anvil | [通过](evidence/native-jwm-forge-anvil-2026-10-30/report.json)：初始可见、往返、SIGSTOP 4 秒保留精确旧 token 并阻塞替代、SIGKILL daemon 后保留身份/新 boot 恢复 |
| Ember↔Forge | [通过](evidence/native-jwm-ember-forge-2026-10-30/report.json)：同上；真实 jsh printf 任务执行和私有结果 marker 通过，实际画面显示完整身体 |
| Frost↔Forge | [通过](evidence/native-jwm-frost-forge-2026-10-30/report.json)：同上；冻结期间的实际截图仍显示 Frost 身体，Forge 未出现替代身体 |
| 相同 JWM 二进制关闭 frame sync | [预期未通过](evidence/native-jwm-negative-2026-10-30/report.json)：GTK 初次呈现停在 granted，撤除后持续 awaiting_removal_proof；没有降低 GTK/协调器门槛 |

这三组双窗口场景覆盖四个前端，不等于四端同时多实例、多 split 或所有配对验收。
JWM compositor 范围 **297 tests passed**、严格 all-target Clippy 和修改文件格式检查
通过，XCB 路径编译通过；XCB 原生运行尚未验证。Ember 扩大的 UI 范围为 77 pass /
2 fail，独立干净 `c21dbf6` worktree 复现同样两条 glass 布局断言失败，未写成全绿。
构建来源、校验和、回归前后和基线日志见
[本轮检查](evidence/native-frame-checks-2026-10-30.json)。

## 原生窗口诊断与证据边界

早期 Xvfb/Metacity 原生运行确认旧身体确实撤除，但没有 GTK 呈现证明，迁移失败。
GTK/GDK 4.14.5 返回 `complete=true`、`presentation_time=0`；Cairo/XRender 和
GL/XPresent 的诊断都观察到了此情况。0 表示没有可用呈现时间，
与 [GDK API 定义](https://docs.gtk.org/gdk4/method.FrameTimings.get_presentation_time.html)
一致。GDK X11 的同步还依赖 compositor 的
[`_NET_WM_FRAME_DRAWN` 支持](https://github.com/GNOME/gtk/blob/4.14.5/gdk/x11/gdksurface-x11.c#L581)。
本轮补上上述 JWM opt-in 链路；原始失败报告继续保留。

`tests/native_windows.py` 将相同检查变成可重复的原生双窗口验收：

```sh
env -u SSH_CONNECTION -u SSH_TTY XDG_SESSION_ID=eva-native-test \
  python3 tests/native_windows.py --daemon target/debug/jcompaniond \
  --host forge=/absolute/path/to/forge --host anvil=/absolute/path/to/anvil \
  --wm /absolute/path/to/jwm --frame-sync --freeze-owner --restart-daemon
```

脚本使用私有二进制快照和校验和、临时 home/XDG 配置、无服务自动激活的私有 DBus、独立
Xvfb/JWM（或 Metacity）。记录授权前画面、逐窗口身体像素、驻留 journal、实际 PNG 和
往返交接结果。任一帧样本出现多窗口身体会失败；缺少实际交接同样返回非零。
截图采样不能证明任意两帧之间的物理唯一性，也不证明硬件、Wayland、IME 或性能。
自动分类现已允许默认猫形象的 dimmed/原生色彩转换；仍不识别 Compact、高对比或
其他皮肤，零匹配不能证明身体不存在。PNG 先截取，journal 后读取，两者不是原子快照；
不能把旧截图旁的新 phase/epoch 当成同一瞬间双身体或精确性能证据。
报告保留全部样本记录/校验和，代表性 PNG 的保留情况由 screenshot_retained 标明。
Forge 冻结时可能被 WM 重排/裁出画面，保留 token 不代表其每个样本都仍然可见。

## 完整范围核对

“实现存在”与“已验收”分开列出；未验证项目保持未完成。

| 工程任务 | 当前依据 | 尚需完成/验证 |
|---|---|---|
| C01 协议、能力、长度、快照 | 严格 JSON、长度/来源/序列检查、版本化请求、客户端握手测试 | 更完整的版本错配/重放/畸形帧进程矩阵；增量/重同步兼容演进 |
| C02 独占、驻留、日志、恢复 | reducer、持久日志、SIGSTOP/daemon SIGKILL；真实 IPC 修复安全区域恢复后的同 epoch 准备重试 | 宿主永久消失后的可信表面销毁证明与恢复入口；休眠/会话生命周期实测 |
| C03 GUI adapter | 8 GUI / 32 PTY、实际输入/方向路由、正反交接/快速切换通过；补齐发布与合成回执关联 | 其他 compositor/驱动、同进程多窗、旧窗口/关闭/重连、休眠及连续物理证明 |
| C04 Ember | 修复 padding、Vulkan/JWM 清除回执、跨窗格、显式命令与同 PID exec/read 关闭保护、逻辑键释放；外部 Vim 修改保留、可见缩放及完整矩阵通过 | Glow/Wayland、选择/滚动/IME；两条基线 UI 断言失败仍保留 |
| C05 Forge 异构交接 | 补 JWM X11 原生帧回执；三组异构原生往返及故障恢复通过 | 其他 compositor/后端、真实硬件/休眠/窗口关闭矩阵、延迟与性能验收 |
| C06 Anvil/Frost parity | 四端各两实例/四 split；完整八窗身体遍历、快速切换及 Frost 冻结/重启通过 | 其他后端/设备、全部配对/关闭/休眠、真实 UI 操作矩阵仍缺 |
| C07 Eva | 既有唯一音频 owner 桥接；本轮租约/重启/释放真实 IPC 通过 | 真实麦克风/播放、Esc/停止/自然打断/设备释放与单身体状态；不得用协议事件替代 |
| C08 模型与预算 | 明确 Responses 适配器、受限建议、离线/拒绝/超时/429 fixture | 指定配置的真实 API smoke、授权出口与 usage、并发/预算验收 |
| C09 记忆与迁移 | SQLite 审阅事务、作用域、删除；本轮跨进程持久删除通过 | 四端实际记忆 UI、撤销式旧记忆导入、存储满/回滚/删除派生内容的完整矩阵 |
| C10 任务/审批/回执 | 只读任务事实、本轮修复串台、保留原执行器 | 真实 jagent 活动、原生审阅导航、accepted/failed/unknown、未知不重放、跨 pane 迟到结果矩阵 |
| C11 JWM 单节点 | 已有 X11/Wayland 绘制路径、atlas、锁屏 observer；本轮补 native-host X11 提交回执 | 单节点可信退休/呈现 fence 仍缺；终端安全锚点认证、输入卡、多屏/锁屏/direct scanout 实测 |
| C12 发布与诊断 | 精确 Git pin、manifest 工具、部署文档、CI、两类新增进程/原生脚本 | 按最终版本冻结源码/二进制/证据、可重复安装、版本错配与回退、完整发布验收 |

体验层还包括：12 组事实驱动动作与优先级、八种外观、Full/Calm/Static、reduced motion/
高对比/键盘入口、Stay Here/Follow Me/Recall、安静时段、独立对话卡、不改变正文高度或
CanvasMotion、私密/远程上下文边界。源码已覆盖其中多项，但四端实际操作的证据不足，
本页不将它们整组标为通过。可选 Hide and Seek 保持未实现/默认关闭。

历史失败证据仍保留：
[Frost→Forge](evidence/native-frost-forge-2026-10-30/report.json) 中已人工确认 Frost 身体
实际可见，随后 Forge 获得新授权并显示身体；严格往返仍未通过。
[Ember→Forge](evidence/native-ember-forge-2026-10-30/report.json) 的新建 `/bin/sh` 空画布
没有建立可验证的 Ember 可见身体，当时需要用真实任务画布继续验证，不能凭授权/Active
状态补作像素通过。上述早期 native 命令均返回非零；本轮通过的是前文独立列出的
JWM frame-sync 三组新报告，不回写或提升这些历史失败。

以下性能出口仍无完整证据：30 分钟空闲模型请求为 0、隐藏/静止无身体专用连续帧、
点击反馈 p95≤50ms、健康迁移 p95≤300ms、身体额外绘制 p95≤0.5ms、输入/滚动 A/B≤5%、
本地停播 p95≤150ms，以及真实模型延迟/用量。构建时间和截图采样间隔不能代替这些指标。

## 下一步执行顺序

1. 继续真实 provider/远程、更多 builtin/wait/loop、shell 后台作业/父 shell 退出后子进程等生命周期、原生压缩证明、其他端 Vim9、同进程多窗、休眠和部分回执；
   崩溃自动恢复仍需可信销毁证明。再扩大真实输入/选择/滚动/IME 与各外观/运动模式验收。
2. 扩大 X11 frame feedback 的真实协议生命周期/GLX/EGL/XCB 验证；单节点模式仍需
   独立的退休/呈现 fence、锚点认证及多屏/锁屏/direct scanout 证据。
3. 完成实际记忆/上下文 UI、Eva 设备和配置明确的模型 smoke，以及各项性能出口。
4. 完整要求逐项通过后冻结发布源码/二进制/证据 manifest 与回退流程。

当前整体结论：方案持续推进，MVP 与完整方案尚未达到全部完成条件。
