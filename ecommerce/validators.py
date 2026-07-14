from django.core.exceptions import ValidationError

IMAGE_SIGNATURES = {
    b'\x89PNG': 'image/png',
    b'\xff\xd8\xff': 'image/jpeg',
    b'GIF87a': 'image/gif',
    b'GIF89a': 'image/gif',
    b'RIFF': 'image/webp',
    b'BM': 'image/bmp',
}


def validate_image_file(file):
    """Validate uploaded image: type and max size (5 MB)."""
    max_mb = 5
    max_bytes = max_mb * 1024 * 1024

    if hasattr(file, 'size') and file.size > max_bytes:
        raise ValidationError(f"Image size must be at most {max_mb} MB.")

    try:
        header = file.read(512)
        file.seek(0)
    except Exception:
        raise ValidationError("Unable to read uploaded file.")

    is_valid = any(header.startswith(sig) for sig in IMAGE_SIGNATURES)
    if not is_valid:
        raise ValidationError("Uploaded file is not a valid image.")

    return file
