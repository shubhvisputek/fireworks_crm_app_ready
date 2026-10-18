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
    backup_dir: str = ''
    host: str = '127.0.0.1'
    port: int = 8000
    timezone: str = 'Asia/Kolkata'
    secure_cookies: bool = False
    admin_password: str | None = None
    require_admin_password: bool = False
    seed_demo: bool = False
    max_body_bytes: int = 10 * 1024 * 1024
    max_restore_bytes: int = 500 * 1024 * 1024
    auto_backup: bool = True
    session_days: int = 7
    login_max_failures: int = 10
    login_window_seconds: int = 15 * 60
    default_admin_password: str = field(default='admin123', repr=False)
    trust_proxy: bool = False  # take the client address from X-Forwarded-For (only behind your own proxy)
    allowed_hosts: tuple = ()  # extra host names, e.g. a domain behind a reverse proxy (FIREWORKS_ALLOWED_HOSTS)

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
            backup_dir=env.get('FIREWORKS_BACKUP_DIR', os.path.join(data_dir, 'backups')),
            auto_backup=env.get('FIREWORKS_AUTO_BACKUP', '1') != '0',
            host=env.get('HOST', '127.0.0.1'),
            port=int(env.get('PORT', '8000')),
            timezone=env.get('FIREWORKS_TIMEZONE', 'Asia/Kolkata'),
            secure_cookies=env.get('FIREWORKS_SECURE_COOKIES') == '1',
            trust_proxy=env.get('FIREWORKS_TRUST_PROXY') == '1',
            # Render sets RENDER_EXTERNAL_HOSTNAME to the service's public name.
            allowed_hosts=tuple(h.strip().lower().rstrip('.') for h in
                                f"{env.get('FIREWORKS_ALLOWED_HOSTS', '')},{env.get('RENDER_EXTERNAL_HOSTNAME', '')}".split(',') if h.strip()),
            admin_password=env.get('FIREWORKS_ADMIN_PASSWORD') or None,
            require_admin_password=env.get('FIREWORKS_REQUIRE_ADMIN_PASSWORD') == '1',
            seed_demo=env.get('FIREWORKS_SEED_DEMO') == '1',
            max_body_bytes=int(env.get('FIREWORKS_MAX_BODY_BYTES', str(10 * 1024 * 1024))),
        )

    def ensure_directories(self):
        for path in (os.path.dirname(self.db_path), os.path.dirname(self.secret_path), self.backup_dir):
            if path:
                os.makedirs(path, mode=0o700, exist_ok=True)
