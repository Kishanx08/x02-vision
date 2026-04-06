module.exports = {
  apps: [
    {
      name: "x02vision-v2",
      script: "/root/x02-vision/.venv/bin/python",
      args: "-m uvicorn x02_vision_v2_api:app --host 0.0.0.0 --port 8000 --workers 1",
      cwd: "/root/x02-vision",
      instances: 1,
      exec_mode: "fork",
      autorestart: true,
      watch: false,
      max_memory_restart: "2G",
      env: {
        PYTHONUNBUFFERED: "1"
      }
    }
  ]
};