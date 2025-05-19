import sys
import time
import struct
import numpy as np
import matplotlib.pyplot as plt
# 使用通用的 Qt Agg 后端，兼容 PySide6
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
# 导入 PySide6 相关模块
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QPushButton, QComboBox,
                             QGroupBox, QGridLayout, QTableWidget, QTableWidgetItem,
                             QHeaderView, QMessageBox, QSplitter)
from PySide6.QtCore import Qt, QTimer, Slot, QThread, Signal # 导入 Slot, QThread, Signal
from PySide6.QtGui import QFont # QFont 通常在 QtGui 中
from pymodbus.client.serial import ModbusSerialClient
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadDecoder
import serial.tools.list_ports

# 添加中文支持
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

class AllSensorsReader:
    """读取 TEV, 超声波, UHF 传感器数据的类 (与GUI框架无关)"""

    def __init__(self, port, slave_address=1):
        """
        初始化监测装置连接

        参数:
            port: 串口名称，如 'COM1'
            slave_address: 从站地址，默认为1
        """
        self.port = port
        self.client = ModbusSerialClient(
            port=port,
            baudrate=9600,
            bytesize=8,
            parity='N',
            stopbits=1,
            timeout=1
        )
        self.slave_address = slave_address
        self.connected = False

    def connect(self):
        """建立与设备的连接"""
        try:
            self.connected = self.client.connect()
        except Exception as e:
            print(f"连接时发生错误: {e}")
            self.connected = False
        return self.connected

    def disconnect(self):
        """断开与设备的连接"""
        if self.connected:
            try:
                self.client.close()
                self.connected = False
            except Exception as e:
                print(f"断开连接时发生错误: {e}")

    def read_float(self, address):
        """读取浮点型数据"""
        if not self.connected: return None
        try:
            response = self.client.read_input_registers(address=address, count=2, slave=self.slave_address)
            if response.isError():
                print(f"读取寄存器 {address} (float) 错误: {response}")
                return None
            decoder = BinaryPayloadDecoder.fromRegisters(
                response.registers,
                byteorder=Endian.BIG,
                wordorder=Endian.LITTLE
            )
            return decoder.decode_32bit_float()
        except Exception as e:
            print(f"读取浮点数据时发生异常 (地址 {address}): {e}")
            return None

    def read_short(self, address):
        """读取短整型数据"""
        if not self.connected: return None
        try:
            response = self.client.read_input_registers(address=address, count=1, slave=self.slave_address)
            if response.isError():
                print(f"读取寄存器 {address} (short) 错误: {response}")
                return None
            return response.registers[0]
        except Exception as e:
            print(f"读取短整型数据时发生异常 (地址 {address}): {e}")
            return None

    def read_telemetry_data(self):
        """读取所有遥测数据"""
        if not self.connected: return None
        data = {}
        read_success = True
        tev_count = self.read_short(100); data['TEV放电次数'] = tev_count if tev_count is not None else None; read_success &= (tev_count is not None)
        # uhf_count = self.read_short(101); data['UHF放电次数'] = uhf_count if uhf_count is not None else None; read_success &= (uhf_count is not None)
        tev_mv = self.read_short(109); data['TEV_mV值'] = tev_mv if tev_mv is not None else None; read_success &= (tev_mv is not None)
        ultrasonic_mv = self.read_short(110); data['超声波_mV值'] = ultrasonic_mv if ultrasonic_mv is not None else None; read_success &= (ultrasonic_mv is not None)
        uhf_mv = self.read_short(111); data['UHF_mV值'] = uhf_mv if uhf_mv is not None else None; read_success &= (uhf_mv is not None)
        tev_db = self.read_float(102); data['TEV_dB值'] = tev_db if tev_db is not None else None; read_success &= (tev_db is not None)
        ultrasonic_db = self.read_float(104); data['超声波_dB值'] = ultrasonic_db if ultrasonic_db is not None else None; read_success &= (ultrasonic_db is not None)
        uhf_db = self.read_float(106); data['UHF_dB值'] = uhf_db if uhf_db is not None else None; read_success &= (uhf_db is not None)

        if not read_success:
            print("警告：部分遥测数据读取失败")
        return data

    def read_waveform_data(self, max_read_count=125):
        """读取三种图谱数据"""
        if not self.connected: return None
        waveforms = {}
        read_success = True
        waveform_info = {
            'TEV图谱': {'start_address': 2000, 'registers_to_read': 128},
            '超声波图谱': {'start_address': 2128, 'registers_to_read': 128},
            'UHF图谱': {'start_address': 2256, 'registers_to_read': 128},
        }
        for name, info in waveform_info.items():
            waveform_data = []
            start_address = info['start_address']
            registers_to_read = info['registers_to_read']
            current_address = start_address
            error_occurred = False
            try:
                while registers_to_read > 0:
                    count = min(registers_to_read, max_read_count)
                    response = self.client.read_input_registers(address=current_address, count=count, slave=self.slave_address)
                    if response.isError():
                        print(f"    读取 {name} 数据错误 (地址 {current_address}, 数量 {count}): {response}")
                        error_occurred = True; break
                    waveform_data.extend(response.registers)
                    registers_to_read -= count
                    current_address += count
                    time.sleep(0.1) # 避免请求过于频繁
                if not error_occurred:
                    waveforms[name] = waveform_data
                else:
                    waveforms[name] = []; read_success = False
            except Exception as e:
                print(f"  读取 {name} 时发生异常: {e}")
                waveforms[name] = []; read_success = False; break
        if not read_success:
            print("警告：部分图谱数据读取失败或发生异常")
        return waveforms

