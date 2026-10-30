module.exports = {
  apps: [
    {
      name: "Resume_Analyzer",
      cwd: "./Backend",
      script: "uvicorn",
      args: "app.main:app --host 0.0.0.0 --port 8400",
      interpreter: "none",
      env: {
        NODE_ENV: "production",
      },
      watch: false,
      max_memory_restart: "1G",
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      out_file: "./logs/pm2-out.log",
      error_file: "./logs/pm2-err.log",
    },
  ],
};