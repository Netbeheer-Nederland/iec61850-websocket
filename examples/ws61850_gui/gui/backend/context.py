from gui.connection_manager import ConnectionManager
from gui.model_service import ModelService
from gui.state import RuntimeState

runtime = RuntimeState()
connection_manager = ConnectionManager(runtime)
model_service = ModelService(runtime, connection_manager)
