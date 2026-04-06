from services.ocr_service import OCRService


def test_ocr_backend_detection():
    service = OCRService()
    backend = service._get_available_backend()
    assert backend in {None, "tesseract", "paddle"}

    if backend == "tesseract":
        assert service._tesseract_available() is True
