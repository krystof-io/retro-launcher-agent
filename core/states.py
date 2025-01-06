from enum import Enum, auto

class EmulatorState(Enum):
    IDLE = auto()
    LAUNCHING = auto()
    RUNNING = auto()
    STOPPING = auto()
    ERROR = auto()

class MonitorMode(Enum):
    REAL = auto()
    SIMULATED = auto()