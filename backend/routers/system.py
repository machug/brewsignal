"""System management endpoints.

Safety: Destructive operations (reboot/shutdown) require:
1. Request comes from localhost/LAN (checked by default)
2. Explicit confirmation in request body
"""

import logging
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..cleanup import cleanup_old_readings, get_reading_stats

# Hailo detection paths
HAILORTCLI_PATH = "/usr/bin/hailortcli"
HAILO_DEVICE_PATH = "/dev/hailo0"

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/system", tags=["system"])

# System command paths - hardcoded for security (prevents PATH manipulation attacks)
TIMEDATECTL_PATH = "/usr/bin/timedatectl"
SUDO_PATH = "/usr/bin/sudo"

# Read version from VERSION file
_version_file = Path(__file__).parent.parent.parent / "VERSION"
VERSION = _version_file.read_text().strip() if _version_file.exists() else "0.0.0"


class GPUInfo(BaseModel):
    """GPU information for inference capability assessment."""
    vendor: str  # "nvidia", "amd", "intel", "apple", "none"
    name: Optional[str] = None
    vram_mb: Optional[int] = None


class PlatformInfo(BaseModel):
    """Platform detection for contextual recommendations."""
    is_raspberry_pi: bool
    model: Optional[str] = None  # e.g., "Raspberry Pi 5 Model B Rev 1.0"
    architecture: str  # e.g., "aarch64", "x86_64"
    gpu: GPUInfo


class SystemInfo(BaseModel):
    hostname: str
    ip_addresses: list[str]
    uptime_seconds: Optional[float]
    version: str = VERSION
    platform: Optional[PlatformInfo] = None


class SystemAction(BaseModel):
    confirm: bool = False


class TimezoneUpdate(BaseModel):
    timezone: str


