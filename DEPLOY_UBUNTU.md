# Ubuntu VPS Deployment

## 1. Install system packages

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv nginx tesseract-ocr
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
sudo mkdir -p /opt/media_moderation
sudo chown $USER:$USER /opt/media_moderation
```

Put these files there:
- `efficientnet_model.py`
- `media_processor.py`
- `media_moderation_api.py`
- `services/`
- `requirements.txt`
- `ecosystem.config.cjs`
- `x02_vision_v2_efficientnet_b4_best.pth`

## 4. Create virtual environment

```bash
cd /opt/media_moderation
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 5. Start with PM2

```bash
cd /opt/media_moderation
pm2 start ecosystem.config.cjs
pm2 save
pm2 startup
```

Useful commands:

```bash
pm2 status
pm2 logs media-moderation
pm2 restart media-moderation
pm2 stop media-moderation
```

## 6. Configure Nginx

Copy the included config:

```bash
sudo cp nginx-media-moderation.conf /etc/nginx/sites-available/media-moderation
sudo ln -s /etc/nginx/sites-available/media-moderation /etc/nginx/sites-enabled/media-moderation
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

- PM2 is configured to bind Uvicorn to `127.0.0.1:8000` and let Nginx expose it publicly.
- `workers=1` is intentional so one process owns one model copy. Increase carefully because each worker loads the model again.
- `client_max_body_size 500M` matches the API upload limit.
- Remote URL downloads are temporary and are deleted after processing.
- OCR requires `tesseract-ocr`, which is included in the install command above.
- DistilBERT-based text moderation is installed from `requirements.txt` via `transformers`.
- If you want PaddleOCR instead of Tesseract, install it separately on the VPS with `pip install paddleocr`.
