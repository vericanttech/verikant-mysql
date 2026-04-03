"""
Optional SSH tunnel to PythonAnywhere MySQL for local development.

Set SSH_TUNNEL=1 and PA_SSH_* vars (see .env.example). The app rewrites the
SQLAlchemy URI to 127.0.0.1:<local_port> while the tunnel is active.
"""
from __future__ import annotations

import atexit
import os
from typing import Any, Optional, Tuple

_tunnel: Optional[Any] = None


def maybe_start_ssh_tunnel(database_url: str) -> Tuple[str, Optional[Any]]:
    """
    If SSH_TUNNEL is enabled and URL is MySQL, start sshtunnel and return
    a new URL pointing at the local forward port.
    """
    global _tunnel

    flag = os.environ.get('SSH_TUNNEL', '').strip().lower()
    if flag not in ('1', 'true', 'yes'):
        return database_url, None

    if not database_url.startswith('mysql'):
        return database_url, None

    from sqlalchemy.engine.url import make_url
    import sshtunnel
    from sshtunnel import SSHTunnelForwarder

    try:
        u = make_url(database_url)
    except Exception:
        return database_url, None

    remote_host = u.host
    remote_port = u.port or 3306
    if not remote_host:
        return database_url, None

    ssh_host = os.environ.get('PA_SSH_HOST', 'ssh.pythonanywhere.com')
    ssh_user = os.environ.get('PA_SSH_USER', '').strip()
    ssh_password = os.environ.get('PA_SSH_PASSWORD')
    ssh_key = os.environ.get('PA_SSH_KEY_PATH', '').strip() or None

    if not ssh_user:
        raise RuntimeError('SSH_TUNNEL is enabled but PA_SSH_USER is not set.')

    if not ssh_password and not ssh_key:
        raise RuntimeError(
            'SSH_TUNNEL is enabled but set PA_SSH_PASSWORD (website login) '
            'or PA_SSH_KEY_PATH to an SSH private key.'
        )

    timeout = float(os.environ.get('SSH_TUNNEL_TIMEOUT', '30'))
    sshtunnel.SSH_TIMEOUT = timeout
    sshtunnel.TUNNEL_TIMEOUT = timeout

    tunnel = SSHTunnelForwarder(
        (ssh_host, 22),
        ssh_username=ssh_user,
        ssh_password=ssh_password if ssh_password else None,
        ssh_pkey=ssh_key,
        remote_bind_address=(remote_host, int(remote_port)),
        local_bind_address=('127.0.0.1', 0),
    )
    tunnel.start()
    _tunnel = tunnel

    def _stop_tunnel() -> None:
        try:
            if tunnel.is_active:
                tunnel.stop()
        except Exception:
            pass

    atexit.register(_stop_tunnel)

    local_port = tunnel.local_bind_port
    new_url = u.set(host='127.0.0.1', port=local_port).render_as_string(
        hide_password=False
    )
    return new_url, tunnel
