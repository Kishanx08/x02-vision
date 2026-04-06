module.exports = {
  apps: [
    {
      name: "media-moderation",
      script: ".venv/bin/python",
      args: "-m uvicorn media_moderation_api:app --host 127.0.0.1 --port 8000 --workers 1",
      cwd: "/opt/media_moderation",
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