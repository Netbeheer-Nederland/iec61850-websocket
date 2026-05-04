from bff.connection_manager import ConnectionManager
from bff.model_service import ModelService
from bff.state import RuntimeState

runtime = RuntimeState()
connection_manager = ConnectionManager(runtime)
model_service = ModelService(runtime, connection_manager)
