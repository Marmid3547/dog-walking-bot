module.exports = {
  apps: [{
    name: 'bot',
    script: 'bot.py',
    interpreter: '/root/dog-walking-bot/venv/bin/python',
    cwd: '/root/dog-walking-bot',
    env: {
      NODE_ENV: 'production'
    },
    error_file: './logs/err.log',
    out_file: './logs/out.log',
    log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
    merge_logs: true,
    autorestart: true,
    watch: false,
    max_memory_restart: '1G',
    instances: 1,
    exec_mode: 'fork'
  }]
};