# --- Matplotlib Canvas Class (使用 PySide6) ---
class MonitorCanvas(FigureCanvas):
    """通用数据显示画布"""
    def __init__(self, parent=None, width=5, height=2, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = self.fig.add_subplot(111)
        super(MonitorCanvas, self).__init__(self.fig)
        self.setParent(parent)
        self.init_plot("图谱数据")

    def init_plot(self, title="图谱数据"):
        """初始化图表"""
        self.axes.clear()
        self.axes.set_title(title)
        self.axes.set_xlabel('采样点')
        self.axes.set_ylabel('幅值')
        self.axes.grid(True)
        self.fig.tight_layout()
        self.draw()

    def update_plot(self, data, title="图谱数据"):
        """更新图表数据"""
        self.axes.clear()
        if data:
             self.axes.plot(data, 'b-')
        self.axes.set_title(title)
        self.axes.set_xlabel('采样点')
        self.axes.set_ylabel('幅值')
        self.axes.grid(True)
        self.fig.tight_layout()
        self.draw()

# --- 主应用窗口类 (使用 PySide6) ---
class AllSensorsApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('GP-开关柜多传感器监测软件 (PySide6 - 多线程)')
        self.setGeometry(100, 100, 1000, 700)

        self.reader = None
        self.timer = QTimer(self) # 自动刷新定时器
        self.timer.timeout.connect(self.trigger_data_update) # 连接到触发更新的槽

        self.telemetry_worker = None
        self.waveforms_worker = None

        self.initUI()
        self.refresh_ports()

    def initUI(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # --- 连接控制区 ---
        connection_group = QGroupBox("连接设置")
        connection_layout = QHBoxLayout()
        connection_group.setLayout(connection_layout)

        self.port_combo = QComboBox()
        self.port_combo.setToolTip("选择设备连接的串口")
        self.refresh_button = QPushButton("刷新串口")
        self.refresh_button.clicked.connect(self.refresh_ports) # PySide6 信号连接
        self.connect_button = QPushButton("连接")
        self.connect_button.clicked.connect(self.connect_device) # PySide6 信号连接
        self.disconnect_button = QPushButton("断开")
        self.disconnect_button.clicked.connect(self.disconnect_device) # PySide6 信号连接
        self.disconnect_button.setEnabled(False)

        connection_layout.addWidget(QLabel("串口:"))
        connection_layout.addWidget(self.port_combo, 1)
        connection_layout.addWidget(self.refresh_button)
        connection_layout.addWidget(self.connect_button)
        connection_layout.addWidget(self.disconnect_button)

        # --- 数据显示区 (使用 QSplitter) ---
        # PySide6 使用 Qt.Orientation.Horizontal
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- 遥测数据显示区 ---
        telemetry_group = QGroupBox("遥测数据")
        telemetry_layout = QVBoxLayout()
        telemetry_group.setLayout(telemetry_layout)

        self.telemetry_table = QTableWidget()
        self.telemetry_table.setRowCount(7)  # 从8行改为7行，移除UHF放电次数
        self.telemetry_table.setColumnCount(2)
        self.telemetry_table.setHorizontalHeaderLabels(['参数', '值'])
        self.telemetry_table.verticalHeader().setVisible(False)
        # PySide6 中调整大小模式的设置方式
        self.telemetry_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.telemetry_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.telemetry_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers) # PySide6 枚举

        param_names = ['TEV放电次数', 'TEV_dB值', 'TEV_mV值',
                       '超声波_dB值', '超声波_mV值',
                       'UHF_dB值', 'UHF_mV值']  # 移除'UHF放电次数'
        for i, name in enumerate(param_names):
            self.telemetry_table.setItem(i, 0, QTableWidgetItem(name))
            self.telemetry_table.setItem(i, 1, QTableWidgetItem('--'))

        telemetry_layout.addWidget(self.telemetry_table)
        splitter.addWidget(telemetry_group)

        # --- 图谱显示区 ---
        waveform_group = QGroupBox("图谱数据")
        waveform_layout = QVBoxLayout()
        waveform_group.setLayout(waveform_layout)

        self.tev_canvas = MonitorCanvas(self)
        self.ultrasonic_canvas = MonitorCanvas(self)
        self.uhf_canvas = MonitorCanvas(self)

        self.tev_canvas.init_plot("TEV图谱")
        self.ultrasonic_canvas.init_plot("超声波图谱")
        self.uhf_canvas.init_plot("UHF图谱")

        waveform_layout.addWidget(self.tev_canvas)
        waveform_layout.addWidget(self.ultrasonic_canvas)
        waveform_layout.addWidget(self.uhf_canvas)
        splitter.addWidget(waveform_group)

        splitter.setSizes([300, 700])

        # --- 自动刷新控制 ---
        refresh_control_layout = QHBoxLayout()
        self.auto_refresh_combo = QComboBox()
        self.auto_refresh_combo.addItems(['手动刷新', '1秒', '2秒', '5秒', '10秒'])
        self.auto_refresh_combo.currentIndexChanged.connect(self.set_auto_refresh) # PySide6 信号连接
        self.manual_refresh_button = QPushButton("手动刷新数据")
        self.manual_refresh_button.clicked.connect(self.trigger_data_update) # PySide6 信号连接, 改为 trigger_data_update
        self.manual_refresh_button.setEnabled(False)

        refresh_control_layout.addWidget(QLabel("自动刷新:"))
        refresh_control_layout.addWidget(self.auto_refresh_combo)
        refresh_control_layout.addWidget(self.manual_refresh_button)
        refresh_control_layout.addStretch()

        # --- 布局整合 ---
        main_layout.addWidget(connection_group)
        main_layout.addWidget(splitter, 1)
        main_layout.addLayout(refresh_control_layout)

        # --- 状态栏 ---
        self.statusBar().showMessage('准备就绪')

    @Slot() # 明确标记为槽函数 (可选，但推荐)
    def refresh_ports(self):
        """刷新可用串口列表"""
        self.port_combo.clear()
        ports = serial.tools.list_ports.comports()
        if not ports:
            self.port_combo.addItem("未找到串口")
            self.port_combo.setEnabled(False)
            self.connect_button.setEnabled(False)
        else:
            for port, desc, hwid in sorted(ports):
                self.port_combo.addItem(f"{port} - {desc}", port)
            self.port_combo.setEnabled(True)
            self.connect_button.setEnabled(True)
        self.statusBar().showMessage('串口列表已刷新')

    @Slot()
    def connect_device(self):
        """连接到选定的设备"""
        selected_index = self.port_combo.currentIndex()
        if selected_index == -1 or not self.port_combo.itemData(selected_index):
             QMessageBox.warning(self, "连接错误", "请选择一个有效的串口")
             return

        port_name = self.port_combo.itemData(selected_index)
        self.statusBar().showMessage(f'正在连接 {port_name}...')
        QApplication.processEvents()

        if self.reader and self.reader.connected:
            self.disconnect_device() # 会停止现有线程

        self.reader = AllSensorsReader(port_name)
        if self.reader.connect():
            self.statusBar().showMessage(f'成功连接到 {port_name}')
            self.connect_button.setEnabled(False)
            self.disconnect_button.setEnabled(True)
            self.port_combo.setEnabled(False)
            self.refresh_button.setEnabled(False)
            self.manual_refresh_button.setEnabled(True)
            self.set_auto_refresh(self.auto_refresh_combo.currentIndex()) # 启动定时器或首次更新
            self.trigger_data_update() # 首次连接后立即更新一次数据
        else:
            QMessageBox.critical(self, "连接失败", f"无法连接到 {port_name}。\n请检查设备是否连接或被占用。")
            self.statusBar().showMessage('连接失败')
            self.reader = None

    @Slot()
    def disconnect_device(self):
        """断开设备连接"""
        self.timer.stop() # 停止自动刷新

        if self.telemetry_worker and self.telemetry_worker.isRunning():
            self.telemetry_worker.stop()
            # self.telemetry_worker.wait() # 确保线程结束
        self.telemetry_worker = None

        if self.waveforms_worker and self.waveforms_worker.isRunning():
            self.waveforms_worker.stop()
            # self.waveforms_worker.wait() # 确保线程结束
        self.waveforms_worker = None

        if self.reader and self.reader.connected:
            self.reader.disconnect()
            self.statusBar().showMessage('设备已断开')
        else:
            self.statusBar().showMessage('设备未连接或已断开')

        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)
        self.port_combo.setEnabled(True)
        self.refresh_button.setEnabled(True)
        self.manual_refresh_button.setEnabled(False)
        self.reader = None # 清理reader实例
        self.clear_display()

    @Slot(int) # 明确参数类型
    def set_auto_refresh(self, index):
        """设置自动刷新间隔"""
        self.timer.stop()
        if index == 0: # 手动刷新
            self.statusBar().showMessage('自动刷新已关闭. 请使用手动刷新.')
            # 手动刷新模式下，不启动定时器
        else:
            intervals = [1000, 2000, 5000, 10000]
            interval = intervals[index - 1]
            if self.reader and self.reader.connected:
                self.timer.start(interval)
                self.statusBar().showMessage(f'自动刷新间隔: {interval/1000} 秒')
            else:
                 self.statusBar().showMessage('请先连接设备以启动自动刷新')

    @Slot()
    def trigger_data_update(self):
        """触发遥测和图谱数据的异步更新"""
        if not self.reader or not self.reader.connected:
            if self.timer.isActive():
                self.timer.stop()
                self.auto_refresh_combo.setCurrentIndex(0) # 回到手动刷新
                QMessageBox.warning(self, "连接断开", "设备连接已断开，自动刷新已停止。")
            self.statusBar().showMessage('设备未连接，无法更新数据')
            return

        self.statusBar().showMessage('准备读取数据...') # 更新状态提示
        QApplication.processEvents() # 允许UI更新

        # --- 启动遥测数据读取线程 ---
        if not self.telemetry_worker or not self.telemetry_worker.isRunning():
            self.telemetry_worker = TelemetryWorker(self.reader)
            self.telemetry_worker.data_ready.connect(self._handle_telemetry_data)
            self.telemetry_worker.error_occurred.connect(self._handle_worker_error)
            self.telemetry_worker.finished.connect(self._cleanup_telemetry_worker) # QThread.finished
            self.telemetry_worker.start()
        else:
            print("遥测数据线程已在运行")

        # --- 启动图谱数据读取线程 ---
        if not self.waveforms_worker or not self.waveforms_worker.isRunning():
            self.waveforms_worker = WaveformsWorker(self.reader)
            self.waveforms_worker.data_ready.connect(self._handle_waveforms_data)
            self.waveforms_worker.error_occurred.connect(self._handle_worker_error)
            self.waveforms_worker.finished.connect(self._cleanup_waveforms_worker) # QThread.finished
            self.waveforms_worker.start()
        else:
            print("图谱数据线程已在运行")

    # Slot to handle telemetry data from worker
    @Slot(dict)
    def _handle_telemetry_data(self, telemetry_data):
        """处理从工作线程接收到的遥测数据"""
        if telemetry_data:
            param_map = {
                'TEV放电次数': 0, 'TEV_dB值': 1, 'TEV_mV值': 2,
                '超声波_dB值': 3, '超声波_mV值': 4,
                'UHF_dB值': 5, 'UHF_mV值': 6
            }
            for key, value in telemetry_data.items():
                row = param_map.get(key)
                if row is not None:
                    display_value = '--'
                    if value is not None:
                        if isinstance(value, float):
                            display_value = f"{value:.2f}"
                        else:
                            display_value = str(value)
                    self.telemetry_table.setItem(row, 1, QTableWidgetItem(display_value))
            self.statusBar().showMessage('遥测数据已更新 ' + time.strftime('%H:%M:%S'))
        else:
            print("接收到空的遥测数据")
            # Optionally update table to show '读取失败' for telemetry
            for i in range(self.telemetry_table.rowCount()):
                 self.telemetry_table.setItem(i, 1, QTableWidgetItem('无数据'))

    # Slot to handle waveform data from worker
    @Slot(dict)
    def _handle_waveforms_data(self, waveform_data_dict):
        """处理从工作线程接收到的图谱数据"""
        if waveform_data_dict:
            self.tev_canvas.update_plot(waveform_data_dict.get('TEV图谱', []), "TEV图谱")
            self.ultrasonic_canvas.update_plot(waveform_data_dict.get('超声波图谱', []), "超声波图谱")
            self.uhf_canvas.update_plot(waveform_data_dict.get('UHF图谱', []), "UHF图谱")
            self.statusBar().showMessage('图谱数据已更新 ' + time.strftime('%H:%M:%S'))
        else:
            print("接收到空的图谱数据")
            self.tev_canvas.init_plot("TEV图谱 (无数据)")
            self.ultrasonic_canvas.init_plot("超声波图谱 (无数据)")
            self.uhf_canvas.init_plot("UHF图谱 (无数据)")

    # Slot to handle errors from workers
    @Slot(str)
    def _handle_worker_error(self, error_message):
        """处理工作线程发送的错误信息"""
        print(f"工作线程错误: {error_message}")
        self.statusBar().showMessage(f'错误: {error_message}')
        # Optionally, update specific parts of UI to indicate failure for that data type

    @Slot()
    def _cleanup_telemetry_worker(self):
        # print("遥测工作线程完成")
        if self.telemetry_worker:
            self.telemetry_worker.deleteLater() # Schedule for deletion
        self.telemetry_worker = None

    @Slot()
    def _cleanup_waveforms_worker(self):
        # print("图谱工作线程完成")
        if self.waveforms_worker:
            self.waveforms_worker.deleteLater() # Schedule for deletion
        self.waveforms_worker = None

    def update_data(self):
        """原有的 update_data，现在改为 trigger_data_update"""
        self.trigger_data_update()

    def clear_display(self):
         """清空数据显示区域"""
         for i in range(self.telemetry_table.rowCount()):
             self.telemetry_table.setItem(i, 1, QTableWidgetItem('--'))
         self.tev_canvas.init_plot("TEV图谱")
         self.ultrasonic_canvas.init_plot("超声波图谱")
         self.uhf_canvas.init_plot("UHF图谱")

    def closeEvent(self, event):
        """关闭窗口前确保断开连接并停止线程"""
        self.disconnect_device() # disconnect_device 现在会处理线程停止
        event.accept()