def get_ip_addresses() -> list[str]:
    """Get all non-loopback IP addresses."""
    ips = []
    try:
        result = subprocess.run(
            ["hostname", "-I"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            ips = result.stdout.strip().split()
    except Exception:
        pass
    return ips


def get_uptime() -> Optional[float]:
    """Get system uptime in seconds."""
    try:
        with open("/proc/uptime") as f:
            return float(f.read().split()[0])
    except Exception:
        return None


def detect_platform() -> PlatformInfo:
    """Detect platform type (Pi vs desktop) and GPU availability."""
    import platform as plat

    is_pi = False
    model = None
    architecture = plat.machine()

    # Check for Raspberry Pi
    try:
        model_path = Path("/sys/firmware/devicetree/base/model")
        if model_path.exists():
            model = model_path.read_text().strip('\x00').strip()
            is_pi = "raspberry pi" in model.lower()
    except Exception:
        pass

    # Fallback: check /proc/cpuinfo for Pi
    if not is_pi:
        try:
            cpuinfo = Path("/proc/cpuinfo").read_text()
            if "raspberry" in cpuinfo.lower() or "BCM" in cpuinfo:
                is_pi = True
        except Exception:
            pass

    # Detect GPU
    gpu = detect_gpu()

    return PlatformInfo(
        is_raspberry_pi=is_pi,
        model=model,
        architecture=architecture,
        gpu=gpu,
    )


def detect_gpu() -> GPUInfo:
    """Detect GPU vendor and capabilities."""
    # Try NVIDIA first (nvidia-smi)
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split(",")
            name = parts[0].strip() if parts else None
            vram = int(float(parts[1].strip())) if len(parts) > 1 else None
            return GPUInfo(vendor="nvidia", name=name, vram_mb=vram)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    except Exception as e:
        logger.debug(f"nvidia-smi error: {e}")

    # Try AMD (rocm-smi or check sysfs)
    try:
        result = subprocess.run(
            ["rocm-smi", "--showproductname"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            # Parse AMD GPU name from output
            for line in result.stdout.splitlines():
                if "GPU" in line and ":" in line:
                    name = line.split(":")[-1].strip()
                    return GPUInfo(vendor="amd", name=name)
            return GPUInfo(vendor="amd", name="AMD GPU")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    except Exception as e:
        logger.debug(f"rocm-smi error: {e}")

    # Check for AMD via sysfs
    try:
        drm_path = Path("/sys/class/drm")
        if drm_path.exists():
            for card in drm_path.iterdir():
                vendor_path = card / "device" / "vendor"
                if vendor_path.exists():
                    vendor_id = vendor_path.read_text().strip()
                    if vendor_id == "0x1002":  # AMD vendor ID
                        return GPUInfo(vendor="amd", name="AMD GPU")
    except Exception:
        pass

    # Check for Intel integrated
    try:
        result = subprocess.run(
            ["lspci"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "VGA" in line or "3D" in line:
                    if "NVIDIA" in line.upper():
                        return GPUInfo(vendor="nvidia", name=line.split(":")[-1].strip())
                    elif "AMD" in line.upper() or "ATI" in line.upper():
                        return GPUInfo(vendor="amd", name=line.split(":")[-1].strip())
                    elif "Intel" in line:
                        return GPUInfo(vendor="intel", name=line.split(":")[-1].strip())
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    except Exception:
        pass

    # macOS: Check for Apple Silicon
    import sys
    if sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if "Apple" in result.stdout:
                return GPUInfo(vendor="apple", name="Apple Silicon")
        except Exception:
            pass

    return GPUInfo(vendor="none")


def is_local_request(request: Request) -> bool:
    """Check if request is from localhost or local network."""
    client_ip = request.client.host if request.client else ""
    # Allow localhost
    if client_ip in ("127.0.0.1", "::1", "localhost"):
        return True
    # Allow private network ranges
    if client_ip.startswith(("10.", "172.16.", "172.17.", "172.18.", "172.19.",
                             "172.20.", "172.21.", "172.22.", "172.23.",
                             "172.24.", "172.25.", "172.26.", "172.27.",
                             "172.28.", "172.29.", "172.30.", "172.31.",
                             "192.168.")):
        return True
    return False


@router.get("/info", response_model=SystemInfo)
async def get_system_info():
    """Get system information including platform detection."""
    return SystemInfo(
        hostname=socket.gethostname(),
        ip_addresses=get_ip_addresses(),
        uptime_seconds=get_uptime(),
        platform=detect_platform(),
    )


@router.post("/reboot")
async def reboot_system(action: SystemAction, request: Request):
    """Reboot the system. Requires confirmation."""
    if not is_local_request(request):
        raise HTTPException(
            status_code=403,
            detail="System controls only available from local network",
        )
    if not action.confirm:
        raise HTTPException(
            status_code=400,
            detail="Set confirm=true to proceed with reboot",
        )
    try:
        # Use systemctl if available, fallback to reboot command
        subprocess.Popen(["sudo", "systemctl", "reboot"])
        return {"status": "rebooting"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/shutdown")
async def shutdown_system(action: SystemAction, request: Request):
    """Shutdown the system. Requires confirmation."""
    if not is_local_request(request):
        raise HTTPException(
            status_code=403,
            detail="System controls only available from local network",
        )
    if not action.confirm:
        raise HTTPException(
            status_code=400,
            detail="Set confirm=true to proceed with shutdown",
        )
    try:
        subprocess.Popen(["sudo", "systemctl", "poweroff"])
        return {"status": "shutting_down"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/timezones")
async def list_timezones():
    """List available timezones."""
    timezones = []
    zoneinfo_path = Path("/usr/share/zoneinfo")
    if zoneinfo_path.exists():
        for region in ["America", "Europe", "Asia", "Australia", "Pacific", "UTC"]:
            region_path = zoneinfo_path / region
            if region_path.is_dir():
                for tz in region_path.iterdir():
                    if tz.is_file():
                        timezones.append(f"{region}/{tz.name}")
            elif region == "UTC" and (zoneinfo_path / "UTC").exists():
                timezones.append("UTC")
    return {"timezones": sorted(timezones)}


@router.get("/timezone")
async def get_timezone():
    """Get current timezone."""
    # Validate timedatectl exists
    if not Path(TIMEDATECTL_PATH).exists():
        logger.error(f"timedatectl not found at {TIMEDATECTL_PATH}")
        return {"timezone": "UTC"}

    try:
        result = subprocess.run(
            [TIMEDATECTL_PATH, "show", "--property=Timezone", "--value"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            tz = result.stdout.strip()
            logger.debug(f"Returning timezone from timedatectl: {tz}")
            return {"timezone": tz}

        # Fallback to /etc/timezone
        tz_file = Path("/etc/timezone")
        if tz_file.exists():
            tz = tz_file.read_text().strip()
            logger.debug(f"Returning timezone from /etc/timezone: {tz}")
            return {"timezone": tz}
    except Exception as e:
        logger.error(f"Error getting timezone: {e}")

    logger.warning("Falling back to UTC timezone")
    return {"timezone": "UTC"}


@router.put("/timezone")
async def set_timezone(update: TimezoneUpdate, request: Request):
    """Set system timezone."""
    if not is_local_request(request):
        raise HTTPException(
            status_code=403,
            detail="System controls only available from local network",
        )

    # Validate timezone exists
    tz_path = Path(f"/usr/share/zoneinfo/{update.timezone}")
    if not tz_path.exists():
        raise HTTPException(status_code=400, detail=f"Unknown timezone: {update.timezone}")

    # Validate required binaries exist
    if not Path(SUDO_PATH).exists():
        raise HTTPException(status_code=500, detail="sudo not found")
    if not Path(TIMEDATECTL_PATH).exists():
        raise HTTPException(status_code=500, detail="timedatectl not found")

    try:
        subprocess.run(
            [SUDO_PATH, TIMEDATECTL_PATH, "set-timezone", update.timezone],
            check=True,
            timeout=10,
        )
        return {"timezone": update.timezone}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Failed to set timezone: {e}")


@router.get("/storage")
async def get_storage_stats():
    """Get database storage statistics."""
    stats = await get_reading_stats()
    total = stats.get("total_readings") or 0
    stats["estimated_size_bytes"] = int(total) * 100  # rough estimate
    return stats


class CleanupRequest(BaseModel):
    retention_days: int = 30
    confirm: bool = False


class AIAcceleratorDevice(BaseModel):
    path: str
    architecture: str
    firmware_version: str
    tops: int


class AIAcceleratorStatus(BaseModel):
    available: bool
    device: Optional[AIAcceleratorDevice] = None


@router.post("/cleanup")
async def trigger_cleanup(cleanup: CleanupRequest, request: Request):
    """Manually trigger data cleanup. Requires confirmation."""
    if not is_local_request(request):
        raise HTTPException(
            status_code=403,
            detail="System controls only available from local network",
        )
    if not cleanup.confirm:
        # Return preview of what would be deleted
        from datetime import timedelta
        from sqlalchemy import func, select
        from ..database import async_session_factory
        from ..models import Reading

        cutoff = datetime.now(timezone.utc) - timedelta(days=cleanup.retention_days)
        async with async_session_factory() as session:
            result = await session.execute(
                select(func.count()).select_from(Reading).where(Reading.timestamp < cutoff)
            )
            count = result.scalar() or 0

        return {
            "status": "preview",
            "retention_days": cleanup.retention_days,
            "readings_to_delete": count,
            "message": "Set confirm=true to proceed with deletion",
        }

    deleted = await cleanup_old_readings(cleanup.retention_days)
    return {
        "status": "completed",
        "retention_days": cleanup.retention_days,
        "deleted_readings": deleted,
    }


def detect_ai_accelerator() -> AIAcceleratorStatus:
    """Detect Hailo AI accelerator (AI HAT+ 2)."""
    # Quick check: does the device node exist?
    if not Path(HAILO_DEVICE_PATH).exists():
        return AIAcceleratorStatus(available=False)

    # Try to get detailed info via hailortcli
    if not Path(HAILORTCLI_PATH).exists():
        # Device exists but CLI not installed - assume available
        return AIAcceleratorStatus(
            available=True,
            device=AIAcceleratorDevice(
                path=HAILO_DEVICE_PATH,
                architecture="unknown",
                firmware_version="unknown",
                tops=0,
            ),
        )

    try:
        result = subprocess.run(
            [HAILORTCLI_PATH, "fw-control", "identify"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            # CLI failed but device exists
            return AIAcceleratorStatus(
                available=True,
                device=AIAcceleratorDevice(
                    path=HAILO_DEVICE_PATH,
                    architecture="unknown",
                    firmware_version="unknown",
                    tops=0,
                ),
            )

        # Parse output for device info
        output = result.stdout
        architecture = "unknown"
        firmware_version = "unknown"
        tops = 0

        for line in output.splitlines():
            line_lower = line.lower()
            if "device architecture:" in line_lower:
                architecture = line.split(":")[-1].strip()
            elif "firmware version:" in line_lower:
                firmware_version = line.split(":")[-1].strip().split()[0]

        # Map architecture to TOPS
        if "hailo10h" in architecture.lower():
            tops = 40
        elif "hailo8" in architecture.lower():
            tops = 26 if "8l" not in architecture.lower() else 13

        return AIAcceleratorStatus(
            available=True,
            device=AIAcceleratorDevice(
                path=HAILO_DEVICE_PATH,
                architecture=architecture,
                firmware_version=firmware_version,
                tops=tops,
            ),
        )

    except subprocess.TimeoutExpired:
        logger.warning("hailortcli timed out")
        return AIAcceleratorStatus(
            available=True,
            device=AIAcceleratorDevice(
                path=HAILO_DEVICE_PATH,
                architecture="unknown",
                firmware_version="unknown",
                tops=0,
            ),
        )
    except Exception as e:
        logger.error(f"Error detecting AI accelerator: {e}")
        return AIAcceleratorStatus(available=False)


@router.get("/ai-accelerator", response_model=AIAcceleratorStatus)
async def get_ai_accelerator_status():
    """Check if AI accelerator (Hailo) is available."""
    return detect_ai_accelerator()
