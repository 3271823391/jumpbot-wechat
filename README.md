# Windows《跳一跳》自动游戏与学习

在 Windows 微信小游戏《跳一跳》中，程序自动寻找标题为“跳一跳”的窗口，识别棋子与目标，按真实跳跃结果更新按压时间模型。游戏窗口可以移动；程序不会调整页面大小。识别不可靠、窗口失焦或游戏失败时会停止操作，**不会自动重开**。

## 三步启动

1. 安装 [Python 3.10 或更新版本](https://www.python.org/downloads/windows/)。安装后在命令提示符运行 `py -3 --version`，确认可以启动 Python。
2. 打开微信《跳一跳》，让游戏窗口保持可见、未最小化。停在开始页或正在进行的游戏画面都可以。
3. 下载或克隆本仓库，双击 **[start.bat](start.bat)**。首次启动会自动创建 `.venv` 并安装依赖；以后仍双击同一文件即可。保持弹出的命令窗口打开。

首次安装依赖需要网络。程序会尝试将游戏窗口置前。只允许它操作指定游戏窗口；若窗口被遮挡、移动过程中失焦或截图异常，会安全停止。**不要同时运行两个自动游戏进程。**

## 常用操作

| 操作 | 方法 |
| --- | --- |
| 暂停 | 双击 [pause.bat](pause.bat) |
| 继续 | 双击 [resume.bat](resume.bat)，原运行窗口需仍打开 |
| 立即停止输入 | 按 **F12** 或双击 [stop.bat](stop.bat) |
| 查看当前跳跃预测 | 在项目目录运行 `.\.venv\Scripts\python.exe jumpbot.py status` |
| 查看模型 | 运行 `.\.venv\Scripts\python.exe jumpbot.py model` |

`start.bat` 会清除上次留下的停止和暂停标记。游戏失败后，程序保存结算截图并退出；它**不会**点击“再玩一局”。若要再次运行，请先在游戏里手动开始新局，再双击 `start.bat`。关闭命令窗口也能终止程序，但推荐先用 F12 或 `stop.bat`。

## 逐跳复盘

若要为单局每一跳保存独立原图，先让游戏进入正在游玩的画面，再在项目目录运行：

```powershell
.\.venv\Scripts\python.exe jumpbot.py until-fail --max-jumps 1000
```

截图和 `jumps.jsonl` 会存到 `data/review/日期时间/`；失败时另存 `failure.png`，程序不重开。运行 `.\.venv\Scripts\python.exe make_review.py` 后，双击 `data/review/index.html`，可用左右方向键逐跳查看。若中途画面不可靠，程序会停止并保存 `uncertain.png`。

## 人工标注与模型保存

`data/model.json` 保存真实跳跃测量与按压时间模型，启动时自动加载；每次可靠测量后自动更新。`data/center_templates.npz` 保存人工标注训练成果，启动时自动加载。两个文件只保存在本机。

标注困难方块时运行 `.\.venv\Scripts\python.exe label.py`。工具默认显示复盘记录中失败、未可靠测量或落点偏差较大的跳前原图；传入 PNG 路径可指定图片，`--all` 可查看全部跳前图。用左键点击**目标顶部的最佳落点**，按 `N` 跳过，按 `Q` 退出。标注保存在 `data/target_labels.jsonl`。完成后运行 `.\.venv\Scripts\python.exe train_labels.py`，再重新启动游戏程序。无纹理的近白色样本会跳过模板训练，继续使用白点和顶部轮廓识别。

新安装的公开源码包**不含**本机训练数据。程序会通过真实游戏实验逐步建立按压时间模型；早期跳跃属于探索，不能视为已校准的高分模式。无法可靠测量的跳跃会明确记为缺失，不会把目标距离冒充实际距离。

## 开发与报告

在项目目录运行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
.\.venv\Scripts\python.exe simulate.py
.\.venv\Scripts\python.exe report.py
```

测试包含独立模拟场景；依赖本机真实截图的回归案例在公开仓库中会自动跳过。`report.py` 使用本机实验数据生成 `data/summary.json` 和 `data/press_distance.png`。算法、真实实验与模拟实验的区别见 [RESEARCH.md](RESEARCH.md)，开发迭代见 [ITERATIONS.md](ITERATIONS.md)，最新单局验证见 [TEST_REPORT.md](TEST_REPORT.md)。历史数据重算工具为 `reprocess.py`，只应在保留原始截图且需要重算模型时使用。

## 最新验证与限制

2026-10-20 在真实游戏中，人工标注训练后的单局从开始页运行：**前 259 跳成功，第 260 跳失败，结算 6441 分**；255 跳有可靠落点测量，4 跳只确认成功，可测跳跃的平均绝对落点误差约 3.9 像素。失败后没有自动重开。此前另一局曾连续成功 353 跳，第 354 跳失败。两局不能证明模型在所有平台、背景或显示比例下稳定，也不能把模拟通过率当成真实成功率。

## 开源发布与隐私

源码采用 [MIT 许可证](LICENSE)。`.gitignore` 排除本机 `data/`、`archives/`、虚拟环境、截图和运行控制文件；结算画面可能包含账户头像或昵称。发布前请复核暂存区，不要把这些文件加入仓库。源码压缩包由 `package.py` 创建，只包含代码、文档、测试和启动脚本，不包含本机数据。
