# 🚀 QUICK START: x02 Vision V2 API

## YOU HAVE 3 FILES

1. **media_processor.py** - Extracts frames & processes media
2. **x02_vision_v2_api.py** - FastAPI service
3. **efficientnet_model.py** - Your trained model (already have)

---
## BASE URL FOR PRODUCTION: https://vision.x02.me

## STEP 1: Copy Files (1 min)

Create folder:
```
x02_vision_v2/
├─ efficientnet_model.py (you already have this)
├─ media_processor.py (download)
├─ x02_vision_v2_api.py (download)
│
└─ x02_vision_v2_efficientnet_b4_best.pth (your trained model)
```

---

## STEP 2: Install Dependencies (2 min)

```bash
pip install fastapi uvicorn slowapi torch torchvision pillow opencv-python requests
```

---

## STEP 3: Start the Service (1 min)

```bash
python x02_vision_v2_api.py
```

You'll see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
✓ Service initialized successfully
```

---

## STEP 4: Test It (5 min)

### Test 1: Health Check
```bash
curl http://localhost:8000/health
```

### Test 2: Moderate an Image (file)
```bash
curl -X POST http://localhost:8000/moderate-image \
  -F "file=@test_image.jpg"
```

### Test 3: Moderate an Image (URL)
```bash
curl -X POST http://localhost:8000/moderate-image \
  -F "image_url=https://example.com/image.jpg"
```

### Test 4: Moderate a GIF
```bash
curl -X POST http://localhost:8000/moderate-gif \
  -F "file=@test.gif"
```

### Test 5: Moderate a Video
```bash
curl -X POST http://localhost:8000/moderate-video \
  -F "file=@test.mp4" \
  -F "frame_interval=5"
```

### Test 6: Auto-detect (Smart)
```bash
curl -X POST http://localhost:8000/moderate-media \
  -F "file=@any_media_file"
```

---

## WHAT YOU GET

Each response includes:

```json
{
  "model": "x02_vision_v2_efficientnet_b4",
  "media_type": "image",
  "recommendation": "allow",
  "aggregated_scores": {
    "average_score": 5.2,
    "max_score": 12.3,
    "frame_count": 1
  },
  "inference_time_ms": 245
}
```

**recommendation** can be:
- `allow` - Safe, publish it
- `soft_flag` - Review needed
- `hard_block` - Remove immediately

---

## ENDPOINTS SUMMARY

| Endpoint | Use | Input |
|----------|-----|-------|
| `/moderate-image` | Single image | File or URL |
| `/moderate-gif` | GIF animation | File or URL |
| `/moderate-video` | Video file | File or URL |
| `/moderate-media` | Auto-detect | File or URL |

---

## PYTHON TEST CODE

```python
import requests

API = "http://localhost:8000"

# Test image from file
with open("test.jpg", 'rb') as f:
    result = requests.post(
        f"{API}/moderate-image",
        files={'file': f}
    ).json()
    print(f"Image: {result['recommendation']}")

# Test from URL
result = requests.post(
    f"{API}/moderate-image",
    data={'image_url': 'https://example.com/image.jpg'}
).json()
print(f"URL Image: {result['recommendation']}")

# Test video
with open("test.mp4", 'rb') as f:
    result = requests.post(
        f"{API}/moderate-video",
        files={'file': f},
        data={'frame_interval': 5}
    ).json()
    print(f"Video: {result['recommendation']}")
    print(f"Flagged: {result['aggregated_scores']['flagged_percentage']}%")
```

---

## RATE LIMITS

- All endpoints: 100/min per IP
- Concurrent processing: 8 requests at once

---

## PERFORMANCE

| Media | Processing | Notes |
|-------|-----------|-------|
| Image | ~0.1-0.2s | Very fast (OCR removed) |
| GIF (50 frames) | ~3-5s | Fast batch processing |
| Video (30s) | ~10-20s | Configurable frame interval |

---

## THAT'S IT!

```
1. Copy 3 files ✓
2. Install pip packages ✓
3. python x02_vision_v2_api.py ✓
4. Test with curl ✓
5. Done! 🎉
```

Service is **production-ready** and handles:
- ✅ Images (upload + URL)
- ✅ GIFs (upload + URL)
- ✅ Videos (upload + URL)
- ✅ Auto-detection
- ✅ Rate limiting
- ✅ Error handling

---

## NEXT: INTEGRATE WITH YOUR PLATFORM

Once running, integrate with your x02.me API:

```python
# In your post creation endpoint
def create_post(image, caption):
    # Moderate image
    result = requests.post(
        "http://moderation:8000/moderate-image",
        files={'file': image}
    ).json()
    
    if result['recommendation'] == 'hard_block':
        raise Exception("Inappropriate content")
    
    # Save post if safe
    save_post(image, caption)
```

---

## QUESTIONS?

- "How do I change frame interval?" → Use `frame_interval` parameter
- "Can I increase rate limits?" → Modify code in api file
- "How do I deploy?" → Use Docker or Gunicorn
- "How do I monitor?" → Check `/health` endpoint

**Ready? Start the service!** 🚀
