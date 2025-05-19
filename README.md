# 开关柜多传感器局部放电监测软件

本软件用于通过 Modbus RTU (Serial) 协议连接开关柜内的 TEV、超声波、UHF 局部放电监测装置，读取遥测数据和图谱数据，并在图形用户界面中显示。

项目包含以下主要脚本版本：
*   `all_sensors_reader_pyside.py`: 基于 **PySide6**，读取并显示 TEV、超声波、UHF 三种传感器的数据。
*   `all_sensors_reader_pyside_threaded.py`: 基于 **PySide6**，`all_sensors_reader_pyside.py` 的多线程版本，优化了数据读取和界面响应性能。
*   `uhf_monitor_pyside.py`: (较新版本pyside6版本界面。) 仅读取并显示 UHF 传感器的数据。
*  

**推荐使用 `all_sensors_reader.py`, `all_sensors_reader_pyside.py` 或 `all_sensors_reader_pyside_threaded.py`。**

### 下面是Pyside版本代码界面：
![Pyside_版本界面](https://github.com/user-attachments/assets/c584869f-4962-4021-a323-f1a8136cf46b)
![Pyside_版本界面](https://github.com/user-attachments/assets/820fcfa8-8ac3-4191-8374-297d7e47445c)





## 主要功能 (`all_sensors_reader_pyside.py`)

*   通过串口连接到监测装置。
*   实时显示 TEV、超声波的放电次数、dB 值、mV 值，以及 UHF 的 dB 值、mV 值。
*   实时绘制 TEV、超声波、UHF 的图谱数据。
*   支持自动刷新数据（可选择刷新间隔）。
*   支持手动刷新串口列表和数据。
*   清晰的图形用户界面 (GUI)。
*   提供  PySide6 版本。

## 依赖

*   Python 3.x
*   **PyQt5** (用于 `all_sensors_reader.py`) **或 PySide6** (用于 `all_sensors_reader_pyside.py`)
*   matplotlib
*   pyserial
*   pymodbus==3.9.2
*   numpy

您可以使用 pip 安装依赖：
```bash

# 如果运行 PySide6 版本
pip install PySide6 matplotlib pyserial pymodbus numpy
python all_sensors_reader.py
```






## 运行

选择您想运行的版本对应的命令：



**运行 PySide6 版本:**
```bash
python all_sensors_reader_pyside.py
```

**运行 PySide6 多线程版本:**
```bash
python all_sensors_reader_pyside_threaded.py
```

