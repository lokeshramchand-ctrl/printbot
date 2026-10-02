import re
import random
import string
from datetime import datetime

def generate_order_id(sequence_num: int = None) -> str:
    """Generate a clean unique Order ID like PRN-100234."""
    if sequence_num is not None:
        return f"PRN-{sequence_num:06d}"
    
    # Fallback timestamp + random suffix
    time_part = datetime.utcnow().strftime("%y%m%d%H%M")
    rand_part = "".join(random.choices(string.digits, k=3))
    return f"PRN-{time_part}{rand_part}"

def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal and unsafe characters."""
    filename = re.sub(r'[^\w\s\.-]', '_', filename)
    filename = filename.strip().replace(' ', '_')
    return filename or "document"

def format_file_size(size_bytes: int) -> str:
    """Format bytes into readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
