"""
cameras.py
==========
REST endpoints untuk status kamera.

Endpoints:
    GET  /api/cameras/         — Daftar semua kamera & status real-time
    GET  /api/cameras/{id}     — Status satu kamera
"""

from fastapi import APIRouter, HTTPException

from app.models.schemas import CameraStatus, FallState

router = APIRouter()

# In-memory registry kamera aktif.
# Di production, ini akan dikelola oleh camera manager service.
_camera_registry: dict[str, CameraStatus] = {}


def register_camera(camera_id: str) -> None:
    """Daftarkan kamera baru ke registry."""
    if camera_id not in _camera_registry:
        _camera_registry[camera_id] = CameraStatus(camera_id=camera_id)


def update_camera_status(camera_id: str, **kwargs) -> None:
    """Update status kamera di registry."""
    if camera_id in _camera_registry:
        for key, value in kwargs.items():
            setattr(_camera_registry[camera_id], key, value)


@router.get("/", response_model=list[CameraStatus])
async def get_cameras():
    """Ambil status semua kamera yang terdaftar."""
    return list(_camera_registry.values())


@router.get("/{camera_id}", response_model=CameraStatus)
async def get_camera(camera_id: str):
    """Ambil status satu kamera berdasarkan ID."""
    if camera_id not in _camera_registry:
        raise HTTPException(status_code=404, detail="Camera not found")
    return _camera_registry[camera_id]
