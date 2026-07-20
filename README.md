<div align="center">

# TransTiQ

**Offline TiQ-transcript translation**

[🇬🇧 English](#english) ·  [🇨🇳 中文](#chinese) · [🇩🇪 Deutsch](#deutsch)

</div>

---
# <a name="english"></a>🇬🇧 English

---

## Overview

**TransTiQ** is a command-line tool that translates qualitative research interview transcripts following **TiQ (Talk in Qualitative Research)** conventions from one language to another using a local AI model. It is specifically designed to ensure the correct formatting of transcript lines and special transcription symbols in TiQ, such as:
- Pauses `(.)`,`(3)`
- Quiet speech `°pssst°`
- Laughter `@(...)@` and overlapping speech `└` or `⌊`
- Listener's signals `//Mhm//`, cut-offs `/`, uncertain transcription `(word)`
- Timestamps `#00:00:11-6#`

All of these are preserved exactly — only the transcript content is translated.

---

## Features
- **Offline operation** – All processing runs locally; no internet connection required.
- **TiQ symbol preservation** – Retains all transcription conventions defined by TiQ (pauses, timestamps, laughter, overlaps, degree markers, listener signals, cut-offs, uncertain transcriptions).
- **Context-aware translation** – Uses a sliding-window memory to maintain speaker identity and pronoun consistency across batches.
- **Automatic output cleaning** – Removes hallucinated placeholders, fixes spacing, and strips model artifacts.
- **Batch processing** – Translates every `.txt` file in a folder in one command.
- **Configurable** – Adjustable batch size, context window size, GPU offloading, and thread count.

---

## Prerequisites

- **Python 3.10 or later**
- **A GGUF translation model** (see [Model Setup](#model-setup) for download links and setup instructions)
- **A CPU with at least 2.0 GHz and 16 GB+ RAM**

### Optional but recommended

- **An NVIDIA GPU** with 8 GB+ VRAM for significantly faster translation (10× speedup over CPU)

---

## Installation

### Standard installation

```bash
git clone https://github.com/anouarg88/TransTiQ.git
cd TransTiQ
pip install -e .
```

After installation, you can use `transtiq` from any folder:

```bash
transtiq transcript.txt -o transcript_de.txt
```

### Running without full installation (fallback)

If you prefer to run the script directly without installing the package, install only the required dependency and invoke the script with Python:

```bash
git clone https://github.com/anouarg88/TransTiQ.git
cd TransTiQ
pip install llama-cpp-python
```

To run the script, use:

```
python transtiq.py transcript.txt -o transcript_output.txt
```

> **Windows tip:** Use the included `transtiq.cmd` batch file or add the folder to your `PATH` to run `transtiq` from anywhere.

## Model Setup

### Downloading the model

TransTiQ is designed to work with the **Hy-MT2-7B** model, which is optimised for Chinese-to-German translation.

**Recommended model:** `Hy-MT2-7B-Q4_K_M.gguf`

| Download Link | Region |
|---------------|--------|
| [HuggingFace (global)](https://huggingface.co/tencent/Hy-MT2-7B-GGUF) | 🌍 |
| [HF Mirror (China)](https://hf-mirror.com/tencent/Hy-MT2-7B-GGUF) | 🇨🇳 |

1. Download the `.gguf` file from HuggingFace (look for `Hy-MT2-7B-Q4_K_M.gguf`)
2. Place it in the `models/` folder inside the project directory
3. TransTiQ will find it automatically — no `--model` flag needed!

```text
TransTiQ/
├── models/
│   └── Hy-MT2-7B-Q4_K_M.gguf   ← place here
├── transtiq.py
└── ...
```

**Important:** GGUF files are large (4+ GB) and exceed GitHub's file size limits. They are **not included** in the repository — you must download the model separately. The `.gitignore` file is configured to exclude model files.

### Using a different model

You can use any compatible GGUF model by specifying it with the `--model` flag:

```bash
transtiq input.txt --model /path/to/your-model.gguf
```

---

## Usage

### Basic usage

```bash
# Translate zh → de (default) using the default model
transtiq transcript.txt

# Specify output file
transtiq transcript.txt -o translated.txt

# Translate to English
transtiq transcript.txt --to en

# Change source language
transtiq transcript.txt --from en --to de
```

Note that defaults can be edited inside `transtiq.py`.

### Batch processing (entire folder)

```bash
transtiq "E:/my_transcripts/"
```

Each `.txt` file in the folder gets a translated counterpart named `{filename}_tiQ_{lang}.txt`.

### Advanced options

```bash
transtiq transcript.txt \
  --model ./models/Hy-MT2-7B-Q4_K_M.gguf \  # custom model path
  --batch-size 10 \                           # lines per batch (default: 10)
  --context-window 5 \                        # context memory (default: 5)
  --to de \                                   # target language
  --from zh \                                 # source language
  --n-ctx 4096 \                              # model context length
  --n-cores 8 \                               # CPU threads
  --no-gpu                                    # disable GPU offloading
```

### Full options

```
usage: transtiq [-h] [-m MODEL] [-o OUTPUT] [--from SRC] [--to TGT]
                [--batch-size BATCH_SIZE] [--context-window CONTEXT_WINDOW]
                [--n-ctx N_CTX] [--no-gpu] [--n-cores N_CORES]
                [--tokenizer-override TOKENIZER_OVERRIDE]
                input

transtiq -- Offline transcript translation with GGUF models

positional arguments:
  input                  Input .txt file or directory

options:
  -h, --help             Show this help message
  -m, --model            Path to GGUF model
  -o, --output           Output file path
  --from                 Source language (default: zh)
  --to                   Target language (default: de)
  --batch-size           Lines per batch (default: 10)
  --context-window       Context memory lines (default: 5, 0 to disable)
  --n-ctx                Model context length (default: 4096)
  --no-gpu               Disable GPU acceleration
  --n-cores              CPU thread count (default: 6)
  --tokenizer-override   Override tokenizer (e.g. qwen2)
```

---

## Hardware Recommendations

| Setup | Translation Speed | Notes |
|-------|:----------------:|-------|
| CPU only (6 cores) | ~2-4 tok/s | ~40 min per 100-line file |
| Modern CPU (16 cores) | ~6-10 tok/s | ~15-20 min per 100-line file |
| **GPU 8+ GB VRAM** 🚀 | ~25-40 tok/s | **~2-5 min** per 100-line file |

A GPU provides roughly **8-10× speedup** over CPU-only operation.

---

## Input Format (TiQ)

TransTiQ expects transcripts following **TiQ conventions**, commonly used in reconstructive and qualitative research:

```
004 A: °那我们开始吧° #00:00:20-9#
005 B: (.)好的 #00:00:21-9#
006 A: (3)开始之前呢我想和你做一个小实验
```

Each line may contain:
- **Line number** (4 digits, left-aligned)
- **Speaker label** (`A:` / `B:` / etc.) — optional for continuation lines
- **Body text** with transcription symbols
- **Timestamp** `#mm:ss.ms#`

---

## Project Structure

```
TransTiQ/
├── models/                          # GGUF model files (download, not included)
│   └── Hy-MT2-7B-Q4_K_M.gguf
├── tests/
│   └── test_transtiq.py             # Test suite (86 tests)
├── examples/
│   ├── giraffe_short_cn.txt         # Example input transcripts
│   └── giraffe_long_cn.txt
├── transtiq.py                      # Main script
├── transtiq.cmd                     # Windows batch launcher
├── pyproject.toml                   # Python package configuration
├── .gitignore                       # Git exclusion rules
└── README.md                        # This file

```

---

## Running Tests

```bash
# Run all tests
python -m pytest tests/test_transtiq.py -v

# Or
python tests/test_transtiq.py
```

---

## Credits & License

- **Translation model:** [Hy-MT2-7B](https://huggingface.co/tencent/Hy-MT2-7B-GGUF) by Tencent
- **GGUF runtime:** [llama-cpp-python](https://github.com/abetlen/llama-cpp-python)
- **TiQ:** Talk in Qualitative Research transcription conventions (Przyborski & Wohlrab-Sahr 2021)

---

## <a name="deutsch"></a>🇩🇪 Deutsch

<p align="center">
  <strong>Offline-Übersetzung für TiQ-Transkripte</strong>
</p>

---

### Überblick
**TransTiQ** ist ein Kommandozeilenwerkzeug, das qualitative Forschungsinterviewtranskripte im **TiQ-Format (Talk in Qualitative Research)** mit einem lokalen KI-Modell von einer Sprache in eine andere übersetzt. Es wurde speziell entwickelt, um die korrekte Formatierung von Transkriptionszeilen und speziellen Transkriptionssymbolen in TiQ sicherzustellen, wie z. B.:
- Pausen `(.)`, `(3)`
- Leise Sprache `°pssst°`
- Lachen `@(...)@` und überlappende Sprache `└` oder `⌊`
- Hörersignale `//Mhm//`, Abbrüche `/`, unsichere Transkription `(Wort)`
- Zeitstempel `#00:00:11-6#`

All diese Symbole werden exakt beibehalten – nur der Transkriptionsinhalt wird übersetzt.

### Funktionen

- **Offline-Betrieb** –  Verarbeitung läuft lokal ohne Internetverbindung.
- **TiQ-Symbolerhaltung** – Alle Transkriptionssymbole (Pausen, Zeitstempel, Lachen, Überlappungen, leise Sprache, Hörersignale, Abbrüche, unsichere Transkriptionen) bleiben erhalten.
- **Kontextbewusste Übersetzung** – Ein _Scrolling Context-Window_ bewahrt Sprechendenonsistenz und Pronomen über Zeilen hinweg.
- **Automatische Bereinigung** – Entfernt halluzinierte Platzhalter, korrigiert Abstände und entfernt Modellartefakte.
- **Batch-Verarbeitung** – Übersetzt alle `.txt`-Dateien eines Ordners mit einem Befehl.
- **Konfigurierbar** – Einstellbare Batch-Größe, Kontextfenstergröße, GPU-Entlastung und Thread-Anzahl.

### Installation

### Standardinstallation

```bash
git clone https://github.com/anouarg88/TransTiQ.git
cd TransTiQ
pip install -e .
```

Nach der Installation können Sie `transtiq` von jedem Ordner aus verwenden:

```bash
transtiq transkript.txt -o uebersetzung.txt
```

### Ausführung ohne vollständige Installation

Wenn Sie das Skript lieber direkt ausführen möchten, ohne das Paket zu installieren, können Sie alternativ nur das notwendige `llama`-Paket installieren:

```bash
git clone https://github.com/anouarg88/TransTiQ.git
cd TransTiQ
pip install llama-cpp-python
```

Anschließend kann das Script wie folgt mit Python ausgeführt werden:

```
python transtiq.py transkript.txt -o transkript_uebersetzt.txt
```

> **Windows-Tipp:** Nutzen Sie die enthaltene `transtiq.cmd`-Batchdatei oder fügen Sie den Ordner zu Ihrem `PATH` hinzu, um `transtiq` von überall auszuführen.

### Modell einrichten

Laden Sie das Modell von HuggingFace herunter:

| Download-Link | Region |
|---------------|--------|
| [HuggingFace (global)](https://huggingface.co/tencent/Hy-MT2-7B-GGUF) | 🌍 |
| [HF Mirror (China)](https://hf-mirror.com/tencent/Hy-MT2-7B-GGUF) | 🇨🇳 |

Legen Sie die `.gguf`-Datei in den `models/`-Ordner:

```text
TransTiQ/
├── models/
│   └── Hy-MT2-7B-Q4_K_M.gguf
├── transtiq.py
└── ...
```

### Verwendung

```bash
# Standard (Zh → De)
transtiq transkript.txt

# Mit Ausgabedatei
transtiq transkript.txt -o uebersetzung.txt

# Stapelverarbeitung
transtiq "E:/transkripte/"
```

Beachten Sie, dass die Standardwerte in `transtiq.py` angepasst werden können.

### Hardware

| System | Geschwindigkeit |
|--------|:--------------:|
| Nur CPU (6 Kerne) | ~2-4 tok/s |
| Moderne CPU (16 Kerne) | ~6-10 tok/s |
| **GPU 8+ GB VRAM** 🚀 | **~25-40 tok/s** |

### Eingabeformat (TiQ)

TransTiQ erwartet Transkripte, die den **TiQ-Konventionen** folgen, wie sie in der rekonstruktiven und qualitativen Forschung üblich sind:

```
004 A: °那我们开始吧° #00:00:20-9#
005 B: (.)好的 #00:00:21-9#
006 A: (3)开始之前呢我想和你做一个小实验
```

Jede Zeile kann enthalten:
- **Zeilennummer** (4 Ziffern, linksbündig)
- **Sprecherkürzel** (`A:` / `B:` / usw.) — optional für Fortsetzungszeilen
- **Textkörper** mit Transkriptionssymbolen
- **Zeitstempel** `#mm:ss.ms#`

### Projektstruktur

```
TransTiQ/
├── models/                          # GGUF-Modelldateien (separat herunterladen)
│   └── Hy-MT2-7B-Q4_K_M.gguf
├── tests/
│   └── test_transtiq.py             # Testsammlung (86 Tests)
├── examples/
│   ├── giraffe_short_cn.txt         # Beispiel-Transkripte
│   └── giraffe_long_cn.txt
├── transtiq.py                      # Hauptskript
├── transtiq.cmd                     # Windows-Batch-Startdatei
├── pyproject.toml                   # Python-Paketkonfiguration
├── .gitignore                       # Git-Ausschlussregeln
└── README.md                        # Diese Datei

```

### Tests ausführen

```bash
# Alle Tests ausführen
python -m pytest tests/test_transtiq.py -v

# Oder
python tests/test_transtiq.py
```

### Danksagungen & Lizenz

- **Übersetzungsmodell:** [Hy-MT2-7B](https://huggingface.co/tencent/Hy-MT2-7B-GGUF) von Tencent
- **GGUF-Laufzeit:** [llama-cpp-python](https://github.com/abetlen/llama-cpp-python)
- **TiQ:** Talk in Qualitative Research – Transkriptionskonventionen (Przyborski & Wohlrab-Sahr 2021)

## <a name="chinese"></a>🇨🇳 中文

<p align="center">
  <strong>离线翻译TiQ格式访谈转录文本</strong>
</p>

---

### 概述

**TransTiQ** 是一个命令行工具，使用本地AI模型将 **TiQ（Talk in Qualitative Research）格式**的定性研究访谈转录文本从一种语言翻译到另一种语言。它专门设计用于确保TiQ中转录行和特殊转录符号的正确格式，例如：
- 停顿 `(.)`、`(3)`
- 轻声说话 `°pssst°`
- 笑声 `@(...)@` 和重叠语音 `└` 或 `⌊`
- 听者信号 `//嗯嗯//`、中断 `/`、不确定转录 `(词语)`
- 时间戳 `#00:00:11-6#`

所有这些符号都会被精确保留——只有转录内容会被翻译。

### 特点

- **离线运行** – 所有处理在本地完成，无需网络连接。
- **TiQ符号保留** – 保留所有TiQ转录符号（停顿、时间戳、笑声、重叠、音量标记、听者信号、中断、不确定转录）。
- **上下文感知翻译** – 使用滑动窗口记忆来保持说话人身份和代词在批次间一致。
- **自动清理输出** – 移除模型幻觉产生的占位符、修正间距、去除模型伪影。
- **批量处理** – 一键翻译文件夹中的所有 `.txt` 文件。
- **可配置** – 可调整批次大小、上下文窗口大小、GPU卸载和线程数。

### 安装

### 标准安装

```bash
git clone https://github.com/anouarg88/TransTiQ.git
cd TransTiQ
pip install -e .
```

安装后，您可以从任何文件夹使用 `transtiq` 命令：

```bash
transtiq 转录文本.txt -o 翻译结果.txt
```

### 无需完整安装的运行方式（备选）

如果您希望直接运行脚本而不安装完整包，只需安装必要的依赖：

```bash
git clone https://github.com/anouarg88/TransTiQ.git
cd TransTiQ
pip install llama-cpp-python
```

然后用 Python 运行脚本：

```
python transtiq.py 转录文本.txt -o 转录文本_翻译.txt
```

> **Windows 提示：** 使用附带的 `transtiq.cmd` 批处理文件，或将文件夹添加到 `PATH` 环境变量，以便从任何位置运行 `transtiq`。

### 模型设置

下载模型。TransTiQ 专为 **Hy-MT2-7B** 模型设计，该模型针对中德翻译进行了优化。

**推荐模型：** `Hy-MT2-7B-Q4_K_M.gguf`

| 下载链接 | 区域 |
|----------|------|
| [HuggingFace（全球）](https://huggingface.co/tencent/Hy-MT2-7B-GGUF) | 🌍 |
| [HF镜像站（中国）](https://hf-mirror.com/tencent/Hy-MT2-7B-GGUF) | 🇨🇳 |

将下载的 `.gguf` 文件放入项目目录中的 `models/` 文件夹：

```text
TransTiQ/
├── models/
│   └── Hy-MT2-7B-Q4_K_M.gguf   ← 放置在此处
├── transtiq.py
└── ...
```

**注意：** GGUF 文件较大（4GB以上），超过 GitHub 的文件大小限制。它们**不包含**在代码仓库中 — 您必须单独下载模型。`.gitignore` 文件已配置为排除模型文件。

### 使用方法

```bash
# 基本用法（中文 → 德语，默认设置）
transtiq 转录文本.txt

# 指定输出文件
transtiq 转录文本.txt -o 翻译结果.txt

# 翻译到英语
transtiq 转录文本.txt --to en

# 批量处理整个文件夹
transtiq "E:/我的转录文件夹/"
```

请注意，默认值可以在 `transtiq.py` 中修改。

### 高级选项

```bash
transtiq 转录文本.txt \
  --batch-size 10 \       # 每批行数（默认：10）
  --context-window 5 \    # 上下文记忆行数（默认：5）
  --n-cores 8 \           # CPU线程数
  --no-gpu                # 禁用GPU加速
```

### 完整选项

```
usage: transtiq [-h] [-m MODEL] [-o OUTPUT] [--from SRC] [--to TGT]
                [--batch-size BATCH_SIZE] [--context-window CONTEXT_WINDOW]
                [--n-ctx N_CTX] [--no-gpu] [--n-cores N_CORES]
                [--tokenizer-override TOKENIZER_OVERRIDE]
                input
```

### 硬件推荐

| 配置 | 翻译速度 | 说明 |
|------|:--------:|------|
| 仅CPU（6核） | ~2-4 tok/s | 每100行约40分钟 |
| 现代CPU（16核） | ~6-10 tok/s | 每100行约15-20分钟 |
| **GPU 8GB以上显存** 🚀 | ~25-40 tok/s | **每100行仅需2-5分钟** |

GPU相比纯CPU可提供约 **8-10倍的加速**。

### 输入格式（TiQ）

TransTiQ 期望使用遵循 **TiQ 惯例**的转录文本，这些惯例常用于重构性和定性研究：

```
004 A: °那我们开始吧° #00:00:20-9#
005 B: (.)好的 #00:00:21-9#
006 A: (3)开始之前呢我想和你做一个小实验
```

每行可以包含：
- **行号**（4位数字，左对齐）
- **说话人标签**（`A:` / `B:` 等） — 续行可选
- **正文** 包含转录符号
- **时间戳** `#mm:ss.ms#`

### 项目结构

```
TransTiQ/
├── models/                          # GGUF模型文件（需单独下载）
│   └── Hy-MT2-7B-Q4_K_M.gguf
├── tests/
│   └── test_transtiq.py             # 测试套件（86个测试）
├── examples/
│   ├── giraffe_short_cn.txt         # 示例输入转录文本
│   └── giraffe_long_cn.txt
├── transtiq.py                      # 主程序
├── transtiq.cmd                     # Windows批处理启动器
├── pyproject.toml                   # Python包配置
├── .gitignore                       # Git排除规则
└── README.md                        # 本文件

```

### 运行测试

```bash
# 运行所有测试
python -m pytest tests/test_transtiq.py -v

# 或者
python tests/test_transtiq.py
```

### 致谢与许可证

- **翻译模型：** 腾讯 [Hy-MT2-7B](https://huggingface.co/tencent/Hy-MT2-7B-GGUF)
- **GGUF运行时：** [llama-cpp-python](https://github.com/abetlen/llama-cpp-python)
- **TiQ：** Talk in Qualitative Research 转录惯例 (Przyborski & Wohlrab-Sahr 2021)