# --- Worker Threads ---
class WorkerThread(QThread):
    """工作线程基类"""
    error_occurred = Signal(str)  # 错误信号
    # finished_with_data = Signal() # 用于通知数据处理完成，可以清理worker -> 移除，使用QThread.finished

    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self):
        try:
            if not self.reader or not self.reader.connected:
                if self._is_running: self.error_occurred.emit("遥测读取: 设备未连接")
                return
            telemetry_data = self.reader.read_telemetry_data()
            if self._is_running:
                if telemetry_data:
                    self.data_ready.emit(telemetry_data)
                else:
                    self.error_occurred.emit("读取遥测数据失败或无数据")
        except Exception as e:
            if self._is_running: self.error_occurred.emit(f"遥测数据读取异常: {str(e)}")
        # finally:
            # if self._is_running: self.finished_with_data.emit() # -> 移除

class WaveformsWorker(WorkerThread):
    def run(self):
        try:
            if not self.reader or not self.reader.connected:
                if self._is_running: self.error_occurred.emit("图谱读取: 设备未连接")
                return
            waveform_data = self.reader.read_waveform_data()
            if self._is_running:
                if waveform_data:
                    self.data_ready.emit(waveform_data)
                else:
                    self.error_occurred.emit("读取图谱数据失败或无数据")
        except Exception as e:
            if self._is_running: self.error_occurred.emit(f"图谱数据读取异常: {str(e)}")
        # finally:
            # if self._is_running: self.finished_with_data.emit() # -> 移除

