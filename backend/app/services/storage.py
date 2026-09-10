import os
import hashlib
import shutil
from app.core.config import settings

class StorageService:
    def save(self, file_path: str, batch_id: int) -> str:
        sha256 = self._calculate_sha256(file_path)
        target_dir = os.path.join(settings.STORAGE_DIR, str(batch_id))
        os.makedirs(target_dir, exist_ok=True)
        target_path = os.path.join(target_dir, os.path.basename(file_path))
        shutil.copy(file_path, target_path)
        return target_path

    def _calculate_sha256(self, file_path: str) -> str:
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
