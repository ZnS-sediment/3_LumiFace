# Windows / Linux 部署

## 已验证环境

WSL Ubuntu 20.04、Python 3.12.2（项目 .venv）、Node.js 24.11.0、npm 11.6.1、ONNX Runtime 1.20.1 CPU。系统默认 Python 3.8 不满足要求，使用已有 `/home/zns/anaconda3/bin/python` 创建虚拟环境，不替换系统 Python。

项目根目录 `/home/zns/3_LumiFace`。数据库位于 runtime/lumiface.db；样本 runtime/samples；数据集 runtime/datasets；权重 runtime/insightface/models/buffalo_l。

## 当前环境启动

```bash
cd /home/zns/3_LumiFace
bash scripts/start.sh
```

进入 http://localhost:5173，API 文档 http://localhost:8000/docs。 若看到 `{"detail":"Not Found"}`，请先核对地址；网页入口为 5173，8000 是后端端口。更新后的后端根地址会跳转到前端，已有后端进程需要重启后才生效。两个端口已占用时脚本报错，不终止其他用户进程。Ctrl+C 清理脚本启动的前后端进程组。

Windows 资源管理器访问 `\\wsl.localhost\Ubuntu-20.04\home\zns\3_LumiFace`；Windows 浏览器通过 WSL localhost 转发访问页面。若转发被主机策略禁用，在 WSL 可用浏览器访问 127.0.0.1，不应直接开放公网来绕过问题。

## 全新 Linux / WSL

准备 Python 3.11/3.12、python venv、C++ 编译工具、Node/npm。InsightFace 0.7.3 在 Linux 上可能从源码编译，因此需要 g++ 和 Python 开发头文件。使用 CPU 无需 CUDA。

```bash
cd /path/to/3_LumiFace
PYTHON_BIN=python3.11 bash scripts/setup.sh
bash scripts/check.sh
bash scripts/start.sh
```

setup 安装 requirements.txt 与 npm ci，并运行官方模型下载。为了完全复现本次已安装环境，可在相同 Python/OS 上改用 `pip install -r backend/requirements-lock.txt`。其他平台需依赖兼容性验证，不能保证 Linux 锁文件跨平台逐包一致。

官方权重下载失败时，图像增强仍可用，人脸接口返回明确 503。网络恢复后重跑 `python scripts/download_models.py`，再首页“加载模型”。不要用随机向量、Haar 结果或测试替身冒充识别模型。

## 原生 Windows

WSL 是本项目已实际验证的路径。原生 Windows 部署说明如下，**尚未在本次环境执行验证**：

```powershell
cd C:\Projects\3_LumiFace
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
npm ci --prefix frontend
.\.venv\Scripts\python.exe scripts\download_models.py
powershell -ExecutionPolicy Bypass -File scripts\start.ps1
```

InsightFace 若需要编译，请安装 Visual Studio Build Tools 的 C++ 工具链；不要从来源不明的网站安装预编译包。原生 Windows 重新建虚拟环境，不复用 WSL 的 `.venv/bin`。SQLite/路径和 python 脚本使用 pathlib，PowerShell 启动脚本与 Linux Bash 分开。

## 前后端独立启动

```bash
.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
# 另一终端
npm run dev --prefix frontend
```

生产构建 `npm run build --prefix frontend`，然后 `npm run preview --prefix frontend` 在 5173 本地预览已构建文件；preview 已配置 /api 代理。项目不提供公网部署方案和账号认证。

不要启用多个 Uvicorn workers：当前后台任务为单进程锁，重启检测机制也按单进程设计。

## GPU 和 PyTorch

默认 requirements 安装 CPU ORT。要启用 GPU，应在独立验证环境中卸载 CPU 包，安装兼容的 GPU 包；二者不要同时安装：

```bash
.venv/bin/python -m pip uninstall onnxruntime
.venv/bin/python -m pip install onnxruntime-gpu==1.20.1
```

ORT 1.20.x 的 PyPI GPU 版本需要 CUDA 12.x 与 cuDNN 9.x；按 [官方 CUDA provider 兼容表](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html) 配置，不只检查 nvidia-smi。应用按可用 providers 优先 CUDA，报告实际 session providers。GPU 分支未在本次环境实测。

