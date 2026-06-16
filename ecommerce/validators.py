from django.core.exceptions import ValidationError
import imghdr


def validate_image_file(file):
    """Validate uploaded image: type and max size (5 MB)."""
    max_mb = 5
    max_bytes = max_mb * 1024 * 1024

    # File size check
    if hasattr(file, 'size') and file.size > max_bytes:
        raise ValidationError(f"Image size must be at most {max_mb} MB.")

    # Basic check that the file is a valid image
    try:
        header = file.read(512)
        file.seek(0)
    except Exception:
        # If we cannot read the file, reject it
        raise ValidationError("Unable to read uploaded file.")

    if not imghdr.what(None, header):
        raise ValidationError("Uploaded file is not a valid image.")

    return file