class AllSensorsReader:
    """读取 TEV, 超声波, UHF 传感器数据的类 (与GUI框架无关)"""

    def __init__(self, port, slave_address=1):
        """
        初始化监测装置连接

        参数:
            port: 串口名称，如 'COM1'
            slave_address: 从站地址，默认为1
        """
        self.port = port
        self.client = ModbusSerialClient(
            port=port,
            baudrate=9600,
            bytesize=8,
            parity='N',
            stopbits=1,
            timeout=1
        )
        self.slave_address = slave_address
        self.connected = False

    def connect(self):
        """建立与设备的连接"""
        try:
            self.connected = self.client.connect()
        except Exception as e:
            print(f"连接时发生错误: {e}")
            self.connected = False
        return self.connected

    def disconnect(self):
        """断开与设备的连接"""
        if self.connected:
            try:
                self.client.close()
                self.connected = False
            except Exception as e:
                print(f"断开连接时发生错误: {e}")

    def read_float(self, address):
        """读取浮点型数据"""
        if not self.connected: return None
        try:
            response = self.client.read_input_registers(address=address, count=2, slave=self.slave_address)
            if response.isError():
                print(f"读取寄存器 {address} (float) 错误: {response}")
                return None
            decoder = BinaryPayloadDecoder.fromRegisters(
                response.registers,
                byteorder=Endian.BIG,
                wordorder=Endian.LITTLE
            )
            return decoder.decode_32bit_float()
        except Exception as e:
            print(f"读取浮点数据时发生异常 (地址 {address}): {e}")
            return None

    def read_short(self, address):
        """读取短整型数据"""
        if not self.connected: return None
        try:
            response = self.client.read_input_registers(address=address, count=1, slave=self.slave_address)
            if response.isError():
                print(f"读取寄存器 {address} (short) 错误: {response}")
                return None
            return response.registers[0]
        except Exception as e:
            print(f"读取短整型数据时发生异常 (地址 {address}): {e}")
            return None

    def read_telemetry_data(self):
        """读取所有遥测数据"""
        if not self.connected: return None
        data = {}
        read_success = True
        tev_count = self.read_short(100); data['TEV放电次数'] = tev_count if tev_count is not None else None; read_success &= (tev_count is not None)
        # uhf_count = self.read_short(101); data['UHF放电次数'] = uhf_count if uhf_count is not None else None; read_success &= (uhf_count is not None)
        tev_mv = self.read_short(109); data['TEV_mV值'] = tev_mv if tev_mv is not None else None; read_success &= (tev_mv is not None)
        ultrasonic_mv = self.read_short(110); data['超声波_mV值'] = ultrasonic_mv if ultrasonic_mv is not None else None; read_success &= (ultrasonic_mv is not None)
        uhf_mv = self.read_short(111); data['UHF_mV值'] = uhf_mv if uhf_mv is not None else None; read_success &= (uhf_mv is not None)
        tev_db = self.read_float(102); data['TEV_dB值'] = tev_db if tev_db is not None else None; read_success &= (tev_db is not None)
        ultrasonic_db = self.read_float(104); data['超声波_dB值'] = ultrasonic_db if ultrasonic_db is not None else None; read_success &= (ultrasonic_db is not None)
        uhf_db = self.read_float(106); data['UHF_dB值'] = uhf_db if uhf_db is not None else None; read_success &= (uhf_db is not None)

        if not read_success:
            print("警告：部分遥测数据读取失败")
        return data

    def read_waveform_data(self, max_read_count=125):
        """读取三种图谱数据"""
        if not self.connected: return None
        waveforms = {}
        read_success = True
        waveform_info = {
            'TEV图谱': {'start_address': 2000, 'registers_to_read': 128},
            '超声波图谱': {'start_address': 2128, 'registers_to_read': 128},
            'UHF图谱': {'start_address': 2256, 'registers_to_read': 128},
        }
        for name, info in waveform_info.items():
            waveform_data = []
            start_address = info['start_address']
            registers_to_read = info['registers_to_read']
            current_address = start_address
            error_occurred = False
            try:
                while registers_to_read > 0:
                    count = min(registers_to_read, max_read_count)
                    response = self.client.read_input_registers(address=current_address, count=count, slave=self.slave_address)
                    if response.isError():
                        print(f"    读取 {name} 数据错误 (地址 {current_address}, 数量 {count}): {response}")
                        error_occurred = True; break
                    waveform_data.extend(response.registers)
                    registers_to_read -= count
                    current_address += count
                    time.sleep(0.1) # 避免请求过于频繁
                if not error_occurred:
                    waveforms[name] = waveform_data
                else:
                    waveforms[name] = []; read_success = False
            except Exception as e:
                print(f"  读取 {name} 时发生异常: {e}")
                waveforms[name] = []; read_success = False; break
        if not read_success:
            print("警告：部分图谱数据读取失败或发生异常")
        return waveforms