若做 PyTorch 模型实验或硬件诊断，可按 [PyTorch 官方安装页面](https://pytorch.org/get-started/locally/) 选择与 CUDA 匹配的构建，并参考 `backend/requirements-torch.txt`。运行：

```bash
.venv/bin/python scripts/environment.py
```

此脚本在 PyTorch 可用时输出 CUDA 版本与 GPU 名称；未安装时明确标注 optional。核心 ONNX 推理不依赖 PyTorch，避免在 CPU 教学环境额外下载数 GB CUDA 包。

## 自动验证

```bash
bash scripts/check.sh
.venv/bin/python scripts/smoke_real_model.py
frontend/node_modules/.bin/playwright install chromium
bash scripts/browser_check.sh
```

browser_check.sh 要求 8000/5173 空闲，会启动隔离的测试数据库、真实后端和前端，自动运行六页面工作流并停止服务。公开样例与测试数据库保存在 work，正式 runtime 身份库不受影响。失败 trace 位于 work/playwright-artifacts，JSON 报告 work/browser-results.json。

Ubuntu 20.04 使用固定 Playwright 1.56.1；新版浏览器支持可能不同。精简 WSL 缺少运行库时，可通过 Playwright 官方 install-deps 安装所需系统依赖。本次未修改系统库，在 work/browser-libs 解包 Ubuntu 官方运行库，并通过 LD_LIBRARY_PATH 供测试进程使用。中文截图使用本机已安装的 Windows 字体目录；纯 Linux 应安装中文字体，例如 Noto CJK。应用本身使用系统字体栈，不依赖外部字体网络请求。

## 备份、清理和隐私

停止服务后备份 runtime 数据库及关联 samples/datasets 文件夹，模型可以重新下载。不要只拷贝运行中的 SQLite 主文件而遗漏 WAL。目录中有敏感生物特征，备份也必须限制访问。

删人会删除参考图和特征；历史实验及独立数据集需在实验页显式删除。删除过的图库无法直接复现旧实验，旧报告保留参数摘要和预测供审阅。

环境变量：LUMIFACE_DATA 自定义数据根；LUMIFACE_MODELS 自定义模型根。变量在启动前设置，应用不会接受 HTTP 传入文件系统路径。

公开样例脚本的直接依赖另外声明于 `backend/requirements-demo.txt`；当前 InsightFace 依赖链已安装相同版本。图像增强服务不需要公开人脸图片或外部图像服务。

## 真实公开数据与实景验收

```bash
# 顺序执行，避免多个大型模型进程使 7 GB WSL 交换区耗尽
bash scripts/run_public_study.sh
# 自采数据先核对划分与场景证据
.venv/bin/python scripts/audit_field_data.py /path/to/collection.json --output work/field-audit
```

固定子集默认 320 检测输入；主系统默认 640。`LUMIFACE_DETECTION_SIZE=320` 可显式选择 CPU 较小输入，注册/校准/测试时必须保持设置一致；更改后旧检测尺寸的校准记录会被拒绝。

启动后端后才会加载新路由；更新代码后需要重启已有服务。独立验证可使用 `LUMIFACE_TEST_API_PORT=8001 LUMIFACE_TEST_UI_PORT=5174 bash scripts/browser_check.sh`，不会占用已经运行的默认端口。对应 Vite 后端地址来自 LUMIFACE_API_URL，只额外允许显式指定的本地前端 Origin。

如果此前由 Codex 启动的默认端口服务仍运行，更新代码后可以在**普通 WSL 终端**执行：

```bash
cd /home/zns/3_LumiFace
bash scripts/stop.sh
bash scripts/start.sh
```

stop.sh 只向同一用户、本项目工作目录且命令明确为本项目 Uvicorn/Vite 的进程发送 SIGTERM；不会终止公开数据评估或其他项目。隔离工具的进程命名空间可能看不到旧服务器，此时它会明确提示从普通 WSL 终端执行，不会声称已停止。
