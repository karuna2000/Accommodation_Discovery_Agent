from src.api.server import create_app
from src.config.settings import Settings

settings = Settings()
app = create_app(settings=settings)
