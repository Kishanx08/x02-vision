module.exports = {
  apps: [
    {
      name: "x02vision-v2",
      script: ".venv/bin/python",
      args: "-m uvicorn x02_vision_v2_api:app --host 127.0.0.1 --port 8000 --workers 1",
      cwd: "/opt/x02vision-v2",
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