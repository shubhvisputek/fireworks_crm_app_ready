"""Runtime configuration, read once from environment variables."""
import os
from dataclasses import dataclass, field

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOOPBACK_HOSTS = ('127.0.0.1', 'localhost', '::1')


@dataclass(frozen=True)
class Config:
    db_path: str
    secret_path: str
    static_dir: str
    host: str = '127.0.0.1'
    port: int = 8000
    timezone: str = 'Asia/Kolkata'
    secure_cookies: bool = False
    admin_password: str | None = None
    require_admin_password: bool = False
    seed_demo: bool = False
    max_body_bytes: int = 10 * 1024 * 1024
    session_days: int = 7
    login_max_failures: int = 10
    login_window_seconds: int = 15 * 60
    default_admin_password: str = field(default='admin123', repr=False)

    @property
    def is_network_exposed(self):
        return self.host not in LOOPBACK_HOSTS

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        data_dir = env.get('FIREWORKS_DATA_DIR', os.path.join(BASE_DIR, 'data'))
        return cls(
            db_path=env.get('FIREWORKS_DB', os.path.join(data_dir, 'fireworks.db')),
            secret_path=env.get('FIREWORKS_SECRET', os.path.join(data_dir, '.secret')),
            static_dir=os.path.join(BASE_DIR, 'static'),
            host=env.get('HOST', '127.0.0.1'),
            port=int(env.get('PORT', '8000')),
            timezone=env.get('FIREWORKS_TIMEZONE', 'Asia/Kolkata'),
            secure_cookies=env.get('FIREWORKS_SECURE_COOKIES') == '1',
            admin_password=env.get('FIREWORKS_ADMIN_PASSWORD') or None,
            require_admin_password=env.get('FIREWORKS_REQUIRE_ADMIN_PASSWORD') == '1',
            seed_demo=env.get('FIREWORKS_SEED_DEMO') == '1',
            max_body_bytes=int(env.get('FIREWORKS_MAX_BODY_BYTES', str(10 * 1024 * 1024))),
        )

    def ensure_directories(self):
        for path in (os.path.dirname(self.db_path), os.path.dirname(self.secret_path)):
            if path:
                os.makedirs(path, exist_ok=True)
