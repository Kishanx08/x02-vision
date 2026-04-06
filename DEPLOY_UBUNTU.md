# Ubuntu VPS Deployment

## 1. Install system packages

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv nginx
```

## 2. Install Node.js and PM2

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
sudo npm install -g pm2
```

## 3. Copy project to server

Example target:

```bash
sudo mkdir -p /opt/x02vision-v2
sudo chown $USER:$USER /opt/x02vision-v2
```

Put these files there:
- `efficientnet_model.py`
- `media_processor.py`
- `x02_vision_v2_api.py`
- `services/`
- `requirements.txt`
- `ecosystem.config.cjs`
- `nginx-media-moderation.conf`
- `x02_vision_v2_efficientnet_b4_best.pth` (⚠️ **NOT in git - obtain separately**)

## 4. Create virtual environment

```bash
cd /opt/x02vision-v2
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 5. Start with PM2

```bash
cd /opt/x02vision-v2
pm2 start ecosystem.config.cjs
pm2 save
pm2 startup
```

Useful commands:

```bash
pm2 status
pm2 logs x02vision-v2
pm2 restart media-moderation
pm2 stop media-moderation
```

## 6. Configure Nginx

Copy the included config:

```bash
sudo cp nginx-media-moderation.conf /etc/nginx/sites-available/x02vision-v2
sudo ln -s /etc/nginx/sites-available/x02vision-v2 /etc/nginx/sites-enabled/x02vision-v2
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

## 7. Optional domain + TLS

If you have a domain:

1. Point DNS to the VPS
2. Replace `server_name _;` in the Nginx config with your domain
3. Install TLS:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

## Notes

- Keep `workers=1` if you are using one GPU-bound model copy.
- On CPU-only VPS, you can consider more than one worker, but each worker loads its own model into memory.
- Put Nginx in front for TLS, request buffering, and public exposure.
