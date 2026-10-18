from crm.repositories.base import Repository

PUBLIC_COLUMNS = 'id, username, role, active, created_at'


class UserRepository(Repository):
    def get(self, user_id):
        return self.one('SELECT * FROM users WHERE id=?', (user_id,))

    def get_active(self, user_id):
        return self.one('SELECT * FROM users WHERE id=? AND active=1', (user_id,))

    def get_active_by_username(self, username):
        return self.one('SELECT * FROM users WHERE username=? AND active=1', (username,))

    def username_exists(self, username):
        return self.scalar('SELECT 1 FROM users WHERE username=?', (username,)) is not None

    def list_public(self):
        return self.all(f'SELECT {PUBLIC_COLUMNS} FROM users ORDER BY role, username')

    def list_active_hashes(self):
        return [row['password_hash'] for row in self.all('SELECT password_hash FROM users WHERE active=1')]

    def count(self):
        return self.scalar('SELECT COUNT(*) FROM users', default=0)

    def count_active_owners(self):
        return self.scalar("SELECT COUNT(*) FROM users WHERE role='OWNER' AND active=1", default=0)

    def create(self, username, password_hash, role, created_at):
        return self.insert('users', {'username': username, 'password_hash': password_hash, 'role': role, 'active': 1, 'created_at': created_at})

    def set_active(self, user_id, active):
        # Deactivating also bumps the session version so open sessions end immediately.
        self.execute('UPDATE users SET active=?, session_version=session_version+? WHERE id=?', (int(active), 0 if active else 1, user_id))

    def set_password(self, user_id, password_hash):
        self.execute('UPDATE users SET password_hash=?, session_version=session_version+1 WHERE id=?', (password_hash, user_id))
        return self.scalar('SELECT session_version FROM users WHERE id=?', (user_id,), default=0)
