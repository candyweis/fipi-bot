module.exports = {
  apps: [{
    name: 'fipi-bot',
    script: '/root/fipi-bot/venv/bin/python',
    args: '/root/fipi-bot/main.py',
    interpreter: 'none',
    cwd: '/root/fipi-bot',
    autorestart: true,
    watch: false,
    max_memory_restart: '1G',
    min_uptime: '10s',
    max_restarts: 5,
    restart_delay: 5000,
    env: {
      NODE_ENV: 'production',
      PYTHONPATH: '/root/fipi-bot',
      DISPLAY: ':99',
      VIRTUAL_ENV: '/root/fipi-bot/venv',
      PATH: '/root/fipi-bot/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
    },
    error_file: '/root/fipi-bot/logs/err.log',
    out_file: '/root/fipi-bot/logs/out.log',
    log_file: '/root/fipi-bot/logs/combined.log',
    time: true,
    log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
    // Специальные настройки для root
    uid: 0,
    gid: 0
  }]
};
