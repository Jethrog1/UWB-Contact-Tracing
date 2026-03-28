import time
import re
from PyQt6.QtCore import QThread, pyqtSignal

try:
    import serial
except ImportError:
    serial = None

class SerialReaderThread(QThread):
    """
    Background QThread that continuously reads from a physical serial port.
    It attempts to parse lines containing a Tag ID (T0, T1, etc) and two floats (X, Y).
    """
    # tag_id, x, y
    tag_update = pyqtSignal(str, float, float)
    connection_error = pyqtSignal(str)
    
    def __init__(self, port: str, baudrate: int = 115200):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self._running = True
        
    def run(self):
        if serial is None:
            self.connection_error.emit("pyserial is not installed. Please install it using: pip install pyserial")
            return

        try:
            with serial.Serial(self.port, self.baudrate, timeout=1.0) as ser:
                while self._running:
                    try:
                        line = ser.readline().decode('utf-8', errors='ignore').strip()
                        if not line:
                            continue
                        
                        # Try to parse flexible layouts:
                        # "T0,1.23,4.56"
                        # "T1|2.34|5.67"
                        # "T2 X: 1.23 Y: 4.56"
                        
                        # Regex targets: tag starting with T followed by digits, and two subsequent floats
                        match = re.search(r'(T\d+)[^\d+-]+([+-]?\d*\.\d+|[+-]?\d+)[^\d+-]+([+-]?\d*\.\d+|[+-]?\d+)', line)
                        
                        if match:
                            tag_id = match.group(1)
                            x = float(match.group(2))
                            y = float(match.group(3))
                            self.tag_update.emit(tag_id, x, y)
                        else:
                            # Fallback: strictly positional splits like "T0,1.23,4.56"
                            parts = re.split(r'[,|;]', line)
                            if len(parts) >= 3:
                                tag_id = parts[0].strip()
                                if tag_id.startswith('T'):
                                    try:
                                        x = float(parts[1].strip())
                                        y = float(parts[2].strip())
                                        self.tag_update.emit(tag_id, x, y)
                                    except ValueError:
                                        pass
                    except serial.SerialException as e:
                        self.connection_error.emit(f"Serial read error: {e}")
                        break
        except Exception as e:
            self.connection_error.emit(f"Failed to open port {self.port}: {e}")
            
    def stop(self):
        self._running = False
        self.wait()

class MockSerialReaderThread(QThread):
    """
    Virtual Hardware Simulator that oscillates fake T0, T1, T2 tags.
    """
    tag_update = pyqtSignal(str, float, float)
    connection_error = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self._running = True
        
    def run(self):
        import math
        t = 0.0
        while self._running:
            try:
                # T0 moves in a wide circle
                x0 = 5.0 + 3.0 * math.cos(t)
                y0 = 4.0 + 3.0 * math.sin(t)
                
                # T1 moves in a figure-8
                x1 = 5.0 + 2.0 * math.sin(t)
                y1 = 4.0 + 2.0 * math.sin(t) * math.cos(t)
                
                # T2 wanders slowly
                x2 = 2.0 + 1.5 * math.cos(t * 0.5)
                y2 = 6.0 + 1.5 * math.sin(t * 0.3)
                
                self.tag_update.emit("T0", x0, y0)
                self.tag_update.emit("T1", x1, y1)
                self.tag_update.emit("T2", x2, y2)
                
                t += 0.1
                time.sleep(0.1)
            except Exception as e:
                self.connection_error.emit(str(e))
                break
                
    def stop(self):
        self._running = False
        self.wait()