# --- Matplotlib Canvas Class (使用 PySide6) ---
class MonitorCanvas(FigureCanvas):
    """通用数据显示画布"""
    def __init__(self, parent=None, width=5, height=2, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = self.fig.add_subplot(111)
        super(MonitorCanvas, self).__init__(self.fig)
        self.setParent(parent)
        self.init_plot("图谱数据")

    def init_plot(self, title="图谱数据"):
        """初始化图表"""
        self.axes.clear()
        self.axes.set_title(title)
        self.axes.set_xlabel('采样点')
        self.axes.set_ylabel('幅值')
        self.axes.grid(True)
        self.fig.tight_layout()
        self.draw()

    def update_plot(self, data, title="图谱数据"):
        """更新图表数据"""
        self.axes.clear()
        if data:
             self.axes.plot(data, 'b-')
        self.axes.set_title(title)
        self.axes.set_xlabel('采样点')
        self.axes.set_ylabel('幅值')
        self.axes.grid(True)
        self.fig.tight_layout()
        self.draw()

# --- 主应用窗口类 (使用 PySide6) ---
class AllSensorsApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('GP-开关柜多传感器监测软件 (PySide6 - 多线程)')
        self.setGeometry(100, 100, 1000, 700)

        self.reader = None
        self.timer = QTimer(self) # 自动刷新定时器
        self.timer.timeout.connect(self.trigger_data_update) # 连接到触发更新的槽

        self.telemetry_worker = None
        self.waveforms_worker = None

        self.initUI()
        self.refresh_ports()

    def initUI(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # --- 连接控制区 ---
        connection_group = QGroupBox("连接设置")
        connection_layout = QHBoxLayout()
        connection_group.setLayout(connection_layout)

        self.port_combo = QComboBox()
        self.port_combo.setToolTip("选择设备连接的串口")
        self.refresh_button = QPushButton("刷新串口")
        self.refresh_button.clicked.connect(self.refresh_ports) # PySide6 信号连接
        self.connect_button = QPushButton("连接")
        self.connect_button.clicked.connect(self.connect_device) # PySide6 信号连接
        self.disconnect_button = QPushButton("断开")
        self.disconnect_button.clicked.connect(self.disconnect_device) # PySide6 信号连接
        self.disconnect_button.setEnabled(False)

        connection_layout.addWidget(QLabel("串口:"))
        connection_layout.addWidget(self.port_combo, 1)
        connection_layout.addWidget(self.refresh_button)
        connection_layout.addWidget(self.connect_button)
        connection_layout.addWidget(self.disconnect_button)

        # --- 数据显示区 (使用 QSplitter) ---
        # PySide6 使用 Qt.Orientation.Horizontal
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- 遥测数据显示区 ---
        telemetry_group = QGroupBox("遥测数据")
        telemetry_layout = QVBoxLayout()
        telemetry_group.setLayout(telemetry_layout)

        self.telemetry_table = QTableWidget()
        self.telemetry_table.setRowCount(7)  # 从8行改为7行，移除UHF放电次数
        self.telemetry_table.setColumnCount(2)
        self.telemetry_table.setHorizontalHeaderLabels(['参数', '值'])
        self.telemetry_table.verticalHeader().setVisible(False)
        # PySide6 中调整大小模式的设置方式
        self.telemetry_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.telemetry_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.telemetry_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers) # PySide6 枚举

        param_names = ['TEV放电次数', 'TEV_dB值', 'TEV_mV值',
                       '超声波_dB值', '超声波_mV值',
                       'UHF_dB值', 'UHF_mV值']  # 移除'UHF放电次数'
        for i, name in enumerate(param_names):
            self.telemetry_table.setItem(i, 0, QTableWidgetItem(name))
            self.telemetry_table.setItem(i, 1, QTableWidgetItem('--'))

        telemetry_layout.addWidget(self.telemetry_table)
        splitter.addWidget(telemetry_group)

        # --- 图谱显示区 ---
        waveform_group = QGroupBox("图谱数据")
        waveform_layout = QVBoxLayout()
        waveform_group.setLayout(waveform_layout)

        self.tev_canvas = MonitorCanvas(self)
        self.ultrasonic_canvas = MonitorCanvas(self)
        self.uhf_canvas = MonitorCanvas(self)

        self.tev_canvas.init_plot("TEV图谱")
        self.ultrasonic_canvas.init_plot("超声波图谱")
        self.uhf_canvas.init_plot("UHF图谱")

        waveform_layout.addWidget(self.tev_canvas)
        waveform_layout.addWidget(self.ultrasonic_canvas)
        waveform_layout.addWidget(self.uhf_canvas)
        splitter.addWidget(waveform_group)

        splitter.setSizes([300, 700])

        # --- 自动刷新控制 ---
        refresh_control_layout = QHBoxLayout()
        self.auto_refresh_combo = QComboBox()
        self.auto_refresh_combo.addItems(['手动刷新', '1秒', '2秒', '5秒', '10秒'])
        self.auto_refresh_combo.currentIndexChanged.connect(self.set_auto_refresh) # PySide6 信号连接
        self.manual_refresh_button = QPushButton("手动刷新数据")
        self.manual_refresh_button.clicked.connect(self.trigger_data_update) # PySide6 信号连接, 改为 trigger_data_update
        self.manual_refresh_button.setEnabled(False)

        refresh_control_layout.addWidget(QLabel("自动刷新:"))
        refresh_control_layout.addWidget(self.auto_refresh_combo)
        refresh_control_layout.addWidget(self.manual_refresh_button)
        refresh_control_layout.addStretch()

        # --- 布局整合 ---
        main_layout.addWidget(connection_group)
        main_layout.addWidget(splitter, 1)
        main_layout.addLayout(refresh_control_layout)

        # --- 状态栏 ---
        self.statusBar().showMessage('准备就绪')

    @Slot() # 明确标记为槽函数 (可选，但推荐)
    def refresh_ports(self):
        """刷新可用串口列表"""
        self.port_combo.clear()
        ports = serial.tools.list_ports.comports()
        if not ports:
            self.port_combo.addItem("未找到串口")
            self.port_combo.setEnabled(False)
            self.connect_button.setEnabled(False)
        else:
            for port, desc, hwid in sorted(ports):
                self.port_combo.addItem(f"{port} - {desc}", port)
            self.port_combo.setEnabled(True)
            self.connect_button.setEnabled(True)
        self.statusBar().showMessage('串口列表已刷新')

    @Slot()
    def connect_device(self):
        """连接到选定的设备"""
        selected_index = self.port_combo.currentIndex()
        if selected_index == -1 or not self.port_combo.itemData(selected_index):
             QMessageBox.warning(self, "连接错误", "请选择一个有效的串口")
             return

        port_name = self.port_combo.itemData(selected_index)
        self.statusBar().showMessage(f'正在连接 {port_name}...')
        QApplication.processEvents()

        if self.reader and self.reader.connected:
            self.disconnect_device() # 会停止现有线程

        self.reader = AllSensorsReader(port_name)
        if self.reader.connect():
            self.statusBar().showMessage(f'成功连接到 {port_name}')
            self.connect_button.setEnabled(False)
            self.disconnect_button.setEnabled(True)
            self.port_combo.setEnabled(False)
            self.refresh_button.setEnabled(False)
            self.manual_refresh_button.setEnabled(True)
            self.set_auto_refresh(self.auto_refresh_combo.currentIndex()) # 启动定时器或首次更新
            self.trigger_data_update() # 首次连接后立即更新一次数据
        else:
            QMessageBox.critical(self, "连接失败", f"无法连接到 {port_name}。\n请检查设备是否连接或被占用。")
            self.statusBar().showMessage('连接失败')
            self.reader = None

    @Slot()
    def disconnect_device(self):
        """断开设备连接"""
        self.timer.stop() # 停止自动刷新

        if self.telemetry_worker and self.telemetry_worker.isRunning():
            self.telemetry_worker.stop()
            # self.telemetry_worker.wait() # 确保线程结束
        self.telemetry_worker = None

        if self.waveforms_worker and self.waveforms_worker.isRunning():
            self.waveforms_worker.stop()
            # self.waveforms_worker.wait() # 确保线程结束
        self.waveforms_worker = None

        if self.reader and self.reader.connected:
            self.reader.disconnect()
            self.statusBar().showMessage('设备已断开')
        else:
            self.statusBar().showMessage('设备未连接或已断开')

        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)
        self.port_combo.setEnabled(True)
        self.refresh_button.setEnabled(True)
        self.manual_refresh_button.setEnabled(False)
        self.reader = None # 清理reader实例
        self.clear_display()

    @Slot(int) # 明确参数类型
    def set_auto_refresh(self, index):
        """设置自动刷新间隔"""
        self.timer.stop()
        if index == 0: # 手动刷新
            self.statusBar().showMessage('自动刷新已关闭. 请使用手动刷新.')
            # 手动刷新模式下，不启动定时器
        else:
            intervals = [1000, 2000, 5000, 10000]
            interval = intervals[index - 1]
            if self.reader and self.reader.connected:
                self.timer.start(interval)
                self.statusBar().showMessage(f'自动刷新间隔: {interval/1000} 秒')
            else:
                 self.statusBar().showMessage('请先连接设备以启动自动刷新')

    @Slot()
    def trigger_data_update(self):
        """触发遥测和图谱数据的异步更新"""
        if not self.reader or not self.reader.connected:
            if self.timer.isActive():
                self.timer.stop()
                self.auto_refresh_combo.setCurrentIndex(0) # 回到手动刷新
                QMessageBox.warning(self, "连接断开", "设备连接已断开，自动刷新已停止。")
            self.statusBar().showMessage('设备未连接，无法更新数据')
            return

        self.statusBar().showMessage('准备读取数据...') # 更新状态提示
        QApplication.processEvents() # 允许UI更新

        # --- 启动遥测数据读取线程 ---
        if not self.telemetry_worker or not self.telemetry_worker.isRunning():
            self.telemetry_worker = TelemetryWorker(self.reader)
            self.telemetry_worker.data_ready.connect(self._handle_telemetry_data)
            self.telemetry_worker.error_occurred.connect(self._handle_worker_error)
            self.telemetry_worker.finished.connect(self._cleanup_telemetry_worker) # QThread.finished
            self.telemetry_worker.start()
        else:
            print("遥测数据线程已在运行")

        # --- 启动图谱数据读取线程 ---
        if not self.waveforms_worker or not self.waveforms_worker.isRunning():
            self.waveforms_worker = WaveformsWorker(self.reader)
            self.waveforms_worker.data_ready.connect(self._handle_waveforms_data)
            self.waveforms_worker.error_occurred.connect(self._handle_worker_error)
            self.waveforms_worker.finished.connect(self._cleanup_waveforms_worker) # QThread.finished
            self.waveforms_worker.start()
        else:
            print("图谱数据线程已在运行")

    # Slot to handle telemetry data from worker
    @Slot(dict)
    def _handle_telemetry_data(self, telemetry_data):
        """处理从工作线程接收到的遥测数据"""
        if telemetry_data:
            param_map = {
                'TEV放电次数': 0, 'TEV_dB值': 1, 'TEV_mV值': 2,
                '超声波_dB值': 3, '超声波_mV值': 4,
                'UHF_dB值': 5, 'UHF_mV值': 6
            }
            for key, value in telemetry_data.items():
                row = param_map.get(key)
                if row is not None:
                    display_value = '--'
                    if value is not None:
                        if isinstance(value, float):
                            display_value = f"{value:.2f}"
                        else:
                            display_value = str(value)
                    self.telemetry_table.setItem(row, 1, QTableWidgetItem(display_value))
            self.statusBar().showMessage('遥测数据已更新 ' + time.strftime('%H:%M:%S'))
        else:
            print("接收到空的遥测数据")
            # Optionally update table to show '读取失败' for telemetry
            for i in range(self.telemetry_table.rowCount()):
                 self.telemetry_table.setItem(i, 1, QTableWidgetItem('无数据'))

    # Slot to handle waveform data from worker
    @Slot(dict)
    def _handle_waveforms_data(self, waveform_data_dict):
        """处理从工作线程接收到的图谱数据"""
        if waveform_data_dict:
            self.tev_canvas.update_plot(waveform_data_dict.get('TEV图谱', []), "TEV图谱")
            self.ultrasonic_canvas.update_plot(waveform_data_dict.get('超声波图谱', []), "超声波图谱")
            self.uhf_canvas.update_plot(waveform_data_dict.get('UHF图谱', []), "UHF图谱")
            self.statusBar().showMessage('图谱数据已更新 ' + time.strftime('%H:%M:%S'))
        else:
            print("接收到空的图谱数据")
            self.tev_canvas.init_plot("TEV图谱 (无数据)")
            self.ultrasonic_canvas.init_plot("超声波图谱 (无数据)")
            self.uhf_canvas.init_plot("UHF图谱 (无数据)")

    # Slot to handle errors from workers
    @Slot(str)
    def _handle_worker_error(self, error_message):
        """处理工作线程发送的错误信息"""
        print(f"工作线程错误: {error_message}")
        self.statusBar().showMessage(f'错误: {error_message}')
        # Optionally, update specific parts of UI to indicate failure for that data type

    @Slot()
    def _cleanup_telemetry_worker(self):
        # print("遥测工作线程完成")
        if self.telemetry_worker:
            self.telemetry_worker.deleteLater() # Schedule for deletion
        self.telemetry_worker = None

    @Slot()
    def _cleanup_waveforms_worker(self):
        # print("图谱工作线程完成")
        if self.waveforms_worker:
            self.waveforms_worker.deleteLater() # Schedule for deletion
        self.waveforms_worker = None

    def update_data(self):
        """原有的 update_data，现在改为 trigger_data_update"""
        self.trigger_data_update()

    def clear_display(self):
         """清空数据显示区域"""
         for i in range(self.telemetry_table.rowCount()):
             self.telemetry_table.setItem(i, 1, QTableWidgetItem('--'))
         self.tev_canvas.init_plot("TEV图谱")
         self.ultrasonic_canvas.init_plot("超声波图谱")
         self.uhf_canvas.init_plot("UHF图谱")

    def closeEvent(self, event):
        """关闭窗口前确保断开连接并停止线程"""
        self.disconnect_device() # disconnect_device 现在会处理线程停止
        event.accept()

def main_gui():
    app = QApplication(sys.argv)
    mainWin = AllSensorsApp()
    mainWin.show()
    sys.exit(app.exec()) # PySide6 使用 exec()

if __name__ == '__main__':
    main_gui()